/* Declarative exploration goals.
   Every goal is evaluated locally against the authoritative bench state. The
   model never awards progress — it only describes what happened, and these
   rules decide whether that counts.

   `check` receives:
     { reaction, held, conditions, progress } */

import { normalizeFormula } from "./substances.js";
import { tempPreset } from "./conditions.js";

/** Identity of a material set, ignoring order. Used to notice that the learner
    ran the SAME materials at a different temperature and got another product. */
export function materialsKey(held) {
  return held
    .map((item) => `${normalizeFormula(item.formula)}#${item.variant || ""}`)
    .sort()
    .join("|");
}

const gasProduced = (reaction) =>
  reaction.products.some((product) => product.state === "气体") ||
  /气体|气泡|↑|冒/.test(reaction.phenomenon);

const precipitateProduced = (reaction) =>
  reaction.products.some((product) => product.state === "沉淀") ||
  /沉淀|↓|浑浊|析出/.test(reaction.phenomenon);

const hasVariant = (held, formula, variant) =>
  held.some((item) => normalizeFormula(item.formula) === normalizeFormula(formula) && item.variant === variant);

export const QUESTS = [
  {
    id: "first-reaction",
    label: "01",
    title: "第一个反应",
    detail: "任意组合，让实验台真的反应起来",
    check: ({ reaction }) => reaction.reacts,
  },
  {
    id: "make-gas",
    label: "02",
    title: "放出一种气体",
    detail: "让产物里出现气体，看气泡从杯底升起",
    check: ({ reaction }) => reaction.reacts && gasProduced(reaction),
  },
  {
    id: "make-precipitate",
    label: "03",
    title: "析出一种沉淀",
    detail: "用复分解的思路，让溶液里沉下一层",
    check: ({ reaction }) => reaction.reacts && precipitateProduced(reaction),
  },
  {
    id: "displacement",
    label: "04",
    title: "让金属换个位置",
    detail: "做出一个置换反应，验证金属活动性顺序",
    check: ({ reaction }) => reaction.reacts && reaction.type === "置换反应",
  },
  {
    id: "concentrated-vs-dilute",
    label: "05",
    title: "分清浓和稀",
    detail: "用浓酸做成一次反应 —— 它和稀酸的产物完全不同",
    check: ({ reaction, held }) =>
      reaction.reacts &&
      (hasVariant(held, "H₂SO₄", "浓") || hasVariant(held, "HNO₃", "浓") || hasVariant(held, "HCl", "浓")),
  },
  {
    id: "condition-matters",
    label: "06",
    title: "凑齐必要条件",
    detail: "找到一个反应，它需要两个以上的条件才肯发生",
    check: ({ reaction }) =>
      reaction.reacts && reaction.condChecks.filter((check) => check.verdict === "need").length >= 2,
  },
  {
    id: "exact-temperature",
    label: "07",
    title: "用精确温度做成一次",
    detail: "填一个具体的摄氏度，而不是只选「加热」",
    check: ({ reaction, conditions }) =>
      reaction.reacts && tempPreset(conditions).id === "custom",
  },
  {
    id: "same-materials-two-products",
    label: "08",
    title: "同料不同温，两种产物",
    detail: "同一组材料换个温度，做出完全不同的产物",
    check: ({ reaction, held, progress }) => {
      if (!reaction.reacts || !reaction.equation) return false;
      const key = materialsKey(held);
      const previous = progress.discoveries.filter(
        (item) => item.reacts && item.materialsKey === key && item.equation !== reaction.equation,
      );
      return previous.length > 0;
    },
  },
  {
    id: "named-catalyst",
    label: "09",
    title: "找对那一种催化剂",
    detail: "让一个反应在指定催化剂下发生 —— 催化剂不能互换",
    check: ({ reaction, conditions }) =>
      reaction.reacts &&
      conditions.catalyst !== "none" &&
      reaction.condChecks.some(
        (check) => check.verdict === "need" && check.label.startsWith("催化剂:"),
      ),
  },
  {
    id: "chain-synthesis",
    label: "10",
    title: "连锁合成",
    detail: "把产物加回材料库，再用它做下一次反应",
    check: ({ held, progress }) =>
      progress.extra.length > 0 &&
      held.some((item) =>
        progress.extra.some((entry) => normalizeFormula(entry[0]) === normalizeFormula(item.formula)),
      ),
  },
  {
    id: "talk-it-through",
    label: "11",
    title: "把想法说出来",
    detail: "和实验助手聊聊：你的猜测、或者为什么它不反应",
    check: ({ progress }) => progress.chat.some((turn) => turn.role === "user"),
  },
];

export const QUEST_TOTAL = QUESTS.length;

/** A verdict-shaped blank, so goal checks can read `reaction.*` unconditionally
    even when no round has been run yet (e.g. the learner only chatted). */
const NO_REACTION = {
  reacts: false,
  type: "",
  equation: "",
  products: [],
  phenomenon: "",
  why: "",
  condChecks: [],
  missing: "",
  danger: "",
  hint: "",
};

/** Evaluate every unfinished goal against the current bench state. `reaction`
    may be absent: goals not tied to a round are still allowed to complete. */
export function evaluateQuests(context) {
  const scope = { ...context, reaction: context.reaction ?? NO_REACTION };
  const unlocked = [];
  for (const quest of QUESTS) {
    if (scope.progress.quests[quest.id]) continue;
    let passed;
    try {
      passed = Boolean(quest.check(scope));
    } catch {
      passed = false;
    }
    if (passed) unlocked.push(quest);
  }
  return unlocked;
}

/** 1–3 stars from completed goals. Stars summarise exploration breadth, not
    correctness. The first star stays cheap so early experimenting feels
    rewarded; the third requires covering every axis of the bench. */
export function starsFor(progress) {
  const done = QUESTS.filter((quest) => progress.quests[quest.id]).length;
  if (done >= QUEST_TOTAL) return 3;
  if (done >= Math.ceil(QUEST_TOTAL * 0.6)) return 2;
  if (done >= Math.ceil(QUEST_TOTAL * 0.25)) return 1;
  return 0;
}

export const questsDone = (progress) => QUESTS.filter((quest) => progress.quests[quest.id]).length;
