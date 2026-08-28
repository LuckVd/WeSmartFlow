/**
 * generator.js — 立体结构出题引擎（纯逻辑，无渲染依赖）
 *
 * 这是整个"数立方体"功能的确定性数学内核：
 * - 随机生成物理合法的立体结构（每个方块下方必须有支撑）
 * - 精确计算方块总数（答案）
 * - 计算三视图投影（俯视 / 正视 / 左视），用于辅助视角与引导
 *
 * 注意：这里的"随机"由系统可控，答案是确定且精确的——这正是
 * 数立方体场景不能依赖文生图接口、而必须用确定性引擎的原因。
 */

// 把坐标编码成字符串 key，便于集合去重
const key = (x, y, z) => `${x},${y},${z}`;

// 随机整数 [min, max]
const randInt = (min, max) => Math.floor(Math.random() * (max - min + 1)) + min;

// Fisher–Yates 洗牌
function shuffle(arr) {
  for (let i = arr.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [arr[i], arr[j]] = [arr[j], arr[i]];
  }
  return arr;
}

const pick = (arr) => arr[Math.floor(Math.random() * arr.length)];

// 各难度档参数（层数、底面尺寸、方块总数范围）
const LEVEL_CFG = [
  null,
  { layers: 1, w: 3, d: 3, lo: 3, hi: 6 },
  { layers: 2, w: 3, d: 3, lo: 5, hi: 9 },
  { layers: 2, w: 4, d: 4, lo: 8, hi: 13 },
  { layers: 3, w: 4, d: 4, lo: 11, hi: 17 },
  { layers: 3, w: 5, d: 4, lo: 15, hi: 23 },
];

/**
 * 生成第 level 关的立体结构
 * @param {number} level 关卡号（1 起），超过 5 按第 5 档处理
 * @returns {{cells: string[], answer: number, layers: number, w: number, d: number}}
 *          cells 为 key 数组，answer 为精确方块总数
 */
function generateLevel(level) {
  const lv = Math.max(1, Math.min(level, LEVEL_CFG.length - 1));
  const cfg = LEVEL_CFG[lv];
  const cells = new Set();

  const add = (x, y, z) => cells.add(key(x, y, z));
  const has = (x, y, z) => cells.has(key(x, y, z));

  // 1) 铺底层（y = 0），保证结构有"根"
  const base = [];
  for (let x = 0; x < cfg.w; x++) {
    for (let z = 0; z < cfg.d; z++) base.push([x, 0, z]);
  }
  shuffle(base);
  const baseCount = randInt(
    Math.max(2, cfg.lo - 3),
    Math.min(cfg.w * cfg.d, Math.max(3, cfg.hi - 4)),
  );
  for (let i = 0; i < baseCount; i++) add(...base[i]);

  // 2) 向上生长到目标数量（只允许在已有方块正上方加，保证物理合法）
  const target = randInt(cfg.lo, cfg.hi);
  let guard = 0;
  while (cells.size < target && guard++ < 500) {
    const candidates = [];
    for (const k of cells) {
      const [x, y, z] = k.split(",").map(Number);
      if (y + 1 < cfg.layers && !has(x, y + 1, z)) candidates.push([x, y, z]);
    }
    if (candidates.length === 0) break;
    const [x, y, z] = pick(candidates);
    add(x, y + 1, z);
  }

  // 3) 压平为“无歧义结构”：每格高度 = min(正视图列高, 左视图行高)。
  //    这样只凭无数字三视图就能唯一确定结构——学生靠推理（而非看数字）算出总数，
  //    与创造模式 AI 演示的推理方法完全一致，形成教学闭环。
  const pts = parse([...cells]);
  const frontH = Array(cfg.w).fill(0);
  const sideH = Array(cfg.d).fill(0);
  for (const p of pts) {
    frontH[p.x] = Math.max(frontH[p.x], p.y + 1);
    sideH[p.z] = Math.max(sideH[p.z], p.y + 1);
  }
  const flat = new Set();
  const marks = new Set(pts.map((p) => `${p.x},${p.z}`));
  for (const mk of marks) {
    const [x, z] = mk.split(",").map(Number);
    const h = Math.min(frontH[x], sideH[z]);
    for (let y = 0; y < h; y++) flat.add(key(x, y, z));
  }

  return {
    cells: [...flat],
    answer: flat.size,
    layers: cfg.layers,
    w: cfg.w,
    d: cfg.d,
  };
}

/** 解析 cells 数组为 {x,y,z} 对象数组 */
const parse = (cells) =>
  cells.map((k) => {
    const [x, y, z] = k.split(",").map(Number);
    return { x, y, z };
  });

/** 俯视图：返回 w×d 网格，值 = 该列的高度（0 表示空） */
function projectTop(cells, w, d) {
  const pts = parse(cells);
  const grid = Array.from({ length: d }, () => Array(w).fill(0));
  for (const p of pts) grid[p.z][p.x] = Math.max(grid[p.z][p.x], p.y + 1);
  return grid;
}

/** 正视（前视图）：返回 w×layers 网格，值 = 该位置是否有方块（1/0） */
function projectFront(cells, w, layers) {
  const pts = parse(cells);
  const grid = Array.from({ length: layers }, () => Array(w).fill(0));
  for (const p of pts) grid[p.y][p.x] = 1;
  return grid;
}

/** 左视图：返回 d×layers 网格 */
function projectSide(cells, d, layers) {
  const pts = parse(cells);
  const grid = Array.from({ length: layers }, () => Array(d).fill(0));
  for (const p of pts) grid[p.y][p.z] = 1;
  return grid;
}

/** 按层统计数量，用于"逐层讲解" */
function countByLayer(cells, layers) {
  const pts = parse(cells);
  const counts = Array(layers).fill(0);
  for (const p of pts) counts[p.y]++;
  return counts;
}

/** 搭建模式：检查某方块是否有支撑（底层或下方有方块） */
function isSupported(cells, x, y, z) {
  if (y === 0) return true;
  return cells.includes(key(x, y - 1, z));
}

/** 搭建模式：移除某方块及其上方所有方块，保持无悬浮 */
function removeStack(cells, x, y, z) {
  const result = new Set(cells);
  const maxY = Math.max(...parse(cells).map((p) => p.y), 0);
  for (let yy = y; yy <= maxY; yy++) result.delete(key(x, yy, z));
  return [...result];
}
