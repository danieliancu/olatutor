// Pointer Events capture. Turns device input into logical integer points, once, at the source.

import { buildMatrix, matrixMicro, roundHalfAway, toLogical } from "./core.js";

const PEN_PRIORITY_MS = 1500;
const MAX_POINTS = 20000;

export class StrokeCapture {
  constructor(canvas, { pageWidth, pageHeight, onStart, onPoint, onEnd, onCancel, onPan }) {
    this.canvas = canvas;
    this.pageWidth = pageWidth;
    this.pageHeight = pageHeight;
    this.onStart = onStart;
    this.onPoint = onPoint;
    this.onEnd = onEnd;
    this.onCancel = onCancel;
    this.onPan = onPan;
    this.panMode = false;
    this.active = null;
    this.pan = null;
    this.lastPenTime = -Infinity;

    canvas.addEventListener("pointerdown", (event) => this.#down(event));
    canvas.addEventListener("pointermove", (event) => this.#move(event));
    canvas.addEventListener("pointerup", (event) => this.#up(event));
    canvas.addEventListener("pointercancel", (event) => this.#cancel(event));
    canvas.addEventListener("contextmenu", (event) => event.preventDefault());
  }

  setPage(pageWidth, pageHeight) {
    this.pageWidth = pageWidth;
    this.pageHeight = pageHeight;
  }

  // Abandons a gesture in progress, for example when the page changes under it.
  abandon() {
    this.active = null;
    this.pan = null;
  }

  // The canvas may be zoomed or scrolled: its on-screen rectangle already includes both, so the
  // matrix maps the whole page to that rectangle and the position within it is all that matters.
  #geometry() {
    const rect = this.canvas.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    const viewport = [rect.width * dpr, rect.height * dpr];
    const matrix = buildMatrix({
      viewport,
      dpr,
      rotationDeg: 0,
      pageWidth: this.pageWidth,
    });
    return { rect, dpr, viewport, matrix };
  }

  #point(event) {
    const { rect, dpr, matrix } = this.active.geometry;
    const physicalX = (event.clientX - rect.left) * dpr;
    const physicalY = (event.clientY - rect.top) * dpr;
    const [x, y] = toLogical(matrix, physicalX, physicalY);
    const elapsed = Math.max(this.active.lastT, roundHalfAway(event.timeStamp - this.active.t0));
    this.active.lastT = elapsed;
    // Pointer Events report 0.5 for hardware without pressure. Only a pen's value means anything.
    const pressure =
      event.pointerType === "pen" && event.pressure > 0
        ? Math.min(1024, roundHalfAway(event.pressure * 1024))
        : null;
    return [
      Math.min(this.pageWidth, Math.max(0, x)),
      Math.min(this.pageHeight, Math.max(0, y)),
      elapsed,
      pressure,
    ];
  }

  #down(event) {
    if (event.button !== 0 && event.pointerType === "mouse") return;
    if (this.panMode) {
      event.preventDefault();
      this.canvas.setPointerCapture(event.pointerId);
      this.pan = { pointerId: event.pointerId, x: event.clientX, y: event.clientY };
      return;
    }
    if (event.pointerType === "pen") this.lastPenTime = event.timeStamp;
    // A resting hand must not start ink while the pen is in use. Palm rejection proper is M2.
    if (event.pointerType === "touch" && event.timeStamp - this.lastPenTime < PEN_PRIORITY_MS) {
      return;
    }
    if (this.active) return;
    event.preventDefault();
    this.canvas.setPointerCapture(event.pointerId);
    const geometry = this.#geometry();
    this.active = {
      pointerId: event.pointerId,
      pointerType: event.pointerType,
      geometry,
      t0: event.timeStamp,
      lastT: 0,
      points: [],
    };
    this.onStart();
    this.#push(event);
  }

  #push(event) {
    const point = this.#point(event);
    const last = this.active.points.at(-1);
    if (last && last[0] === point[0] && last[1] === point[1] && last[2] === point[2]) return;
    this.active.points.push(point);
    this.onPoint(this.active.points);
  }

  #move(event) {
    if (this.pan && event.pointerId === this.pan.pointerId) {
      this.onPan(this.pan.x - event.clientX, this.pan.y - event.clientY);
      this.pan.x = event.clientX;
      this.pan.y = event.clientY;
      return;
    }
    if (!this.active || event.pointerId !== this.active.pointerId) return;
    if (event.pointerType === "pen") this.lastPenTime = event.timeStamp;
    const events = event.getCoalescedEvents?.() ?? [];
    for (const sample of events.length ? events : [event]) {
      if (this.active.points.length >= MAX_POINTS) {
        this.#finish();
        return;
      }
      this.#push(sample);
    }
  }

  #up(event) {
    if (this.pan && event.pointerId === this.pan.pointerId) {
      this.pan = null;
      return;
    }
    if (!this.active || event.pointerId !== this.active.pointerId) return;
    if (event.pointerType === "pen") this.lastPenTime = event.timeStamp;
    this.#finish();
  }

  #finish() {
    const { points, pointerType, geometry } = this.active;
    this.active = null;
    const { dpr, viewport, matrix } = geometry;
    this.onEnd({
      points,
      source: {
        input: ["pen", "touch", "mouse"].includes(pointerType) ? pointerType : "simulated",
        device: null,
      },
      capture: {
        matrix_micro: matrixMicro(matrix),
        viewport: viewport.map(roundHalfAway),
        dpr_milli: roundHalfAway(dpr * 1000),
        rotation_deg: 0,
      },
    });
  }

  // A cancelled gesture never reaches the journal (spec section 11).
  #cancel(event) {
    if (this.pan && event.pointerId === this.pan.pointerId) {
      this.pan = null;
      return;
    }
    if (!this.active || event.pointerId !== this.active.pointerId) return;
    this.active = null;
    this.onCancel();
  }
}
