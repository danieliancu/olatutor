"""HTTP layer of the manual demonstration. Off unless both gates are on. No login exists."""

import re
from collections.abc import Callable
from functools import wraps
from typing import Any

from django.conf import settings
from django.http import Http404, HttpRequest, HttpResponse, JsonResponse
from django.views.decorators.http import require_GET, require_http_methods

from apps.notebooks.models import NotebookPage
from apps.notebooks.services import SyncRejected
from apps.notebooks.views import _read_json, _rejection, prototype_only

from .catalog import load_catalog
from .engine.feedback import render_explanation, render_feedback
from .models import Verification
from .services import VerificationRequest, record_verification

MAX_BODY_BYTES = 64 * 1024
MAX_DB_INTEGER = 2**31 - 1
HISTORY_LIMIT = 50
REQUEST_FIELDS = {
    "idempotency_key",
    "exercise_id",
    "exercise_version",
    "revision",
    "visible_hash",
    "steps",
    "corrects",
}
KEY_PATTERN = re.compile(r"[A-Za-z0-9_-]{16,64}")
EXERCISE_PATTERN = re.compile(r"[A-Za-z0-9_.-]{1,64}")
HASH_PATTERN = re.compile(r"[0-9a-f]{64}")


def math_demo_only(view: Callable[..., HttpResponse]) -> Callable[..., HttpResponse]:
    @wraps(view)
    def wrapper(request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        if not settings.MATH_DEMO_ENABLED:
            raise Http404
        return view(request, *args, **kwargs)

    return prototype_only(wrapper)


def _page_or_rejection(notebook_id: str, page_id: str) -> NotebookPage:
    page = NotebookPage.objects.filter(notebook_id=notebook_id, page_id=page_id).first()
    if page is None:
        raise SyncRejected(404, "UNKNOWN_PAGE", "There is no such page.")
    return page


def _positive_integer(value: Any) -> bool:
    return type(value) is int and 1 <= value <= MAX_DB_INTEGER


def _storable_text(text: str) -> bool:
    """PostgreSQL JSON cannot hold U+0000, and lone surrogates cannot be encoded at all."""
    if "\x00" in text:
        return False
    try:
        text.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True


def _parse_request(body: Any) -> VerificationRequest:
    if not isinstance(body, dict) or set(body) != REQUEST_FIELDS:
        raise SyncRejected(400, "INVALID_REQUEST", "The request has the wrong fields.")
    key = body["idempotency_key"]
    exercise_id = body["exercise_id"]
    visible_hash = body["visible_hash"]
    steps = body["steps"]
    corrects = body["corrects"]
    valid = (
        isinstance(key, str)
        and KEY_PATTERN.fullmatch(key) is not None
        and isinstance(exercise_id, str)
        and EXERCISE_PATTERN.fullmatch(exercise_id) is not None
        and isinstance(visible_hash, str)
        and HASH_PATTERN.fullmatch(visible_hash) is not None
        and _positive_integer(body["exercise_version"])
        and _positive_integer(body["revision"])
        and (corrects is None or _positive_integer(corrects))
    )
    if not valid:
        raise SyncRejected(400, "INVALID_REQUEST", "A field has the wrong type or format.")
    if not isinstance(steps, list) or not steps or not all(isinstance(s, str) for s in steps):
        raise SyncRejected(400, "INVALID_TRANSCRIPTION", "Steps must be a list of text lines.")
    if not all(_storable_text(step) for step in steps):
        raise SyncRejected(400, "INVALID_TRANSCRIPTION", "A step has characters we cannot store.")
    return VerificationRequest(
        idempotency_key=key,
        exercise_id=exercise_id,
        exercise_version=body["exercise_version"],
        revision=body["revision"],
        visible_hash=visible_hash,
        steps=steps,
        corrects=corrects,
    )


def _serialize(verification: Verification) -> dict[str, Any]:
    """What the client may see. It leaves out computed values, so a line cannot reveal an answer."""
    page = verification.page
    revision = verification.revision
    corrected_by = verification.corrections.values_list("pk", flat=True).first()
    return {
        "id": verification.pk,
        "provenance": verification.transcription.provenance,
        "revision": revision.revision,
        "seq": revision.seq,
        "visible_hash": revision.visible_hash,
        "is_current_page_state": page.deleted_at is None and page.head_seq == revision.seq,
        "exercise_id": verification.exercise_id,
        "exercise_version": verification.exercise_version,
        "mathematical_status": verification.mathematical_status,
        "task_compliance": verification.task_compliance,
        "error_class": verification.error_class,
        "score": verification.score,
        "max_score": verification.max_score,
        "requires_review": verification.requires_review,
        "feedback": render_feedback(verification.code, verification.feedback_line),
        "feedback_line": verification.feedback_line,
        "steps": [
            {
                "index": step["index"],
                "text": step["text"],
                "normalized": [item["normalized"] for item in step["expressions"]],
                "mathematical_status": step["verdict"]["mathematical_status"],
                "error_class": step["verdict"]["error_class"],
                "follows_earlier_error": step["verdict"]["follows_earlier_error"],
                "feedback": render_feedback(step["verdict"]["code"], step["index"] + 1),
            }
            for step in verification.parsed_steps
        ],
        "corrects": verification.corrects_id,
        "corrected_by": corrected_by,
        "versions": {
            "semantic": verification.semantic_version,
            "engine": verification.engine_version,
            "rules": verification.rules_version,
        },
        "created_at": verification.created_at.isoformat(),
    }


@math_demo_only
@require_GET
def exercises(request: HttpRequest) -> JsonResponse:
    """The task as a learner may see it. Expected values and marks rules stay on the server."""
    items = [
        {
            "exercise_id": exercise.exercise_id,
            "exercise_version": exercise.version,
            "title": exercise.title,
            "statement": exercise.statement,
            "steps_required": exercise.steps_required,
            "max_score": exercise.max_score,
        }
        for exercise in load_catalog().values()
    ]
    return JsonResponse({"exercises": items})


@math_demo_only
@require_http_methods(["GET", "POST"])
def verifications(request: HttpRequest, notebook_id: str, page_id: str) -> JsonResponse:
    try:
        page = _page_or_rejection(notebook_id, page_id)
        if request.method == "GET":
            rows = (
                Verification.objects.filter(page=page)
                .select_related("page", "revision", "transcription")
                .order_by("-pk")[:HISTORY_LIMIT]
            )
            return JsonResponse({"verifications": [_serialize(row) for row in rows]})
        length = request.META.get("CONTENT_LENGTH") or "0"
        if not length.isdecimal() or int(length) > MAX_BODY_BYTES:
            raise SyncRejected(413, "BODY_TOO_LARGE", "This request is too large.")
        verification, created = record_verification(page, _parse_request(_read_json(request)))
    except SyncRejected as error:
        return _rejection(error)
    return JsonResponse(_serialize(verification), status=201 if created else 200)


@math_demo_only
@require_GET
def explanation(
    request: HttpRequest, notebook_id: str, page_id: str, verification_id: int
) -> JsonResponse:
    """Further explanation, only when asked. It never contains the worked solution."""
    try:
        page = _page_or_rejection(notebook_id, page_id)
        verification = Verification.objects.filter(page=page, pk=verification_id).first()
        if verification is None:
            raise SyncRejected(404, "UNKNOWN_VERIFICATION", "There is no such check.")
    except SyncRejected as error:
        return _rejection(error)
    line = verification.feedback_line
    return JsonResponse(
        {"code": verification.code, "explanation": render_explanation(verification.code, line)}
    )
