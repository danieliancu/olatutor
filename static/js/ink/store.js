// Durable local journal in IndexedDB. Browsers may still evict this storage; see the spec, section 10.

const DB_NAME = "tutor-ink";
const DB_VERSION = 1;

function promised(request) {
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

function completed(transaction) {
  return new Promise((resolve, reject) => {
    transaction.oncomplete = () => resolve();
    transaction.onerror = () => reject(transaction.error);
    transaction.onabort = () => reject(transaction.error);
  });
}

export class LocalStore {
  static async open() {
    const request = indexedDB.open(DB_NAME, DB_VERSION);
    request.onupgradeneeded = () => {
      const db = request.result;
      const ops = db.createObjectStore("ops", { keyPath: "op_id" });
      ops.createIndex("by_notebook", ["notebook_id", "position"]);
      db.createObjectStore("meta");
    };
    const store = new LocalStore();
    store.db = await promised(request);
    return store;
  }

  async getMeta(key) {
    const tx = this.db.transaction("meta");
    return promised(tx.objectStore("meta").get(key));
  }

  async setMeta(key, value) {
    const tx = this.db.transaction("meta", "readwrite");
    tx.objectStore("meta").put(value, key);
    await completed(tx);
  }

  async putAll(records) {
    if (!records.length) return;
    const tx = this.db.transaction("ops", "readwrite");
    const ops = tx.objectStore("ops");
    for (const record of records) ops.put(record);
    await completed(tx);
  }

  async #updateAll(opIds, change) {
    const tx = this.db.transaction("ops", "readwrite");
    const ops = tx.objectStore("ops");
    for (const opId of opIds) {
      const getRequest = ops.get(opId);
      getRequest.onsuccess = () => {
        if (getRequest.result) ops.put({ ...getRequest.result, ...change });
      };
    }
    await completed(tx);
  }

  markAcked(opIds) {
    return this.#updateAll(opIds, { acked: true });
  }

  // Conflicting work the user has decided about. Kept on the device, but never replayed or sent.
  markSidelined(opIds) {
    return this.#updateAll(opIds, { sidelined: true });
  }

  async load(notebookId) {
    const tx = this.db.transaction("ops");
    const range = IDBKeyRange.bound([notebookId, 0], [notebookId, Number.MAX_SAFE_INTEGER]);
    return promised(tx.objectStore("ops").index("by_notebook").getAll(range));
  }
}
