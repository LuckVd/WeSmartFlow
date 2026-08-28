/* Reaction conditions.
   The first version of this bench had five vague temperature buckets
   (常温/加热/高温/点燃/低温). That cannot express the difference between
   140℃ and 170℃, so ethanol dehydration was unreachable no matter what the
   learner did — the model was right to refuse. Conditions are modelled along
   the axes real middle-school chemistry actually turns on:

     temp      preset bucket OR an exact number in ℃
     env       gas/solution/sealed/molten environment
     catalyst  a NAMED catalyst — Fe, V₂O₅ and MnO₂ are not interchangeable
     pressure  ordinary / pressurised, needed for 合成氨
     ratio     which reagent is in excess, needed for C→CO vs CO₂
     add       remaining stackable switches

   Anything the learner did not choose is reported as "not specified" rather
   than silently defaulted, so the model can say what is still missing instead
   of inventing a setting. */

export const TEMP_PRESETS = [
  { id: "room", label: "常温", icon: "🌡", celsius: 25, hint: "约 25℃" },
  { id: "ice", label: "冰水浴", icon: "❄️", celsius: 0, hint: "约 0℃" },
  { id: "warm", label: "微热", icon: "♨️", celsius: 60, hint: "约 60℃" },
  { id: "boil", label: "水浴加热", icon: "💧", celsius: 100, hint: "约 100℃" },
  { id: "heat", label: "加热", icon: "🔥", celsius: 200, hint: "酒精灯，约 200℃" },
  { id: "strong", label: "强热", icon: "🌋", celsius: 500, hint: "约 500℃" },
  { id: "hot", label: "高温", icon: "⛰", celsius: 1000, hint: "约 1000℃" },
  { id: "ignite", label: "点燃", icon: "🔴", celsius: null, hint: "明火引燃" },
  { id: "custom", label: "精确温度", icon: "🎯", celsius: null, hint: "自己填一个温度" },
];

export const TEMP_MIN = -50;
export const TEMP_MAX = 3000;
export const DEFAULT_CUSTOM_TEMP = 170;

/* Named catalysts. "有催化剂" as a boolean is not chemistry: the whole point of
   合成氨 is that it needs iron specifically. */
export const CATALYSTS = [
  { id: "none", label: "不加", formula: "" },
  { id: "fe", label: "铁触媒", formula: "Fe" },
  { id: "v2o5", label: "五氧化二钒", formula: "V₂O₅" },
  { id: "mno2", label: "二氧化锰", formula: "MnO₂" },
  { id: "pt", label: "铂/铜", formula: "Pt/Cu" },
  { id: "h2so4", label: "浓硫酸作催化剂", formula: "H₂SO₄(浓)" },
  { id: "enzyme", label: "酶", formula: "酶" },
  { id: "al2o3", label: "氧化铝", formula: "Al₂O₃" },
  { id: "other", label: "其他/未知", formula: "未知催化剂" },
];

export const ENVIRONMENTS = [
  { id: "dry", label: "干燥", icon: "🌬" },
  { id: "aqueous", label: "水溶液中", icon: "💧" },
  { id: "sealed", label: "隔绝空气", icon: "🚫" },
  { id: "molten", label: "熔融态", icon: "🫗" },
  { id: "acidic", label: "酸性条件", icon: "🍋" },
  { id: "basic", label: "碱性条件", icon: "🧼" },
];

export const PRESSURES = [
  { id: "normal", label: "常压", icon: "" },
  { id: "high", label: "加压", icon: "🗜" },
  { id: "vacuum", label: "减压", icon: "🌀" },
];

/* Stoichiometry decides the product: C+O₂ gives CO₂ when oxygen is plentiful
   and CO when it is scarce. */
export const RATIOS = [
  { id: "balanced", label: "适量", icon: "" },
  { id: "excess-first", label: "第一种过量", icon: "" },
  { id: "excess-last", label: "最后一种过量", icon: "" },
  { id: "limited-o2", label: "氧气不足", icon: "" },
  { id: "excess-o2", label: "氧气过量", icon: "" },
];

export const ADDITIVES = [
  { id: "electrolysis", label: "通电", icon: "⚡" },
  { id: "light", label: "光照", icon: "☀️" },
  { id: "grind", label: "研磨", icon: "🔨" },
  { id: "stir", label: "搅拌", icon: "🌀" },
  { id: "reflux", label: "回流", icon: "🔄" },
  { id: "distill", label: "边反应边蒸出", icon: "⚗️" },
];

export const MAX_ADDITIVES = 4;

export function defaultConditions() {
  return {
    tempPreset: "room",
    customTemp: DEFAULT_CUSTOM_TEMP,
    env: "dry",
    catalyst: "none",
    pressure: "normal",
    ratio: "balanced",
    add: [],
  };
}

const findById = (list, id) => list.find((item) => item.id === id) || list[0];

export const tempPreset = (conditions) => findById(TEMP_PRESETS, conditions.tempPreset);
export const catalystOf = (conditions) => findById(CATALYSTS, conditions.catalyst);
export const environmentOf = (conditions) => findById(ENVIRONMENTS, conditions.env);
export const pressureOf = (conditions) => findById(PRESSURES, conditions.pressure);
export const ratioOf = (conditions) => findById(RATIOS, conditions.ratio);

export function clampTemp(value) {
  const number = Math.round(Number(value));
  if (!Number.isFinite(number)) return DEFAULT_CUSTOM_TEMP;
  return Math.max(TEMP_MIN, Math.min(TEMP_MAX, number));
}

/** The temperature in ℃, or null when the learner chose 点燃 (no fixed value). */
export function temperatureCelsius(conditions) {
  const preset = tempPreset(conditions);
  if (preset.id === "custom") return clampTemp(conditions.customTemp);
  return preset.celsius;
}

/** How the temperature should read to a human and to the model. */
export function temperatureLabel(conditions) {
  const preset = tempPreset(conditions);
  if (preset.id === "custom") return `${clampTemp(conditions.customTemp)}℃`;
  if (preset.celsius === null) return preset.label;
  return `${preset.label}（约 ${preset.celsius}℃）`;
}

/** Only the axes the learner actually set. Untouched axes are omitted entirely
    so the model can report them as missing instead of assuming a value. */
export function conditionList(conditions) {
  const items = [temperatureLabel(conditions)];
  const environment = environmentOf(conditions);
  if (environment.id !== "dry") items.push(environment.label);
  const catalyst = catalystOf(conditions);
  if (catalyst.id !== "none") items.push(`催化剂:${catalyst.label}`);
  const pressure = pressureOf(conditions);
  if (pressure.id !== "normal") items.push(pressure.label);
  const ratio = ratioOf(conditions);
  if (ratio.id !== "balanced") items.push(ratio.label);
  for (const id of conditions.add) {
    const additive = ADDITIVES.find((item) => item.id === id);
    if (additive) items.push(additive.label);
  }
  return items;
}

export const conditionSentence = (conditions) => conditionList(conditions).join(" + ") || "常温";

/** Structured payload for the backend. Every axis is explicit, including
    whether the learner pinned an exact temperature. */
export function conditionPayload(conditions) {
  const celsius = temperatureCelsius(conditions);
  return {
    temp_label: temperatureLabel(conditions),
    temp_celsius: celsius,
    temp_is_exact: tempPreset(conditions).id === "custom",
    env: environmentOf(conditions).label,
    catalyst: catalystOf(conditions).id === "none" ? "" : catalystOf(conditions).label,
    catalyst_formula: catalystOf(conditions).formula,
    pressure: pressureOf(conditions).label,
    ratio: ratioOf(conditions).label,
    add: conditions.add
      .map((id) => ADDITIVES.find((item) => item.id === id)?.label)
      .filter(Boolean),
  };
}

/* Combinations that genuinely make no sense get a local nudge. This never
   blocks submission — the learner may still try and see why. */
export function conditionConflict(conditions, held) {
  const preset = tempPreset(conditions);
  const environment = environmentOf(conditions);
  const celsius = temperatureCelsius(conditions);

  if (preset.id === "ignite" && environment.id === "sealed") return "隔绝空气就点不着了";
  if (preset.id === "ignite" && environment.id === "aqueous") return "水溶液里点不着";
  if (environment.id === "aqueous" && celsius !== null && celsius > 100) {
    return "常压下水到 100℃ 就沸腾了，水溶液里到不了这个温度";
  }
  if (environment.id === "aqueous" && celsius !== null && celsius < 0) {
    return "水溶液在 0℃ 以下会结冰";
  }
  if (celsius !== null && celsius < 30 && catalystOf(conditions).id !== "none") {
    return "温度这么低，催化剂几乎不起作用";
  }
  const concentrated = held.filter((item) => item.variant === "浓");
  if (concentrated.length && environment.id === "aqueous") {
    const names = concentrated
      .map((item) => item.formula + (item.variant ? `(${item.variant})` : ""))
      .join("、");
    return `${names} 是浓的，放进水里就变稀了`;
  }
  return "";
}

/* Reactions where the SAME materials give different products at different
   temperatures. Shown as an inline nudge so the learner knows precision is the
   point here, without being told the answer. */
const TEMPERATURE_SENSITIVE = [
  {
    match: ["C₂H₅OH", "H₂SO₄"],
    note: "乙醇和浓硫酸在不同温度下产物完全不同，差 30℃ 就是两种物质 —— 试试填一个精确温度",
  },
  { match: ["Cl₂", "NaOH"], note: "氯气和碱在常温与加热下产物不同" },
  { match: ["C", "O₂"], note: "碳和氧气的产物取决于氧气够不够 —— 试试「配比」那一行" },
  { match: ["N₂", "H₂"], note: "合成氨要同时凑齐温度、压强和特定催化剂" },
];

/** A hint when the current materials are known to be condition-selective. */
export function selectivityHint(held) {
  if (held.length < 2) return "";
  const formulas = held.map((item) => item.formula);
  const entry = TEMPERATURE_SENSITIVE.find((candidate) =>
    candidate.match.every((needle) => formulas.some((formula) => formula.startsWith(needle))),
  );
  return entry ? entry.note : "";
}
