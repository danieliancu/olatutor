// Sends committed operations to the server in order, with idempotent retries and bounded backoff.
// A journal that hits a conflict stops on its own; the other pages keep syncing.

const MAX_ATTEMPTS = 6;
const MAX_BATCH_OPS = 100;
const MAX_BATCH_CHARS = 1_500_000;

function csrfCookie() {
  const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
  return match ? match[1] : null;
}

export class SyncEngine {
  constructor({ csrfToken, onStatus, onAcked, onConflict, retryBaseMs = 1000 }) {
    this.csrfToken = csrfToken;
    this.onStatus = onStatus;
    this.onAcked = onAcked;
    this.onConflict = onConflict;
    this.retryBaseMs = retryBaseMs;
    this.journals = [];
    this.running = false;
    this.attempts = 0;
    this.timer = null;

    window.addEventListener("online", () => this.retryNow());
    window.addEventListener("offline", () => this.#report());
  }

  addJournal({ url, serverHead, pending, pageId = null, conflict = false }) {
    const journal = { url, serverHead, pending: [...pending], pageId, conflict, committing: 0 };
    this.journals.push(journal);
    return journal;
  }

  // An operation counts as unsaved from the moment it exists, while it is still being written to
  // local storage. Otherwise "All saved" could show, and a save could pin, without its last stroke.
  beginCommit(journal) {
    journal.committing += 1;
    this.#report();
  }

  enqueue(journal, op) {
    journal.committing -= 1;
    journal.pending.push(op);
    this.schedule();
  }

  pendingCount() {
    return this.journals.reduce(
      (total, j) => total + (j.conflict ? 0 : j.pending.length + j.committing),
      0,
    );
  }

  schedule() {
    this.#report();
    if (!this.running && !this.timer) this.#run();
  }

  retryNow() {
    clearTimeout(this.timer);
    this.timer = null;
    this.attempts = 0;
    this.schedule();
  }

  // Resolves true once this journal is fully acknowledged, false on a failure that needs attention.
  async whenIdle(journal) {
    const unsaved = () => journal.pending.length + journal.committing > 0;
    while (unsaved() && !journal.conflict && this.attempts === 0) {
      await new Promise((resolve) => setTimeout(resolve, 25));
    }
    return !unsaved();
  }

  #report() {
    if (this.journals.some((journal) => journal.conflict)) {
      this.onStatus("conflict", "A page could not be saved. Your writing is kept here.");
      return;
    }
    const pending = this.pendingCount();
    if (pending === 0) this.onStatus("synced", "All saved to the server");
    else if (!navigator.onLine) this.onStatus("offline", `Offline. ${pending} change(s) kept here`);
    else this.onStatus("syncing", `Saving ${pending} change(s)…`);
  }

  async #run() {
    this.running = true;
    try {
      // The document journal comes first, because a page must exist before its ink is accepted.
      let progressed = true;
      while (progressed) {
        progressed = false;
        for (const journal of this.journals) {
          if (journal.conflict) continue;
          const ops = this.#takeBatch(journal);
          if (ops.length) {
            await this.#send(journal, ops);
            progressed = true;
          }
        }
      }
      this.attempts = 0;
      this.#report();
    } catch (error) {
      this.#scheduleRetry(error);
    } finally {
      this.running = false;
    }
  }

  #takeBatch(journal) {
    const ops = [];
    let chars = 0;
    for (const op of journal.pending) {
      // A deletion must wait for the page's own ink, which the server refuses afterwards.
      if (op.type === "DELETE_PAGE" && this.#hasUnsentInk(op.page_id)) break;
      const size = JSON.stringify(op).length;
      if (ops.length && (ops.length >= MAX_BATCH_OPS || chars + size > MAX_BATCH_CHARS)) break;
      // An operation belongs to one writer epoch. Older pending work is sent on its own.
      if (ops.length && (op.writer_id !== ops[0].writer_id || op.epoch !== ops[0].epoch)) break;
      ops.push(op);
      chars += size;
    }
    return ops;
  }

  #hasUnsentInk(pageId) {
    return this.journals.some((j) => j.pageId === pageId && j.pending.length && !j.conflict);
  }

  async #send(journal, ops) {
    const response = await fetch(journal.url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": csrfCookie() ?? this.csrfToken,
      },
      body: JSON.stringify({
        writer_id: ops[0].writer_id,
        epoch: ops[0].epoch,
        base_seq: journal.serverHead,
        ops,
      }),
    });
    if (response.status >= 500 || response.status === 429) {
      throw new Error(`server status ${response.status}`);
    }
    const body = await response.json();
    if (!response.ok) {
      // Unsendable work is never dropped: it stays in the local journal and the UI says so.
      journal.conflict = true;
      this.onConflict(journal, body.code);
      this.#report();
      return;
    }
    journal.pending.splice(0, ops.length);
    journal.serverHead = body.head_seq;
    this.attempts = 0;
    await this.onAcked(ops.map((op) => op.op_id));
    this.#report();
  }

  #scheduleRetry(error) {
    console.warn("ink sync failed", error);
    this.attempts += 1;
    if (this.attempts >= MAX_ATTEMPTS) {
      this.onStatus("paused", "Could not reach the server. Your writing is kept here.");
      return;
    }
    const delay = Math.min(30000, this.retryBaseMs * 2 ** (this.attempts - 1));
    this.onStatus(
      navigator.onLine ? "retrying" : "offline",
      `Not saved to the server yet. Retrying (${this.attempts}/${MAX_ATTEMPTS - 1})`,
    );
    this.timer = setTimeout(() => {
      this.timer = null;
      this.#run();
    }, delay + Math.random() * 250);
  }
}
