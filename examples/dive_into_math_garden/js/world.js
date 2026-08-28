/**
 * world.js — 轻量 Canvas 等距立方体世界（无外网依赖）
 *
 * - 支持鼠标拖拽绕竖直轴旋转观察，让孩子看到同一个立体图形从不同方向看会变成不同视图
 * - 支持锁定正视、左视、背面、立体观察方向
 * - 支持点击格子搭建/点击方块叠高或移除
 * - 只在交互和数据变化时重绘，保证低性能设备也流畅
 */

const COLOR_DEFAULT = "#2f6fe4";
const COLOR_HIGHLIGHT = "#ff8a3d";
const COLOR_EDGE = "#33415a";
const COLOR_GRID = "rgba(150, 166, 196, 0.26)";
const COLOR_GROUND = "rgba(255, 255, 255, 0.12)";

// 乐高经典色板（避开高亮橙）：每块按 key hash 稳定分配一种
const LEGO_PALETTE = ["#0055BF", "#C91A09", "#F2CD37", "#237841", "#E91E63", "#7E3F98"];
function legoColorForKey(key) {
  let h = 0;
  for (let i = 0; i < key.length; i++) h = (h * 31 + key.charCodeAt(i)) | 0;
  return LEGO_PALETTE[Math.abs(h) % LEGO_PALETTE.length];
}

function shade(hex, amount) {
  const n = Number.parseInt(hex.slice(1), 16);
  const r = Math.max(0, Math.min(255, (n >> 16) + amount));
  const g = Math.max(0, Math.min(255, ((n >> 8) & 255) + amount));
  const b = Math.max(0, Math.min(255, (n & 255) + amount));
  return `rgb(${r}, ${g}, ${b})`;
}

function parseCell(k) {
  const [x, y, z] = k.split(",").map(Number);
  return { key: k, x, y, z };
}

function pointInPolygon(point, polygon) {
  let inside = false;
  for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i++) {
    const xi = polygon[i].x;
    const yi = polygon[i].y;
    const xj = polygon[j].x;
    const yj = polygon[j].y;
    const intersect = ((yi > point.y) !== (yj > point.y))
      && (point.x < ((xj - xi) * (point.y - yi)) / (yj - yi || 1e-6) + xi);
    if (intersect) inside = !inside;
  }
  return inside;
}

function normalizeAngle(angle) {
  const two = Math.PI * 2;
  return ((angle % two) + two) % two;
}

class World {
  constructor(host) {
    this.host = host;
    this.canvas = document.createElement("canvas");
    this.canvas.className = "world-canvas";
    this.canvas.style.width = "100%";
    this.canvas.style.height = "100%";
    this.canvas.style.display = "block";
    this.canvas.style.touchAction = "none";
    host.appendChild(this.canvas);

    this.ctx = this.canvas.getContext("2d");
    this._cells = [];
    this._highlight = new Set();
    this._pickHandler = null;
    this._viewChangeHandler = null;
    this._locked = false;
    this._gridW = 5;
    this._gridD = 5;
    this._maxLayers = 5;
    this._tileW = 72;
    this._tileH = 38;
    this._cubeH = 42;
    this._originX = 0;
    this._originY = 0;
    this._angle = -Math.PI / 4;
    this._pitch = 0.86;
    this._hitItems = [];
    this._groundHits = [];
    this._raf = null;
    this._downPos = null;
    this._dragging = false;
    this._lastPointer = null;

    host.addEventListener("pointerdown", (e) => this._onPointerDown(e));
    host.addEventListener("pointermove", (e) => this._onPointerMove(e));
    host.addEventListener("pointerup", (e) => this._onPointerUp(e));
    host.addEventListener("pointercancel", () => this._stopDrag());
    host.addEventListener("pointerleave", () => this._stopDrag());

    this._resizeObserver = new ResizeObserver(() => this._resize());
    this._resizeObserver.observe(host);
    this._resize();
  }

  setGrid(w, d, maxLayers) {
    this._gridW = w;
    this._gridD = d;
    this._maxLayers = maxLayers;
    this._scheduleRender();
  }

  setPickHandler(fn) {
    this._pickHandler = fn;
  }

  setViewChangeHandler(fn) {
    this._viewChangeHandler = fn;
    this._notifyViewChange();
  }

  render(cells) {
    this._cells = cells || [];
    this._scheduleRender();
  }

  setHighlight(keys) {
    this._highlight = new Set(keys || []);
    this._scheduleRender();
  }

  setLocked(locked) {
    this._locked = !!locked;
    this.host.style.cursor = this._locked ? "default" : "grab";
  }

  setView(name) {
    const map = {
      front: 0,
      side: Math.PI / 2,
      left: -Math.PI / 2,
      back: Math.PI,
      iso: -Math.PI / 4,
    };
    this._angle = map[name] ?? this._angle;
    this._notifyViewChange();
    this._scheduleRender();
  }

  getViewDirection() {
    const a = normalizeAngle(this._angle);
    if (a < Math.PI / 4 || a >= Math.PI * 7 / 4) return "front";
    if (a < Math.PI * 3 / 4) return "side";
    if (a < Math.PI * 5 / 4) return "back";
    return "left";
  }

  getViewAngle() {
    return this._angle;
  }

  focusStructure() {
    this._scheduleRender();
  }

  focusGrid() {
    this._scheduleRender();
  }

  dispose() {
    if (this._raf) cancelAnimationFrame(this._raf);
    this._resizeObserver.disconnect();
    this.canvas.remove();
  }

  _onPointerDown(e) {
    this._downPos = { x: e.clientX, y: e.clientY };
    this._lastPointer = { x: e.clientX, y: e.clientY };
    this._dragging = false;
    this.host.setPointerCapture?.(e.pointerId);
  }

  _onPointerMove(e) {
    if (!this._lastPointer || this._locked) return;
    const dx = e.clientX - this._lastPointer.x;
    if (Math.abs(e.clientX - this._downPos.x) > 4 || Math.abs(e.clientY - this._downPos.y) > 4) {
      this._dragging = true;
    }
    if (this._dragging) {
      this._angle += dx * 0.012;
      this._notifyViewChange();
      this._scheduleRender();
    }
    this._lastPointer = { x: e.clientX, y: e.clientY };
  }

  _onPointerUp(e) {
    if (!this._downPos) return;
    const dx = e.clientX - this._downPos.x;
    const dy = e.clientY - this._downPos.y;
    const shouldPick = Math.abs(dx) < 8 && Math.abs(dy) < 8;
    this._stopDrag();
    if (shouldPick && this._pickHandler) this._doPick(e);
  }

  _stopDrag() {
    this._downPos = null;
    this._lastPointer = null;
    this._dragging = false;
  }

  _notifyViewChange() {
    if (this._viewChangeHandler) {
      this._viewChangeHandler({ direction: this.getViewDirection(), angle: this.getViewAngle() });
    }
  }

  _resize() {
    const rect = this.host.getBoundingClientRect();
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    // clamp 到 4096：防止布局循环把宿主高度指数放大（canvas 100% 引用被自己撑起的宿主时会发生）
    const w = Math.min(Math.max(1, Math.floor(rect.width)), 4096);
    const h = Math.min(Math.max(1, Math.floor(rect.height)), 4096);
    this.canvas.width = Math.floor(w * dpr);
    this.canvas.height = Math.floor(h * dpr);
    this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    this._scheduleRender();
  }

  _scheduleRender() {
    if (this._raf) return;
    this._raf = requestAnimationFrame(() => {
      this._raf = null;
      this._redraw();
    });
  }

  _measure() {
    const w = this.host.clientWidth || 800;
    const h = this.host.clientHeight || 480;
    const gridSpan = Math.max(this._gridW + this._gridD, 6);
    this._tileW = Math.max(42, Math.min(86, (w * 1.24) / gridSpan));
    this._tileH = this._tileW * 0.5 * this._pitch;
    this._cubeH = this._tileW * 0.54;

    const bounds = this._sceneBoundsAt(0, 0);
    const sceneCenterX = (bounds.minX + bounds.maxX) / 2;
    const sceneCenterY = (bounds.minY + bounds.maxY) / 2;
    this._originX = w / 2 - sceneCenterX;
    this._originY = h / 2 - sceneCenterY;
  }

  _projectAt(x, y, z, originX, originY) {
    const cx = this._gridW / 2;
    const cz = this._gridD / 2;
    const rx = x - cx;
    const rz = z - cz;
    const cos = Math.cos(this._angle);
    const sin = Math.sin(this._angle);
    const vx = rx * cos - rz * sin;
    const vz = rx * sin + rz * cos;
    return {
      x: originX + vx * this._tileW,
      y: originY + vz * this._tileH - y * this._cubeH,
      depth: vz + y * 0.08,
    };
  }

  _sceneBoundsAt(originX, originY) {
    const points = [];
    const addCellFootprint = (x, y, z, includeBottom = false) => {
      const corners = this._cellCornersAt(x, y, z, originX, originY);
      points.push(...corners.top, ...corners.bottom);
      if (includeBottom) points.push(...corners.top.map((pt) => ({ x: pt.x, y: pt.y + this._cubeH })));
    };

    for (let x = 0; x < this._gridW; x++) {
      for (let z = 0; z < this._gridD; z++) {
        addCellFootprint(x, 0, z);
      }
    }

    for (const cell of this._cells.map(parseCell)) {
      addCellFootprint(cell.x, cell.y, cell.z, true);
    }

    if (!points.length) return { minX: 0, maxX: 0, minY: 0, maxY: 0 };
    return {
      minX: Math.min(...points.map((p) => p.x)),
      maxX: Math.max(...points.map((p) => p.x)),
      minY: Math.min(...points.map((p) => p.y)),
      maxY: Math.max(...points.map((p) => p.y)),
    };
  }

  _project(x, y, z) {
    return this._projectAt(x, y, z, this._originX, this._originY);
  }

  _cellCornersAt(x, y, z, originX, originY) {
    const bottom = [
      this._projectAt(x, y, z, originX, originY),
      this._projectAt(x + 1, y, z, originX, originY),
      this._projectAt(x + 1, y, z + 1, originX, originY),
      this._projectAt(x, y, z + 1, originX, originY),
    ];
    const top = [
      this._projectAt(x, y + 1, z, originX, originY),
      this._projectAt(x + 1, y + 1, z, originX, originY),
      this._projectAt(x + 1, y + 1, z + 1, originX, originY),
      this._projectAt(x, y + 1, z + 1, originX, originY),
    ];
    return { bottom, top };
  }

  _cellCorners(x, y, z) {
    return this._cellCornersAt(x, y, z, this._originX, this._originY);
  }

  _cellTopCenter(x, y, z) {
    return this._project(x + 0.5, y + 1, z + 0.5);
  }

  _diamond(cx, cy) {
    return [
      { x: cx, y: cy - this._tileH / 2 },
      { x: cx + this._tileW / 2, y: cy },
      { x: cx, y: cy + this._tileH / 2 },
      { x: cx - this._tileW / 2, y: cy },
    ];
  }

  _path(points) {
    const ctx = this.ctx;
    ctx.beginPath();
    ctx.moveTo(points[0].x, points[0].y);
    for (let i = 1; i < points.length; i++) ctx.lineTo(points[i].x, points[i].y);
    ctx.closePath();
  }

  _fillPoly(points, fill, stroke = COLOR_EDGE) {
    const ctx = this.ctx;
    this._path(points);
    ctx.fillStyle = fill;
    ctx.fill();
    ctx.strokeStyle = stroke;
    ctx.lineWidth = 1;
    ctx.stroke();
  }

  _faceVisible(points, normal) {
    if (normal === "y+") return true;

    const cos = Math.cos(this._angle);
    const sin = Math.sin(this._angle);
    const normalMap = {
      "x-": { x: -1, z: 0 },
      "x+": { x: 1, z: 0 },
      "z-": { x: 0, z: -1 },
      "z+": { x: 0, z: 1 },
    };
    const n = normalMap[normal];
    if (!n) return false;

    const rotatedNormalDepth = n.x * sin + n.z * cos;
    return rotatedNormalDepth > 1e-6;
  }

  _faceDepth(points) {
    return points.reduce((sum, p) => sum + (p.depth || 0), 0) / points.length;
  }

  _faceAverageY(points) {
    return points.reduce((sum, p) => sum + p.y, 0) / points.length;
  }

  _cellKey(x, y, z) {
    return `${x},${y},${z}`;
  }

  _isExposedFace(cell, normal, occupied) {
    if (normal === "y+") return !occupied.has(this._cellKey(cell.x, cell.y + 1, cell.z));
    if (normal === "x-") return !occupied.has(this._cellKey(cell.x - 1, cell.y, cell.z));
    if (normal === "x+") return !occupied.has(this._cellKey(cell.x + 1, cell.y, cell.z));
    if (normal === "z-") return !occupied.has(this._cellKey(cell.x, cell.y, cell.z - 1));
    if (normal === "z+") return !occupied.has(this._cellKey(cell.x, cell.y, cell.z + 1));
    return true;
  }

  _cubeFaces(cell, occupied) {
    const corners = this._cellCorners(cell.x, cell.y, cell.z);
    const top = corners.top;
    const bottom = corners.bottom;
    const base = this._highlight.has(cell.key) ? COLOR_HIGHLIGHT : legoColorForKey(cell.key);
    const candidates = [
      { points: [bottom[0], bottom[3], top[3], top[0]], fill: shade(base, -28), normal: "x-", base },
      { points: [bottom[1], bottom[2], top[2], top[1]], fill: shade(base, -12), normal: "x+", base },
      { points: [bottom[0], bottom[1], top[1], top[0]], fill: shade(base, -22), normal: "z-", base },
      { points: [bottom[3], bottom[2], top[2], top[3]], fill: shade(base, -8), normal: "z+", base },
      { points: top, fill: shade(base, 18), normal: "y+", base },
    ];

    return candidates
      .filter((face) => this._isExposedFace(cell, face.normal, occupied))
      .filter((face) => this._faceVisible(face.points, face.normal))
      .map((face) => ({
        ...face,
        cell,
        depth: this._faceDepth(face.points),
        screenY: this._faceAverageY(face.points),
      }));
  }

  _convexHull(points) {
    const unique = [];
    const seen = new Set();
    for (const p of points) {
      const k = `${Math.round(p.x * 100)},${Math.round(p.y * 100)}`;
      if (!seen.has(k)) {
        seen.add(k);
        unique.push(p);
      }
    }
    if (unique.length <= 3) return unique;
    const center = {
      x: unique.reduce((sum, p) => sum + p.x, 0) / unique.length,
      y: unique.reduce((sum, p) => sum + p.y, 0) / unique.length,
    };
    return unique.sort((a, b) => Math.atan2(a.y - center.y, a.x - center.x) - Math.atan2(b.y - center.y, b.x - center.x));
  }

  _drawGround() {
    this._groundHits = [];
    for (let x = 0; x < this._gridW; x++) {
      for (let z = 0; z < this._gridD; z++) {
        const corners = this._cellCorners(x, -1, z);
        const poly = corners.top;
        const center = this._project(x + 0.5, 0, z + 0.5);
        this._groundHits.push({ type: "ground", x, z, polygon: poly, depth: center.depth });
      }
    }
    this._groundHits.sort((a, b) => a.depth - b.depth);

    const ctx = this.ctx;
    ctx.save();
    ctx.strokeStyle = COLOR_GRID;
    ctx.lineWidth = 1;
    ctx.setLineDash([3, 5]);
    for (const item of this._groundHits) {
      this._path(item.polygon);
      ctx.stroke();
    }
    ctx.restore();
  }

  _drawAxes() {
    const ctx = this.ctx;
    const origin = this._project(0, 0, 0);
    const pad = 1.2;
    const axes = [
      { end: this._project(this._gridW + pad, 0, 0), color: "#e5534b", label: "x" },
      { end: this._project(0, this._maxLayers + pad, 0), color: "#21a66a", label: "y" },
      { end: this._project(0, 0, this._gridD + pad), color: "#4f7cff", label: "z" },
    ];

    ctx.save();
    ctx.lineWidth = 3.5;
    ctx.lineCap = "round";
    ctx.font = "800 16px -apple-system, PingFang SC, sans-serif";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";

    for (const axis of axes) {
      const dx = axis.end.x - origin.x;
      const dy = axis.end.y - origin.y;
      const mag = Math.hypot(dx, dy) || 1;
      const ux = dx / mag;
      const uy = dy / mag;

      ctx.strokeStyle = axis.color;
      ctx.fillStyle = axis.color;
      ctx.beginPath();
      ctx.moveTo(origin.x, origin.y);
      ctx.lineTo(axis.end.x, axis.end.y);
      ctx.stroke();

      const head = 10;
      const ang = Math.atan2(dy, dx);
      ctx.beginPath();
      ctx.moveTo(axis.end.x, axis.end.y);
      ctx.lineTo(axis.end.x - head * Math.cos(ang - Math.PI / 6), axis.end.y - head * Math.sin(ang - Math.PI / 6));
      ctx.lineTo(axis.end.x - head * Math.cos(ang + Math.PI / 6), axis.end.y - head * Math.sin(ang + Math.PI / 6));
      ctx.closePath();
      ctx.fill();

      ctx.fillText(axis.label, axis.end.x + ux * 16, axis.end.y + uy * 16);
    }
    ctx.restore();
  }

  _drawCube(cell) {
    const corners = this._cellCorners(cell.x, cell.y, cell.z);
    const top = corners.top;
    const bottom = corners.bottom;
    const base = this._highlight.has(cell.key) ? COLOR_HIGHLIGHT : COLOR_DEFAULT;
    const edgeColor = COLOR_EDGE;
    const faces = [
      { points: [bottom[0], bottom[3], top[3], top[0]], fill: shade(base, -28), normal: "x-" },
      { points: [bottom[1], bottom[2], top[2], top[1]], fill: shade(base, -12), normal: "x+" },
      { points: [bottom[0], bottom[1], top[1], top[0]], fill: shade(base, -22), normal: "z-" },
      { points: [bottom[3], bottom[2], top[2], top[3]], fill: shade(base, -8), normal: "z+" },
      { points: top, fill: shade(base, 18), normal: "y+" },
    ];

    const visibleFaces = faces
      .filter((face) => this._faceVisible(face.points, face.normal))
      .sort((a, b) => this._faceDepth(a.points) - this._faceDepth(b.points));
    for (const face of visibleFaces) this._fillPoly(face.points, face.fill, edgeColor);

    const hitPoly = visibleFaces.length ? visibleFaces.flatMap((face) => face.points) : top;
    this._hitItems.push({
      type: "cube",
      x: cell.x,
      y: cell.y,
      z: cell.z,
      polygon: this._convexHull(hitPoly),
      depth: this._project(cell.x + 0.5, cell.y + 0.5, cell.z + 0.5).depth,
    });
  }

  /** 在顶面画乐高式圆形凸点（stud），中心=菱形对角线交点 */
  _drawStud(face) {
    const pts = face.points;
    const cx = (pts[0].x + pts[2].x) / 2;
    const cy = (pts[0].y + pts[2].y) / 2;
    // 固定尺寸：只跟方块视觉宽度 tileW 挂钩，不随视角压扁程度变化
    const rx = Math.max(this._tileW * 0.15, 5);
    const ry = Math.max(rx * 0.58, 3);
    const ctx = this.ctx;
    ctx.save();
    ctx.beginPath();
    ctx.ellipse(cx, cy, rx, ry, 0, 0, Math.PI * 2);
    ctx.fillStyle = shade(face.base, -14);
    ctx.fill();
    ctx.strokeStyle = COLOR_EDGE;
    ctx.lineWidth = 1;
    ctx.stroke();
    ctx.restore();
  }

  _drawStructure(cells) {
    const occupied = new Set(cells.map((cell) => cell.key));
    const faces = cells.flatMap((cell) => this._cubeFaces(cell, occupied));

    // 把 studs 跟 faces 一起参与统一深度排序，否则 stud 不会和面之间形成正确遮挡
    const items = [];
    for (const face of faces) {
      items.push({ kind: "face", depth: face.depth, screenY: face.screenY, face });
      if (face.normal === "y+") {
        items.push({ kind: "stud", depth: face.depth, screenY: face.screenY, face });
      }
    }
    items.sort((a, b) => a.depth - b.depth || a.screenY - b.screenY);

    for (const item of items) {
      if (item.kind === "face") this._fillPoly(item.face.points, item.face.fill, COLOR_EDGE);
      else this._drawStud(item.face);
    }

    for (const cell of cells) {
      const cellFaces = faces.filter((face) => face.cell.key === cell.key);
      const hitPoints = cellFaces.length ? cellFaces.flatMap((face) => face.points) : this._cellCorners(cell.x, cell.y, cell.z).top;
      this._hitItems.push({
        type: "cube",
        x: cell.x,
        y: cell.y,
        z: cell.z,
        polygon: this._convexHull(hitPoints),
        depth: this._project(cell.x + 0.5, cell.y + 0.5, cell.z + 0.5).depth,
      });
    }
  }



  _redraw() {
    const ctx = this.ctx;
    const w = this.host.clientWidth || 1;
    const h = this.host.clientHeight || 1;
    this._measure();
    ctx.clearRect(0, 0, w, h);

    const gradient = ctx.createLinearGradient(0, 0, 0, h);
    gradient.addColorStop(0, "#fbfcff");
    gradient.addColorStop(1, "#f4f7fc");
    ctx.fillStyle = gradient;
    ctx.fillRect(0, 0, w, h);

    this._hitItems = [];
    this._drawGround();
    this._drawAxes();

    const cells = this._cells
      .map(parseCell)
      .map((cell) => ({ ...cell, depth: this._project(cell.x + 0.5, cell.y, cell.z + 0.5).depth }))
      .sort((a, b) => a.depth - b.depth || a.y - b.y);
    this._drawStructure(cells);

    ctx.save();
    ctx.fillStyle = "rgba(31, 36, 48, 0.58)";
    ctx.font = "600 13px -apple-system, PingFang SC, sans-serif";
    ctx.textAlign = "center";
    const viewName = { front: "正前方", side: "右侧", back: "背面", left: "左侧" }[this.getViewDirection()];
    if (this.showViewHint !== false) {
      ctx.fillText(`拖动画布绕竖直轴转动 · 当前观察方向：${viewName}`, w / 2, h - 18);
    }
    if (!cells.length) {
      ctx.font = "600 16px -apple-system, PingFang SC, sans-serif";
      ctx.fillText(this.emptyText || "从网格开始搭一个立体图形吧", w / 2, h * 0.36);
    }
    ctx.restore();
  }

  _doPick(e) {
    const rect = this.canvas.getBoundingClientRect();
    const point = { x: e.clientX - rect.left, y: e.clientY - rect.top };

    const cubeHits = [...this._hitItems].sort((a, b) => b.depth - a.depth);
    for (const item of cubeHits) {
      if (pointInPolygon(point, item.polygon)) {
        this._pickHandler({ type: "cube", x: item.x, y: item.y, z: item.z });
        return;
      }
    }

    const groundHits = [...this._groundHits].sort((a, b) => b.depth - a.depth);
    for (const item of groundHits) {
      if (pointInPolygon(point, item.polygon)) {
        this._pickHandler({ type: "ground", x: item.x, z: item.z });
        return;
      }
    }
  }
}
