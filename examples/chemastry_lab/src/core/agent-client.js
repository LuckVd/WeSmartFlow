import { conditionList, conditionPayload, conditionSentence } from "./conditions.js";
import {
  AGENT_REQUEST_TIMEOUT_MS,
  CHAT_HISTORY_MAX_TURNS,
  CHAT_MESSAGE_MAX_CHARS,
  CHAT_TURN_MAX_CHARS,
  HEALTH_RETRIES,
  HEALTH_TIMEOUT_MS,
} from "./agent-limits.js";

const API_BASE = (import.meta.env?.VITE_CHEM_LAB_API_BASE ?? "").replace(/\/$/, "");
const ENDPOINT = `${API_BASE}/api/demo/chemistry-lab`;

const REACTION_TYPES = new Set([
  "化合反应", "分解反应", "置换反应", "复分解反应", "氧化还原反应", "其他", "",
]);
const PRODUCT_STATES = new Set(["固体", "液体", "气体", "沉淀", "溶液", ""]);
const VERDICTS = new Set(["need", "extra", "bad"]);
const SCOPES = new Set(["中学", "超纲"]);

/** Distinguish "slow" from "offline". A timeout means the engine is still
    there and this round was simply long; only a failed connection is offline. */
export class LabAgentError extends Error {
  constructor(kind, message, status = 0) {
    super(message);
    this.name = "LabAgentError";
    this.kind = kind; // "slow" | "http" | "offline"
    this.status = status;
  }
}

function text(value, limit) {
  return typeof value === "string" ? value.trim().slice(0, limit) : "";
}

export function normalizeReaction(value, submittedConditions = []) {
  if (!value || typeof value !== "object" || typeof value.reacts !== "boolean") {
    throw new LabAgentError("http", "化学引擎返回了无法识别的判定。");
  }
  const products = Array.isArray(value.products) ? value.products : [];
  const checks = Array.isArray(value.cond_check) ? value.cond_check : [];
  // The server already clamps this. Filtering again keeps the bench honest even
  // if an older or misconfigured backend echoes a condition nobody chose.
  const allowed = new Set(submittedConditions);
  const seenChecks = new Set();
  return {
    reacts: value.reacts,
    type: REACTION_TYPES.has(value.type) ? value.type || "" : "",
    equation: text(value.equation, 160),
    products: products
      .filter((item) => item && typeof item === "object")
      .map((item) => ({
        formula: text(item.formula, 40),
        name: text(item.name, 24),
        state: PRODUCT_STATES.has(item.state) ? item.state || "" : "",
        variant: ["浓", "稀", "饱和"].includes(item.variant) ? item.variant : "",
      }))
      .filter((item) => item.formula || item.name),
    phenomenon: text(value.phenomenon, 200),
    why: text(value.why, 200),
    // Labels the verdict as off-syllabus. It must never be why it "didn't react".
    scope: SCOPES.has(value.scope) ? value.scope : "中学",
    condChecks: checks
      .filter((item) => item && typeof item === "object")
      .map((item) => ({
        label: text(item.c, 12),
        verdict: VERDICTS.has(item.verdict) ? item.verdict : "extra",
        note: text(item.note, 16),
      }))
      .filter((item) => {
        if (!item.label || seenChecks.has(item.label)) return false;
        if (allowed.size && !allowed.has(item.label)) return false;
        seenChecks.add(item.label);
        return true;
      }),
    missing: text(value.missing, 120),
    danger: text(value.danger, 200),
    hint: text(value.hint, 160),
    // The server threw the verdict away for being chemically wrong. This is not
    // the same as "no reaction happens", so the page must not say that.
    unresolved: Boolean(value.unresolved),
  };
}

export function normalizeChat(value) {
  if (!value || typeof value !== "object" || typeof value.reply !== "string" || !value.reply.trim()) {
    throw new LabAgentError("http", "助手没有回话。");
  }
  return {
    reply: text(value.reply, 400),
    suggestion: text(value.suggestion, 80),
  };
}

function materialsPayload(held) {
  return held.map((item) => ({
    formula: item.formula,
    name: item.name || "",
    variant: item.variant || "",
  }));
}

function conditionsPayload(conditions) {
  return conditionPayload(conditions);
}

/** The exact condition labels the learner chose, in display order. Mirrors the
    server's `LabConditions.as_list` so both sides filter the same set. */
function submittedConditions(conditions) {
  return conditionList(conditions);
}

async function post(path, body, timeout, signal) {
  const controller = new AbortController();
  const cancelFromOutside = () => controller.abort();
  signal?.addEventListener("abort", cancelFromOutside, { once: true });
  const timer = setTimeout(() => controller.abort(), timeout);
  try {
    const response = await fetch(`${ENDPOINT}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: controller.signal,
    });
    if (!response.ok) {
      throw new LabAgentError("http", `化学引擎返回了错误（HTTP ${response.status}）。`, response.status);
    }
    return await response.json();
  } catch (error) {
    if (error instanceof LabAgentError) throw error;
    if (error?.name === "AbortError" || error?.name === "TimeoutError") {
      throw new LabAgentError("slow", `这次判定超过 ${Math.round(timeout / 1000)} 秒还没回来。`);
    }
    throw new LabAgentError("offline", "连不上 AI 化学引擎。");
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener("abort", cancelFromOutside);
  }
}

export async function askReaction({ held, conditions, vessel = "烧杯", tried = 1, thinking = null, signal = null }) {
  const raw = await post(
    "/react",
    {
      materials: materialsPayload(held),
      conditions: conditionsPayload(conditions),
      vessel,
      tried,
      // null lets the server keep its own default.
      thinking,
    },
    AGENT_REQUEST_TIMEOUT_MS,
    signal,
  );
  return normalizeReaction(raw, submittedConditions(conditions));
}

export async function askChat({
  message,
  held = [],
  conditions,
  history = [],
  lastReaction = null,
  thinking = null,
  signal = null,
}) {
  const body = {
    message: message.slice(0, CHAT_MESSAGE_MAX_CHARS),
    materials: materialsPayload(held),
    conditions: conditionsPayload(conditions),
    history: history.slice(-CHAT_HISTORY_MAX_TURNS).map((turn) => ({
      role: turn.role,
      content: turn.content.slice(0, CHAT_TURN_MAX_CHARS),
    })),
    thinking,
  };
  if (lastReaction) {
    body.reacted = lastReaction.reacts;
    body.last_equation = (lastReaction.equation || "").slice(0, 160);
    body.last_why = (lastReaction.why || "").slice(0, 200);
  }
  return normalizeChat(await post("/chat", body, AGENT_REQUEST_TIMEOUT_MS, signal));
}

/** Slow is not offline: retry a few short probes before declaring the engine down.
    Resolves to `{ ok, thinking }` so the page can adopt the server's default. */
export async function probeEngine(tries = HEALTH_RETRIES) {
  for (let attempt = tries; attempt > 0; attempt -= 1) {
    try {
      const response = await fetch(`${ENDPOINT}/health`, {
        signal: AbortSignal.timeout(HEALTH_TIMEOUT_MS),
      });
      if (!response.ok) throw new Error("unhealthy");
      const data = await response.json();
      return {
        ok: data?.status === "ok",
        thinking: typeof data?.thinking === "boolean" ? data.thinking : null,
      };
    } catch {
      if (attempt > 1) await new Promise((resolve) => setTimeout(resolve, 1_500));
    }
  }
  return { ok: false, thinking: null };
}

export const labelFor = (held, conditions) =>
  `${held.map((item) => item.formula + (item.variant ? `(${item.variant})` : "")).join(" + ")}（${conditionSentence(conditions)}）`;
