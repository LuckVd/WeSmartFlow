/**
 * mathcannon.js — 算式炮弹（走进数学花园 · 代数能力培养）
 *
 * 核心玩法：逐层三选一运算挑战
 * - 玩家维护一个当前手牌数值，最大值挑战和目标值挑战都从 0 开始
 * - 屏幕上有 3 座塔，每座塔由运算牌堆叠（+ / − / × / ÷ + 数学表达式）
 * - 每回合只能在当前三座塔的最底层牌中选一张生效，随后三座塔的最底层牌同时碎掉
 * - 最大值挑战：完成所有层后，最终数值越接近本局理论最大值越高分
 * - 目标值挑战：系统给出一个可由某种逐层选择得到的目标，最终越接近越高分
 * - 难度组 4 档：小学四则+分数 / 初中根号+三角 / 高中 π/e/log/三角 / 大学极限+级数+积分
 *
 * 关键设计：
 * - 数值默认隐藏：玩家必须思考/计算才能比较大小
 * - 玩家点击任意格子（含自己手牌）→ 浮显该格子的当前数值（保留 3 位小数）
 *   每点一次都计入查询次数
 * - 理论最大值在出题时通过穷举所有逐层三选一路径提前算好，保证结果准确
 */

const mcRnd = (min, max) => Math.floor(Math.random() * (max - min + 1)) + min;
const mcPick = (arr) => arr[Math.floor(Math.random() * arr.length)];
const mcGcd = (a, b) => b === 0 ? Math.abs(a) : mcGcd(b, a % b);
const mcShuffle = (arr) => {
  for (let i = arr.length - 1; i > 0; i--) {
    const j = mcRnd(0, i);
    [arr[i], arr[j]] = [arr[j], arr[i]];
  }
  return arr;
};
const mcRound = (n, d = 3) => {
  const m = Math.pow(10, d);
  return Math.round(n * m) / m;
};
const mcFmt = (n) => Number(mcRound(n, 3)).toFixed(3);

/** 分数生成：返回 {display, value} */
function mcFrac(num, den) {
  const g = mcGcd(num, den);
  const n = num / g, d = den / g;
  return {
    display: d === 1 ? String(n) : `${n}/${d}`,
    html: d === 1 ? String(n) : mcFracHtml(n, d),
    value: n / d,
  };
}

function mcFracHtml(num, den) {
  return `<span class="math-frac"><span>${num}</span><span>${den}</span></span>`;
}

function mcExpr(display, value, html = null) {
  return { display, html: html || display, value };
}

const MC_TRIG = {
  "sin30°": { value: 0.5, html: "sin30°" },
  "sin45°": { value: Math.SQRT2 / 2, html: "sin45°" },
  "sin60°": { value: Math.SQRT3 / 2, html: "sin60°" },
  "cos30°": { value: Math.SQRT3 / 2, html: "cos30°" },
  "cos45°": { value: Math.SQRT2 / 2, html: "cos45°" },
  "cos60°": { value: 0.5, html: "cos60°" },
  "tan30°": { value: Math.SQRT3 / 3, html: "tan30°" },
  "tan45°": { value: 1, html: "tan45°" },
  "tan60°": { value: Math.SQRT3, html: "tan60°" },
};

function mcRootTerm(n, coef = 1) {
  return {
    display: `${coef === 1 ? "" : coef}√${n}`,
    html: `${coef === 1 ? "" : coef}<span class="math-root">√<span>${n}</span></span>`,
    value: coef * Math.sqrt(n),
  };
}

function mcConstTerm(name, coef = 1) {
  const values = { π: Math.PI, e: Math.E };
  return {
    display: `${coef === 1 ? "" : coef}${name}`,
    html: `${coef === 1 ? "" : coef}<span class="math-const">${name}</span>`,
    value: coef * values[name],
  };
}

function mcPiPowerTerm(num, den = 1) {
  const exp = num / den;
  const display = den === 1 ? `π^${num}` : `π^(${num}/${den})`;
  const htmlExp = den === 1 ? String(num) : mcFracHtml(num, den);
  return {
    display,
    html: `<span class="math-const">π</span><sup>${htmlExp}</sup>`,
    value: Math.PI ** exp,
  };
}

function mcTrigTerm(name) {
  const t = MC_TRIG[name];
  return { display: name, html: t.html, value: t.value };
}

function mcCombineTerms(terms, sep = " + ") {
  return mcExpr(
    terms.map((t) => t.display).join(sep),
    mcRound(terms.reduce((sum, t) => sum + t.value, 0), 3),
    terms.map((t) => t.html).join(sep),
  );
}

// ── 多样化辅助：无理根号池 / 多根号抽取 / 项混合器 ──

// 非完全平方数池：值非整数，逼玩家估算（√2≈1.41 … √99≈9.95）
const MC_IRR_ROOTS = [
  2, 3, 5, 6, 7, 8, 10, 11, 12, 13, 14, 15, 17, 18, 19, 20, 21, 22, 23, 24,
  26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 37, 38, 39, 40, 41, 42, 43, 44, 45,
  46, 47, 48, 50, 51, 52, 53, 54, 55, 56, 57, 58, 59, 60, 61, 62, 63, 65, 66,
  67, 68, 69, 70, 71, 72, 73, 74, 75, 76, 77, 78, 79, 80, 82, 83, 84, 85, 86,
  87, 88, 89, 90, 91, 92, 93, 94, 95, 96, 97, 98, 99,
];
function mcIrrRoot(lo = 2, hi = 60) {
  const cands = MC_IRR_ROOTS.filter((n) => n >= lo && n <= hi);
  return mcPick(cands.length ? cands : [2, 3, 5, 6, 7]);
}

/** 抽 n 个不重复的无理根号项 */
function mcRootTerms(n, lo = 2, hi = 60) {
  const used = new Set();
  const terms = [];
  for (let i = 0; i < n; i++) {
    let r, guard = 0;
    do { r = mcIrrRoot(lo, hi); } while (used.has(r) && guard++ < 30);
    used.add(r);
    terms.push(mcRootTerm(r));
  }
  return terms;
}

/** 抽 n 个不重复的三角函数项 */
function mcTrigTerms(n) {
  const keys = Object.keys(MC_TRIG);
  return mcShuffle(keys).slice(0, n).map((k) => mcTrigTerm(k));
}

// ── 4 难度组配置 ──
const MATH_GROUPS = [
  { id: "primary", name: "小学组", desc: "整数 + 简单分数", level: 1,
    handDisplay: () => "🃏 起点",
    towerRange: [1, 60] },
  { id: "junior", name: "初中组", desc: "根号 + 立方根", level: 2,
    handDisplay: () => "🃏 起点",
    towerRange: [1, 42] },
  { id: "senior", name: "高中组", desc: "高次方根 + 对数 + 三角", level: 3,
    handDisplay: () => "🃏 起点",
    towerRange: [1, 24] },
  { id: "university", name: "大学组", desc: "极限 + 级数 + 积分", level: 4,
    handDisplay: () => "🃏 起点",
    towerRange: [0.2, 18] },
];

// ── 元素生成器（按组，函数返回 {display, value}）──
const ELEMENT_GENS = {
  primary: [
    () => { const n = mcRnd(2, 80); const a = mcRnd(1, 20); return mcExpr(`${n + a} − ${a}`, n); },
    () => { const n = mcRnd(80, 260); const a = mcRnd(12, 90); return mcExpr(`${n - a} + ${a}`, n); },
    () => { const den = mcRnd(97, 999); const whole = mcRnd(2, 55); const num = whole * den + mcRnd(1, den - 1); return mcExpr(`${num}/${den}`, num / den, mcFracHtml(num, den)); },
    () => { const den = mcRnd(101, 899); const whole = mcRnd(60, 180); const num = whole * den + mcRnd(1, den - 1); return mcExpr(`${num}/${den}`, num / den, mcFracHtml(num, den)); },
    () => { const n = mcRnd(1, 20), d = mcRnd(2, 20); return mcFrac(n, d); },
    () => { const a = mcRnd(2, 30), b = mcRnd(1, 15); return mcExpr(`${a} + ${b}`, a + b); },
    () => { let a, b; do { a = mcRnd(10, 60); b = mcRnd(2, a - 1); } while (a <= b); return mcExpr(`${a} − ${b}`, a - b); },
    () => { const a = mcRnd(2, 12), b = mcRnd(2, 8); return mcExpr(`${a} × ${b}`, a * b); },
    () => { const b = mcRnd(2, 8); const k = mcRnd(2, 12); return mcExpr(`${b * k} ÷ ${b}`, k); },
    // 三步加法
    () => { const a = mcRnd(2, 20), b = mcRnd(2, 20), c = mcRnd(2, 20); return mcExpr(`${a} + ${b} + ${c}`, a + b + c); },
    // 三步加减混合（保证正）
    () => { const a = mcRnd(20, 60), b = mcRnd(2, 15), c = mcRnd(2, 15); return mcExpr(`${a} + ${b} − ${c}`, a + b - c); },
    // 乘加混合
    () => { const a = mcRnd(2, 8), b = mcRnd(2, 6), c = mcRnd(1, 12); return mcExpr(`${a} × ${b} + ${c}`, a * b + c); },
    // 乘减混合（保证正）
    () => { const a = mcRnd(3, 9), b = mcRnd(3, 6), c = mcRnd(1, a * b - 1); return mcExpr(`${a} × ${b} − ${c}`, a * b - c); },
    // 带括号
    () => { const a = mcRnd(2, 5), b = mcRnd(2, 4), c = mcRnd(2, 6); return mcExpr(`(${a} + ${b}) × ${c}`, (a + b) * c); },
    // 除法 + 整数
    () => { const b = mcRnd(2, 9); const k = mcRnd(3, 10); const c = mcRnd(1, 8); return mcExpr(`${b * k} ÷ ${b} + ${c}`, k + c); },
    () => {
      const a = mcRnd(2, 8), b = mcRnd(2, 7), c = mcRnd(2, 9), d = mcRnd(3, 18);
      return mcExpr(`(${a} + ${b}) × ${c} − ${d}`, (a + b) * c - d);
    },
    () => {
      const a = mcRnd(40, 160), b = mcRnd(2, 9), k = mcRnd(3, 14), c = mcRnd(5, 30);
      return mcExpr(`${a} − ${b * k} ÷ ${b} + ${c}`, a - k + c);
    },
    () => {
      const den = mcRnd(23, 97);
      const n1 = mcRnd(den + 1, den * 5);
      const n2 = mcRnd(1, den - 1);
      return mcExpr(`${n1}/${den} + ${n2}/${den}`, (n1 + n2) / den, `${mcFracHtml(n1, den)} + ${mcFracHtml(n2, den)}`);
    },
    () => {
      const den = mcRnd(37, 149);
      const n = mcRnd(den * 2, den * 12);
      const add = mcRnd(2, 40);
      return mcExpr(`${n}/${den} + ${add}`, n / den + add, `${mcFracHtml(n, den)} + ${add}`);
    },
    () => {
      const a = mcRnd(2, 9), b = mcRnd(2, 9), c = mcRnd(2, 9), d = mcRnd(2, 9);
      return mcExpr(`${a} × ${b} + ${c} × ${d}`, a * b + c * d);
    },
  ],
  junior: [
    () => { const k = mcRnd(2, 8); return mcExpr(`√${k * k}`, k, `<span class="math-root">√<span>${k * k}</span></span>`); },
    () => { const k = mcRnd(2, 5); return mcExpr(`∛${k * k * k}`, k, `<span class="math-root">∛<span>${k * k * k}</span></span>`); },
    () => { const a = mcPick([2, 3, 5, 6, 7, 10, 11, 13, 14, 15]); const b = mcRnd(2, 4); return mcExpr(`${b}√${a}`, mcRound(b * Math.sqrt(a), 3), `${b}<span class="math-root">√<span>${a}</span></span>`); },
    () => { const a = mcRnd(1, 8); const b = mcRnd(1, 6); return mcExpr(`${a} + √${b * b}`, a + b, `${a} + <span class="math-root">√<span>${b * b}</span></span>`); },
    () => { const a = mcRnd(1, 4); const b = mcRnd(1, 3); return mcExpr(`${a} + ∛${b * b * b}`, a + b, `${a} + <span class="math-root">∛<span>${b * b * b}</span></span>`); },
    () => { const a = mcRnd(1, 6), b = mcRnd(1, 6); return mcExpr(`√${a * a} + √${b * b}`, a + b, `<span class="math-root">√<span>${a * a}</span></span> + <span class="math-root">√<span>${b * b}</span></span>`); },
    () => { const den = mcRnd(97, 999); const whole = mcRnd(2, 26); const num = whole * den + mcRnd(1, den - 1); return mcExpr(`${num}/${den}`, num / den, mcFracHtml(num, den)); },
    // 两个无理根号 + 三角（√31 + √21 + sin45° 短版）
    () => mcCombineTerms([...mcRootTerms(2, 14, 50), mcTrigTerm(mcPick(["sin45°", "cos60°", "tan30°", "sin30°", "cos45°"]))]),
    // 三个无理根号 + 三角（用户重点：√31 + √21 + √14 + sin45°）
    () => mcCombineTerms([...mcRootTerms(3, 11, 45), mcTrigTerm(mcPick(["sin45°", "cos30°", "tan30°", "sin60°"]))]),
    // 三个无理根号（√2 + √7 + √13）
    () => mcCombineTerms(mcRootTerms(3, 2, 40)),
    // 四个无理根号（超长：√5 + √11 + √17 + √23）
    () => mcCombineTerms(mcRootTerms(4, 2, 24)),
    // 整数 + 三个无理根号
    () => { const a = mcRnd(2, 8); return mcCombineTerms([mcExpr(String(a), a), ...mcRootTerms(3, 2, 30)]); },
    // 整数 + 两个无理根号
    () => { const a = mcRnd(2, 10); return mcCombineTerms([mcExpr(String(a), a), ...mcRootTerms(2, 2, 40)]); },
    // π + 无理根号
    () => mcCombineTerms([mcConstTerm("π"), mcRootTerm(mcIrrRoot(2, 40))]),
    // π + 整数
    () => { const a = mcRnd(1, 10); return mcCombineTerms([mcConstTerm("π"), mcExpr(String(a), a)]); },
    // 2π + 无理根号
    () => mcCombineTerms([mcConstTerm("π", 2), mcRootTerm(mcIrrRoot(2, 30))]),
    // 立方根 + 无理平方根混合
    () => { const k = mcRnd(2, 5); return mcCombineTerms([mcExpr(`∛${k ** 3}`, k, `<span class="math-root">∛<span>${k ** 3}</span></span>`), mcRootTerm(mcIrrRoot(2, 40))]); },
    // 两个带系数无理根号之和（2√3 + 3√5）
    () => { const a = mcIrrRoot(2, 15), b = mcIrrRoot(2, 15); return mcCombineTerms([mcRootTerm(a, mcRnd(2, 3)), mcRootTerm(b, mcRnd(2, 3))]); },
    // 无理根号 + 分数
    () => { const den = mcRnd(3, 20); const num = mcRnd(1, den - 1); return mcCombineTerms([mcRootTerm(mcIrrRoot(2, 30)), { display: `${num}/${den}`, html: mcFracHtml(num, den), value: num / den }]); },
    () => { const n = mcRnd(1, 12), d = mcRnd(2, 12); return mcFrac(n, d); },
  ],
  senior: [
    () => { const n = mcPick([3, 4, 5]); const k = mcRnd(2, 3); return mcExpr(`${["³", "⁴", "⁵"][n - 3]}√${k ** n}`, k, `<sup>${n}</sup><span class="math-root">√<span>${k ** n}</span></span>`); },
    () => { const a = mcPick([2, 3, 5, 10]); const k = mcRnd(2, 3); return mcExpr(`log_${a} ${a ** k}`, k, `log<sub>${a}</sub>${a ** k}`); },
    () => { const ang = mcPick([30, 45, 60]); const map = { 30: 0.5, 45: Math.SQRT2 / 2, 60: Math.SQRT3 / 2 }; return mcExpr(`sin${ang}°`, mcRound(map[ang], 3)); },
    () => { const ang = mcPick([30, 45, 60]); const map = { 30: Math.SQRT3 / 2, 45: Math.SQRT2 / 2, 60: 0.5 }; return mcExpr(`cos${ang}°`, mcRound(map[ang], 3)); },
    () => { const ang = mcPick([30, 45, 60]); const map = { 30: Math.SQRT3 / 3, 45: 1, 60: Math.SQRT3 }; return mcExpr(`tan${ang}°`, mcRound(map[ang], 3)); },
    () => { const den = mcRnd(211, 997); const whole = mcRnd(2, 14); const num = whole * den + mcRnd(1, den - 1); return mcExpr(`${num}/${den}`, num / den, mcFracHtml(num, den)); },
    () => mcCombineTerms([mcConstTerm("π"), mcConstTerm("e")]),
    () => {
      const trig = mcPick(["sin45°", "cos30°", "tan30°"]);
      return mcCombineTerms([mcConstTerm("π"), mcTrigTerm(trig), mcRootTerm(mcPick([2, 3, 5, 7]))]);
    },
    () => {
      const base = mcPick([2, 3, 5]);
      const k = mcRnd(2, 3);
      return mcCombineTerms([
        mcExpr(`log_${base} ${base ** k}`, k, `log<sub>${base}</sub>${base ** k}`),
        mcTrigTerm(mcPick(["sin60°", "cos45°", "tan30°"])),
        mcRootTerm(mcPick([11, 13, 17])),
      ]);
    },
    () => {
      const den = mcRnd(101, 401);
      const num = mcRnd(den * 2, den * 8);
      return mcCombineTerms([mcConstTerm("e"), { display: `${num}/${den}`, html: mcFracHtml(num, den), value: num / den }, mcTrigTerm("sin30°")]);
    },
    () => mcCombineTerms([mcPiPowerTerm(1, 2), mcConstTerm("e"), mcTrigTerm(mcPick(["sin45°", "cos30°"]))]),
    () => mcCombineTerms([mcPiPowerTerm(3, 2), mcRootTerm(mcIrrRoot(5, 31)), mcTrigTerm("sin30°")]),
    () => mcExpr(`π^(1/2) + π/e`, mcRound(Math.sqrt(Math.PI) + Math.PI / Math.E, 3), `<span class="math-const">π</span><sup>${mcFracHtml(1, 2)}</sup> + ${mcFracHtml(`<span class="math-const">π</span>`, `<span class="math-const">e</span>`)}`),
    () => {
      const roots = mcRootTerms(2, 10, 60);
      return mcCombineTerms([mcPiPowerTerm(1, 2), roots[0], roots[1], mcTrigTerm(mcPick(["tan30°", "cos45°"]))]);
    },
    () => mcCombineTerms([mcPiPowerTerm(2, 3), mcConstTerm("π"), mcTrigTerm(mcPick(["sin30°", "cos60°"]))]),
    () => { const a = mcRnd(2, 5); const b = mcRnd(1, 4); return mcExpr(`${a} + √${b * b}`, a + b, `${a} + <span class="math-root">√<span>${b * b}</span></span>`); },
    () => { const a = mcRnd(2, 4); return mcExpr(`${a}·sin30°`, a * 0.5); },
  ],
  university: [
    () => mcExpr(`lim x→∞ 1/x`, 0, `<span class="math-lim">lim<sub>x→∞</sub></span>${mcFracHtml(1, "x")}`),
    () => { const a = mcRnd(2, 4); return mcExpr(`lim x→∞ ${a}/x²`, 0, `<span class="math-lim">lim<sub>x→∞</sub></span>${mcFracHtml(a, "x²")}`); },
    () => { const a = mcRnd(1, 4); return mcExpr(`lim x→${a} (x²-${a*a})/(x-${a})`, 2 * a, `<span class="math-lim">lim<sub>x→${a}</sub></span>${mcFracHtml(`x²-${a*a}`, `x-${a}`)}`); },
    () => { const a = mcRnd(1, 3); const r = mcRound(0.1 + Math.random() * 0.6, 2); return mcExpr(`∑${a}·${r}ⁿ`, mcRound(a / (1 - r), 2), `<span class="math-sum">∑</span>${a}·${r}<sup>n</sup>`); },
    () => { const n = mcRnd(2, 4); return mcExpr(`∫₀¹ x${n === 2 ? "²" : (n === 3 ? "³" : "⁴")} dx`, mcRound(1 / n, 3), `∫<sub>0</sub><sup>1</sup> x<sup>${n}</sup> dx`); },
    () => { const a = mcRnd(2, 4); return mcExpr(`∫₀² ${a}x dx`, 2 * a, `∫<sub>0</sub><sup>2</sup> ${a}x dx`); },
    () => mcExpr(`lim n→∞ (1+1/n)ⁿ`, Math.E, `<span class="math-lim">lim<sub>n→∞</sub></span>(1+${mcFracHtml(1, "n")})<sup>n</sup>`),
    () => { const a = mcRnd(1, 3); return mcExpr(`lim n→∞ (1+${a}/n)ⁿ`, mcRound(Math.exp(a), 3), `<span class="math-lim">lim<sub>n→∞</sub></span>(1+${mcFracHtml(a, "n")})<sup>n</sup>`); },
    () => { const den = mcRnd(307, 997); const whole = mcRnd(1, 7); const num = whole * den + mcRnd(1, den - 1); return mcExpr(`${num}/${den}`, num / den, mcFracHtml(num, den)); },
    () => mcExpr(`π + e`, mcRound(Math.PI + Math.E, 3), `<span class="math-const">π</span> + <span class="math-const">e</span>`),
    () => mcExpr(`π²/e`, mcRound((Math.PI ** 2) / Math.E, 3), `${mcFracHtml(`<span class="math-const">π</span><sup>2</sup>`, `<span class="math-const">e</span>`)}`),
    () => mcExpr(`e/π + sin45°`, mcRound(Math.E / Math.PI + MC_TRIG["sin45°"].value, 3), `${mcFracHtml(`<span class="math-const">e</span>`, `<span class="math-const">π</span>`)} + sin45°`),
    () => {
      const a = mcRnd(2, 7);
      return mcExpr(`lim x→0 sin(${a}x)/x`, a, `<span class="math-lim">lim<sub>x→0</sub></span>${mcFracHtml(`sin(${a}x)`, "x")}`);
    },
    () => {
      const a = mcRnd(2, 6);
      return mcExpr(`lim x→0 (e^(${a}x)-1)/x`, a, `<span class="math-lim">lim<sub>x→0</sub></span>${mcFracHtml(`e<sup>${a}x</sup>-1`, "x")}`);
    },
    () => {
      const a = mcRnd(2, 5);
      return mcExpr(`lim x→0 ln(1+${a}x)/x`, a, `<span class="math-lim">lim<sub>x→0</sub></span>${mcFracHtml(`ln(1+${a}x)`, "x")}`);
    },
    () => {
      const n = mcRnd(2, 5), a = mcRnd(1, 3);
      return mcExpr(`lim h→0 ((${a}+h)^${n}-${a ** n})/h`, n * (a ** (n - 1)), `<span class="math-lim">lim<sub>h→0</sub></span>${mcFracHtml(`(${a}+h)<sup>${n}</sup>-${a ** n}`, "h")}`);
    },
    () => {
      const a = mcRnd(2, 5), b = mcRnd(0, 2);
      return mcExpr(`lim n→∞ ((n+${a})/(n+${b}))^n`, mcRound(Math.exp(a - b), 3), `<span class="math-lim">lim<sub>n→∞</sub></span>(${mcFracHtml(`n+${a}`, `n+${b}`)})<sup>n</sup>`);
    },
    () => {
      const a = mcRnd(2, 5);
      return mcExpr(`∫₀¹ ${a}/(1+x²) dx`, mcRound(a * Math.PI / 4, 3), `∫<sub>0</sub><sup>1</sup>${mcFracHtml(a, "1+x²")} dx`);
    },
    () => {
      const n = mcRnd(2, 4);
      return mcCombineTerms([
        mcExpr(`∫₀¹ x^${n} dx`, mcRound(1 / (n + 1), 3), `∫<sub>0</sub><sup>1</sup> x<sup>${n}</sup> dx`),
        mcConstTerm("π"),
        mcTrigTerm(mcPick(["sin30°", "cos60°"])),
      ]);
    },
    () => { const n = mcRnd(1, 8), d = mcRnd(2, 8); return mcFrac(n, d); },
  ],
};

// ── 游戏状态 ──
const MC = {
  challengeMode: "max",   // max | target
  boardDifficulty: "hard", // easy | medium | hard
  groupId: null,
  group: null,
  hand: null,             // {display, value}
  startHand: null,        // 起始牌，用于右侧明牌展示
  handId: "hand",         // 查询统计用的"格子 ID"
  tower: [[], [], []],    // 3 列堆叠（索引 0 = 最底）
  originalTower: [[], [], []], // 开局塔快照，用于历史题面与理论最优复现
  eaten: [],              // 已选择生效的牌，展示在右侧
  totalCells: 0,          // 本局总层数（每回合三座塔同时碎掉一层）
  peeked: new Set(),      // 查看过的不同格子 key（只做视觉标记）
  peekCount: 0,           // 点击查看次数（计分用，每次点击都算）
  lives: 3,
  optimum: null,
  target: null,
  bestGap: 0,
  bestPath: [],
  bestExpr: "",
  records: [],
  turns: 0,
  hits: 0,
  eats: 0,
  busy: false,
  running: false,
  won: false,
};

// ── DOM 引用 ──
let mcHand, mcTower, mcEatenList, mcHudScore, mcHudGroup, mcHudLives, mcHudEats, mcHudPeek, mcFinishBtn, mcRecords;
const MC_ELEMENT_POOL = new Map();
const MC_RECORD_KEY = "dive-into-math-garden:mathcannon-history:v3";
const MC_LEGACY_RECORD_KEYS = ["mathcannonHistoryV3", "mathcannonRecords"];

function mcRowsForDifficulty(diff = MC.boardDifficulty) {
  if (diff === "easy") return mcRnd(1, 2);
  if (diff === "medium") return mcRnd(3, 4);
  return 5;
}

// ── 元素生成 ──
function mcMakeElement(groupId) {
  const gens = ELEMENT_GENS[groupId];
  return mcPick(gens)();
}

function mcCloneElem(e) {
  return { display: e.display, html: e.html, value: e.value, op: e.op };
}

function mcCloneTower(tower) {
  return tower.map((col) => col.map((e) => mcCloneElem(e)));
}

function mcSnapshotPuzzle() {
  return {
    version: 3,
    groupId: MC.groupId,
    challengeMode: MC.challengeMode,
    boardDifficulty: MC.boardDifficulty,
    startHand: mcCloneElem(MC.startHand),
    tower: mcCloneTower(MC.originalTower?.length ? MC.originalTower : MC.tower),
    optimum: MC.optimum,
    target: MC.target,
    bestGap: MC.bestGap,
  };
}

function mcGetElementPool(groupId) {
  if (MC_ELEMENT_POOL.has(groupId)) return MC_ELEMENT_POOL.get(groupId);
  const lvRange = MATH_GROUPS.find((g) => g.id === groupId).towerRange;
  const [rangeMin, rangeMax] = lvRange;
  const pool = [];
  let guard = 0;
  while (pool.length < 900 && guard++ < 4000) {
    const e = mcMakeElement(groupId);
    if (!Number.isFinite(e.value)) continue;
    if (e.value <= 0.04) continue;
    if (e.value < rangeMin || e.value > rangeMax) continue;
    pool.push(mcCloneElem(e));
  }
  pool.sort((a, b) => a.value - b.value);
  MC_ELEMENT_POOL.set(groupId, pool);
  return pool;
}

/** 对值 v 反向查找"近似能用的 display"：若不在范围内则兜底用简单算式 */
function mcDisplayForValue(v, groupId) {
  const gens = ELEMENT_GENS[groupId];
  // 最多采样 30 次找一个匹配的 display
  for (let i = 0; i < 30; i++) {
    const e = mcPick(gens)();
    if (Math.abs(e.value - v) < 0.5) return e;
  }
  const n = Math.max(1, Math.round(v));
  const a = mcRnd(1, 9);
  return mcExpr(`${n + a} − ${a}`, n);
}

function mcMakeRangedElement(groupId, minValue, maxValue, usedDisplays = new Set()) {
  const pool = mcGetElementPool(groupId);
  const unused = (items) => items.filter((e) => !usedDisplays.has(e.display));
  const candidates = pool.filter((e) => e.value >= minValue - 1e-9 && e.value <= maxValue + 1e-9);
  const freshCandidates = unused(candidates);
  if (freshCandidates.length) {
    const picked = mcCloneElem(mcPick(freshCandidates));
    usedDisplays.add(picked.display);
    return picked;
  }
  let best = null;
  let bestDist = Infinity;
  const searchPool = unused(pool).length ? unused(pool) : pool;
  for (const e of searchPool) {
    const dist = e.value < minValue ? minValue - e.value : e.value - maxValue;
    if (dist < bestDist) {
      best = e;
      bestDist = dist;
    }
  }
  if (best && best.value > 0.04) {
    const picked = mcCloneElem(best);
    usedDisplays.add(picked.display);
    return picked;
  }
  const v = Math.max(1, Math.round((minValue + maxValue) / 2));
  const fallback = mcDisplayForValue(v, groupId);
  usedDisplays.add(fallback.display);
  return fallback;
}

/** 一座候选塔：按层从表达式池里抽牌后随机分到三列，列内索引 0 为第一回合底层。 */
function mcGenerateBalancedTower(groupId, cols = 3, perCol = null) {
  const lvRange = MATH_GROUPS.find((g) => g.id === groupId).towerRange;
  const rangeMin = lvRange[0];
  const rangeMax = lvRange[1];
  perCol = perCol || mcRowsForDifficulty();

  const usedDisplays = new Set();
  const tower = Array.from({ length: cols }, () => []);
  for (let depth = 0; depth < perCol; depth++) {
    const t = perCol <= 1 ? 1 : depth / (perCol - 1);
    const layerLo = rangeMin + (rangeMax - rangeMin) * (0.02 + 0.55 * t);
    const layerHi = rangeMin + (rangeMax - rangeMin) * Math.min(1, 0.28 + 0.72 * t);
    const layer = [];
    for (let c = 0; c < cols; c++) {
      const jitterLo = Math.max(rangeMin, layerLo * mcPick([0.75, 0.9, 1]));
      const jitterHi = Math.min(rangeMax, layerHi * mcPick([0.92, 1, 1.08]));
      layer.push(mcMakeRangedElement(groupId, jitterLo, Math.max(jitterLo, jitterHi), usedDisplays));
    }
    mcShuffle(layer);
    for (let c = 0; c < cols; c++) tower[c].push(layer[c]);
  }
  return tower;
}

function mcSolveDP(startHand, tower) {
  const dims = tower.map((col) => col.length);
  const total = dims.reduce((s, n) => s + n, 0);
  const memo = new Set();
  const path = [];
  const eatenValue = (state) => {
    let sum = 0;
    for (let c = 0; c < tower.length; c++) {
      for (let i = 0; i < state[c]; i++) sum += tower[c][i].value;
    }
    return sum;
  };
  const dfs = (state) => {
    const key = state.join(",");
    if (memo.has(key)) return false;
    const eaten = state.reduce((s, n) => s + n, 0);
    if (eaten >= total) return true;
    const handVal = startHand.value + eatenValue(state);
    const choices = [];
    for (let c = 0; c < tower.length; c++) {
      const idx = state[c];
      if (idx < tower[c].length && mcCanEat(handVal, tower[c][idx].value)) choices.push(c);
    }
    choices.sort((a, b) => tower[b][state[b]].value - tower[a][state[a]].value);
    for (const c of choices) {
      state[c]++;
      path.push(c);
      if (dfs(state)) return true;
      path.pop();
      state[c]--;
    }
    memo.add(key);
    return false;
  };
  const start = Array(tower.length).fill(0);
  return { solvable: dfs(start), steps: path.length, path: [...path] };
}

function mcNoSuccessfulLock(startHand, tower) {
  const total = tower.reduce((s, col) => s + col.length, 0);
  const seen = new Set();
  const stack = [Array(tower.length).fill(0)];
  const eatenValue = (state) => {
    let sum = 0;
    for (let c = 0; c < tower.length; c++) {
      for (let i = 0; i < state[c]; i++) sum += tower[c][i].value;
    }
    return sum;
  };

  while (stack.length) {
    const state = stack.pop();
    const key = state.join(",");
    if (seen.has(key)) continue;
    seen.add(key);

    const eaten = state.reduce((s, n) => s + n, 0);
    if (eaten >= total) continue;

    const handVal = startHand.value + eatenValue(state);
    const next = [];
    for (let c = 0; c < tower.length; c++) {
      const idx = state[c];
      if (idx < tower[c].length && mcCanEat(handVal, tower[c][idx].value)) next.push(c);
    }
    if (next.length === 0) return false;
    for (const c of next) {
      const ns = [...state];
      ns[c]++;
      stack.push(ns);
    }
  }
  return true;
}

/** 旧版逐张吃牌规则的兼容验证器：当前逐层三选一玩法不再调用。 */
function mcSimulateGreedy(startHand, tower) {
  let hand = { value: startHand.value };
  // 拷贝一份，避免破坏入参
  const cur = tower.map((col) => col.map((e) => ({ value: e.value, display: e.display })));
  const maxSteps = 1000;
  for (let step = 0; step < maxSteps; step++) {
    const eatable = [];
    for (let c = 0; c < cur.length; c++) {
      if (cur[c].length === 0) continue;
      if (hand.value >= cur[c][0].value - 1e-9) {
        eatable.push({ c, val: cur[c][0].value });
      }
    }
    if (eatable.length === 0) {
      const cleared = cur.every((c) => c.length === 0);
      return { solvable: cleared, steps: step };
    }
    eatable.sort((a, b) => a.val - b.val);
    const pick = eatable[0];
    const e = cur[pick.c].shift();
    hand.value += e.value;
    if (cur.every((c) => c.length === 0)) {
      return { solvable: true, steps: step + 1 };
    }
  }
  return { solvable: false, steps: maxSteps };
}

/** 旧版逐张吃牌规则的保底生成器：当前开局直接使用 mcGenerateBalancedTower。 */
function mcGenerateSolvableTower(groupId) {
  for (let att = 0; att < 160; att++) {
    const tower = mcGenerateBalancedTower(groupId);
    const minBottom = Math.min(...tower.map((c) => c[0].value));
    const startHandVal = Math.max(0.1, mcRound(minBottom * 1.10, 3));
    const hand = mcExpr(`起始牌`, startHandVal, `<span class="mc-start-card">🃏 起始牌</span><span class="mc-hand-hint-soft">点我看数值</span>`);
    const solved = mcSolveDP(hand, tower);
    const sortedCols = tower.filter((col) => col.every((e, i) => i === 0 || col[i - 1].value <= e.value + 1e-9)).length;
    if (solved.solvable && sortedCols < tower.length && mcNoSuccessfulLock(hand, tower)) {
      return { tower, hand, steps: solved.steps, path: solved.path };
    }
  }
  // 兜底：3 列各 4 个，小值递增（保底可玩）
  const tiny = (v) => mcExpr(`${v + 2} − 2`, v);
  const tower = [
    [tiny(3), tiny(4), tiny(5), tiny(6)],
    [tiny(4), tiny(5), tiny(6), tiny(7)],
    [tiny(5), tiny(6), tiny(7), tiny(8)],
  ];
  return {
    tower,
    hand: mcExpr(`起始牌`, 3.3, `<span class="mc-start-card">🃏 起始牌</span><span class="mc-hand-hint-soft">点我看数值</span>`),
    steps: 0,
  };
}

// ── 攻击逻辑 ──
function mcCanEat(handVal, elemVal) {
  return handVal >= elemVal - 1e-9;
}

function mcApplyOp(current, elem) {
  const v = elem.value;
  if (elem.op === "+") return current + v;
  if (elem.op === "−") return current - v;
  if (elem.op === "×") return current * v;
  if (elem.op === "÷") return Math.abs(v) < 1e-9 ? current : current / v;
  return current + v;
}

function mcDecorateOps(tower) {
  return tower.map((col) => col.map((elem, depth) => {
    const op = depth < 2
      ? mcPick(["+", "+", "+", "−", "−", "×", "÷"])
      : mcPick(["+", "+", "−", "−", "×", "÷"]);
    if ((op === "×" || op === "÷") && elem.value > 12) {
      return { ...elem, op: mcPick(["+", "−"]) };
    }
    return { ...elem, op };
  }));
}

function mcOpHtml(elem) {
  return `<span class="mc-op">${elem.op || "+"}</span><span class="mc-op-expr">(${elem.html || elem.display})</span>`;
}

function mcLayerCount(tower) {
  return Math.max(0, ...tower.map((col) => col.length));
}

function mcSearchOutcomes(startValue, tower) {
  const outcomes = [];
  const totalLayers = mcLayerCount(tower);
  const path = [];
  const dfs = (depth, value) => {
    if (!Number.isFinite(value) || Math.abs(value) > 1e15) return;
    if (depth >= totalLayers) {
      outcomes.push({ value, path: [...path] });
      return;
    }
    for (let c = 0; c < tower.length; c++) {
      const elem = tower[c]?.[depth];
      if (!elem) continue;
      path.push(c);
      dfs(depth + 1, mcApplyOp(value, elem));
      path.pop();
    }
  };
  dfs(0, startValue);
  return outcomes;
}

function mcRandomOutcome(startValue, tower) {
  let value = startValue;
  const totalLayers = mcLayerCount(tower);
  for (let depth = 0; depth < totalLayers; depth++) {
    const choices = tower
      .map((col, c) => ({ c, elem: col[depth] }))
      .filter((item) => item.elem);
    if (!choices.length) break;
    const pick = mcPick(choices);
    value = mcApplyOp(value, pick.elem);
  }
  return value;
}

function mcBestMaxValue(startValue, tower) {
  let best = -Infinity;
  let bestPath = [];
  const totalLayers = mcLayerCount(tower);
  const path = [];

  const dfs = (depth, value) => {
    if (!Number.isFinite(value) || Math.abs(value) > 1e15) return;
    if (depth >= totalLayers) {
      if (value > best) {
        best = value;
        bestPath = [...path];
      }
      return;
    }
    for (let c = 0; c < tower.length; c++) {
      const elem = tower[c]?.[depth];
      if (!elem) continue;
      path.push(c);
      dfs(depth + 1, mcApplyOp(value, elem));
      path.pop();
    }
  };

  dfs(0, startValue);
  return { value: Number.isFinite(best) ? best : startValue, path: bestPath };
}

function mcBuildOptimalExpr(startValue, tower, path) {
  let value = startValue;
  const parts = [`${mcFmt(startValue)}`];
  for (let depth = 0; depth < path.length; depth++) {
    const c = path[depth];
    const elem = tower[c]?.[depth];
    if (!elem) break;
    const op = elem.op || "+";
    value = mcApplyOp(value, elem);
    parts.push(`第${depth + 1}层选塔${c + 1}：${op}${mcFmt(elem.value)}=${mcFmt(value)}`);
  }
  return parts.join(" → ");
}

function mcClosestToTarget(startValue, tower, target) {
  const outcomes = mcSearchOutcomes(startValue, tower);
  if (!outcomes.length) return startValue;
  return outcomes.reduce((best, item) => Math.abs(item.value - target) < Math.abs(best - target) ? item.value : best, outcomes[0].value);
}

function mcAnalyzeChallenge(startValue, tower, mode) {
  const best = mcBestMaxValue(startValue, tower);
  if (mode === "target") {
    const target = mcRandomOutcome(startValue, tower);
    return { outcomes: [], optimum: best.value, target, bestGap: 0, bestPath: best.path };
  }
  return { outcomes: [], optimum: best.value, target: null, bestGap: 0, bestPath: best.path };
}

function mcLoadRecords() {
  try {
    return JSON.parse(localStorage.getItem(MC_RECORD_KEY) || "[]");
  } catch (e) {
    return [];
  }
}

function mcSaveRecord(record) {
  const records = [record, ...mcLoadRecords()].slice(0, 12);
  localStorage.setItem(MC_RECORD_KEY, JSON.stringify(records));
  MC.records = records;
  mcRenderRecords();
}

function mcClearRecords() {
  localStorage.removeItem(MC_RECORD_KEY);
  MC_LEGACY_RECORD_KEYS.forEach((key) => localStorage.removeItem(key));
  MC.records = [];
  mcRenderRecords();
}

function mcRenderRecords() {
  if (!mcRecords) return;
  const records = MC.records?.length ? MC.records : mcLoadRecords();
  MC.records = records;
  if (!records.length) {
    mcRecords.textContent = "暂无历史";
    return;
  }
  mcRecords.innerHTML = "";
  records.slice(0, 8).forEach((r, idx) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "mc-record-row";
    btn.innerHTML = `
      <b>${r.score}分</b>
      <span>${r.group} · ${r.mode}</span>
      <em>Gap ${r.gap} · 查 ${r.peeks} · 点此重挑战</em>
    `;
    btn.disabled = !r.puzzle;
    btn.addEventListener("click", () => {
      if (r.puzzle) mcRestorePuzzle(r.puzzle);
    });
    mcRecords.appendChild(btn);
  });
}

function mcBindRuntimeDom() {
  mcHand = document.getElementById("mcHand");
  mcTower = document.getElementById("mcTower");
  mcEatenList = document.getElementById("mcEatenList");
  mcHudScore = document.getElementById("mcHudScore");
  mcHudGroup = document.getElementById("mcHudGroup");
  mcHudLives = document.getElementById("mcHudLives");
  mcHudEats = document.getElementById("mcHudEats");
  mcHudPeek = document.getElementById("mcHudPeek");
  mcFinishBtn = document.getElementById("mcFinishBtn");
  mcRecords = document.getElementById("mcRecords");
}

function mcResetRunState() {
  MC.eaten = [];
  MC.totalCells = mcLayerCount(MC.tower);
  MC.peeked = new Set();
  MC.peekCount = 0;
  MC.lives = 3;
  MC.turns = 0;
  MC.hits = 0;
  MC.eats = 0;
  MC.busy = false;
  MC.won = false;
  MC.running = true;
}

function mcRestorePuzzle(puzzle) {
  stopCannon();
  MC.groupId = puzzle.groupId || "primary";
  MC.group = MATH_GROUPS.find((g) => g.id === MC.groupId) || MATH_GROUPS[0];
  MC.challengeMode = puzzle.challengeMode || "max";
  MC.boardDifficulty = puzzle.boardDifficulty || "hard";
  MC.startHand = mcExpr("起始牌", 0, `<span class="mc-start-card">🃏 起始牌（从 0 开始）</span><span class="mc-hand-hint-soft">点我看数值</span>`);
  MC.hand = mcCloneElem(MC.startHand);
  MC.tower = mcCloneTower(puzzle.tower || []);
  MC.originalTower = mcCloneTower(MC.tower);
  const mcBest = mcBestMaxValue(MC.hand.value, MC.originalTower);
  MC.optimum = mcBest.value;
  MC.bestPath = mcBest.path || [];
  MC.bestExpr = mcBuildOptimalExpr(MC.hand.value, MC.originalTower, MC.bestPath);
  const isNewRulePuzzle = puzzle.version >= 3 && Number.isFinite(puzzle.startHand?.value) && Math.abs(puzzle.startHand.value) < 1e-9;
  MC.target = isNewRulePuzzle && Number.isFinite(puzzle.target) ? puzzle.target : mcRandomOutcome(MC.hand.value, MC.originalTower);
  MC.bestGap = Number.isFinite(puzzle.bestGap) ? puzzle.bestGap : 0;
  mcResetRunState();
  mcBindRuntimeDom();
  document.querySelectorAll(".cannon-mode-btn").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.mcMode === MC.challengeMode);
  });
  document.querySelectorAll(".cannon-diff-btn").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.mcDiff === MC.boardDifficulty);
  });
  document.querySelectorAll(".cannon-lv-btn").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.groupId === MC.groupId);
  });
  mcRenderHUD();
  mcRenderHand();
  mcRenderTower();
  mcRenderLevelInfo();
}

async function mcAttack(col) {
  if (!MC.running || MC.busy || MC.won) return;
  if (!MC.tower[col] || MC.tower[col].length === 0) return;
  const elem = MC.tower[col][0];
  const bottomLayer = MC.tower.map((towerCol) => towerCol[0]).filter(Boolean);

  MC.busy = true;
  MC.turns++;

  const cell = mcTower?.querySelector(`.mc-col[data-col="${col}"] .mc-elem.bottom`);
  const nextValue = mcApplyOp(MC.hand.value, elem);
  mcShowCombatText(cell, `${elem.op}${mcFmt(elem.value)} → ${mcFmt(nextValue)}`, "success");
  mcAnimateBottomLayer();
  setTimeout(() => {
    MC.hand = {
      display: `${MC.hand.display} ${elem.op} ${elem.display}`,
      html: MC.hand.html,
      value: nextValue,
    };
    MC.eaten.unshift({ ...elem, chosen: true, shattered: bottomLayer.length - 1 });
    for (let c = 0; c < MC.tower.length; c++) {
      if (MC.tower[c].length) MC.tower[c].shift();
    }
    MC.eats++;
    MC.hits++;
    mcRenderHUD();
    mcRenderHand();
    mcRenderTower();
    MC.busy = false;
    checkWin();
  }, 420);
}

function checkWin() {
  if (MC.tower.every((col) => col.length === 0)) {
    MC.won = true;
    mcRenderHUD();
    setTimeout(() => mcEndGame(), 600);
  }
}

// ── Click 查看（peek）：任何格子点击都触发 ──
function mcPeek(key, display, value, anchor) {
  MC.peekCount++;
  MC.peeked.add(key);
  // 视觉标记：被 peek 过的格子带淡紫边框
  if (anchor && !anchor.classList.contains("peeked")) anchor.classList.add("peeked");
  mcShowTip(anchor, mcFmt(value));
  if (mcHudPeek) mcHudPeek.textContent = `🔍 查看次数：${MC.peekCount}`;
}

// 浮显 tooltip
function mcShowTip(anchor, text) {
  if (!anchor) return;
  // 移除已有
  document.querySelectorAll(".mc-peek-tip").forEach((t) => t.remove());
  const tip = document.createElement("div");
  tip.className = "mc-peek-tip";
  tip.textContent = text;
  document.body.appendChild(tip);
  const r = anchor.getBoundingClientRect();
  tip.style.left = `${r.left + r.width / 2}px`;
  tip.style.top = `${r.top - 14}px`;
  // 1.6s 自动消失
  setTimeout(() => tip.classList.add("fade"), 1000);
  setTimeout(() => tip.remove(), 1700);
}

function mcShowCombatText(anchor, text, kind = "success") {
  if (!anchor) return;
  const fx = document.createElement("div");
  fx.className = `mc-combat-text ${kind}`;
  fx.textContent = text;
  document.body.appendChild(fx);
  const r = anchor.getBoundingClientRect();
  fx.style.left = `${r.left + r.width / 2}px`;
  fx.style.top = `${r.top + r.height / 2}px`;
  setTimeout(() => fx.remove(), 900);
}

// ── 动画 ──
function mcAnimateEat(col) {
  const cell = mcTower?.querySelector(`.mc-col[data-col="${col}"] .mc-elem.bottom`);
  if (cell) {
    cell.classList.add("eat");
    setTimeout(() => cell?.classList.remove("eat"), 420);
  }
  mcBeep(660, 0.08);
  mcBeep(880, 0.14, "sine", 0.14, 0.08);
}

function mcAnimateBottomLayer() {
  mcTower?.querySelectorAll(".mc-elem.bottom").forEach((cell) => {
    cell.classList.add("eat");
    setTimeout(() => cell?.classList.remove("eat"), 420);
  });
  mcBeep(660, 0.08);
  mcBeep(880, 0.14, "sine", 0.14, 0.08);
}

function mcAnimateFail(col) {
  const cell = mcTower?.querySelector(`.mc-col[data-col="${col}"] .mc-elem.bottom`);
  if (cell) cell.classList.add("fail");
  mcBeep(200, 0.25, "sawtooth", 0.13);
}

// ── 渲染 ──
function mcRenderHUD() {
  if (mcHudScore) mcHudScore.textContent = `${MC.eats} / ${MC.totalCells} · ${MC.turns} 回合`;
  const modeName = MC.challengeMode === "target" ? "目标值挑战" : "最大值挑战";
  const diffName = { easy: "Easy", medium: "Medium", hard: "Hard" }[MC.boardDifficulty] || "Hard";
  if (mcHudGroup) mcHudGroup.textContent = `${MC.group.name} · ${diffName} · ${modeName}`;
  if (mcHudLives) {
    if (MC.challengeMode === "target") {
      mcHudLives.textContent = `目标：${mcFmt(MC.target || 0)} · 当前差：${mcFmt(Math.abs(MC.hand.value - (MC.target || 0)))}`;
    } else {
      mcHudLives.textContent = `理论最大：${mcFmt(MC.optimum || 0)} · 差距：${mcFmt(Math.abs((MC.optimum || 0) - MC.hand.value))}`;
    }
  }
  if (mcHudEats) mcHudEats.textContent = `🃏 手牌`;
  if (mcHudPeek) mcHudPeek.textContent = `🔍 查看次数：${MC.peekCount}`;
  if (mcFinishBtn) mcFinishBtn.disabled = !MC.running;
}

function mcRenderHand() {
  if (!mcHand) return;
  mcHand.innerHTML = `
    <div class="mc-hand-label">当前手牌</div>
    <div class="mc-hand-current">≈ ${mcFmt(MC.hand.value)}</div>
    <div class="mc-hand-start math-render">${MC.startHand?.html || MC.hand.html || MC.hand.display}</div>
    <div class="mc-hand-count">已完成 ${MC.eats} / ${MC.totalCells} 层</div>
    <div class="mc-hand-hint">每层三选一，选中牌生效，其余底牌同时碎掉</div>`;
  mcHand.onclick = () => {
    mcPeek("hand-self", MC.hand.display, MC.hand.value, mcHand);
  };
  mcRenderEaten();
}

function mcRenderEaten() {
  if (!mcEatenList) return;
  mcEatenList.innerHTML = "";
  if (!MC.eaten.length) {
    const empty = document.createElement("div");
    empty.className = "mc-eaten-empty";
    empty.textContent = "还没有吃牌";
    mcEatenList.appendChild(empty);
    return;
  }
  MC.eaten.slice(0, 30).forEach((elem, idx) => {
    const card = document.createElement("button");
    card.type = "button";
    card.className = "mc-eaten-card math-render";
    const shatteredNote = Number.isFinite(elem.shattered) && elem.shattered > 0 ? `<small>本层另 ${elem.shattered} 张已碎</small>` : "";
    card.innerHTML = `${mcOpHtml(elem)}${shatteredNote}`;
    card.addEventListener("click", () => mcPeek(`eaten-${idx}-${elem.display}`, elem.display, elem.value, card));
    mcEatenList.appendChild(card);
  });
}

function mcRenderTower() {
  if (!mcTower) return;
  mcTower.innerHTML = "";
  for (let c = 0; c < MC.tower.length; c++) {
    const colEl = document.createElement("div");
    colEl.className = "mc-col";
    colEl.dataset.col = c;
    MC.tower[c].forEach((elem, i) => {
      const cell = document.createElement("div");
      cell.className = "mc-elem" + (i === 0 ? " bottom" : "");
      cell.dataset.col = c;
      cell.dataset.idx = i;
      cell.innerHTML = `<span class="mc-elem-disp math-render">${mcOpHtml(elem)}</span>`;
      cell.addEventListener("click", (e) => {
        mcPeek(`t-${c}-${i}-${elem.display}-${elem.value.toFixed(3)}`, elem.display, elem.value, cell);
      });
      if (i === 0) {
        const attackBtn = document.createElement("button");
        attackBtn.className = "mc-attack-btn";
        attackBtn.type = "button";
        attackBtn.textContent = "使用";
        attackBtn.addEventListener("click", (e) => {
          e.stopPropagation();
          mcAttack(c);
        });
        cell.appendChild(attackBtn);
        attackBtn.title = "本层选择这张牌生效；三座塔的当前底牌会同时碎掉";
      }
      colEl.appendChild(cell);
    });
    mcTower.appendChild(colEl);
  }
}

function mcRenderLevelInfo() {
  const title = document.getElementById("algebraLevelInfo");
  const subtitle = document.getElementById("algebraSubtitle");
  if (title) title.textContent = `算式炮弹 · ${MC.group.name}`;
  if (subtitle) {
    subtitle.textContent =
      "手牌从 0 开始；每回合从三座塔当前底层中选一张生效，然后三张底牌同时碎掉。最大值挑战追求理论最大；目标值挑战追求靠近目标。";
  }
}

// ── 局末 ──
function mcEndGame() {
  MC.running = false;
  const peekCount = MC.peekCount;
  const finalValue = MC.hand.value;
  const targetValue = MC.challengeMode === "target" ? MC.target : MC.optimum;
  const gap = Math.abs(finalValue - targetValue);
  const scale = Math.max(1, Math.abs(targetValue));
  const accuracy = Math.max(0, 1 - gap / scale);
  const peekPenalty = Math.min(12, peekCount * 0.6);
  const score = Math.max(0, Math.round(accuracy * 100 - peekPenalty));
  const medal = gap < 1e-6 ? "🎯 完美命中" : (score >= 90 ? "🧠 接近最优" : (score >= 70 ? "📐 很接近" : "💪 继续挑战"));
  const modeName = MC.challengeMode === "target" ? "目标值挑战" : "最大值挑战";
  const bestExpr = MC.bestExpr || mcBuildOptimalExpr(MC.startHand.value, MC.originalTower, MC.bestPath);
  const exprLine = MC.challengeMode === "max" && bestExpr ? `\n最优算式：${bestExpr}` : "";
  const comment = MC.challengeMode === "target"
    ? `目标：${mcFmt(MC.target)}，你的结果：${mcFmt(finalValue)}，Gap：${mcFmt(gap)}。`
    : `理论最大：${mcFmt(MC.optimum)}，你的结果：${mcFmt(finalValue)}，Gap：${mcFmt(gap)}。${exprLine}`;

  mcSaveRecord({
    mode: modeName,
    group: `${MC.group.name}/${({ easy: "Easy", medium: "Medium", hard: "Hard" }[MC.boardDifficulty] || "Hard")}`,
    score,
    finalValue: mcFmt(finalValue),
    targetValue: mcFmt(targetValue),
    gap: mcFmt(gap),
    peeks: peekCount,
    time: new Date().toLocaleString(),
    puzzle: mcSnapshotPuzzle(),
  });

  showModal(
    "🎉",
    `${medal} · ${score} 分`,
    `${modeName}\n${comment}\n查询次数：${peekCount}`,
    "再来一次",
    () => startCannonLevel(MC.groupId),
  );
}

// ── 音效 ──
let mcAudio = null;
function mcBeep(freq, dur, type = "sine", vol = 0.12, delay = 0) {
  try {
    if (!mcAudio) mcAudio = new (window.AudioContext || window.webkitAudioContext)();
    const t = mcAudio.currentTime + delay;
    const osc = mcAudio.createOscillator();
    const gain = mcAudio.createGain();
    osc.type = type; osc.frequency.value = freq;
    gain.gain.setValueAtTime(vol, t);
    gain.gain.exponentialRampToValueAtTime(0.001, t + dur);
    osc.connect(gain).connect(mcAudio.destination);
    osc.start(t); osc.stop(t + dur + 0.02);
  } catch (e) {}
}

// ── 对外接口 ──
function startCannon() {
  mcFinishBtn = document.getElementById("mcFinishBtn");
  mcRecords = document.getElementById("mcRecords");
  MC.records = mcLoadRecords();
  MC_LEGACY_RECORD_KEYS.forEach((key) => localStorage.removeItem(key));
  mcRenderRecords();
  document.querySelectorAll(".cannon-mode-btn").forEach((btn) => {
    btn.onclick = () => {
      MC.challengeMode = btn.dataset.mcMode;
      document.querySelectorAll(".cannon-mode-btn").forEach((b) => b.classList.toggle("active", b === btn));
      if (MC.groupId) startCannonLevel(MC.groupId);
    };
  });
  document.querySelectorAll(".cannon-diff-btn").forEach((btn) => {
    btn.onclick = () => {
      MC.boardDifficulty = btn.dataset.mcDiff;
      document.querySelectorAll(".cannon-diff-btn").forEach((b) => b.classList.toggle("active", b === btn));
      if (MC.groupId) startCannonLevel(MC.groupId);
    };
  });
  if (mcFinishBtn) mcFinishBtn.onclick = () => mcEndGame();
  const clearHistoryBtn = document.getElementById("mcClearHistoryBtn");
  if (clearHistoryBtn) clearHistoryBtn.onclick = () => mcClearRecords();
  const lv = document.getElementById("cannonLevels");
  if (lv && !lv.children.length) {
    MATH_GROUPS.forEach((g) => {
      const btn = document.createElement("button");
      btn.className = "cannon-lv-btn";
      btn.dataset.groupId = g.id;
      btn.innerHTML = `<div class="lv-name">${g.name}</div><div class="lv-desc">${g.desc}</div>`;
      btn.addEventListener("click", () => startCannonLevel(g.id));
      lv.appendChild(btn);
    });
  }
  if (!MC.groupId) startCannonLevel("primary");
}

function startCannonLevel(groupId) {
  stopCannon();
  MC.groupId = groupId;
  MC.group = MATH_GROUPS.find((g) => g.id === groupId);
  document.querySelectorAll(".cannon-lv-btn").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.groupId === groupId);
  });
  document.querySelectorAll(".cannon-diff-btn").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.mcDiff === MC.boardDifficulty);
  });
  const tower = mcGenerateBalancedTower(groupId);
  const startHandVal = 0;
  MC.hand = mcExpr(`起始牌`, startHandVal, `<span class="mc-start-card">🃏 起始牌（从 0 开始）</span><span class="mc-hand-hint-soft">点我看数值</span>`);
  MC.startHand = { ...MC.hand };
  MC.tower = mcDecorateOps(tower);
  MC.originalTower = mcCloneTower(MC.tower);
  const analysis = mcAnalyzeChallenge(MC.hand.value, MC.originalTower, MC.challengeMode);
  MC.optimum = analysis.optimum;
  MC.target = analysis.target;
  MC.bestGap = analysis.bestGap;
  MC.bestPath = analysis.bestPath || [];
  MC.bestExpr = mcBuildOptimalExpr(MC.hand.value, MC.originalTower, MC.bestPath);
  mcResetRunState();
  mcBindRuntimeDom();
  mcRenderHUD();
  mcRenderHand();
  mcRenderTower();
  mcRenderLevelInfo();
}

function stopCannon() {
  MC.running = false;
  MC.won = false;
  MC.busy = false;
}
