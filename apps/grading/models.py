"""Append-only records: database triggers refuse updates and deletes. A correction is a new row.

Ink, exercise content, transcription and feedback stay separate. Ink is only referenced, through the
immutable revision. Exercises live in the versioned catalogue, and are referenced by id and version.
"""

from django.db import models
from django.db.models import Q

from apps.notebooks.models import NotebookPage, PageRevision


class ManualTranscription(models.Model):
    """Text a person typed and confirmed for one revision. Nothing shows that it matches the ink."""

    revision = models.ForeignKey(
        PageRevision, on_delete=models.PROTECT, related_name="manual_transcriptions"
    )
    exercise_id = models.CharField(max_length=64)
    exercise_version = models.PositiveIntegerField()
    steps = models.JSONField()
    provenance = models.CharField(max_length=32)
    semantic_version = models.PositiveIntegerField()
    graph = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)


class Verification(models.Model):
    page = models.ForeignKey(NotebookPage, on_delete=models.PROTECT, related_name="verifications")
    revision = models.ForeignKey(
        PageRevision, on_delete=models.PROTECT, related_name="verifications"
    )
    transcription = models.OneToOneField(
        ManualTranscription, on_delete=models.PROTECT, related_name="verification"
    )
    exercise_id = models.CharField(max_length=64)
    exercise_version = models.PositiveIntegerField()
    idempotency_key = models.CharField(max_length=64)
    request_hash = models.CharField(max_length=64)
    semantic_version = models.PositiveIntegerField()
    engine_version = models.CharField(max_length=64)
    rules_version = models.CharField(max_length=64)
    mathematical_status = models.CharField(max_length=16)
    task_compliance = models.CharField(max_length=16)
    error_class = models.CharField(max_length=32, null=True, blank=True)  # noqa: DJ001
    score = models.PositiveIntegerField(null=True)
    max_score = models.PositiveIntegerField()
    code = models.CharField(max_length=64)
    feedback_line = models.PositiveIntegerField(null=True)
    requires_review = models.BooleanField()
    limit_exceeded = models.CharField(max_length=64, null=True, blank=True)  # noqa: DJ001
    solution_result = models.JSONField()
    step_results = models.JSONField()
    parsed_steps = models.JSONField()
    corrects = models.ForeignKey(
        "self", on_delete=models.PROTECT, null=True, blank=True, related_name="corrections"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["page", "idempotency_key"], name="unique_verification_key"
            ),
            # One direct correction per record, so that the history stays a line and not a tree.
            models.UniqueConstraint(
                fields=["corrects"],
                condition=Q(corrects__isnull=False),
                name="unique_direct_correction",
            ),
            models.CheckConstraint(
                condition=~Q(mathematical_status__in=["UNSUPPORTED", "UNDETERMINED"])
                | (Q(score__isnull=True) & Q(requires_review=True)),
                name="undetermined_has_no_score_and_needs_review",
            ),
            models.CheckConstraint(
                condition=~Q(task_compliance="COMPLIANT") | Q(mathematical_status="CORRECT"),
                name="compliant_requires_correct",
            ),
        ]
