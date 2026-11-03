from django.db import models


class Notebook(models.Model):
    """Client-generated IDs, so a page can start offline. Tenancy arrives in Milestone 5."""

    id = models.CharField(primary_key=True, max_length=64)
    head_seq = models.PositiveIntegerField(default=0)
    chain_hash = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)


class NotebookPage(models.Model):
    notebook = models.ForeignKey(Notebook, on_delete=models.CASCADE, related_name="pages")
    page_id = models.CharField(max_length=64)
    width = models.PositiveIntegerField()
    height = models.PositiveIntegerField()
    orientation = models.CharField(max_length=16)
    head_seq = models.PositiveIntegerField(default=0)
    chain_hash = models.CharField(max_length=64)
    # Deleting hides a page. Its journal and revisions stay, so evidence is never lost by accident.
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["notebook", "page_id"], name="unique_page_in_notebook"),
        ]


class InkOperation(models.Model):
    """Append-only journal. A database trigger blocks UPDATE; DELETE stays possible for erasure."""

    DOCUMENT_JOURNAL = "~document"

    notebook = models.ForeignKey(Notebook, on_delete=models.CASCADE, related_name="operations")
    journal = models.CharField(max_length=64)
    seq = models.PositiveIntegerField()
    op_id = models.CharField(max_length=64)
    writer_id = models.CharField(max_length=64)
    epoch = models.PositiveIntegerField()
    client_seq = models.PositiveIntegerField()
    payload_hash = models.CharField(max_length=64)
    op = models.JSONField()
    received_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["seq"]
        constraints = [
            models.UniqueConstraint(
                fields=["notebook", "journal", "seq"], name="unique_journal_seq"
            ),
            models.UniqueConstraint(fields=["notebook", "op_id"], name="unique_op_in_notebook"),
            models.UniqueConstraint(
                fields=["notebook", "journal", "writer_id", "epoch", "client_seq"],
                name="unique_writer_position",
            ),
        ]


class InkSnapshot(models.Model):
    """A verified cache of replay. The journal stays the source of truth."""

    page = models.ForeignKey(NotebookPage, on_delete=models.CASCADE, related_name="snapshots")
    seq = models.PositiveIntegerField()
    state = models.JSONField()
    chain_hash = models.CharField(max_length=64)
    full_hash = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["page", "seq"], name="unique_snapshot_seq"),
        ]


class PageRevision(models.Model):
    """An immutable pin of a page at one journal position. Grading evidence will reference these."""

    page = models.ForeignKey(NotebookPage, on_delete=models.CASCADE, related_name="revisions")
    revision = models.PositiveIntegerField()
    seq = models.PositiveIntegerField()
    visible_hash = models.CharField(max_length=64)
    full_hash = models.CharField(max_length=64)
    chain_hash = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["revision"]
        constraints = [
            models.UniqueConstraint(fields=["page", "revision"], name="unique_page_revision"),
            models.UniqueConstraint(fields=["page", "seq"], name="unique_page_revision_seq"),
        ]


class QuarantinedBatch(models.Model):
    """A rejected batch kept so that no student work is lost; never counted as evidence."""

    notebook_id_claimed = models.CharField(max_length=64)
    journal = models.CharField(max_length=64)
    code = models.CharField(max_length=64)
    detail = models.TextField(blank=True)
    body = models.JSONField()
    received_at = models.DateTimeField(auto_now_add=True)
