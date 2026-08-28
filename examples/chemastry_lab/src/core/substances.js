/* Substance identity.
   A substance is [formula, name, variant?]. The variant is the dimension a
   formula cannot express: 稀 / 浓 / 饱和. Concentrated and dilute sulfuric acid
   are both H₂SO₄, but one is an oxidiser and the other a plain strong acid, so
   they must never collapse into the same entry.

   Keys:
     strict = normalised formula + '#' + variant   (used when filling the vessel)
     loose  = normalised formula                   (used when banking products)
     name   = normalised Chinese name              (fallback when only a name came back)
   Normalisation is needed because a model may return H2O / 2H₂O / H₂O↑ / Ca(OH)2. */

const SUBSCRIPTS = "₀₁₂₃₄₅₆₇₈₉";

export function normalizeFormula(value) {
  return (value || "")
    .trim()
    .replace(/[₀-₉]/g, (char) => SUBSCRIPTS.indexOf(char))
    .replace(/[（]/g, "(")
    .replace(/[）]/g, ")")
    .replace(/[↑↓]/g, "")
    .replace(/\((?:g|s|l|aq|固|液|气|水溶液)\)/gi, "")
    .replace(/\s|·|•|・/g, "")
    .replace(/^\d+(?=[A-Za-z(])/, "")
    .toUpperCase();
}

export function normalizeName(value) {
  return (value || "").trim().replace(/\s/g, "").replace(/(试液|溶液)$/, "");
}

export const variantOf = (item) => item[2] || "";
export const strictKey = (formula, variant) => `${normalizeFormula(formula)}#${variant || ""}`;

/** A Chinese name can carry its own concentration; lift it into the variant. */
export function variantFromName(name) {
  const match = /^(浓|稀|饱和)/.exec((name || "").trim());
  return match ? match[1] : "";
}

/** Display form for humans: H₂SO₄(浓) */
export const displayOf = (held) => held.formula + (held.variant ? `(${held.variant})` : "");

export const LIBRARY = [
  {
    cat: "金属",
    items: [
      ["Na", "钠"], ["K", "钾"], ["Mg", "镁"], ["Al", "铝"], ["Fe", "铁"],
      ["Cu", "铜"], ["Zn", "锌"], ["Ag", "银"], ["Ca", "钙"],
    ],
  },
  {
    cat: "非金属 / 气体",
    items: [
      ["H₂", "氢气"], ["O₂", "氧气"], ["N₂", "氮气"], ["Cl₂", "氯气"],
      ["C", "碳"], ["S", "硫"], ["P", "磷"], ["I₂", "碘"],
    ],
  },
  {
    cat: "氧化物",
    items: [
      ["H₂O", "水"], ["CO₂", "二氧化碳"], ["CO", "一氧化碳"], ["CuO", "氧化铜"],
      ["Fe₂O₃", "氧化铁"], ["CaO", "氧化钙"], ["SO₂", "二氧化硫"],
      ["MnO₂", "二氧化锰"], ["Al₂O₃", "氧化铝"],
    ],
  },
  {
    cat: "酸",
    items: [
      ["HCl", "稀盐酸", "稀"], ["HCl", "浓盐酸", "浓"],
      ["H₂SO₄", "稀硫酸", "稀"], ["H₂SO₄", "浓硫酸", "浓"],
      ["HNO₃", "稀硝酸", "稀"], ["HNO₃", "浓硝酸", "浓"],
      ["H₂CO₃", "碳酸"],
    ],
  },
  {
    cat: "碱",
    items: [
      ["NaOH", "氢氧化钠"], ["NaOH", "浓氢氧化钠", "浓"],
      ["Ca(OH)₂", "氢氧化钙"], ["KOH", "氢氧化钾"], ["NH₃·H₂O", "氨水"],
    ],
  },
  {
    cat: "盐",
    items: [
      ["NaCl", "食盐"], ["CuSO₄", "硫酸铜"], ["Na₂CO₃", "碳酸钠"],
      ["NaHCO₃", "小苏打"], ["CaCO₃", "碳酸钙"], ["AgNO₃", "硝酸银"],
      ["BaCl₂", "氯化钡"], ["KMnO₄", "高锰酸钾"], ["KClO₃", "氯酸钾"],
      ["FeSO₄", "硫酸亚铁"],
    ],
  },
  {
    cat: "有机物",
    items: [
      ["C₂H₅OH", "酒精"], ["CH₃COOH", "醋酸"], ["C₆H₁₂O₆", "葡萄糖"],
      ["CH₄", "甲烷"], ["C₂H₄", "乙烯"], ["C₂H₂", "乙炔"],
      ["(C₂H₅)₂O", "乙醚"], ["CH₃CHO", "乙醛"],
      ["CH₃COOC₂H₅", "乙酸乙酯"], ["C₆H₆", "苯"],
      ["(C₆H₁₀O₅)ₙ", "淀粉"], ["C₁₂H₂₂O₁₁", "蔗糖"],
    ],
  },
  {
    cat: "指示剂 / 其他",
    items: [
      ["石蕊", "石蕊试液"], ["酚酞", "酚酞试液"],
      ["H₂O₂", "过氧化氢"], ["NH₃", "氨气"],
    ],
  },
];

/** What actually differs between these two bottles, in one line. */
export const VARIANT_NOTES = {
  "H₂SO₄|浓": "吸水、脱水、强氧化性；不放氢气",
  "H₂SO₄|稀": "普通强酸；活泼金属置换出氢气",
  "HNO₃|浓": "强氧化性，遇铜放 NO₂（红棕）",
  "HNO₃|稀": "强氧化性，遇铜放 NO（无色）",
  "HCl|浓": "易挥发，瓶口冒白雾",
  "HCl|稀": "普通强酸",
  "NaOH|浓": "浓碱，强腐蚀",
};

export const variantNote = (held) => VARIANT_NOTES[`${held.formula}|${held.variant || ""}`] || "";

export const MAX_HELD = 5;

/* Reaction conditions live in ./conditions.js — they need far more structure
   than a flat list of chips (exact temperatures, named catalysts, ratios). */

/** Find a substance already in the library. When loose, ignore the variant so
    banking a product does not spawn a near-duplicate entry. */
export function findMaterial({ formula, name, variant, loose, extra = [] }) {
  const wanted = variant || variantFromName(name);
  const byFormula = normalizeFormula(formula);
  const byName = normalizeName(name);
  const all = LIBRARY.flatMap((group) => group.items).concat(extra);
  return (
    all.find((item) => {
      if (byFormula && normalizeFormula(item[0]) === byFormula) {
        return loose ? true : variantOf(item) === wanted;
      }
      if (byName && normalizeName(item[1]) === byName) return true;
      return false;
    }) || null
  );
}
