// The JS core against the same fixtures as the Python core. Hashes must match byte for byte.

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import {
  buildMatrix,
  CHAIN_GENESIS,
  computeEraseItems,
  DocumentState,
  encode,
  InkError,
  matrixMicro,
  opHash,
  PageState,
  replayPage,
  sha256Hex,
  toLogical,
} from "../../static/js/ink/core.js";
import { sha256, toHex } from "../../static/js/ink/sha256.js";

const dir = new URL("../../contracts/digital_ink/v1/fixtures/", import.meta.url);
const load = (name) => JSON.parse(readFileSync(new URL(name, dir), "utf-8"));

const vectors = load("encoding_vectors.json");
const replayFixture = load("replay.json");
const rejectFixture = load("reject.json");
const randomFixture = load("random.json");
const transforms = load("transforms.json");
const documentFixture = load("document.json");
const { page } = replayFixture;

const replay = (ops, pin = 0) => replayPage(page.page_id, page.width, page.height, ops, pin);

for (const vector of vectors.cases) {
  test(`encoding: ${vector.name}`, () => {
    assert.equal(toHex(encode(vector.value)), vector.hex);
  });
}

for (const vector of vectors.sha256) {
  const label = vector.repeat ? `${vector.repeat} x ${vector.times}` : JSON.stringify(vector.ascii);
  test(`sha256 NIST vector: ${label}`, () => {
    const text = vector.repeat ? vector.repeat.repeat(vector.times) : vector.ascii;
    assert.equal(toHex(sha256(new TextEncoder().encode(text))), vector.hex);
  });
}

test("chain genesis comes from the documented label", () => {
  const label = new TextEncoder().encode(vectors.chain_genesis_ascii);
  assert.equal(CHAIN_GENESIS, sha256Hex(label));
});

for (const scenario of [...replayFixture.cases, ...randomFixture.cases]) {
  test(`replay: ${scenario.name}`, () => {
    const state = replay(scenario.ops, scenario.pin_index);
    const { expect } = scenario;
    assert.deepEqual(
      state.visible().map(({ id, points }) => ({ id, points })),
      expect.visible,
    );
    assert.deepEqual(state.undo, expect.undo);
    assert.deepEqual(state.redo, expect.redo);
    assert.deepEqual(scenario.ops.map(opHash), expect.op_hashes);
    assert.equal(state.chainHash, expect.chain_hash);
    assert.equal(state.visibleHash(), expect.visible_hash);
    assert.equal(state.fullHash(), expect.full_hash);
  });
}

for (const scenario of rejectFixture.cases) {
  test(`reject: ${scenario.name}`, () => {
    const state = new PageState(page.page_id, page.width, page.height, scenario.pin_index);
    scenario.ops.slice(0, scenario.at).forEach((op) => state.apply(op));
    assert.throws(
      () => state.apply(scenario.ops[scenario.at]),
      (error) => error instanceof InkError && error.code === scenario.code,
    );
  });
}

for (const scenario of transforms.cases) {
  test(`transform: ${scenario.name}`, () => {
    const { params } = scenario;
    const matrix = buildMatrix({
      viewport: params.viewport,
      dpr: params.dpr,
      rotationDeg: params.rotation_deg,
      pageWidth: params.page_width,
      scroll: params.scroll,
      zoom: params.zoom,
    });
    for (const point of scenario.points) {
      const [x, y] = toLogical(matrix, ...point.in);
      assert.ok(Math.abs(x - point.out[0]) <= transforms.tolerance, `x ${x} vs ${point.out[0]}`);
      assert.ok(Math.abs(y - point.out[1]) <= transforms.tolerance, `y ${y} vs ${point.out[1]}`);
    }
    assert.ok(matrixMicro(matrix).every(Number.isInteger));
  });
}

for (const scenario of documentFixture.cases) {
  test(`document: ${scenario.name}`, () => {
    const document = new DocumentState();
    scenario.ops.forEach((op, index) => {
      if (index === scenario.at) {
        assert.throws(
          () => document.apply(op),
          (error) => error instanceof InkError && error.code === scenario.code,
        );
      } else if (scenario.at === undefined || index < scenario.at) {
        document.apply(op);
      }
    });
    if (scenario.at === undefined) assert.deepEqual(document.livePages(), scenario.live);
  });
}

// ---- Properties, with a seeded generator so that failures reproduce ----

function mulberry32(seed) {
  let a = seed;
  return () => {
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function strokeOp(seq, strokeId, xs) {
  return {
    v: 1,
    op_id: `op-${seq}`,
    type: "ADD_STROKE",
    page_id: page.page_id,
    writer_id: "writer-js",
    epoch: 1,
    client_seq: seq,
    origin: "user",
    client_time_ms: null,
    payload: {
      stroke: {
        id: strokeId,
        layer: "student",
        style: { width: 8, color: "#112233" },
        source: { input: "simulated", device: null },
        capture: {
          matrix_micro: [1000000, 0, 0, 1000000, 0, 0],
          viewport: [2100, 2970],
          dpr_milli: 1000,
          rotation_deg: 0,
        },
        points: xs.map((x, i) => [x, 100, i, null]),
        raw_points: null,
      },
    },
  };
}

function historyOp(seq, type, target) {
  return {
    v: 1,
    op_id: `op-${seq}`,
    type,
    page_id: page.page_id,
    writer_id: "writer-js",
    epoch: 1,
    client_seq: seq,
    origin: "user",
    client_time_ms: null,
    payload: { target_op_id: target },
  };
}

function eraseOp(seq, items) {
  return {
    v: 1,
    op_id: `op-${seq}`,
    type: "ERASE_SEGMENT",
    page_id: page.page_id,
    writer_id: "writer-js",
    epoch: 1,
    client_seq: seq,
    origin: "user",
    client_time_ms: null,
    payload: { items, eraser: { radius: 20, path: [[0, 0]] } },
  };
}

test("property: undo^n redo^n restores the visible page", () => {
  for (let seed = 1; seed <= 25; seed++) {
    const random = mulberry32(seed);
    const state = new PageState(page.page_id, page.width, page.height);
    let seq = 0;
    let fresh = 0;
    const newId = () => `n${++fresh}`;
    for (let i = 0; i < 40; i++) {
      seq++;
      if (random() < 0.6 || state.visibleNodes().length === 0) {
        const xs = Array.from({ length: 1 + Math.floor(random() * 10) }, () =>
          Math.floor(random() * 2000),
        );
        state.apply(strokeOp(seq, newId(), xs));
      } else {
        const x = Math.floor(random() * 2000);
        const items = computeEraseItems(state, [[x, 100]], 60, newId);
        if (items.length) state.apply(eraseOp(seq, items));
      }
    }
    const before = state.visibleHash();
    let undone = 0;
    while (state.undo.length) {
      state.apply(historyOp(++seq, "UNDO", state.undo.at(-1)));
      undone++;
    }
    assert.deepEqual(state.visible(), []);
    for (let i = 0; i < undone; i++) state.apply(historyOp(++seq, "REDO", state.redo.at(-1)));
    assert.equal(state.visibleHash(), before, `seed ${seed}`);
  }
});

// ---- Eraser policy ----

function pageWith(...lines) {
  const state = new PageState(page.page_id, page.width, page.height);
  lines.forEach((xs, i) => state.apply(strokeOp(i + 1, `s${i + 1}`, xs)));
  return state;
}

function idMaker() {
  let n = 0;
  return () => `c${++n}`;
}

test("eraser: removing a middle vertex splits the stroke", () => {
  const items = computeEraseItems(pageWith([0, 100, 200, 300, 400]), [[200, 100]], 10, idMaker());
  assert.deepEqual(items, [
    {
      parent_id: "s1",
      children: [
        { id: "c1", start: 0, end: 1 },
        { id: "c2", start: 3, end: 4 },
      ],
    },
  ]);
});

test("eraser: hitting every vertex leaves no children", () => {
  const items = computeEraseItems(pageWith([100, 105]), [[102, 100]], 50, idMaker());
  assert.deepEqual(items, [{ parent_id: "s1", children: [] }]);
});

test("eraser: crossing a segment with no vertex inside splits between the vertices", () => {
  const path = [
    [150, 0],
    [150, 200],
  ];
  const items = computeEraseItems(pageWith([100, 200]), path, 5, idMaker());
  assert.deepEqual(items, [
    {
      parent_id: "s1",
      children: [
        { id: "c1", start: 0, end: 0 },
        { id: "c2", start: 1, end: 1 },
      ],
    },
  ]);
});

test("eraser: an isolated vertex stays as a single-point child", () => {
  const items = computeEraseItems(pageWith([0, 100, 200]), [[100, 100]], 5, idMaker());
  assert.deepEqual(items[0].children, [
    { id: "c1", start: 0, end: 0 },
    { id: "c2", start: 2, end: 2 },
  ]);
});

test("eraser: nothing nearby produces no operation", () => {
  assert.deepEqual(computeEraseItems(pageWith([0, 100]), [[900, 900]], 5, idMaker()), []);
});

test("eraser: output is always accepted by replay", () => {
  const state = pageWith([0, 100, 200, 300], [150, 250]);
  const items = computeEraseItems(state, [[150, 100]], 60, idMaker());
  state.apply(eraseOp(50, items));
  assert.ok(state.visibleNodes().length > 0);
});
