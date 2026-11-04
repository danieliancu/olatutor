// Wires the notebook together. All ink rules live in core.js; this file only coordinates.

import { StrokeCapture } from "./capture.js";
import { computeEraseItems, DocumentState, InkError, PageState } from "./core.js";
import { drawLatestSegment, drawPage, fitCanvas } from "./render.js";
import { LocalStore } from "./store.js";
import { SyncEngine } from "./sync.js";

const SIZES = {
  portrait: { width: 2100, height: 2970 },
  landscape: { width: 2970, height: 2100 },
};
const PEN = { width: 8, color: "#1b2430" };
const ERASER_RADIUS = 40;
const ZOOM_LEVELS = [1, 1.5, 2];

function newId() {
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  return btoa(String.fromCharCode(...bytes))
    .replaceAll("+", "-")
    .replaceAll("/", "_")
    .replaceAll("=", "");
}

const el = (id) => document.getElementById(id);

function ackedFirst(records) {
  const byPosition = (a, b) => a.position - b.position;
  return [
    ...records.filter((r) => r.acked).sort(byPosition),
    ...records.filter((r) => !r.acked).sort(byPosition),
  ];
}

class NotebookApp {
  constructor(root) {
    this.notebookId = root.dataset.notebookId;
    this.csrfToken = root.dataset.csrfToken;
    this.viewport = el("page-viewport");
    this.canvas = el("page");
    this.ctx = this.canvas.getContext("2d");
    this.tool = "pen";
    this.zoomIndex = 0;
    this.store = null;
    this.storageOk = true;
    this.position = 0;
    this.documentSeq = 0;
    this.document = new DocumentState();
    this.pages = new Map();
    this.activePage = null;
    this.eraserPath = [];
  }

  get state() {
    return this.activePage.state;
  }

  apiUrl(path) {
    return `/api/ink/v1/notebooks/${this.notebookId}/${path}`;
  }

  async start() {
    await this.#openStore();
    await this.#loadIdentity();

    const stored = this.store ? await this.store.load(this.notebookId) : [];
    this.position = stored.reduce((max, r) => Math.max(max, r.position + 1), 0);
    const local = stored.filter((r) => !r.sidelined);
    const remote = await this.#fetchRemote();

    this.sync = new SyncEngine({
      csrfToken: this.csrfToken,
      onStatus: (state, text) => this.#showStatus(state, text),
      onAcked: (opIds) => this.#markAcked(opIds),
      onConflict: (journal, code) => this.#onConflict(journal, code),
    });

    const documentRecords = this.#openDocument(local, remote);
    const pageRecords = [];
    for (const [pageId, payload] of this.document.pages) {
      pageRecords.push(...(await this.#openPage(pageId, payload, local, remote)));
    }
    await this.#persistServerOps([...documentRecords, ...pageRecords]);

    const pages = this.#navigablePages();
    const fitsScreen = window.innerWidth > window.innerHeight ? "landscape" : "portrait";
    el("page-orientation").value = fitsScreen;
    if (pages.length === 0) {
      await this.createPage(fitsScreen);
    } else {
      const saved = this.store ? await this.store.getMeta(`active:${this.notebookId}`) : null;
      this.activePage = this.pages.get(pages.includes(saved) ? saved : pages[0]);
    }

    this.capture = new StrokeCapture(this.canvas, {
      pageWidth: this.state.width,
      pageHeight: this.state.height,
      onStart: () => {
        this.eraserPath = [];
      },
      onPoint: (points) => this.#onPoint(points),
      onEnd: (stroke) => this.#onEnd(stroke),
      onCancel: () => this.redraw(),
      onPan: (dx, dy) => this.viewport.scrollBy(dx, dy),
    });
    this.#wireControls();
    this.showPage(this.activePage.id);
    window.addEventListener("resize", () => this.resize());
    this.sync.schedule();
    this.#registerServiceWorker();
    this.canvas.dataset.ready = "true";
  }

  async #openStore() {
    try {
      this.store = await LocalStore.open();
    } catch (error) {
      console.error("local storage unavailable", error);
      this.storageOk = false;
    }
  }

  async #loadIdentity() {
    let writerId = null;
    let epoch = 0;
    if (this.store) {
      writerId = await this.store.getMeta("writer_id");
      epoch = (await this.store.getMeta(`epoch:${this.notebookId}`)) ?? 0;
    }
    this.writerId = writerId ?? newId();
    this.epoch = epoch + 1;
    if (this.store) {
      await this.store.setMeta("writer_id", this.writerId);
      await this.store.setMeta(`epoch:${this.notebookId}`, this.epoch);
    }
  }

  async #fetchRemote() {
    try {
      const response = await fetch(this.apiUrl(""));
      return response.ok ? await response.json() : null;
    } catch (error) {
      console.warn("server not reachable at start", error);
      return null;
    }
  }

  #toRecord(op, journal, acked) {
    return {
      op_id: op.op_id,
      notebook_id: this.notebookId,
      position: this.position++,
      journal,
      op,
      acked,
    };
  }

  // Page lifecycle operations commute, so local and server work can simply be combined.
  #openDocument(local, remote) {
    const mine = ackedFirst(local.filter((r) => r.journal === "document"));
    let pending = mine.filter((r) => !r.acked).map((r) => r.op);
    let ops = mine.map((r) => r.op);
    if (remote) {
      const accepted = new Set(remote.document.ops.map((op) => op.op_id));
      pending = pending.filter((op) => !accepted.has(op.op_id));
      ops = [...remote.document.ops, ...pending];
    }
    for (const op of ops) {
      try {
        this.document.apply(op);
      } catch (error) {
        if (!(error instanceof InkError)) throw error;
        console.error("skipping a page operation that no longer applies", op.op_id, error.code);
        pending = pending.filter((other) => other.op_id !== op.op_id);
      }
    }
    this.documentJournal = this.sync.addJournal({
      url: this.apiUrl("document/ops/"),
      serverHead: remote?.document.head_seq ?? ops.length - pending.length,
      pending,
    });
    const pendingIds = new Set(pending.map((op) => op.op_id));
    return ops
      .filter((op) => !pendingIds.has(op.op_id))
      .map((op) => this.#toRecord(op, "document", true));
  }

  // The server journal wins for anything it has acknowledged. Local-only work stays pending, and a
  // journal that moved on without this browser is a conflict for the user, never a silent merge.
  async #openPage(pageId, payload, local, remote) {
    const remotePage = remote?.pages.find((p) => p.page_id === pageId);
    const mine = ackedFirst(local.filter((r) => r.journal === "page" && r.op.page_id === pageId));
    const known = new Set(mine.map((r) => r.op_id));
    let pending = mine.filter((r) => !r.acked).map((r) => r.op);
    let serverOps = mine.filter((r) => r.acked).map((r) => r.op);
    let conflict = false;

    if (remote) {
      serverOps = remotePage?.ops ?? [];
      const accepted = new Set(serverOps.map((op) => op.op_id));
      pending = pending.filter((op) => !accepted.has(op.op_id));
      const moved = serverOps.some((op) => !known.has(op.op_id));
      conflict = pending.length > 0 && (moved || this.document.deleted.has(pageId));
    }

    const savedPin = this.store ? ((await this.store.getMeta(`pin:${pageId}`)) ?? 0) : 0;
    const pin = Math.max(remotePage?.pin_seq ?? 0, savedPin);
    const page = {
      id: pageId,
      payload,
      state: new PageState(pageId, payload.width, payload.height, pin),
      clientSeq: 0,
      mine: null,
      sidelined: [],
    };
    this.pages.set(pageId, page);

    for (const op of serverOps) page.state.apply(op);
    if (conflict) {
      page.mine = this.#replayOrNull(page, mine.map((r) => r.op));
      page.sidelined = pending;
    } else {
      const applied = [];
      try {
        for (const op of pending) {
          page.state.apply(op);
          applied.push(op);
        }
      } catch (error) {
        if (!(error instanceof InkError)) throw error;
        console.error("local work no longer applies", error.code);
        conflict = true;
        page.mine = this.#replayOrNull(page, mine.map((r) => r.op));
        page.sidelined = pending;
        page.state = new PageState(pageId, payload.width, payload.height, pin);
        for (const op of serverOps) page.state.apply(op);
      }
    }

    page.journal = this.sync.addJournal({
      url: this.apiUrl(`pages/${pageId}/ops/`),
      serverHead: remotePage?.head_seq ?? serverOps.length,
      pending: conflict ? page.sidelined : pending,
      pageId,
      conflict,
    });
    return serverOps.map((op) => this.#toRecord(op, "page", true));
  }

  #replayOrNull(page, ops) {
    const copy = new PageState(page.id, page.payload.width, page.payload.height);
    try {
      for (const op of ops) copy.apply(op);
      return copy;
    } catch (error) {
      if (!(error instanceof InkError)) throw error;
      console.error("could not rebuild the local version", error.code);
      return null;
    }
  }

  // Keeps server history on the device, so that the page can also reopen without a network.
  async #persistServerOps(records) {
    if (!this.store) return;
    try {
      await this.store.putAll(records);
    } catch (error) {
      console.error("could not store the notebook locally", error);
      this.storageOk = false;
    }
  }

  #registerServiceWorker() {
    if (!("serviceWorker" in navigator)) return;
    // Unavailable on plain-HTTP LAN addresses. The notebook still works, but cannot reopen offline.
    navigator.serviceWorker
      .register("/sw.js")
      .then(() => navigator.serviceWorker.ready)
      .then(() => caches.open("tutor-shell-v1"))
      .then((cache) => cache.add(window.location.href))
      .catch((error) => console.warn("offline reopening is unavailable", error));
  }

  #navigablePages() {
    return [...this.document.pages.keys()].filter(
      (id) => !this.document.deleted.has(id) || this.pages.get(id)?.journal?.conflict,
    );
  }

  #showStatus(state, text) {
    const status = el("sync-status");
    if (!this.storageOk && state !== "conflict") {
      status.dataset.state = "storage-error";
      status.textContent = `Writing is not being stored on this device. ${text}`;
    } else {
      status.dataset.state = state;
      status.textContent = text;
    }
    el("sync-retry").hidden = state !== "paused";
  }

  #onConflict(journal, code) {
    console.warn("page could not be saved", code);
    const page = [...this.pages.values()].find((p) => p.journal === journal);
    if (page) page.sidelined = journal.pending;
    this.#updateConflictPanel();
  }

  #updateConflictPanel() {
    const panel = el("conflict");
    const page = this.activePage;
    const inConflict = Boolean(page?.journal?.conflict);
    panel.hidden = !inConflict;
    if (inConflict) {
      const count = page.sidelined.length;
      el("conflict-text").textContent =
        `This page changed somewhere else. ${count} of your change(s) are kept on this device ` +
        "and have not been saved to the server.";
      el("conflict-copy").disabled = !(page.mine ?? page.state);
    }
  }

  async #markAcked(opIds) {
    if (!this.store) return;
    try {
      await this.store.markAcked(opIds);
    } catch (error) {
      console.error("could not record acknowledgement", error);
    }
  }

  #envelope(type, pageId, seq, payload) {
    return {
      v: 1,
      op_id: newId(),
      type,
      page_id: pageId,
      writer_id: this.writerId,
      epoch: this.epoch,
      client_seq: seq,
      origin: "user",
      client_time_ms: Math.floor(Date.now()),
      payload,
    };
  }

  async #persist(record) {
    if (!this.store) return;
    try {
      await this.store.putAll([record]);
    } catch (error) {
      console.error("could not persist operation locally", error);
      this.storageOk = false;
    }
  }

  async #commitDocument(type, pageId, payload) {
    const op = this.#envelope(type, pageId, ++this.documentSeq, payload);
    this.document.apply(op);
    this.sync.beginCommit(this.documentJournal);
    await this.#persist(this.#toRecord(op, "document", false));
    this.sync.enqueue(this.documentJournal, op);
    return op;
  }

  async #commitInk(page, type, payload) {
    const op = this.#envelope(type, page.id, ++page.clientSeq, payload);
    page.state.apply(op);
    this.sync.beginCommit(page.journal);
    await this.#persist(this.#toRecord(op, "page", false));
    this.sync.enqueue(page.journal, op);
    this.updateButtons();
    return op;
  }

  async createPage(orientation) {
    const id = newId();
    const size = SIZES[orientation];
    const payload = { ...size, orientation, background: "blank" };
    await this.#commitDocument("CREATE_PAGE", id, payload);
    const page = {
      id,
      payload,
      state: new PageState(id, size.width, size.height),
      clientSeq: 0,
      mine: null,
      sidelined: [],
    };
    page.journal = this.sync.addJournal({
      url: this.apiUrl(`pages/${id}/ops/`),
      serverHead: 0,
      pending: [],
      pageId: id,
    });
    this.pages.set(id, page);
    this.activePage = page;
    return page;
  }

  async deleteActivePage() {
    const pages = this.#navigablePages();
    if (pages.length < 2) return;
    const index = pages.indexOf(this.activePage.id);
    const next = pages[index + 1] ?? pages[index - 1];
    await this.#commitDocument("DELETE_PAGE", this.activePage.id, {});
    el("delete-confirm").hidden = true;
    this.showPage(next);
  }

  // CHANGE_PAGE: navigation only. It stays on this device and is never journaled.
  showPage(pageId) {
    this.capture.abandon();
    this.activePage = this.pages.get(pageId);
    this.capture.setPage(this.state.width, this.state.height);
    this.viewport.scrollTo(0, 0);
    this.store?.setMeta(`active:${this.notebookId}`, pageId).catch((error) => {
      console.warn("could not remember the open page", error);
    });
    this.#resetComparison();
    this.#updateConflictPanel();
    this.resize();
  }

  #onPoint(points) {
    if (this.tool === "eraser") {
      const [x, y] = points.at(-1);
      this.eraserPath.push([x, y]);
      return;
    }
    drawLatestSegment(this.ctx, points, PEN.width, PEN.color, this.view.scale);
  }

  #onEnd(stroke) {
    const page = this.activePage;
    if (this.tool === "eraser") {
      const items = computeEraseItems(page.state, this.eraserPath, ERASER_RADIUS, newId);
      if (items.length) {
        this.#commitInk(page, "ERASE_SEGMENT", {
          items,
          eraser: { radius: ERASER_RADIUS, path: this.eraserPath },
        });
      }
    } else {
      this.#commitInk(page, "ADD_STROKE", {
        stroke: {
          id: newId(),
          layer: "student",
          style: { width: PEN.width, color: PEN.color },
          source: stroke.source,
          capture: stroke.capture,
          points: stroke.points,
          raw_points: null,
        },
      });
    }
    this.redraw();
  }

  undo() {
    if (!this.state.canUndo()) return;
    this.#commitInk(this.activePage, "UNDO", { target_op_id: this.state.undo.at(-1) });
    this.redraw();
  }

  redo() {
    if (!this.state.redo.length) return;
    this.#commitInk(this.activePage, "REDO", { target_op_id: this.state.redo.at(-1) });
    this.redraw();
  }

  selectTool(tool) {
    this.tool = tool;
    this.capture.panMode = tool === "hand";
    for (const name of ["pen", "eraser", "hand"]) {
      el(`tool-${name}`).setAttribute("aria-pressed", String(tool === name));
    }
    this.canvas.dataset.tool = tool;
  }

  setZoom(index) {
    this.zoomIndex = Math.min(ZOOM_LEVELS.length - 1, Math.max(0, index));
    this.resize();
  }

  #wireControls() {
    el("tool-pen").addEventListener("click", () => this.selectTool("pen"));
    el("tool-eraser").addEventListener("click", () => this.selectTool("eraser"));
    el("tool-hand").addEventListener("click", () => this.selectTool("hand"));
    el("undo").addEventListener("click", () => this.undo());
    el("redo").addEventListener("click", () => this.redo());
    el("save").addEventListener("click", () => this.save());
    el("sync-retry").addEventListener("click", () => this.sync.retryNow());
    el("zoom-in").addEventListener("click", () => this.setZoom(this.zoomIndex + 1));
    el("zoom-out").addEventListener("click", () => this.setZoom(this.zoomIndex - 1));
    el("page-prev").addEventListener("click", () => this.#stepPage(-1));
    el("page-next").addEventListener("click", () => this.#stepPage(1));
    el("page-new").addEventListener("click", async () => {
      const page = await this.createPage(el("page-orientation").value);
      this.showPage(page.id);
    });
    el("page-delete").addEventListener("click", () => {
      el("delete-confirm").hidden = false;
    });
    el("delete-yes").addEventListener("click", () => this.deleteActivePage());
    el("delete-no").addEventListener("click", () => {
      el("delete-confirm").hidden = true;
    });
    el("conflict-copy").addEventListener("click", () => this.keepMineAsNewPage());
    el("conflict-discard").addEventListener("click", () => this.useOtherVersion());
    document.addEventListener("keydown", (event) => {
      if (!(event.ctrlKey || event.metaKey)) return;
      const key = event.key.toLowerCase();
      if (key === "z" && !event.shiftKey) {
        event.preventDefault();
        this.undo();
      } else if (key === "y" || (key === "z" && event.shiftKey)) {
        event.preventDefault();
        this.redo();
      }
    });
  }

  #stepPage(direction) {
    const pages = this.#navigablePages();
    const target = pages[pages.indexOf(this.activePage.id) + direction];
    if (target) this.showPage(target);
  }

  // Copies the local version into a new page. History is not carried over: the conflicting journal
  // stays on this device, and the server's page is untouched.
  async keepMineAsNewPage() {
    const source = this.activePage;
    const mine = source.mine ?? source.state;
    const page = await this.createPage(source.payload.orientation);
    for (const node of mine.visibleNodes()) {
      const root = mine.roots.get(node.root_id);
      const offset = root.points[node.start][2];
      await this.#commitInk(page, "ADD_STROKE", {
        stroke: {
          id: newId(),
          layer: "student",
          style: root.style,
          source: root.source,
          capture: root.capture,
          points: root.points
            .slice(node.start, node.end + 1)
            .map(([x, y, t, p]) => [x, y, t - offset, p]),
          raw_points: null,
        },
      });
    }
    await this.#setAsideConflict(source);
    await this.sync.whenIdle(page.journal);
    window.location.reload();
  }

  async useOtherVersion() {
    await this.#setAsideConflict(this.activePage);
    window.location.reload();
  }

  async #setAsideConflict(page) {
    const opIds = page.sidelined.map((op) => op.op_id);
    await this.store?.markSidelined(opIds);
  }

  updateButtons() {
    if (!this.activePage) return;
    el("undo").disabled = !this.state.canUndo();
    el("redo").disabled = this.state.redo.length === 0;
    const pages = this.#navigablePages();
    const index = pages.indexOf(this.activePage.id);
    el("page-label").textContent = `Page ${index + 1} of ${pages.length}`;
    el("page-prev").disabled = index <= 0;
    el("page-next").disabled = index >= pages.length - 1;
    el("page-delete").disabled = pages.length < 2;
    el("zoom-out").disabled = this.zoomIndex === 0;
    el("zoom-in").disabled = this.zoomIndex === ZOOM_LEVELS.length - 1;
    el("zoom-label").textContent = `${Math.round(ZOOM_LEVELS[this.zoomIndex] * 100)}%`;
    document.dispatchEvent(new CustomEvent("notebook:changed"));
  }

  resize() {
    const zoom = ZOOM_LEVELS[this.zoomIndex];
    this.view = fitCanvas(this.canvas, this.viewport, this.state.width, this.state.height, zoom);
    this.redraw();
  }

  redraw() {
    drawPage(this.ctx, this.canvas, this.state.visible(), this.view.scale);
    this.updateButtons();
  }

  #setComparison(state, text) {
    const compare = el("compare-status");
    compare.dataset.state = state;
    compare.textContent = text;
  }

  #resetComparison() {
    this.#setComparison("none", "Save the page to compare it.");
    el("revision").textContent = "–";
    el("client-hash").textContent = "–";
    el("server-hash").textContent = "–";
    el("server-render").hidden = true;
  }

  #postRevision(page, seq, chainHash, visibleHash) {
    return fetch(this.apiUrl(`pages/${page.id}/revisions/`), {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": this.csrfToken },
      body: JSON.stringify({ seq, chain_hash: chainHash, visible_hash: visibleHash }),
    });
  }

  // Finishes saving and pins the page, for callers that need the revision itself. Returns
  // { status: "pinned", ... } or a status saying why not. A network failure rejects, unpinned or not.
  async pinCurrentPage() {
    const page = this.activePage;
    if (page.state.opIndex.size === 0) return { status: "empty" };
    const synced = await this.sync.whenIdle(page.journal);
    if (!synced) return { status: "not-synced" };
    const seq = page.state.opIndex.size;
    const visibleHash = page.state.visibleHash();
    const response = await this.#postRevision(page, seq, page.state.chainHash, visibleHash);
    if (!response.ok) {
      const { code } = await response.json();
      return { status: "rejected", code };
    }
    const revision = await response.json();
    page.state.pinIndex = seq;
    await this.store?.setMeta(`pin:${page.id}`, seq);
    this.updateButtons();
    return {
      status: "pinned",
      pageId: page.id,
      revision: revision.revision,
      seq: revision.seq,
      visibleHash: revision.visible_hash,
    };
  }

  // Pins the current page as an immutable revision, then shows what Python rebuilt from the journal.
  async save() {
    const page = this.activePage;
    this.#setComparison("working", "Saving…");
    const synced = await this.sync.whenIdle(page.journal);
    if (!synced) {
      this.#setComparison("error", "Not saved to the server yet. Your writing is kept here.");
      return;
    }
    const seq = page.state.opIndex.size;
    const clientHash = page.state.visibleHash();
    const chainHash = page.state.chainHash;
    el("client-hash").textContent = clientHash;
    try {
      const pin = await this.#postRevision(page, seq, chainHash, clientHash);
      if (!pin.ok) {
        const { code } = await pin.json();
        this.#setComparison("mismatch", `The server did not accept this page (${code}).`);
        return;
      }
      const revision = await pin.json();
      const pageUrl = this.apiUrl(`pages/${page.id}/`);
      const rebuilt = await (await fetch(`${pageUrl}reconstruction/?seq=${seq}`)).json();
      page.state.pinIndex = seq;
      await this.store?.setMeta(`pin:${page.id}`, seq);
      this.updateButtons();
      el("revision").textContent = String(revision.revision);
      el("server-hash").textContent = rebuilt.visible_hash;
      const image = el("server-render");
      image.src = `${pageUrl}render.png?seq=${seq}`;
      image.hidden = false;
      if (rebuilt.visible_hash === clientHash && rebuilt.chain_hash === chainHash) {
        this.#setComparison("match", "Match: the server rebuilt exactly this page.");
      } else {
        this.#setComparison("mismatch", "Mismatch: the server rebuilt a different page.");
      }
    } catch (error) {
      console.warn("save failed", error);
      this.#setComparison("error", "Could not reach the server. Your writing is kept here.");
    }
  }
}

window.addEventListener("unhandledrejection", (event) => {
  console.error("unexpected notebook error", event.reason);
  const status = el("sync-status");
  status.dataset.state = "conflict";
  status.textContent = "Something went wrong saving your last change. Please reload the page.";
});

const app = new NotebookApp(el("app"));
window.tutorInk = app; // Prototype only: lets the end-to-end tests read the client's page state.
app.start().catch((error) => {
  console.error("notebook failed to start", error);
  const status = el("sync-status");
  status.dataset.state = "conflict";
  status.textContent = "The notebook could not start. Please reload the page.";
});
