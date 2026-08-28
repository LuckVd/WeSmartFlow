/**
 * app.js — 空间想象能力培养主逻辑
 *
 * 三个学习部分：
 * 1. 认识正视图、俯视图、左视图，并支持拖拽旋转观察、实时三视图
 * 2. 数格子闯关：先给正视图猜一共有几个；答错逐步揭示俯视图、左视图，最后解锁旋转观察
 * 3. 孩子自己搭积木或画三视图，让 AI 猜格子数量
 */

const $ = (id) => document.getElementById(id);

const host = $("canvasHost");
const world = new World(host);

// AI 恢复专用画布（create 模式显示，与用户画布左右对照）
const worldAI = new World($("canvasHostAI"));
worldAI.emptyText = "点「🧩 让 AI 恢复图形」，看 AI 只凭三视图把它拼回来";
worldAI.showViewHint = false;

const SHAPES = [
  { name: "小楼梯", w: 4, d: 3, layers: 3, cells: ["0,0,0", "1,0,0", "1,1,0", "2,0,0", "2,1,0", "2,2,0", "2,0,1", "3,0,1"] },
  { name: "城堡角", w: 4, d: 4, layers: 3, cells: ["0,0,0", "1,0,0", "0,0,1", "1,0,1", "1,1,1", "2,0,1", "2,1,1", "3,0,1", "3,0,2", "3,1,2", "2,0,3"] },
  { name: "弯弯桥", w: 5, d: 3, layers: 2, cells: ["0,0,1", "1,0,1", "2,0,1", "3,0,1", "4,0,1", "0,1,1", "2,1,1", "4,1,1", "1,0,0", "3,0,2"] },
  { name: "高低花坛", w: 4, d: 4, layers: 4, cells: ["0,0,0", "0,1,0", "1,0,0", "1,0,1", "1,1,1", "1,2,1", "2,0,1", "2,0,2", "2,1,2", "3,0,2", "3,1,2", "3,2,2", "3,3,2"] },
];

const state = {
  garden: "spatial",   // 当前顶层花园：spatial | algebra
  mode: "learn",
  shapeIndex: 0,
  cells: [...SHAPES[0].cells],
  w: SHAPES[0].w,
  d: SHAPES[0].d,
  layers: SHAPES[0].layers,
  buildTool: "place",
  challengeLevel: 1,
  challengeStage: 1,
  challengeWrong: 0,
  aiThinking: false,
  aiRestored: false,
  voiceOn: true,
  stats: { learned: 0, solved: 0, wrong: 0, created: 0 },
};

function showHint(text) {
  const b = $("hintBanner");
  b.textContent = text;
  b.classList.add("show");
}

function hideHint() {
  const b = $("hintBanner");
  b.classList.remove("show");
  b.textContent = "";
}

function showModal(emoji, title, text, btnLabel, onContinue) {
  $("modalEmoji").textContent = emoji;
  $("modalTitle").textContent = title;
  $("modalText").textContent = text;
  $("modalBtn").textContent = btnLabel;
  $("modal").hidden = false;
  $("modalBtn").onclick = () => {
    $("modal").hidden = true;
    if (onContinue) onContinue();
  };
}

function setActiveButton(groupSelector, activeButton) {
  document.querySelectorAll(groupSelector).forEach((btn) => btn.classList.toggle("active", btn === activeButton));
}

function dimensionsFromCells(cells, fallback = { w: 4, d: 4, layers: 3 }) {
  if (!cells.length) return fallback;
  const pts = parse(cells);
  return {
    w: Math.max(...pts.map((p) => p.x)) + 1,
    d: Math.max(...pts.map((p) => p.z)) + 1,
    layers: Math.max(...pts.map((p) => p.y)) + 1,
  };
}

function orientPoint(p, dir, w, d) {
  if (dir === "side") return { x: d - 1 - p.z, z: p.x, y: p.y };
  if (dir === "back") return { x: w - 1 - p.x, z: d - 1 - p.z, y: p.y };
  if (dir === "left") return { x: d - 1 - p.z, z: p.x, y: p.y };
  return { x: p.x, z: p.z, y: p.y };
}

function orientedDims(dir, w, d) {
  return dir === "side" || dir === "left" ? { w: d, d: w } : { w, d };
}

function projectForDirection(cells, w, d, layers, dir) {
  const dims = orientedDims(dir, w, d);
  const top = Array.from({ length: dims.d }, () => Array(dims.w).fill(0));
  const front = Array.from({ length: layers }, () => Array(dims.w).fill(0));
  const side = Array.from({ length: layers }, () => Array(dims.d).fill(0));
  for (const p of parse(cells)) {
    const q = orientPoint(p, dir, w, d);
    top[q.z][q.x] = Math.max(top[q.z][q.x], q.y + 1);
    front[q.y][q.x] = 1;
    side[q.y][q.z] = 1;
  }
  return { top, front, side, w: dims.w, d: dims.d, layers };
}

function countVisibleCells(grid) {
  return grid.reduce((sum, row) => sum + row.filter((v) => v > 0).length, 0);
}

function cropGridToShape(grid) {
  const rows = grid.length;
  const cols = grid[0] ? grid[0].length : 0;
  let minR = rows;
  let maxR = -1;
  let minC = cols;
  let maxC = -1;

  for (let r = 0; r < rows; r++) {
    for (let c = 0; c < cols; c++) {
      if (grid[r][c] > 0) {
        minR = Math.min(minR, r);
        maxR = Math.max(maxR, r);
        minC = Math.min(minC, c);
        maxC = Math.max(maxC, c);
      }
    }
  }

  if (maxR < 0) return [[0]];
  return grid.slice(minR, maxR + 1).map((row) => row.slice(minC, maxC + 1));
}

function drawGridCanvas(canvas, grid, options = {}) {
  const { showNumbers = false, maxVal = 1, flipY = false, hidden = false, label = "" } = options;
  const sourceGrid = flipY ? [...grid].reverse() : grid;
  const shapeGrid = cropGridToShape(sourceGrid);
  const rows = shapeGrid.length;
  const cols = shapeGrid[0] ? shapeGrid[0].length : 0;
  const ctx = canvas.getContext("2d");
  const pad = 10;
  const cell = 25;
  canvas.width = pad * 2 + Math.max(cols, 1) * cell;
  canvas.height = pad * 2 + Math.max(rows, 1) * cell;
  ctx.clearRect(0, 0, canvas.width, canvas.height);

  if (hidden) {
    ctx.fillStyle = "#f3f5fa";
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.fillStyle = "#9aa4b5";
    ctx.font = "bold 13px -apple-system, sans-serif";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(label || "待解锁", canvas.width / 2, canvas.height / 2);
    return;
  }

  ctx.fillStyle = "#ffffff";
  ctx.fillRect(0, 0, canvas.width, canvas.height);

  for (let r = 0; r < rows; r++) {
    for (let c = 0; c < cols; c++) {
      const v = shapeGrid[r][c];
      const x = pad + c * cell;
      const y = pad + r * cell;

      if (v <= 0) {
        ctx.save();
        ctx.strokeStyle = "rgba(51,65,90,0.24)";
        ctx.lineWidth = 1;
        ctx.setLineDash([4, 4]);
        ctx.strokeRect(x + 0.5, y + 0.5, cell - 1, cell - 1);
        ctx.restore();
        continue;
      }

      ctx.fillStyle = `rgba(91,140,255,${0.46 + 0.44 * (maxVal > 1 ? v / maxVal : 1)})`;
      ctx.fillRect(x, y, cell, cell);

      if (showNumbers) {
        ctx.fillStyle = "#1f2430";
        ctx.font = "bold 13px -apple-system, sans-serif";
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillText(String(v), x + cell / 2, y + cell / 2);
      }
    }
  }

  ctx.strokeStyle = "rgba(51,65,90,0.72)";
  ctx.lineWidth = 1.25;
  ctx.lineCap = "square";
  for (let r = 0; r < rows; r++) {
    for (let c = 0; c < cols; c++) {
      if (shapeGrid[r][c] <= 0) continue;
      const x = pad + c * cell;
      const y = pad + r * cell;
      ctx.strokeRect(x + 0.5, y + 0.5, cell - 1, cell - 1);
    }
  }
}

function rotatedFootprint(cell, angle, w, d) {
  const cx = w / 2;
  const cz = d / 2;
  const cos = Math.cos(angle);
  const sin = Math.sin(angle);
  return [
    { x: cell.x, z: cell.z },
    { x: cell.x + 1, z: cell.z },
    { x: cell.x + 1, z: cell.z + 1 },
    { x: cell.x, z: cell.z + 1 },
  ].map((p) => {
    const rx = p.x - cx;
    const rz = p.z - cz;
    return {
      x: rx * cos - rz * sin,
      z: rx * sin + rz * cos,
    };
  });
}

function continuousProjectionShapes(cells, angle, type) {
  const shapes = [];
  for (const cell of parse(cells)) {
    const footprint = rotatedFootprint(cell, angle, state.w, state.d);
    if (type === "top") {
      shapes.push({
        points: footprint.map((p) => ({ x: p.x, y: p.z })),
        center: {
          x: footprint.reduce((sum, p) => sum + p.x, 0) / footprint.length,
          y: footprint.reduce((sum, p) => sum + p.z, 0) / footprint.length,
        },
        value: cell.y + 1,
        depth: cell.y,
      });
      continue;
    }

    const axisValues = footprint.map((p) => (type === "side" ? p.z : p.x));
    const minAxis = Math.min(...axisValues);
    const maxAxis = Math.max(...axisValues);
    shapes.push({
      points: [
        { x: minAxis, y: -(cell.y + 1) },
        { x: maxAxis, y: -(cell.y + 1) },
        { x: maxAxis, y: -cell.y },
        { x: minAxis, y: -cell.y },
      ],
      axisValues,
      center: { x: (minAxis + maxAxis) / 2, y: -(cell.y + 0.5) },
      value: 1,
      depth: type === "side"
        ? footprint.reduce((sum, p) => sum + p.x, 0) / footprint.length
        : footprint.reduce((sum, p) => sum + p.z, 0) / footprint.length,
    });
  }
  return shapes.sort((a, b) => a.depth - b.depth);
}

function pathProjectionShape(ctx, points) {
  ctx.beginPath();
  ctx.moveTo(points[0].x, points[0].y);
  for (let i = 1; i < points.length; i++) ctx.lineTo(points[i].x, points[i].y);
  ctx.closePath();
}

function shapeSignature(shape) {
  return shape.points
    .map((p) => `${Math.round(p.x * 100)},${Math.round(p.y * 100)}`)
    .sort()
    .join("|");
}

function splitProjectionShapes(shapes, type) {
  const buckets = new Map();
  for (const shape of shapes) {
    const key = type === "top"
      ? shapeSignature(shape)
      : `${Math.round(shape.center.x * 100)},${Math.round(shape.center.y * 100)}`;
    const list = buckets.get(key) || [];
    list.push(shape);
    buckets.set(key, list);
  }

  const visible = [];
  const hidden = [];
  for (const list of buckets.values()) {
    list.sort((a, b) => {
      if (type === "top") return b.value - a.value || b.depth - a.depth;
      return b.depth - a.depth;
    });
    visible.push(list[0]);
    hidden.push(...list.slice(1));
  }

  return { visible, hidden };
}

function drawProjectionOutline(ctx, shape, toCanvas) {
  ctx.save();
  pathProjectionShape(ctx, shape.points.map(toCanvas));
  ctx.stroke();
  ctx.restore();
}

function drawMergedRectProjection(ctx, shapes, toCanvas) {
  const xs = [];
  const ys = [];
  const rects = shapes.map((shape) => {
    const x1 = Math.min(...shape.points.map((p) => p.x));
    const x2 = Math.max(...shape.points.map((p) => p.x));
    const y1 = Math.min(...shape.points.map((p) => p.y));
    const y2 = Math.max(...shape.points.map((p) => p.y));
    xs.push(x1, x2);
    ys.push(y1, y2);
    return { x1, x2, y1, y2 };
  });
  const uniq = (values) => [...new Set(values.map((v) => Math.round(v * 1000) / 1000))].sort((a, b) => a - b);
  const xVals = uniq(xs);
  const yVals = uniq(ys);
  const covered = Array.from({ length: Math.max(0, yVals.length - 1) }, () => Array(Math.max(0, xVals.length - 1)).fill(false));

  for (const rect of rects) {
    for (let yi = 0; yi < yVals.length - 1; yi++) {
      const cy = (yVals[yi] + yVals[yi + 1]) / 2;
      if (cy <= rect.y1 + 1e-6 || cy >= rect.y2 - 1e-6) continue;
      for (let xi = 0; xi < xVals.length - 1; xi++) {
        const cx = (xVals[xi] + xVals[xi + 1]) / 2;
        if (cx > rect.x1 + 1e-6 && cx < rect.x2 - 1e-6) covered[yi][xi] = true;
      }
    }
  }

  ctx.save();
  for (let yi = 0; yi < yVals.length - 1; yi++) {
    for (let xi = 0; xi < xVals.length - 1; xi++) {
      if (!covered[yi][xi]) continue;
      const a = toCanvas({ x: xVals[xi], y: yVals[yi] });
      const b = toCanvas({ x: xVals[xi + 1], y: yVals[yi + 1] });
      ctx.fillRect(a.x, a.y, b.x - a.x, b.y - a.y);
    }
  }
  ctx.restore();

  ctx.save();
  ctx.strokeStyle = "rgba(51,65,90,0.78)";
  ctx.lineWidth = 1.25;
  ctx.lineCap = "square";
  const drawLine = (a, b) => {
    const pa = toCanvas(a);
    const pb = toCanvas(b);
    ctx.beginPath();
    ctx.moveTo(pa.x, pa.y);
    ctx.lineTo(pb.x, pb.y);
    ctx.stroke();
  };
  for (let yi = 0; yi < yVals.length - 1; yi++) {
    for (let xi = 0; xi < xVals.length - 1; xi++) {
      if (!covered[yi][xi]) continue;
      if (!covered[yi][xi - 1]) drawLine({ x: xVals[xi], y: yVals[yi] }, { x: xVals[xi], y: yVals[yi + 1] });
      if (!covered[yi][xi + 1]) drawLine({ x: xVals[xi + 1], y: yVals[yi] }, { x: xVals[xi + 1], y: yVals[yi + 1] });
      if (!covered[yi - 1]?.[xi]) drawLine({ x: xVals[xi], y: yVals[yi] }, { x: xVals[xi + 1], y: yVals[yi] });
      if (!covered[yi + 1]?.[xi]) drawLine({ x: xVals[xi], y: yVals[yi + 1] }, { x: xVals[xi + 1], y: yVals[yi + 1] });
    }
  }
  ctx.restore();
}

function drawContinuousView(canvas, cells, options = {}) {
  const { angle = 0, type = "front", hidden = false, label = "", showNumbers = false } = options;
  const ctx = canvas.getContext("2d");
  const shapes = continuousProjectionShapes(cells, angle, type);
  const pad = 14;
  const unit = 30;

  if (!shapes.length) {
    canvas.width = 72;
    canvas.height = 52;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.fillStyle = hidden ? "#f3f5fa" : "#ffffff";
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    return;
  }

  const allPoints = shapes.flatMap((shape) => shape.points);
  const minX = Math.min(...allPoints.map((p) => p.x));
  const maxX = Math.max(...allPoints.map((p) => p.x));
  const minY = Math.min(...allPoints.map((p) => p.y));
  const maxY = Math.max(...allPoints.map((p) => p.y));
  canvas.width = Math.ceil((maxX - minX) * unit + pad * 2);
  canvas.height = Math.ceil((maxY - minY) * unit + pad * 2);
  ctx.clearRect(0, 0, canvas.width, canvas.height);

  if (hidden) {
    ctx.fillStyle = "#f3f5fa";
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.fillStyle = "#9aa4b5";
    ctx.font = "bold 13px -apple-system, sans-serif";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(label || "待解锁", canvas.width / 2, canvas.height / 2);
    return;
  }

  const toCanvas = (p) => ({
    x: pad + (p.x - minX) * unit,
    y: pad + (p.y - minY) * unit,
  });

  ctx.fillStyle = "#ffffff";
  ctx.fillRect(0, 0, canvas.width, canvas.height);

  const { visible } = splitProjectionShapes(shapes, type);
  const visibleFill = type === "top" ? "rgba(33,166,106,0.82)" : "rgba(91,140,255,0.86)";

  ctx.fillStyle = visibleFill;
  if (type !== "top") {
    drawMergedRectProjection(ctx, visible, toCanvas);
  } else {
    for (const shape of visible) {
      pathProjectionShape(ctx, shape.points.map(toCanvas));
      ctx.fill();
    }

    ctx.strokeStyle = "rgba(51,65,90,0.78)";
    ctx.lineWidth = 1.25;
    ctx.lineJoin = "miter";
    ctx.lineCap = "square";
    for (const shape of visible) drawProjectionOutline(ctx, shape, toCanvas);
  }

  if (showNumbers && type === "top") {
    const topMap = new Map();
    for (const shape of visible) {
      const key = `${Math.round(shape.center.x * 1000)},${Math.round(shape.center.y * 1000)}`;
      topMap.set(key, shape);
    }
    ctx.fillStyle = "#1f2430";
    ctx.font = "bold 12px -apple-system, sans-serif";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    for (const shape of topMap.values()) {
      if (shape.value <= 1) continue;
      const p = toCanvas(shape.center);
      ctx.fillText(String(shape.value), p.x, p.y);
    }
  }
}

function directionName(dir) {
  return { front: "正前方", side: "右侧", back: "背面", left: "左侧" }[dir] || "当前方向";
}

function viewNoteForDirection(dir) {
  return `右侧三视图跟随当前旋转角连续重算：正视图、俯视图、左视图都不是离散切换，而是实时投影。`;
}

function initViews() {
  const grid = $("viewsGrid");
  grid.innerHTML = "";
  for (const [name, id, desc] of [
    ["正视图 / 主视图", "front", "从 z 轴正方向看（宽 × 高）"],
    ["俯视图", "top", "从 y 轴正方向看（宽 × 深）"],
    ["左视图", "side", "从 x 轴正方向看（深 × 高）"],
  ]) {
    const cell = document.createElement("div");
    cell.className = "view-cell";
    const h = document.createElement("h3");
    h.textContent = name;
    const p = document.createElement("p");
    p.textContent = desc;
    p.id = `view-desc-${id}`;
    const canvas = document.createElement("canvas");
    canvas.className = "view-canvas";
    canvas.id = `view-${id}`;
    cell.append(h, p, canvas);
    grid.appendChild(cell);
  }
}

function updateViews() {
  const frontCanvas = $("view-front");
  const topCanvas = $("view-top");
  const sideCanvas = $("view-side");
  if (!frontCanvas || !topCanvas || !sideCanvas) return;

  const inChallenge = state.mode === "challenge";
  const stage = state.challengeStage || 1;
  const proj = projectForDirection(state.cells, state.w, state.d, state.layers, "front");

  $("view-desc-front").textContent = "从 z 轴正方向看过来（宽 × 高）";
  $("view-desc-top").textContent = "从 y 轴正方向看下来（宽 × 深）";
  $("view-desc-side").textContent = "从 x 轴正方向看过来（深 × 高）";

  drawGridCanvas(frontCanvas, proj.front, { flipY: true });
  // 俯视图的行索引是 z（不是 y），不需要 flipY：
  // 3D front 视角下 z=0 在画面上方、z 大在画面下方，
  // canvas 顶部 row 0 = 画面上方，所以 row 0 直接对应 z=0（后方）才与 3D 视角一致。
  // 若 flipY=true 会把前方（z 大）推到 canvas 顶部，与 3D 方向相反，看上去"完全不对"。
  // 俯视图永远无数字：数字=答案，给了就没人需要推理了。
  // 正确推理路径：每格高度取正视图列高与左视图行高的较小值，再求和。
  drawGridCanvas(topCanvas, proj.top, { flipY: false, hidden: inChallenge && stage < 2, label: "答错后揭晓" });
  drawGridCanvas(sideCanvas, proj.side, { flipY: true, hidden: inChallenge && stage < 3, label: "答错后揭晓" });

  $("viewTip").textContent = state.mode === "challenge" ? "（闯关中按步骤解锁）" : "（x 宽 · y 高 · z 深）";
}

function renderWorld(cells = state.cells) {
  world.setGrid(state.w, state.d, state.layers);
  world.setHighlight([]);
  world.render(cells);
  updateViews();
}

function updateStats() {
  $("progressStats").innerHTML = `
    <div class="stat-row"><span>看懂三视图</span><b>${state.stats.learned} 次</b></div>
    <div class="stat-row"><span>闯关答对</span><b>${state.stats.solved} 题</b></div>
    <div class="stat-row"><span>累计尝试</span><b>${state.stats.wrong} 次</b></div>
    <div class="stat-row"><span>自己创作</span><b>${state.stats.created} 个</b></div>`;
}

function setMode(mode) {
  // 模式仅在空间花园中存在（learn / challenge / create）
  if (state.garden !== "spatial") return;
  state.mode = mode;
  document.querySelectorAll(".mode-btn").forEach((b) => b.classList.toggle("active", b.dataset.mode === mode));
  $("learnCard").hidden = mode !== "learn";
  $("challengeCard").hidden = mode !== "challenge";
  $("createCard").hidden = mode !== "create";
  $("viewCard").hidden = false;
  setDualStage(mode === "create");
  $("stageBody").hidden = false;
  $("toolbar").hidden = mode === "challenge";
  hideHint();

  if (mode === "learn") startLearn();
  if (mode === "challenge") startChallenge();
  if (mode === "create") startCreate();
}

/**
 * 顶层花园切换：「空间想象能力培养」↔「代数能力培养」
 * - 代数花园已独立成 #algebraGarden，里面直接挂 cannonStage + cannonLevels
 * - 空间花园切换到代数时停掉 spatial 用的资源（AI / 异步）
 */
function switchGarden(name) {
  if (state.garden === name) return;
  // 离开代数时停掉 cannon
  if (state.garden === "algebra" && typeof stopCannon === "function") stopCannon();
  state.garden = name;
  document.querySelectorAll(".garden-btn").forEach((b) => b.classList.toggle("active", b.dataset.garden === name));
  const isSpatial = name === "spatial";
  $("spatialGarden").hidden = !isSpatial;
  $("algebraGarden").hidden = isSpatial;
  $("gardenBadge").textContent = isSpatial ? "空间想象能力培养" : "代数能力培养";
  if (isSpatial) {
    // 切回空间花园时恢复之前的 mode（默认 learn）
    if (!state.mode) state.mode = "learn";
    setMode(state.mode);
  } else {
    // 进入代数花园：启动 cannon 难度选择
    if (typeof startCannon === "function") startCannon();
    if (typeof state.aiThinking !== "undefined") state.aiThinking = false;
  }
}

/** 双画布（create 模式）↔ 单画布（learn / challenge） */
function setDualStage(dual) {
  $("stageBody").classList.toggle("dual", dual);
  $("aiStageWrap").hidden = !dual;
  $("userStageLabel").hidden = !dual;
  if (dual) {
    // hidden→显示后下一帧强制 resize：该场景下 ResizeObserver 不一定触发，canvas 会停在 1×1
    requestAnimationFrame(() => requestAnimationFrame(() => worldAI._resize()));
  }
}

/** 气泡里显示“AI 正在思考···”（带跳动点点），LLM 返回后移除 */
let thinkingEl = null;
function showThinking(text) {
  removeThinking();
  const line = document.createElement("span");
  line.className = "line thinking";
  line.textContent = text;
  for (let i = 0; i < 3; i++) {
    const d = document.createElement("i");
    d.className = "dot";
    d.textContent = "·";
    line.appendChild(d);
  }
  $("aiBubble").appendChild(line);
  thinkingEl = line;
}
function removeThinking() {
  if (thinkingEl) { thinkingEl.remove(); thinkingEl = null; }
}

function loadShape(index) {
  const shape = SHAPES[index];
  state.shapeIndex = index;
  state.cells = [...shape.cells];
  state.w = shape.w;
  state.d = shape.d;
  state.layers = shape.layers;
  $("levelInfo").textContent = `认识三视图 · ${shape.name}`;
  $("stageSubtitle").textContent = "拖动画布绕竖直轴转动观察立体图形；右侧是固定的正视图、俯视图、左视图三个标准投影。";
  renderWorld();
}

function startLearn() {
  world.setLocked(false);
  world.setPickHandler(onBuildPick);
  world.setView("iso");
  $("toolbar").hidden = false;
  loadShape(state.shapeIndex);
  updateStats();
  showHint("交互已加载 ✅ 左侧可拖拽旋转观察；右侧是固定的正视图、俯视图、左视图三个标准投影。 ");
}

function startChallenge() {
  const lv = generateLevel(state.challengeLevel);
  state.cells = lv.cells;
  state.w = lv.w;
  state.d = lv.d;
  state.layers = lv.layers;
  state.challengeStage = 1;
  state.challengeWrong = 0;
  world.setPickHandler(null);
  world.setLocked(true);
  world.setView("front");
  $("answerInput").value = "";
  $("answerInput").disabled = false;
  $("submitBtn").disabled = false;
  $("nextLevelBtn").hidden = true;
  $("toolbar").hidden = true;
  $("levelInfo").textContent = `第 ${state.challengeLevel} 关 · 只看正视图`;
  $("stageSubtitle").textContent = "先不要旋转：只看正视图，猜一猜一共有几个。答错会逐步解锁更多视图。";
  $("challengeText").textContent = "只看正视图：你猜一共有几个小立方体？";
  renderWorld();
  updateStats();
}

function expectedChallengeAnswer() {
  return state.cells.length;
}

/** 答错后推进阶段：1→2 公布俯视图，2→3 公布左视图，3→4 揭晓答案+解锁旋转 */
function advanceStage() {
  state.challengeStage = Math.min(4, state.challengeStage + 1);
  const stage = state.challengeStage;

  if (stage === 2) {
    showModal("🤔", "公布俯视图帮你算！", "正视图看不出被挡住的方块，没法直接算总数。\n\n俯视图告诉你哪些位置有方块（看不出高度）。结合两个视图想一想：每个位置最高能叠几层？", "继续挑战", () => {
      $("levelInfo").textContent = `第 ${state.challengeLevel} 关 · 正视图 + 俯视图`;
      $("challengeText").textContent = "结合正视图和俯视图：这个结构一共有几个小立方体？";
      $("stageSubtitle").textContent = "正视图告诉我每列最高到几层，俯视图告诉我哪些位置有方块——把每列的方块数加起来试试。";
      updateViews();
      $("answerInput").value = "";
      $("answerInput").focus();
    });
  } else if (stage === 3) {
    showModal("🤔", "再试一次！", "再公布左视图：从左边看每一层的形状。三个视图合起来想一想，一共是几个？", "继续挑战", () => {
      $("levelInfo").textContent = `第 ${state.challengeLevel} 关 · 三视图都给出`;
      $("challengeText").textContent = "三视图都给出来了：这个结构一共有几个小立方体？";
      $("stageSubtitle").textContent = "正视图管每列最高，左视图管每行最高——每个位置的高度取两个里较小的那个，再加起来。";
      updateViews();
      $("answerInput").value = "";
      $("answerInput").focus();
    });
  } else {
    world.setLocked(false);
    updateViews();
    showModal("📖", "答案揭晓", `这个结构一共有 ${state.cells.length} 个小立方体。现在可以自由旋转观察，看看三个视图是怎么对应起来的。`, "知道了", () => {});
    $("levelInfo").textContent = `第 ${state.challengeLevel} 关 · 已揭晓答案`;
    $("challengeText").textContent = `答案：一共有 ${state.cells.length} 个小立方体。`;
    $("stageSubtitle").textContent = "已解锁旋转，拖动画布从不同方向观察验证。";
    $("answerInput").disabled = true;
    $("submitBtn").disabled = true;
    $("nextLevelBtn").hidden = false;
  }
}

/** 答对：解锁全部三视图 + 旋转，显示“下一关” */
function completeChallenge(stageWhenSolved) {
  state.challengeStage = 4;
  world.setLocked(false);
  updateViews();
  $("levelInfo").textContent = `第 ${state.challengeLevel} 关 · 完成！`;
  $("challengeText").textContent = `太棒了！这个结构一共有 ${state.cells.length} 个小立方体。`;
  $("stageSubtitle").textContent = "三视图和旋转都已解锁，可以自由观察验证你的答案。";
  $("answerInput").disabled = true;
  $("submitBtn").disabled = true;
  $("nextLevelBtn").hidden = false;
  if (stageWhenSolved === 1) {
    showModal("🎉", "一眼看穿！", `只看正视图就猜对了！这个结构一共有 ${state.cells.length} 个小立方体。三视图和旋转已解锁，转一转验证一下。`, "继续", () => {});
  } else {
    showModal("🎉", "答对啦！", `这个结构一共有 ${state.cells.length} 个小立方体。三视图和旋转观察都已解锁，转一转验证一下。`, "继续", () => {});
  }
}

function submitChallenge() {
  if (state.mode !== "challenge") return;
  if (state.challengeStage >= 4) return;
  const v = Number.parseInt($("answerInput").value, 10);
  if (Number.isNaN(v)) return;
  const answer = expectedChallengeAnswer();
  $("answerInput").value = "";
  if (v === answer) {
    state.stats.solved++;
    updateStats();
    completeChallenge(state.challengeStage);
  } else {
    state.stats.wrong++;
    state.challengeWrong++;
    updateStats();
    advanceStage();
  }
}

function startCreate() {
  state.cells = [];
  state.w = 5;
  state.d = 5;
  state.layers = 5;
  state.buildTool = "place";
  state.aiThinking = false;
  state.aiRestored = false;
  $("aiSpeech").hidden = true;
  world.setLocked(false);
  world.setPickHandler(onBuildPick);
  world.setView("iso");
  worldAI.setGrid(5, 5, 5);
  worldAI.setView("iso");
  worldAI.setHighlight([]);
  worldAI.render([]);
  $("toolbar").hidden = false;
  $("levelInfo").textContent = "自由创作 · 搭积木让 AI 猜";
  $("stageSubtitle").textContent = "点击网格放置，点击方块向上叠；搭好后让 AI 从三个方向观察推理，看看它是怎么算出来的。";
  setActiveButton("#createCard .tool-btn", $("toolPlace"));
  renderWorld();
  updateStats();
}

function onBuildPick(pick) {
  if (state.mode !== "learn" && state.mode !== "create") return;
  if (state.aiThinking) return; // AI 观察中，先不许动
  // 用户重新搭建时，清掉 AI 画布上一次的恢复结果
  if (state.mode === "create" && state.aiRestored) {
    state.aiRestored = false;
    worldAI.setHighlight([]);
    worldAI.render([]);
  }
  if (pick.type === "ground" && state.buildTool === "place") {
    const k = key(pick.x, 0, pick.z);
    if (!state.cells.includes(k)) state.cells.push(k);
  } else if (pick.type === "cube") {
    if (state.buildTool === "place") {
      const k = key(pick.x, pick.y + 1, pick.z);
      if (pick.y + 1 < state.layers && !state.cells.includes(k)) state.cells.push(k);
    } else {
      state.cells = removeStack(state.cells, pick.x, pick.y, pick.z);
    }
  }
  if (state.mode === "create") state.stats.created = Math.max(state.stats.created, 1);
  const dims = dimensionsFromCells(state.cells, { w: state.w, d: state.d, layers: state.layers });
  state.w = Math.max(state.w, dims.w);
  state.d = Math.max(state.d, dims.d);
  state.layers = Math.max(state.layers, dims.layers, 3);
  renderWorld();
  updateStats();
}

function setBuildTool(tool, btn) {
  state.buildTool = tool;
  if (state.mode === "learn") setActiveButton("#learnPlaceBtn, #learnRemoveBtn", btn);
  if (state.mode === "create") setActiveButton("#toolPlace, #toolRemove", btn);
}

function clearCurrentBuild() {
  state.cells = [];
  renderWorld();
  showHint("已经清空啦。现在可以点「＋搭积木」快速添加，也可以直接点击画布上的网格搭建。");
}

function addOneCubeSmart() {
  const occupied = new Set(state.cells);
  for (let y = 0; y < state.layers; y++) {
    for (let z = 0; z < state.d; z++) {
      for (let x = 0; x < state.w; x++) {
        const current = key(x, y, z);
        const supported = y === 0 || occupied.has(key(x, y - 1, z));
        if (!occupied.has(current) && supported) {
          state.cells.push(current);
          world.setHighlight([current]);
          world.render(state.cells);
          updateViews();
          showHint("已添加 1 块积木。相邻方块会贴合在一起，右侧三个视图同步刷新。 ");
          return;
        }
      }
    }
  }
  showHint("当前图形已经搭到这个练习允许的最高层啦，可以先点「－拿掉」或「清空」再继续搭。");
}

// ── AI 人设：情绪话术池（每次随机抽，更有生命感） ──
const pickLine = (arr) => arr[Math.floor(Math.random() * arr.length)];
const AI_SPEECH = {
  frontOpen: [
    "让我先看看正面……",
    "先从正面看起！",
    "站好啦，先看正面……",
  ],
  layer: [
    "第 {i} 层……能看到 {n} 个方块。",
    "数数看，第 {i} 层有 {n} 个。",
    "嗯——第 {i} 层，{n} 个！",
  ],
  frontTotal: [
    "正面一共能看到 {n} 个。",
    "好，正面看到 {n} 个！",
  ],
  sideOpen: [
    "再绕到侧面看看……",
    "嗯，我再去侧面瞅瞅……",
    "换个方向，去侧面看看……",
  ],
  sideTotal: [
    "侧面能看到 {m} 个。嗯……正面加侧面，还是差了点什么……",
    "侧面看到 {m} 个。光靠这两个方向还不够……",
  ],
  topOpen: [
    "最后从上面看看！",
    "还差一个角度——从头顶往下看！",
    "关键时刻，俯视图登场！",
  ],
  topRead: [
    "俯视图有 {n} 个位置有方块——但看不出每格叠了几层……",
    "从上往下看，{n} 个位置有方块。高度嘛，看不出来……",
  ],
  topInfer: [
    "我推理：每格高度取正视图和左视图的较小值——一共 {k} 个！",
    "按我的推理方法拼出来，应该是 {k} 个！",
  ],
  guess: [
    "我猜——一共有 {g} 个！",
    "嗯！我赌 {g} 个！",
    "就是它了，{g} 个！",
  ],
  win: [
    "哼哼，三个方向都看过了，难不倒我！",
    "嘿嘿，被我看穿了吧！",
    "正面、侧面、上面，一个都逃不过我的眼睛！",
  ],
  lose: [
    "什么？！居然差了 {k} 个？！",
    "呜……一定是哪里看漏了……",
    "不可能！我明明数得很仔细……",
  ],
};

/** 浏览器 TTS：让 AI 真的把话读出来（免费，macOS 自带中文语音） */
function speak(text) {
  if (!state.voiceOn) return;
  if (!("speechSynthesis" in window)) return;
  try {
    const u = new SpeechSynthesisUtterance(text.replace(/[……—！？、]/g, ""));
    u.lang = "zh-CN";
    u.rate = 0.95;
    u.pitch = 1.25;
    window.speechSynthesis.speak(u);
  } catch (e) { /* 静默失败，不影响游戏 */ }
}

/** 切换 AI 头像表情：emoji + 情绪动画类 */
function setAvatar(emoji, mood) {
  const el = document.querySelector(".ai-avatar");
  if (!el) return;
  el.textContent = emoji;
  el.className = "ai-avatar" + (mood ? " " + mood : "");
}

function aiGuess() {
  if (state.aiThinking) return;
  if (state.cells.length === 0) {
    showHint("先搭一些方块，AI 才能猜哦。");
    return;
  }

  // ── AI 绕三个方向观察：正面 → 侧面 → 俯视（全程无数字，只看形状）──
  state.aiThinking = true;
  world.setLocked(true);

  const proj = projectForDirection(state.cells, state.w, state.d, state.layers, "front");
  const frontLayers = proj.front.map((row) => row.filter((v) => v > 0).length);
  const frontVisible = frontLayers.reduce((a, b) => a + b, 0);
  const sideVisible = proj.side.reduce((sum, row) => sum + row.filter((v) => v > 0).length, 0);
  const topSpots = proj.top.flat().filter((v) => v > 0).length;
  const actual = state.cells.length;
  // AI 的猜测来自推理引擎：只凭无数字三视图推出的结构（绝不偷看真实高度）
  const guess = minStructureFromViews().length;

  const tpl = (s, obj) => s.replace(/\{(\w+)\}/g, (_, k) => obj[k]);

  const entries = [
    { text: tpl(pickLine(AI_SPEECH.frontOpen), {}), view: "view-front", set3d: "front" },
    ...frontLayers.map((n, i) => (n > 0
      ? { text: tpl(pickLine(AI_SPEECH.layer), { i: i + 1, n }), view: "view-front" }
      : null)).filter(Boolean),
    { text: tpl(pickLine(AI_SPEECH.frontTotal), { n: frontVisible }), view: "view-front" },
    { text: tpl(pickLine(AI_SPEECH.sideOpen), {}), view: "view-side", set3d: "left" },
    { text: tpl(pickLine(AI_SPEECH.sideTotal), { m: sideVisible }), view: "view-side" },
    { text: tpl(pickLine(AI_SPEECH.topOpen), {}), view: "view-top" },
    { text: tpl(pickLine(AI_SPEECH.topRead), { n: topSpots }), view: "view-top" },
    { text: tpl(pickLine(AI_SPEECH.topInfer), { k: guess }), view: "view-top" },
    { text: tpl(pickLine(AI_SPEECH.guess), { g: guess }), view: null },
  ];

  playSpeech(entries, () => {
    const correct = guess === actual;
    const k = Math.abs(guess - actual);
    if (correct) {
      setAvatar("🥳", "happy");
      speak(pickLine(AI_SPEECH.win));
    } else {
      setAvatar("🤔", "thinking");
      speak("原来还有藏在视图外的方块！");
    }
    showModal(
      correct ? "🥳" : "🔍",
      correct ? "推理正确！" : "发现三视图的极限！",
      correct
        ? `我只凭三视图的形状推算出 ${guess} 个，实际就是 ${actual} 个！${pickLine(AI_SPEECH.win)}方法：每格高度取正视图和左视图的较小值。`
        : `我推算 ${guess} 个，你实际搭了 ${actual} 个——差 ${k} 个！它们藏在三视图看不见的地方：同一个位置叠得更高，从正面、侧面、上面都看不出来。\n\n光看三视图的形状，有时不能唯一确定立体图形！点「🧩 让 AI 恢复图形」看看我推理出的图形长什么样～`,
      "继续",
      () => {
        state.aiThinking = false;
        world.setLocked(false);
        $("aiSpeech").hidden = true;
        setAvatar("🤖", "idle");
      },
    );
  });
}

/** AI 逐条“思考 aloud”：支持每条指定高亮视图 + 3D 转场 + TTS + 表情 */
function playSpeech(entries, onDone) {
  const bubble = $("aiBubble");
  bubble.innerHTML = "";
  $("aiSpeech").hidden = false;
  setAvatar("🤔", "thinking");

  let currentCell = null;
  const highlight = (viewId) => {
    if (currentCell) currentCell.classList.remove("highlight");
    currentCell = viewId ? document.querySelector(`#${viewId}`)?.closest(".view-cell") : null;
    if (currentCell) currentCell.classList.add("highlight");
  };

  let i = 0;
  const step = () => {
    if (i >= entries.length) {
      highlight(null);
      setAvatar("😲", "eureka");
      setTimeout(() => { if (onDone) onDone(); }, 800);
      return;
    }
    const entry = entries[i++];
    if (entry.view) highlight(entry.view);
    if (entry.set3d) world.setView(entry.set3d);
    if (i === entries.length) setAvatar("😲", "eureka");
    const line = document.createElement("span");
    line.className = "line";
    line.textContent = entry.text;
    bubble.appendChild(line);
    speak(entry.text);
    setTimeout(step, 1250);
  };
  step();
}

/** 追加一条话术到气泡（不打断正在播的，用于恢复动画期间） */
function appendSpeechLine(text) {
  const line = document.createElement("span");
  line.className = "line";
  line.textContent = text;
  $("aiBubble").appendChild(line);
}

// ── 可选 LLM 接入：如需后端能力，请在 WeSmartFlow 后端显式挂载 /api/demo/dive-into-math-garden/llm；失败时使用本地规则降级。──

async function askLLM(messages) {
  try {
    const res = await fetch("/api/demo/dive-into-math-garden/llm", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ messages }),
    });
    return await res.json();
  } catch (e) {
    return { ok: false, error: String(e) };
  }
}

/** 把三视图序列化成 LLM 能读的文本——全部二值形状（X/·），不带任何数字。
 *  俯视图数字 = 每格真实高度 = 答案本身，给了就不是推理了。 */
function viewsTextForLLM() {
  const proj = projectForDirection(state.cells, state.w, state.d, state.layers, "front");
  const bin = (g) => g.map((r) => r.map((v) => (v > 0 ? "X" : "·")).join(" ")).join("\n");
  return `正视图（上排是最上层，X=能看到方块）：\n${bin(proj.front)}\n\n俯视图（X=这个位置有方块，看不出叠了几层）：\n${bin(proj.top)}\n\n左视图：\n${bin(proj.side)}`;
}

/** 轮3：总结——带上"推理结果 vs 实际结构"的对比事实，让 LLM 点评教学点 */
function restorePrompt(inferCount, realCount, identical) {
  const fact = identical
    ? `你推理出的结构和小朋友搭的一模一样（都是 ${realCount} 个方块）——三视图完全确定了它。`
    : `你推理出了 ${inferCount} 个方块，小朋友实际搭了 ${realCount} 个——两个结构不同，但三视图一模一样！`;
  return [
    { role: "system", content: "你是一个活泼的数学小老师机器人，正在和小学三年级的小朋友玩三视图积木游戏。说话简短生动，像和小朋友聊天，不要出现坐标、公式或 markdown。" },
    { role: "user", content: `刚才的挑战：小朋友搭了积木结构，你只凭无数字的三视图（只有形状轮廓，看不出每格叠了几层）推理恢复。${fact}\n\n请说一段总结（两三句话，70字以内）：${identical
      ? "庆祝你推理成功，并点出方法：正视图告诉我每列最高，左视图告诉我每行最高，每格取两个高度的较小值。"
      : "点出今天最重要的发现：光看三视图不能唯一确定立体图形！被挡住的高度差异从三个方向都看不出来。这正是三视图的极限。"}` },
  ];
}

/** 轮1：观察——只凭三视图形状描述像什么（不给方块总数，信息对称） */
function observePrompt() {
  return [
    { role: "system", content: "你是一个活泼的数学小老师机器人，正在和小学三年级的小朋友玩三视图积木游戏。说话简短生动，一到两句话。" },
    { role: "user", content: `小朋友搭了一个积木结构。三视图如下（只有形状，看不出每格叠了几层）：\n${viewsTextForLLM()}\n\n请只凭这三张图，用一到两句话生动地描述这个结构长什么样、让你想到什么（楼梯？小城堡？桥？墙？）。不要出现任何数字和坐标。` },
  ];
}

/** 轮2：恢复策略——无数字三视图的推理方法 */
function planPrompt() {
  return [
    { role: "system", content: "你是一个活泼的数学小老师机器人，正在和小学三年级的小朋友玩三视图积木游戏。说话简短生动，一到两句话。" },
    { role: "user", content: `还是这个结构，三视图（无数字）：\n${viewsTextForLLM()}\n\n现在你要把它从零重新拼出来。用一到两句话说说你的推理计划：正视图告诉我每列最高到几层，左视图告诉我每行最高到几层，俯视图告诉我哪些位置有方块——每个位置叠的高度取两个高度的较小值就一定符合三视图。不要出现坐标。` },
  ];
}

// ── 三视图恢复动画（确定性引擎：从无数字三视图推理重建）──

/**
 * AI 推理引擎：只凭无数字三视图（形状轮廓）推出一个满足约束的结构。
 *   frontH(x) = 正视图 x 列最高层；sideH(z) = 左视图 z 行最高层
 *   h(x,z) = 俯视图有标记 ? min(frontH(x), sideH(z)) : 0
 * 可证该结构的三视图与给定完全一致（合法解），
 * 但不一定是用户的原结构——这正是"三视图不能唯一确定立体图形"的教学点。
 */
function minStructureFromViews() {
  const proj = projectForDirection(state.cells, state.w, state.d, state.layers, "front");
  const frontH = Array(state.w).fill(0);
  for (let y = 0; y < proj.front.length; y++)
    for (let x = 0; x < state.w; x++)
      if (proj.front[y][x]) frontH[x] = Math.max(frontH[x], y + 1);
  const sideH = Array(state.d).fill(0);
  for (let y = 0; y < proj.side.length; y++)
    for (let z = 0; z < state.d; z++)
      if (proj.side[y][z]) sideH[z] = Math.max(sideH[z], y + 1);
  const cells = [];
  for (let z = 0; z < state.d; z++)
    for (let x = 0; x < state.w; x++)
      if (proj.top[z][x] > 0) {
        const h = Math.min(frontH[x], sideH[z]);
        for (let y = 0; y < h; y++) cells.push(`${x},${y},${z}`);
      }
  return cells;
}

/** 把 cells 按列分组：[{x, z, h}]，按 z 行 x 列排序 */
function columnsFromCells(cells) {
  const cols = new Map();
  for (const k of cells) {
    const [x, y, z] = k.split(",").map(Number);
    const ck = `${x},${z}`;
    cols.set(ck, Math.max(cols.get(ck) || 0, y + 1));
  }
  return [...cols.entries()]
    .map(([ck, h]) => {
      const [x, z] = ck.split(",").map(Number);
      return { x, z, h };
    })
    .sort((a, b) => a.z - b.z || a.x - b.x);
}

/**
 * 在指定画布上清空后逐列重建：每列按俯视图高度整柱出现，当前列高亮。
 * onStep(col, i, n) 每列回调；onDone 完成。
 */
function animateRestore(worldInst, cells, onStep, onDone) {
  const cols = columnsFromCells(cells);
  const interval = cols.length > 8 ? 480 : 950;
  let built = [];
  let ci = 0;
  worldInst.render([]);
  const step = () => {
    if (ci >= cols.length) {
      worldInst.setHighlight([]);
      if (onDone) onDone();
      return;
    }
    const col = cols[ci++];
    for (let y = 0; y < col.h; y++) built.push(`${col.x},${y},${col.z}`);
    worldInst.render(built);
    worldInst.setHighlight(built.slice(-col.h));
    if (onStep) onStep(col, ci, cols.length);
    setTimeout(step, interval);
  };
  step();
}

/** 调一轮 LLM，返回文本或 null（失败/超时降级） */
async function askLLMText(prompt) {
  try {
    const r = await askLLM(prompt);
    if (r.ok && r.text) return r.text.trim();
  } catch (e) { /* 降级 */ }
  return null;
}

/**
 * AI 从无数字三视图恢复图形（三轮对话推理 + 双画布对照）：
 * AI 绝不偷看原结构——推理结果由 minStructureFromViews() 只凭视图轮廓算出。
 * 轮1 观察描述（LLM）→ 轮2 恢复策略（LLM）→ 右画布逐列重建动画 → 轮3 总结（LLM，动画期间并行）
 */
async function aiRestore() {
  if (state.aiThinking) return;
  if (state.cells.length === 0) {
    showHint("先搭一些方块，AI 才能从三视图恢复它哦。");
    return;
  }
  const originalCells = [...state.cells];
  // AI 的推理结果：只凭无数字三视图，绝不偷看 originalCells
  const inferredCells = minStructureFromViews();
  const realCount = originalCells.length;
  const inferCount = inferredCells.length;
  const identical = inferCount === realCount && inferredCells.every((k) => originalCells.includes(k));

  state.aiThinking = true;
  world.setLocked(true);
  world.setView("iso");
  setAvatar("🤔", "thinking");
  $("aiBubble").innerHTML = "";
  $("aiSpeech").hidden = false;

  // 轮1：观察
  showThinking("AI 正在观察三视图");
  const obs = await askLLMText(observePrompt());
  removeThinking();
  appendSpeechLine(obs || "让我仔细看看这三张图……嗯，有思路了！");
  if (obs) speak(obs);
  await new Promise((r) => setTimeout(r, 600));

  // 轮2：恢复策略
  showThinking("AI 正在思考恢复步骤");
  const plan = await askLLMText(planPrompt());
  removeThinking();
  appendSpeechLine(plan || "正视图告诉我每列最高几层，左视图告诉我每行最高几层，每格取较小的那个高度——开叠！");
  if (plan) speak(plan);
  await new Promise((r) => setTimeout(r, 600));

  // 准备 AI 画布，轮3 后台并行
  worldAI.setGrid(state.w, state.d, state.layers);
  worldAI.setView("iso");
  worldAI.setHighlight([]);
  const llm3Promise = askLLMText(restorePrompt(inferCount, realCount, identical));

  appendSpeechLine("开工！按我的推理把它拼出来——");
  speak("开工！按我的推理把它拼出来");

  animateRestore(worldAI, inferredCells, (col, i, n) => {
    appendSpeechLine(`第 ${i} 格：推算叠 ${col.h} ${col.h > 1 ? "块" : "块"}！`);
    if (n <= 6 || i === n) speak(`叠 ${col.h} 块`);
  }, async () => {
    if (identical) {
      appendSpeechLine("恢复完成！和左边你搭的一模一样——");
    } else {
      appendSpeechLine("恢复完成！咦，和左边的长得不太一样……对比一下——");
    }
    const summary = await llm3Promise;
    state.aiRestored = true;
    setAvatar(identical ? "🥳" : "🤔", identical ? "happy" : "thinking");
    if (summary) {
      appendSpeechLine(summary);
      speak(summary);
    }
    if (identical) {
      showModal(
        "🧩",
        "完全恢复！",
        `我只凭三视图的形状就把你的图形拼回来了——${realCount} 个方块，一个不差！\n\n${summary || "正视图管每列最高，左视图管每行最高，每格取较小值——这就是我的推理秘诀！"}`,
        "太厉害了！",
        closeRestore,
      );
    } else {
      showModal(
        "🔍",
        "重大发现！",
        `我推理出了 ${inferCount} 个方块，你搭的其实是 ${realCount} 个——我们俩的图形不一样，但三视图一模一样！\n\n被挡住的高度差异，从正面、侧面、上面三个方向都看不出来。这就是三视图的极限：光看三视图，有时不能唯一确定一个立体图形！\n\n${summary || ""}`,
        "原来如此！",
        closeRestore,
      );
    }
  });
}

function closeRestore() {
  state.aiThinking = false;
  world.setLocked(false);
  $("aiSpeech").hidden = true;
  setAvatar("🤖", "idle");
}

initViews();

$("modeSwitch").addEventListener("click", (e) => {
  const btn = e.target.closest(".mode-btn");
  if (btn) setMode(btn.dataset.mode);
});
$("gardenSwitch").addEventListener("click", (e) => {
  const btn = e.target.closest(".garden-btn");
  if (btn) switchGarden(btn.dataset.garden);
});
$("viewFrontBtn").addEventListener("click", () => world.setView("front"));
$("viewSideBtn").addEventListener("click", () => world.setView("left"));
$("viewBackBtn").addEventListener("click", () => world.setView("back"));
$("viewResetBtn").addEventListener("click", () => world.setView("iso"));
$("prevShapeBtn").addEventListener("click", () => loadShape((state.shapeIndex + SHAPES.length - 1) % SHAPES.length));
$("nextShapeBtn").addEventListener("click", () => {
  state.stats.learned++;
  updateStats();
  loadShape((state.shapeIndex + 1) % SHAPES.length);
});
$("learnPlaceBtn").addEventListener("click", () => {
  const btn = $("learnPlaceBtn");
  setBuildTool("place", btn);
  addOneCubeSmart();
  btn.textContent = "已添加 1 块";
  window.setTimeout(() => { btn.textContent = "＋ 搭积木"; }, 900);
});
$("learnRemoveBtn").addEventListener("click", () => {
  setBuildTool("remove", $("learnRemoveBtn"));
  showHint("已切换到拿掉模式。现在点击画布上的方块，就会把这一列从这里往上的积木拿掉。");
});
$("learnClearBtn").addEventListener("click", clearCurrentBuild);
$("submitBtn").addEventListener("click", submitChallenge);
$("answerInput").addEventListener("keydown", (e) => { if (e.key === "Enter") submitChallenge(); });
$("nextLevelBtn").addEventListener("click", () => {
  state.challengeLevel++;
  startChallenge();
});
$("toolPlace").addEventListener("click", () => setBuildTool("place", $("toolPlace")));
$("toolRemove").addEventListener("click", () => setBuildTool("remove", $("toolRemove")));
$("toolClear").addEventListener("click", clearCurrentBuild);
$("aiGuessBtn").addEventListener("click", aiGuess);
$("aiRestoreBtn").addEventListener("click", aiRestore);
$("voiceToggle").addEventListener("click", () => {
  state.voiceOn = !state.voiceOn;
  const btn = $("voiceToggle");
  btn.textContent = state.voiceOn ? "🔊" : "🔇";
  btn.classList.toggle("off", !state.voiceOn);
  if (!state.voiceOn && "speechSynthesis" in window) window.speechSynthesis.cancel();
  if (state.voiceOn) speak("语音打开啦！");
});

setMode("learn");
switchGarden("spatial");
