"""HTTP layer of the notebook prototype. No authentication yet, so it is off outside development."""

import json
import secrets
from collections.abc import Callable
from functools import wraps
from typing import Any

from django.conf import settings
from django.core.exceptions import RequestDataTooBig
from django.http import Http404, HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST

from .ink.render import render_png
from .models import InkOperation, NotebookPage, PageRevision
from .services import SyncRejected, append_batch, create_revision, notebook_state, replay_at


def prototype_only(view: Callable[..., HttpResponse]) -> Callable[..., HttpResponse]:
    @wraps(view)
    def wrapper(request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        if not settings.INK_PROTOTYPE_ENABLED:
            raise Http404
        return view(request, *args, **kwargs)

    return wrapper


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = dict(pairs)
    if len(result) != len(pairs):
        raise ValueError("duplicate key")
    return result


def _reject_constant(name: str) -> None:
    raise ValueError(f"{name} is not valid JSON")


def _read_json(request: HttpRequest) -> Any:
    try:
        return json.loads(
            request.body,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_constant,
        )
    except RequestDataTooBig as error:
        raise SyncRejected(413, "BODY_TOO_LARGE") from error
    except (ValueError, RecursionError, UnicodeDecodeError) as error:
        raise SyncRejected(400, "INVALID_JSON") from error


def _rejection(error: SyncRejected) -> JsonResponse:
    return JsonResponse(
        {
            "code": error.code,
            "detail": error.detail,
            "head_seq": error.head_seq,
            "expected_client_seq": error.expected_client_seq,
        },
        status=error.status,
    )


def _page(notebook_id: str, page_id: str) -> NotebookPage:
    return get_object_or_404(NotebookPage, notebook_id=notebook_id, page_id=page_id)


def _requested_seq(request: HttpRequest) -> int | None:
    raw = request.GET.get("seq")
    if raw is None:
        return None
    if not raw.isdecimal() or len(raw) > 12:
        raise Http404
    return int(raw)


@prototype_only
@require_GET
def new_notebook(request: HttpRequest) -> HttpResponse:
    return redirect("notebook", notebook_id=secrets.token_urlsafe(16))


@prototype_only
@require_GET
@ensure_csrf_cookie
def notebook(request: HttpRequest, notebook_id: str) -> HttpResponse:
    return render(request, "notebook.html", {"notebook_id": notebook_id})


@prototype_only
@require_GET
def service_worker(request: HttpRequest) -> HttpResponse:
    """Served from the root, because a service worker only controls pages below its own URL."""
    script = settings.BASE_DIR / "static" / "js" / "ink" / "sw.js"
    response = HttpResponse(script.read_bytes(), content_type="text/javascript")
    response["Cache-Control"] = "no-cache"
    return response


@prototype_only
@require_GET
def notebook_snapshot(request: HttpRequest, notebook_id: str) -> JsonResponse:
    return JsonResponse(notebook_state(notebook_id))


@prototype_only
@require_POST
def document_ops(request: HttpRequest, notebook_id: str) -> JsonResponse:
    return _append(request, notebook_id, InkOperation.DOCUMENT_JOURNAL)


@prototype_only
@require_POST
def page_ops(request: HttpRequest, notebook_id: str, page_id: str) -> JsonResponse:
    return _append(request, notebook_id, page_id)


def _append(request: HttpRequest, notebook_id: str, journal: str) -> JsonResponse:
    try:
        result = append_batch(notebook_id, journal, _read_json(request))
    except SyncRejected as error:
        return _rejection(error)
    return JsonResponse(
        {"head_seq": result.head_seq, "chain_hash": result.chain_hash, "acks": result.acks}
    )


@prototype_only
@require_GET
def reconstruction(request: HttpRequest, notebook_id: str, page_id: str) -> JsonResponse:
    page = _page(notebook_id, page_id)
    seq = _requested_seq(request)
    state = replay_at(page, seq)
    return JsonResponse(
        {
            "seq": page.head_seq if seq is None else min(seq, page.head_seq),
            "width": state.width,
            "height": state.height,
            "strokes": state.visible(),
            "visible_hash": state.visible_hash(),
            "full_hash": state.full_hash(),
            "chain_hash": state.chain_hash,
        }
    )


@prototype_only
@require_GET
def render_page(request: HttpRequest, notebook_id: str, page_id: str) -> HttpResponse:
    page = _page(notebook_id, page_id)
    state = replay_at(page, _requested_seq(request))
    png = render_png(state.width, state.height, state.visible())
    return HttpResponse(png, content_type="image/png")


@prototype_only
@require_POST
def revisions(request: HttpRequest, notebook_id: str, page_id: str) -> JsonResponse:
    page = _page(notebook_id, page_id)
    try:
        body = _read_json(request)
        if not isinstance(body, dict) or type(body.get("seq")) is not int:
            raise SyncRejected(400, "INVALID_BATCH")
        revision: PageRevision = create_revision(
            page, body["seq"], str(body.get("chain_hash")), str(body.get("visible_hash"))
        )
    except SyncRejected as error:
        return _rejection(error)
    return JsonResponse(
        {
            "revision": revision.revision,
            "seq": revision.seq,
            "visible_hash": revision.visible_hash,
            "full_hash": revision.full_hash,
            "chain_hash": revision.chain_hash,
        },
        status=201,
    )
