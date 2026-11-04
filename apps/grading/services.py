"""Records a verification: idempotent, pinned to a revision, and decided only by the server.

The client sends what was confirmed. It never sends an expected answer, a score or a rule. Grading
runs outside any lock, because it is pure and bounded. Unique constraints settle races.
"""

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.notebooks.models import NotebookPage, PageRevision
from apps.notebooks.services import SyncRejected

from .catalog import load_catalog
from .engine.exercise import Exercise
from .engine.grade import Assessment
from .engine.version import ENGINE_VERSION, RULES_VERSION
from .models import ManualTranscription, Verification
from .results import grade_graph
from .semantics import PROVENANCE, SEMANTIC_VERSION, build_manual_graph


@dataclass(frozen=True)
class VerificationRequest:
    idempotency_key: str
    exercise_id: str
    exercise_version: int
    revision: int
    visible_hash: str
    steps: list[str]
    corrects: int | None

    def request_hash(self) -> str:
        payload = {
            "exercise_id": self.exercise_id,
            "exercise_version": self.exercise_version,
            "revision": self.revision,
            "visible_hash": self.visible_hash,
            "steps": self.steps,
            "corrects": self.corrects,
        }
        encoded = json.dumps(payload, sort_keys=True, ensure_ascii=True).encode("ascii")
        return hashlib.sha256(encoded).hexdigest()


def _replay(page: NotebookPage, request: VerificationRequest) -> Verification | None:
    existing = Verification.objects.filter(
        page=page, idempotency_key=request.idempotency_key
    ).first()
    if existing is None:
        return None
    if existing.request_hash != request.request_hash():
        raise SyncRejected(409, "IDEMPOTENCY_MISMATCH", "This key was used for different work.")
    return existing


def _pinned_revision(page: NotebookPage, request: VerificationRequest) -> PageRevision:
    if page.deleted_at is not None:
        raise SyncRejected(409, "PAGE_DELETED", "This page has been deleted.")
    revision = PageRevision.objects.filter(page=page, revision=request.revision).first()
    if revision is None:
        raise SyncRejected(404, "UNKNOWN_REVISION", "This page has no such revision.")
    if revision.visible_hash != request.visible_hash:
        raise SyncRejected(409, "REVISION_HASH_MISMATCH", "This is not the revision's content.")
    if revision.seq == 0:
        raise SyncRejected(409, "EMPTY_REVISION", "This revision has no writing on it.")
    return revision


def _authoritative_exercise(request: VerificationRequest) -> Exercise:
    exercise = load_catalog().get(request.exercise_id)
    if exercise is None:
        raise SyncRejected(404, "UNKNOWN_EXERCISE", "There is no such exercise.")
    if exercise.version != request.exercise_version:
        raise SyncRejected(409, "EXERCISE_VERSION_MISMATCH", "This exercise has changed.")
    return exercise


def _correction_target(
    page: NotebookPage, revision: PageRevision, exercise: Exercise, request: VerificationRequest
) -> Verification | None:
    if request.corrects is None:
        return None
    target = (
        Verification.objects.filter(page=page, pk=request.corrects)
        .select_related("transcription")
        .first()
    )
    if target is None:
        raise SyncRejected(404, "UNKNOWN_CORRECTION_TARGET", "There is no such earlier check.")
    if target.revision_id != revision.pk or target.exercise_id != exercise.exercise_id:
        raise SyncRejected(409, "CORRECTION_CONTEXT_MISMATCH", "This corrects a different check.")
    if target.transcription.steps == request.steps:
        raise SyncRejected(409, "CORRECTION_UNCHANGED", "The transcription has not changed.")
    return target


def _parsed_steps(assessment: Assessment) -> list[dict[str, Any]]:
    verdicts = {verdict.index: verdict for verdict in assessment.step_verdicts}
    return [
        {
            "index": step.index,
            "text": step.text,
            "expressions": [expression.to_dict() for expression in step.expressions],
            "verdict": verdicts[step.index].to_dict(),
        }
        for step in assessment.steps
    ]


def record_verification(
    page: NotebookPage, request: VerificationRequest
) -> tuple[Verification, bool]:
    """Returns the record, and whether it is new. A replay returns the original record unchanged."""
    existing = _replay(page, request)
    if existing is not None:
        return existing, False

    revision = _pinned_revision(page, request)
    exercise = _authoritative_exercise(request)
    target = _correction_target(page, revision, exercise, request)

    graph = build_manual_graph(
        notebook_id=page.notebook_id,
        page_id=page.page_id,
        revision=revision.revision,
        seq=revision.seq,
        visible_hash=revision.visible_hash,
        exercise_ref=exercise.ref,
        steps=request.steps,
        processed_at=timezone.now().isoformat().replace("+00:00", "Z"),
    )
    assessment, solution, steps = grade_graph(graph, exercise)

    try:
        with transaction.atomic():
            transcription = ManualTranscription.objects.create(
                revision=revision,
                exercise_id=exercise.exercise_id,
                exercise_version=exercise.version,
                steps=request.steps,
                provenance=PROVENANCE,
                semantic_version=SEMANTIC_VERSION,
                graph=graph,
            )
            created = Verification.objects.create(
                page=page,
                revision=revision,
                transcription=transcription,
                exercise_id=exercise.exercise_id,
                exercise_version=exercise.version,
                idempotency_key=request.idempotency_key,
                request_hash=request.request_hash(),
                semantic_version=SEMANTIC_VERSION,
                engine_version=ENGINE_VERSION,
                rules_version=RULES_VERSION,
                mathematical_status=assessment.mathematical_status,
                task_compliance=assessment.task_compliance,
                error_class=assessment.error_class,
                score=assessment.score,
                max_score=assessment.max_score,
                code=assessment.code,
                feedback_line=assessment.focus_line,
                requires_review=assessment.requires_review,
                limit_exceeded=assessment.limit,
                solution_result=solution,
                step_results=steps,
                parsed_steps=_parsed_steps(assessment),
                corrects=target,
            )
    except IntegrityError as error:
        # A concurrent request won. Either it was the same work, or this check is already corrected.
        existing = _replay(page, request)
        if existing is not None:
            return existing, False
        raise SyncRejected(409, "ALREADY_CORRECTED", "This check has been corrected.") from error
    return created, True
