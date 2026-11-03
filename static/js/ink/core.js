// Digital Ink v1 core: canonical encoding, hashing, validation and journal replay.
// No DOM access, so the same module runs in browsers and under `node --test`.
// Written separately from apps/notebooks/ink/; the shared fixtures prove the two agree.

import { fromHex, sha256, toHex } from "./sha256.js";

export const MAX_SAFE = Number.MAX_SAFE_INTEGER;

export class InkError extends Error {
  constructor(code, detail = "") {
    super(detail ? `${code}: ${detail}` : code);
    this.code = code;
  }
}

const utf8 = new TextEncoder();

function assertWellFormed(text) {
  for (let i = 0; i < text.length; i++) {
    const unit = text.charCodeAt(i);
    if (unit >= 0xd800 && unit <= 0xdbff) {
      const next = text.charCodeAt(i + 1);
      if (!(next >= 0xdc00 && next <= 0xdfff)) throw new InkError("INVALID_STRING");
      i++;
    } else if (unit >= 0xdc00 && unit <= 0xdfff) {
      throw new InkError("INVALID_STRING");
    }
  }
}

function isAscii(text) {
  for (let i = 0; i < text.length; i++) if (text.charCodeAt(i) > 0x7f) return false;
  return true;
}

export function scan(value) {
  if (value === null || typeof value === "boolean") return;
  if (typeof value === "number") {
    if (!Number.isInteger(value)) throw new InkError("FLOAT_NOT_ALLOWED");
    if (Math.abs(value) > MAX_SAFE) throw new InkError("INT_OUT_OF_RANGE");
    return;
  }
  if (typeof value === "string") {
    if (value.includes("\u0000")) throw new InkError("INVALID_STRING");
    assertWellFormed(value);
    return;
  }
  if (Array.isArray(value)) {
    for (const item of value) scan(item);
    return;
  }
  if (typeof value === "object") {
    for (const [key, item] of Object.entries(value)) {
      if (!isAscii(key)) throw new InkError("INVALID_STRING");
      scan(item);
    }
    return;
  }
  throw new InkError("INVALID_SHAPE");
}

class ByteWriter {
  constructor() {
    this.buffer = new Uint8Array(1024);
    this.view = new DataView(this.buffer.buffer);
    this.length = 0;
  }
  reserve(extra) {
    if (this.length + extra <= this.buffer.length) return;
    const grown = new Uint8Array(Math.max(this.buffer.length * 2, this.length + extra));
    grown.set(this.buffer.subarray(0, this.length));
    this.buffer = grown;
    this.view = new DataView(grown.buffer);
  }
  byte(value) {
    this.reserve(1);
    this.buffer[this.length++] = value;
  }
  uint32(value) {
    this.reserve(4);
    this.view.setUint32(this.length, value);
    this.length += 4;
  }
  int64(value) {
    this.reserve(8);
    this.view.setBigInt64(this.length, BigInt(value));
    this.length += 8;
  }
  raw(bytes) {
    this.reserve(bytes.length);
    this.buffer.set(bytes, this.length);
    this.length += bytes.length;
  }
  result() {
    return this.buffer.slice(0, this.length);
  }
}

function writeString(writer, text) {
  assertWellFormed(text);
  const bytes = utf8.encode(text);
  writer.byte(0x02);
  writer.uint32(bytes.length);
  writer.raw(bytes);
}

function writeValue(writer, value) {
  if (value === null) {
    writer.byte(0x00);
  } else if (typeof value === "boolean") {
    writer.byte(0x04);
    writer.byte(value ? 1 : 0);
  } else if (typeof value === "number") {
    if (!Number.isInteger(value)) throw new InkError("FLOAT_NOT_ALLOWED");
    if (Math.abs(value) > MAX_SAFE) throw new InkError("INT_OUT_OF_RANGE");
    writer.byte(0x01);
    writer.int64(value);
  } else if (typeof value === "string") {
    writeString(writer, value);
  } else if (Array.isArray(value)) {
    writer.byte(0x03);
    writer.uint32(value.length);
    for (const item of value) writeValue(writer, item);
  } else if (typeof value === "object") {
    const keys = Object.keys(value).sort();
    writer.byte(0x05);
    writer.uint32(keys.length);
    for (const key of keys) {
      if (!isAscii(key)) throw new InkError("INVALID_STRING");
      writeString(writer, key);
      writeValue(writer, value[key]);
    }
  } else {
    throw new InkError("INVALID_SHAPE");
  }
}

export function encode(value) {
  const writer = new ByteWriter();
  writeValue(writer, value);
  return writer.result();
}

export function sha256Hex(bytes) {
  return toHex(sha256(bytes));
}

export function opHash(op) {
  return sha256Hex(encode(op));
}

export const CHAIN_GENESIS = sha256Hex(utf8.encode("tutor.ink.v1.chain"));

export function chainNext(previousHex, opHashHex) {
  const previous = fromHex(previousHex);
  const current = fromHex(opHashHex);
  const joined = new Uint8Array(previous.length + current.length);
  joined.set(previous);
  joined.set(current, previous.length);
  return sha256Hex(joined);
}

// ---- Structural validation, mirroring contracts/digital_ink/v1/schema.json ----

const ID = /^[A-Za-z0-9_-]{1,64}$/;
const COLOR = /^#[0-9a-f]{6}$/;
const IMPLEMENTED = [
  "ADD_STROKE",
  "REMOVE_STROKE",
  "ERASE_SEGMENT",
  "RESTORE_STROKE",
  "UNDO",
  "REDO",
  "CREATE_PAGE",
  "DELETE_PAGE",
];
// Navigation is local to a client: it is never journaled, hashed or sent.
const LOCAL_ONLY = ["CHANGE_PAGE"];

function shape(condition, detail) {
  if (!condition) throw new InkError("INVALID_SHAPE", detail);
}

function isObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function exactKeys(value, keys, detail) {
  shape(isObject(value), detail);
  const actual = Object.keys(value).sort();
  const expected = [...keys].sort();
  shape(actual.length === expected.length && actual.every((k, i) => k === expected[i]), detail);
}

function isInt(value, min = -MAX_SAFE, max = MAX_SAFE) {
  return Number.isInteger(value) && value >= min && value <= max;
}

function isId(value) {
  return typeof value === "string" && ID.test(value);
}

function isPair(value) {
  return Array.isArray(value) && value.length === 2 && isInt(value[0]) && isInt(value[1]);
}

function checkStroke(stroke) {
  exactKeys(stroke, ["id", "layer", "style", "source", "capture", "points", "raw_points"], "stroke");
  shape(isId(stroke.id), "stroke.id");
  shape(stroke.layer === "student", "stroke.layer");
  exactKeys(stroke.style, ["width", "color"], "style");
  shape(isInt(stroke.style.width, 1, 200), "style.width");
  shape(typeof stroke.style.color === "string" && COLOR.test(stroke.style.color), "style.color");
  exactKeys(stroke.source, ["input", "device"], "source");
  shape(["pen", "touch", "mouse", "simulated"].includes(stroke.source.input), "source.input");
  shape(
    stroke.source.device === null ||
      (typeof stroke.source.device === "string" && stroke.source.device.length <= 128),
    "source.device",
  );
  exactKeys(stroke.capture, ["matrix_micro", "viewport", "dpr_milli", "rotation_deg"], "capture");
  const matrix = stroke.capture.matrix_micro;
  shape(Array.isArray(matrix) && matrix.length === 6 && matrix.every((v) => isInt(v)), "matrix");
  shape(isPair(stroke.capture.viewport), "viewport");
  shape(isInt(stroke.capture.dpr_milli, 1), "dpr_milli");
  shape([0, 90, 180, 270].includes(stroke.capture.rotation_deg), "rotation_deg");
  const points = stroke.points;
  shape(Array.isArray(points) && points.length >= 1 && points.length <= 20000, "points");
  for (const point of points) {
    shape(Array.isArray(point) && point.length === 4, "point");
    shape(isInt(point[0], 0) && isInt(point[1], 0) && isInt(point[2], 0), "point");
    shape(point[3] === null || isInt(point[3], 0, 1024), "pressure");
  }
  const raw = stroke.raw_points;
  shape(raw === null || (Array.isArray(raw) && raw.length <= 20000 && raw.every(isPair)), "raw");
}

function checkPayload(type, payload) {
  shape(isObject(payload), "payload");
  if (type === "ADD_STROKE") {
    exactKeys(payload, ["stroke"], "payload");
    checkStroke(payload.stroke);
  } else if (type === "REMOVE_STROKE") {
    exactKeys(payload, ["stroke_ids", "reason"], "payload");
    const ids = payload.stroke_ids;
    shape(Array.isArray(ids) && ids.length >= 1 && ids.length <= 2000 && ids.every(isId), "ids");
    shape(["user", "palm"].includes(payload.reason), "reason");
  } else if (type === "ERASE_SEGMENT") {
    exactKeys(payload, ["items", "eraser"], "payload");
    const items = payload.items;
    shape(Array.isArray(items) && items.length >= 1 && items.length <= 2000, "items");
    for (const item of items) {
      exactKeys(item, ["parent_id", "children"], "item");
      shape(isId(item.parent_id), "parent_id");
      shape(Array.isArray(item.children) && item.children.length <= 20000, "children");
      for (const child of item.children) {
        exactKeys(child, ["id", "start", "end"], "child");
        shape(isId(child.id) && isInt(child.start, 0) && isInt(child.end, 0), "child");
      }
    }
    exactKeys(payload.eraser, ["radius", "path"], "eraser");
    shape(isInt(payload.eraser.radius, 1), "radius");
    const path = payload.eraser.path;
    shape(Array.isArray(path) && path.length <= 20000 && path.every(isPair), "path");
  } else if (type === "RESTORE_STROKE") {
    exactKeys(payload, ["stroke_id"], "payload");
    shape(isId(payload.stroke_id), "stroke_id");
  } else if (type === "DELETE_PAGE") {
    exactKeys(payload, [], "payload");
  } else if (type === "UNDO" || type === "REDO") {
    exactKeys(payload, ["target_op_id"], "payload");
    shape(isId(payload.target_op_id), "target_op_id");
  } else if (type === "CREATE_PAGE") {
    exactKeys(payload, ["width", "height", "orientation", "background"], "payload");
    shape(isInt(payload.width, 100, 20000) && isInt(payload.height, 100, 20000), "page size");
    shape(["portrait", "landscape"].includes(payload.orientation), "orientation");
    shape(payload.background === "blank", "background");
  }
}

export function validateOp(op) {
  if (!isObject(op)) throw new InkError("INVALID_SHAPE", "operation");
  scan(op);
  if (op.v !== 1) throw new InkError("UNKNOWN_VERSION");
  if (LOCAL_ONLY.includes(op.type)) throw new InkError("UNSUPPORTED_OP", op.type);
  exactKeys(
    op,
    ["v", "op_id", "type", "page_id", "writer_id", "epoch", "client_seq", "origin", "client_time_ms", "payload"],
    "operation",
  );
  shape(IMPLEMENTED.includes(op.type), "type");
  shape(isId(op.op_id) && isId(op.page_id) && isId(op.writer_id), "ids");
  shape(isInt(op.epoch, 1) && isInt(op.client_seq, 1), "sequence");
  shape(op.origin === "user" || op.origin === "system", "origin");
  shape(op.client_time_ms === null || isInt(op.client_time_ms), "client_time_ms");
  checkPayload(op.type, op.payload);
}

// ---- Replay ----

function compareIds(a, b) {
  return a < b ? -1 : a > b ? 1 : 0;
}

export class PageState {
  constructor(pageId, width, height, pinIndex = 0) {
    this.pageId = pageId;
    this.width = width;
    this.height = height;
    this.pinIndex = pinIndex;
    this.roots = new Map();
    this.nodes = new Map();
    this.effects = new Map();
    this.undo = [];
    this.redo = [];
    this.opIndex = new Map();
    this.nextZ = 0;
    this.chainHash = CHAIN_GENESIS;
    this.palmRemoved = [];
  }

  apply(op) {
    validateOp(op);
    if (op.type === "CREATE_PAGE" || op.type === "DELETE_PAGE") {
      throw new InkError("WRONG_JOURNAL");
    }
    if (op.page_id !== this.pageId) throw new InkError("WRONG_PAGE");
    if (this.opIndex.has(op.op_id)) throw new InkError("DUPLICATE_OP");
    if (op.type === "ADD_STROKE") this.#addStroke(op);
    else if (op.type === "REMOVE_STROKE") this.#removeStroke(op);
    else if (op.type === "ERASE_SEGMENT") this.#eraseSegment(op);
    else if (op.type === "RESTORE_STROKE") this.#restoreStroke(op);
    else if (op.type === "UNDO") this.#undo(op);
    else this.#redo(op);
    this.opIndex.set(op.op_id, this.opIndex.size);
    this.chainHash = chainNext(this.chainHash, opHash(op));
  }

  #requireUser(op) {
    if (op.origin !== "user") throw new InkError("INVALID_ORIGIN");
  }

  #pushContent(opId, activate, deactivate) {
    this.effects.set(opId, { activate, deactivate });
    this.undo.push(opId);
    this.redo.length = 0;
  }

  #addStroke(op) {
    this.#requireUser(op);
    const stroke = op.payload.stroke;
    if (this.nodes.has(stroke.id)) throw new InkError("DUPLICATE_STROKE");
    let previous = 0;
    stroke.points.forEach(([x, y, t], index) => {
      if (x > this.width || y > this.height) throw new InkError("POINT_OUT_OF_PAGE");
      if ((index === 0 && t !== 0) || t < previous) throw new InkError("INVALID_TIMING");
      previous = t;
    });
    this.roots.set(stroke.id, stroke);
    this.nodes.set(stroke.id, {
      id: stroke.id,
      root_id: stroke.id,
      parent_id: null,
      start: 0,
      end: stroke.points.length - 1,
      z: this.nextZ,
      active: true,
    });
    this.nextZ++;
    this.#pushContent(op.op_id, [stroke.id], []);
  }

  #removeStroke(op) {
    const ids = op.payload.stroke_ids;
    if (new Set(ids).size !== ids.length) throw new InkError("DUPLICATE_STROKE");
    for (const id of ids) {
      const node = this.nodes.get(id);
      if (!node) throw new InkError("UNKNOWN_STROKE");
      if (!node.active) throw new InkError("STROKE_NOT_ACTIVE");
    }
    if (op.origin === "system") {
      this.#removeAsPalm(op);
      return;
    }
    if (op.payload.reason !== "user") throw new InkError("INVALID_ORIGIN");
    for (const id of ids) this.nodes.get(id).active = false;
    this.#pushContent(op.op_id, [], [...ids]);
  }

  #removeAsPalm(op) {
    const ids = op.payload.stroke_ids;
    if (op.payload.reason !== "palm" || ids.length !== 1) {
      throw new InkError("SYSTEM_REMOVE_INVALID");
    }
    const strokeId = ids[0];
    if (!this.roots.has(strokeId)) throw new InkError("SYSTEM_REMOVE_INVALID");
    const addOp = this.undo.find((opId) => {
      const { activate } = this.effects.get(opId);
      return activate.length === 1 && activate[0] === strokeId;
    });
    if (addOp === undefined) throw new InkError("SYSTEM_REMOVE_INVALID");
    if (this.opIndex.get(addOp) < this.pinIndex) throw new InkError("PINNED");
    for (const other of [...this.undo, ...this.redo]) {
      const effect = this.effects.get(other);
      const touches = effect.activate.includes(strokeId) || effect.deactivate.includes(strokeId);
      if (other !== addOp && touches) throw new InkError("SYSTEM_REMOVE_INVALID");
    }
    this.nodes.get(strokeId).active = false;
    this.undo.splice(this.undo.indexOf(addOp), 1);
    this.palmRemoved.push(strokeId);
    this.effects.set(op.op_id, { activate: [], deactivate: [strokeId] });
  }

  #eraseSegment(op) {
    this.#requireUser(op);
    const activate = [];
    const deactivate = [];
    const created = [];
    const newIds = new Set();
    const parents = new Set();
    for (const item of op.payload.items) {
      const parent = this.nodes.get(item.parent_id);
      if (!parent) throw new InkError("UNKNOWN_STROKE");
      if (!parent.active) throw new InkError("STROKE_NOT_ACTIVE");
      if (parents.has(item.parent_id)) throw new InkError("DUPLICATE_STROKE");
      parents.add(item.parent_id);

      let cursor = parent.start;
      for (const child of item.children) {
        if (child.start < cursor || child.end < child.start) throw new InkError("INVALID_RANGE");
        if (child.end > parent.end) throw new InkError("INVALID_RANGE");
        cursor = child.end + 1;
        if (this.nodes.has(child.id) || newIds.has(child.id)) {
          throw new InkError("DUPLICATE_STROKE");
        }
        newIds.add(child.id);
        created.push({
          id: child.id,
          root_id: parent.root_id,
          parent_id: item.parent_id,
          start: child.start,
          end: child.end,
          z: parent.z,
          active: true,
        });
        activate.push(child.id);
      }
      const only = item.children.length === 1 ? item.children[0] : null;
      if (only && only.start === parent.start && only.end === parent.end) {
        throw new InkError("ERASE_NOOP");
      }
      deactivate.push(item.parent_id);
    }
    for (const node of created) this.nodes.set(node.id, node);
    for (const id of deactivate) this.nodes.get(id).active = false;
    this.#pushContent(op.op_id, activate, deactivate);
  }

  #restoreStroke(op) {
    this.#requireUser(op);
    const strokeId = op.payload.stroke_id;
    const node = this.nodes.get(strokeId);
    if (!node) throw new InkError("UNKNOWN_STROKE");
    if (node.active) throw new InkError("STROKE_ALREADY_ACTIVE");
    if (this.palmRemoved.includes(strokeId)) throw new InkError("RESTORE_BLOCKED");
    if (this.#hasActiveDescendant(strokeId)) throw new InkError("ACTIVE_DESCENDANTS");
    node.active = true;
    this.#pushContent(op.op_id, [strokeId], []);
  }

  #hasActiveDescendant(strokeId) {
    for (const node of this.nodes.values()) {
      let ancestor = node.parent_id;
      while (ancestor !== null) {
        if (ancestor === strokeId && node.active) return true;
        ancestor = this.nodes.get(ancestor).parent_id;
      }
    }
    return false;
  }

  #undo(op) {
    this.#requireUser(op);
    const target = op.payload.target_op_id;
    if (this.undo.at(-1) !== target) throw new InkError("NOT_STACK_TOP");
    if (this.opIndex.get(target) < this.pinIndex) throw new InkError("PINNED");
    const effect = this.effects.get(target);
    for (const id of effect.activate) this.nodes.get(id).active = false;
    for (const id of effect.deactivate) this.nodes.get(id).active = true;
    this.redo.push(this.undo.pop());
  }

  #redo(op) {
    this.#requireUser(op);
    const target = op.payload.target_op_id;
    if (this.redo.at(-1) !== target) throw new InkError("NOT_STACK_TOP");
    const effect = this.effects.get(target);
    for (const id of effect.deactivate) this.nodes.get(id).active = false;
    for (const id of effect.activate) this.nodes.get(id).active = true;
    this.undo.push(this.redo.pop());
  }

  canUndo() {
    const top = this.undo.at(-1);
    return top !== undefined && this.opIndex.get(top) >= this.pinIndex;
  }

  visibleNodes() {
    const active = [...this.nodes.values()].filter((node) => node.active);
    active.sort((a, b) => a.z - b.z || a.start - b.start || compareIds(a.id, b.id));
    return active;
  }

  visible() {
    return this.visibleNodes().map((node) => {
      const root = this.roots.get(node.root_id);
      return {
        id: node.id,
        z: node.z,
        width: root.style.width,
        color: root.style.color,
        points: root.points.slice(node.start, node.end + 1),
      };
    });
  }

  visibleHash() {
    return sha256Hex(encode({ width: this.width, height: this.height, strokes: this.visible() }));
  }

  fullHash() {
    const ids = [...this.nodes.keys()].sort(compareIds);
    const nodes = ids.map((id) => {
      const node = this.nodes.get(id);
      const root = this.roots.get(id);
      return { ...node, root_digest: root ? sha256Hex(encode(root)) : null };
    });
    return sha256Hex(
      encode({
        page_id: this.pageId,
        width: this.width,
        height: this.height,
        nodes,
        undo: this.undo,
        redo: this.redo,
        palm_removed: [...this.palmRemoved].sort(compareIds),
      }),
    );
  }
}

export class DocumentState {
  constructor() {
    this.pages = new Map();
    this.deleted = new Set();
    this.opIds = new Set();
  }

  apply(op) {
    validateOp(op);
    if (op.type !== "CREATE_PAGE" && op.type !== "DELETE_PAGE") {
      throw new InkError("WRONG_JOURNAL");
    }
    if (this.opIds.has(op.op_id)) throw new InkError("DUPLICATE_OP");
    if (op.origin !== "user") throw new InkError("INVALID_ORIGIN");
    if (op.type === "CREATE_PAGE") {
      if (this.pages.has(op.page_id)) throw new InkError("DUPLICATE_PAGE");
      const isPortrait = op.payload.height >= op.payload.width;
      if (isPortrait !== (op.payload.orientation === "portrait")) {
        throw new InkError("INVALID_PAGE");
      }
      this.pages.set(op.page_id, op.payload);
    } else {
      if (!this.pages.has(op.page_id)) throw new InkError("UNKNOWN_PAGE");
      if (this.deleted.has(op.page_id)) throw new InkError("PAGE_DELETED");
      this.deleted.add(op.page_id);
    }
    this.opIds.add(op.op_id);
  }

  livePages() {
    return [...this.pages.keys()].filter((id) => !this.deleted.has(id));
  }
}

export function replayPage(pageId, width, height, ops, pinIndex = 0) {
  const state = new PageState(pageId, width, height, pinIndex);
  for (const op of ops) state.apply(op);
  return state;
}

// ---- Physical to logical transform (spec section 3) ----

export function roundHalfAway(value) {
  return Math.sign(value) * Math.floor(Math.abs(value) + 0.5) + 0;
}

export function buildMatrix({ viewport, dpr, rotationDeg, pageWidth, scroll = [0, 0], zoom = 1 }) {
  const width = viewport[0] / dpr;
  const height = viewport[1] / dpr;
  let rotation;
  let viewWidth;
  if (rotationDeg === 0) {
    rotation = [1, 0, 0, 1, 0, 0];
    viewWidth = width;
  } else if (rotationDeg === 90) {
    rotation = [0, -1, 1, 0, 0, width];
    viewWidth = height;
  } else if (rotationDeg === 180) {
    rotation = [-1, 0, 0, -1, width, height];
    viewWidth = width;
  } else if (rotationDeg === 270) {
    rotation = [0, 1, -1, 0, height, 0];
    viewWidth = height;
  } else {
    throw new RangeError("rotation must be 0, 90, 180 or 270");
  }
  const unitsPerCssPx = pageWidth / viewWidth / zoom;
  const scale = unitsPerCssPx / dpr;
  const [a, b, c, d, e, f] = rotation;
  return [
    a * scale,
    b * scale,
    c * scale,
    d * scale,
    e * unitsPerCssPx + scroll[0],
    f * unitsPerCssPx + scroll[1],
  ];
}

export function toLogical(matrix, x, y) {
  const [a, b, c, d, e, f] = matrix;
  return [roundHalfAway(a * x + c * y + e), roundHalfAway(b * x + d * y + f)];
}

export function matrixMicro(matrix) {
  return matrix.map((value) => roundHalfAway(value * 1_000_000));
}

// ---- Eraser policy: computes the explicit ranges an ERASE_SEGMENT op records ----

function pointNearSegment(px, py, ax, ay, bx, by, radius) {
  const dx = bx - ax;
  const dy = by - ay;
  const lengthSq = dx * dx + dy * dy;
  const r2 = radius * radius;
  if (lengthSq === 0) return (px - ax) ** 2 + (py - ay) ** 2 <= r2;
  const dot = (px - ax) * dx + (py - ay) * dy;
  if (dot <= 0) return (px - ax) ** 2 + (py - ay) ** 2 <= r2;
  if (dot >= lengthSq) return (px - bx) ** 2 + (py - by) ** 2 <= r2;
  const cross = (px - ax) * dy - (py - ay) * dx;
  return cross * cross <= r2 * lengthSq;
}

function orientation(ax, ay, bx, by, cx, cy) {
  return Math.sign((bx - ax) * (cy - ay) - (by - ay) * (cx - ax));
}

function segmentsCross(p, q, a, b) {
  return (
    orientation(p[0], p[1], q[0], q[1], a[0], a[1]) !==
      orientation(p[0], p[1], q[0], q[1], b[0], b[1]) &&
    orientation(a[0], a[1], b[0], b[1], p[0], p[1]) !==
      orientation(a[0], a[1], b[0], b[1], q[0], q[1])
  );
}

function hitsEraser(x, y, path, radius) {
  if (path.length === 1) return pointNearSegment(x, y, ...path[0], ...path[0], radius);
  for (let i = 1; i < path.length; i++) {
    if (pointNearSegment(x, y, ...path[i - 1], ...path[i], radius)) return true;
  }
  return false;
}

function crossesEraser(from, to, path) {
  for (let i = 1; i < path.length; i++) {
    if (segmentsCross(from, to, path[i - 1], path[i])) return true;
  }
  return false;
}

// Returns the `items` of an ERASE_SEGMENT, or an empty list when nothing is touched. Tests use only
// integer coordinates, so the outcome is exact. This is client policy: replay never re-runs it.
export function computeEraseItems(state, path, radius, newId) {
  const items = [];
  for (const node of state.visibleNodes()) {
    const points = state.roots.get(node.root_id).points;
    const removed = new Set();
    const cutAfter = new Set();
    for (let i = node.start; i <= node.end; i++) {
      if (hitsEraser(points[i][0], points[i][1], path, radius)) removed.add(i);
      if (i < node.end && crossesEraser(points[i], points[i + 1], path)) cutAfter.add(i);
    }
    if (removed.size === 0 && cutAfter.size === 0) continue;

    const children = [];
    let start = null;
    for (let i = node.start; i <= node.end; i++) {
      if (removed.has(i)) {
        if (start !== null) children.push({ id: newId(), start, end: i - 1 });
        start = null;
        continue;
      }
      if (start === null) start = i;
      if (cutAfter.has(i)) {
        children.push({ id: newId(), start, end: i });
        start = null;
      }
    }
    if (start !== null) children.push({ id: newId(), start, end: node.end });
    items.push({ parent_id: node.id, children });
  }
  return items;
}
