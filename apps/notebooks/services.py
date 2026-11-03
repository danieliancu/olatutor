"""Journal persistence and synchronisation rules (spec section 10)."""

import logging
from dataclasses import dataclass
from typing import Any

from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from .ink.encoding import CHAIN_GENESIS, InkError, op_hash
from .ink.replay import DocumentState, PageState, replay_page
from .ink.schema import validate_op
from .models import (
    InkOperation,
    InkSnapshot,
    Notebook,
    NotebookPage,
    PageRevision,
    QuarantinedBatch,
)

logger = logging.getLogger(__name__)

SNAPSHOT_EVERY = 50
MAX_OPS_PER_BATCH = 200


class SyncRejected(Exception):
    """The batch was not applied. `quarantine` keeps its content for later recovery."""

    def __init__(
        self,
        status: int,
        code: str,
        detail: str = "",
        *,
        quarantine: bool = False,
        head_seq: int | None = None,
        expected_client_seq: int | None = None,
    ) -> None:
        super().__init__(code)
        self.status = status
        self.code = code
        self.detail = detail
        self.quarantine = quarantine
        self.head_seq = head_seq
        self.expected_client_seq = expected_client_seq


@dataclass
class AppendResult:
    head_seq: int
    chain_hash: str
    acks: list[dict[str, Any]]


def _replay_ops(page: NotebookPage, after: int, up_to: int | None = None) -> list[dict[str, Any]]:
    rows = InkOperation.objects.filter(
        notebook_id=page.notebook_id, journal=page.page_id, seq__gt=after
    )
    if up_to is not None:
        rows = rows.filter(seq__lte=up_to)
    return [row.op for row in rows.order_by("seq")]


def _pin_index(page: NotebookPage) -> int:
    return page.revisions.aggregate(pin=Max("seq"))["pin"] or 0


def load_page_state(page: NotebookPage) -> PageState:
    """Rebuild page state. A snapshot is only trusted if it reaches the journal's chain hash."""
    pin = _pin_index(page)
    snapshot = page.snapshots.order_by("-seq").first()
    if snapshot is not None:
        state = PageState.from_snapshot(snapshot.state, pin_index=pin)
        for op in _replay_ops(page, snapshot.seq):
            state.apply(op)
        if state.chain_hash == page.chain_hash:
            return state
        logger.error("snapshot %s of page %s failed verification", snapshot.pk, page.pk)
    return replay_page(page.page_id, page.width, page.height, _replay_ops(page, 0), pin)


def replay_at(page: NotebookPage, seq: int | None = None) -> PageState:
    """Replay from zero, ignoring snapshots: the authoritative reconstruction."""
    return replay_page(page.page_id, page.width, page.height, _replay_ops(page, 0, seq))


def _quarantine(notebook_id: str, journal: str, body: Any, error: SyncRejected) -> None:
    QuarantinedBatch.objects.create(
        notebook_id_claimed=notebook_id,
        journal=journal,
        code=error.code,
        detail=error.detail[:2000],
        body=_json_safe(body),
    )


def _json_safe(body: Any) -> Any:
    """A batch may be rejected because of the very values that Postgres JSON cannot hold."""
    try:
        return _strip_surrogates(body)
    except (TypeError, ValueError):
        return {"unstorable": True}


def _strip_surrogates(value: Any) -> Any:
    if isinstance(value, str):
        return value.encode("utf-8", "replace").decode("utf-8").replace("\x00", "�")
    if isinstance(value, list):
        return [_strip_surrogates(item) for item in value]
    if isinstance(value, dict):
        return {_strip_surrogates(k): _strip_surrogates(v) for k, v in value.items()}
    return value


def _parse_batch(body: Any) -> tuple[str, int, int, list[dict[str, Any]]]:
    if not isinstance(body, dict) or set(body) != {"writer_id", "epoch", "base_seq", "ops"}:
        raise SyncRejected(400, "INVALID_BATCH")
    writer_id, epoch, base_seq, ops = (body[k] for k in ("writer_id", "epoch", "base_seq", "ops"))
    if type(base_seq) is not int or base_seq < 0 or type(epoch) is not int:
        raise SyncRejected(400, "INVALID_BATCH")
    if not isinstance(ops, list) or not ops or len(ops) > MAX_OPS_PER_BATCH:
        raise SyncRejected(400, "INVALID_BATCH", "a batch holds 1 to 200 operations")
    return writer_id, epoch, base_seq, ops


def append_batch(notebook_id: str, journal: str, body: Any) -> AppendResult:
    """Apply a whole batch or nothing. Retries return the original sequence numbers."""
    try:
        with transaction.atomic():
            return _append_locked(notebook_id, journal, body)
    except SyncRejected as error:
        if error.quarantine:
            _quarantine(notebook_id, journal, body, error)
        raise


def _append_locked(notebook_id: str, journal: str, body: Any) -> AppendResult:
    writer_id, epoch, base_seq, ops = _parse_batch(body)
    is_document = journal == InkOperation.DOCUMENT_JOURNAL

    notebook, _ = Notebook.objects.get_or_create(
        id=notebook_id, defaults={"chain_hash": CHAIN_GENESIS}
    )
    notebook = Notebook.objects.select_for_update().get(pk=notebook.pk)
    page: NotebookPage | None = None
    if not is_document:
        page = (
            NotebookPage.objects.select_for_update()
            .filter(notebook=notebook, page_id=journal)
            .first()
        )
        if page is None:
            raise SyncRejected(404, "UNKNOWN_PAGE")
    head = notebook.head_seq if page is None else page.head_seq

    acks: list[dict[str, Any]] = []
    new_ops: list[tuple[dict[str, Any], str]] = []
    for op in ops:
        try:
            validate_op(op)
        except InkError as error:
            raise SyncRejected(422, error.code, error.detail, quarantine=True) from error
        if op["writer_id"] != writer_id or op["epoch"] != epoch:
            raise SyncRejected(400, "INVALID_BATCH", "operation does not match the batch writer")
        payload_hash = op_hash(op)
        existing = InkOperation.objects.filter(notebook=notebook, op_id=op["op_id"]).first()
        if existing is None:
            new_ops.append((op, payload_hash))
            continue
        if existing.payload_hash != payload_hash or existing.journal != journal:
            raise SyncRejected(
                409, "IDEMPOTENCY_MISMATCH", op["op_id"], quarantine=True, head_seq=head
            )
        if new_ops:
            raise SyncRejected(400, "INVALID_BATCH", "retried operations must come first")
        acks.append({"op_id": op["op_id"], "seq": existing.seq})

    if not new_ops:
        chain = notebook.chain_hash if page is None else page.chain_hash
        return AppendResult(head, chain, acks)

    if page is not None and page.deleted_at is not None:
        raise SyncRejected(409, "PAGE_DELETED", quarantine=True, head_seq=head)

    # Page lifecycle operations use unique IDs and commute, so only ink is single-writer.
    if not is_document and base_seq + len(acks) != head:
        raise SyncRejected(
            409,
            "BASE_CONFLICT",
            "another writer advanced this journal",
            quarantine=True,
            head_seq=head,
        )

    high_water = (
        InkOperation.objects.filter(
            notebook=notebook, journal=journal, writer_id=writer_id, epoch=epoch
        ).aggregate(high=Max("client_seq"))["high"]
        or 0
    )
    for op, _hash in new_ops:
        if op["client_seq"] != high_water + 1:
            raise SyncRejected(
                409, "SEQUENCE_GAP", head_seq=head, expected_client_seq=high_water + 1
            )
        high_water += 1

    document_state: DocumentState | None = None
    page_state: PageState | None = None
    if page is None:
        document_state = DocumentState(chain_hash=notebook.chain_hash)
        for known in notebook.pages.all():
            document_state.pages[known.page_id] = {}
            if known.deleted_at is not None:
                document_state.deleted.add(known.page_id)
    else:
        page_state = load_page_state(page)

    rows = []
    seq = head
    for op, payload_hash in new_ops:
        try:
            if document_state is not None:
                document_state.apply(op)
            else:
                assert page_state is not None
                page_state.apply(op)
        except InkError as error:
            raise SyncRejected(422, error.code, error.detail, quarantine=True) from error
        seq += 1
        rows.append(
            InkOperation(
                notebook=notebook,
                journal=journal,
                seq=seq,
                op_id=op["op_id"],
                writer_id=writer_id,
                epoch=epoch,
                client_seq=op["client_seq"],
                payload_hash=payload_hash,
                op=op,
            )
        )
        acks.append({"op_id": op["op_id"], "seq": seq})
    InkOperation.objects.bulk_create(rows)

    if document_state is not None:
        for op, _hash in new_ops:
            if op["type"] == "CREATE_PAGE":
                NotebookPage.objects.create(
                    notebook=notebook,
                    page_id=op["page_id"],
                    width=op["payload"]["width"],
                    height=op["payload"]["height"],
                    orientation=op["payload"]["orientation"],
                    chain_hash=CHAIN_GENESIS,
                )
            else:
                NotebookPage.objects.filter(notebook=notebook, page_id=op["page_id"]).update(
                    deleted_at=timezone.now()
                )
        notebook.head_seq = seq
        notebook.chain_hash = document_state.chain_hash
        notebook.save(update_fields=["head_seq", "chain_hash"])
        return AppendResult(seq, notebook.chain_hash, acks)

    assert page is not None and page_state is not None
    page.head_seq = seq
    page.chain_hash = page_state.chain_hash
    page.save(update_fields=["head_seq", "chain_hash"])
    if seq // SNAPSHOT_EVERY > head // SNAPSHOT_EVERY:
        InkSnapshot.objects.create(
            page=page,
            seq=seq,
            state=page_state.to_snapshot(),
            chain_hash=page_state.chain_hash,
            full_hash=page_state.full_hash(),
        )
    return AppendResult(seq, page.chain_hash, acks)


def notebook_state(notebook_id: str) -> dict[str, Any]:
    """Everything a client needs to open a notebook, in one request."""
    notebook = Notebook.objects.filter(pk=notebook_id).first()
    if notebook is None:
        return {"document": {"head_seq": 0, "ops": []}, "pages": []}
    journals: dict[str, list[dict[str, Any]]] = {}
    for row in InkOperation.objects.filter(notebook=notebook).order_by("journal", "seq"):
        journals.setdefault(row.journal, []).append(row.op)
    pins = dict(
        PageRevision.objects.filter(page__notebook=notebook)
        .values_list("page__page_id")
        .annotate(pin=Max("seq"))
    )
    return {
        "document": {
            "head_seq": notebook.head_seq,
            "ops": journals.get(InkOperation.DOCUMENT_JOURNAL, []),
        },
        "pages": [
            {
                "page_id": page.page_id,
                "head_seq": page.head_seq,
                "ops": journals.get(page.page_id, []),
                "pin_seq": pins.get(page.page_id, 0),
                "deleted": page.deleted_at is not None,
            }
            for page in notebook.pages.order_by("id")
        ],
    }


def create_revision(
    page: NotebookPage, seq: int, chain_hash: str, visible_hash: str
) -> PageRevision:
    """Pin a page position, but only if the client's hashes match the server's own replay."""
    with transaction.atomic():
        locked = NotebookPage.objects.select_for_update().get(pk=page.pk)
        existing = locked.revisions.filter(seq=seq).first()
        if existing is not None:
            if (existing.chain_hash, existing.visible_hash) != (chain_hash, visible_hash):
                raise SyncRejected(409, "HASH_MISMATCH")
            return existing
        if seq > locked.head_seq or seq < 0:
            raise SyncRejected(409, "REVISION_NOT_SYNCED", head_seq=locked.head_seq)
        if seq < _pin_index(locked):
            raise SyncRejected(409, "REVISION_BEHIND_PIN")
        state = replay_at(locked, seq)
        if (state.chain_hash, state.visible_hash()) != (chain_hash, visible_hash):
            raise SyncRejected(409, "HASH_MISMATCH")
        last = locked.revisions.aggregate(last=Max("revision"))["last"] or 0
        return PageRevision.objects.create(
            page=locked,
            revision=last + 1,
            seq=seq,
            visible_hash=visible_hash,
            full_hash=state.full_hash(),
            chain_hash=chain_hash,
        )
