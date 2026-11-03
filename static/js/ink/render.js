// Canvas drawing. Curve smoothing happens only here: stored points are never altered.

// Browsers limit canvas memory, and a zoomed A4 page on a high-DPI screen could exceed it.
const MAX_BITMAP_SIDE = 4096;

export function fitCanvas(canvas, viewport, pageWidth, pageHeight, zoom) {
  const dpr = window.devicePixelRatio || 1;
  const cssWidth = viewport.clientWidth * zoom;
  const cssHeight = (cssWidth * pageHeight) / pageWidth;
  canvas.style.width = `${cssWidth}px`;
  canvas.style.height = `${cssHeight}px`;
  const density = Math.min(dpr, MAX_BITMAP_SIDE / Math.max(cssWidth, cssHeight));
  canvas.width = Math.round(cssWidth * density);
  canvas.height = Math.round(cssHeight * density);
  return { cssWidth, cssHeight, dpr, scale: canvas.width / pageWidth };
}

function applyStyle(ctx, width, color, scale) {
  ctx.strokeStyle = color;
  ctx.fillStyle = color;
  ctx.lineWidth = Math.max(1, width * scale);
  ctx.lineCap = "round";
  ctx.lineJoin = "round";
}

export function drawStroke(ctx, points, width, color, scale) {
  applyStyle(ctx, width, color, scale);
  if (points.length === 1) {
    ctx.beginPath();
    ctx.arc(points[0][0] * scale, points[0][1] * scale, ctx.lineWidth / 2, 0, Math.PI * 2);
    ctx.fill();
    return;
  }
  ctx.beginPath();
  ctx.moveTo(points[0][0] * scale, points[0][1] * scale);
  for (let i = 1; i < points.length - 1; i++) {
    const midX = ((points[i][0] + points[i + 1][0]) / 2) * scale;
    const midY = ((points[i][1] + points[i + 1][1]) / 2) * scale;
    ctx.quadraticCurveTo(points[i][0] * scale, points[i][1] * scale, midX, midY);
  }
  const last = points.at(-1);
  ctx.lineTo(last[0] * scale, last[1] * scale);
  ctx.stroke();
}

// Draws only the newest piece, so that ink appears without repainting the whole page.
export function drawLatestSegment(ctx, points, width, color, scale) {
  if (points.length < 2) {
    drawStroke(ctx, points, width, color, scale);
    return;
  }
  const from = points.at(-2);
  const to = points.at(-1);
  applyStyle(ctx, width, color, scale);
  ctx.beginPath();
  ctx.moveTo(from[0] * scale, from[1] * scale);
  ctx.lineTo(to[0] * scale, to[1] * scale);
  ctx.stroke();
}

export function drawPage(ctx, canvas, strokes, scale) {
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  for (const stroke of strokes) {
    drawStroke(ctx, stroke.points, stroke.width, stroke.color, scale);
  }
}
