/* Namespaced browser memory.
   localStorage is shared across the whole WeSmartFlow origin and is NOT scoped
   by path, so the key must carry both the demo namespace and a version.

   v2 added `materialsKey` and `conditions` to each discovery so the bench can
   tell that the SAME materials produced a different product at another
   temperature.
   v3 replaced the one-shot prediction counter with a `chat` transcript, so the
   assistant conversation survives a reload.
   Older payloads are migrated rather than discarded: a v1/v2 record simply has
   no transcript, and a v2 `predictions` count is folded into the goal it used to
   unlock so nobody loses a star they already earned. */

const STORAGE_KEY = "chemistry-lab:progress:v3";
const LEGACY_KEYS = ["chemistry-lab:progress:v2", "chemistry-lab:progress:v1"];
const MAX_DISCOVERIES = 120;
const MAX_EXTRA = 60;
const MAX_CHAT_TURNS = 60;
const CHAT_CONTENT_MAX = 800;

function emptyProgress() {
  return { discoveries: [], extra: [], quests: {}, chat: [] };
}

function readRaw() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) return JSON.parse(raw);
    for (const key of LEGACY_KEYS) {
      const legacy = localStorage.getItem(key);
      if (legacy) return JSON.parse(legacy);
    }
    return null;
  } catch {
    // Private mode or a corrupted payload: start from a clean bench.
    return null;
  }
}

function sanitizeDiscovery(item) {
  if (!item || typeof item !== "object") return null;
  const label = typeof item.label === "string" ? item.label.slice(0, 120) : "";
  if (!label) return null;
  return {
    reacts: Boolean(item.reacts),
    equation: typeof item.equation === "string" ? item.equation.slice(0, 160) : "",
    label,
    type: typeof item.type === "string" ? item.type.slice(0, 12) : "",
    materialsKey: typeof item.materialsKey === "string" ? item.materialsKey.slice(0, 200) : "",
    conditions: typeof item.conditions === "string" ? item.conditions.slice(0, 160) : "",
  };
}

function sanitizeExtra(item) {
  if (!Array.isArray(item) || typeof item[0] !== "string" || !item[0].trim()) return null;
  const entry = [item[0].slice(0, 40), typeof item[1] === "string" ? item[1].slice(0, 24) : item[0]];
  if (typeof item[2] === "string" && ["浓", "稀", "饱和"].includes(item[2])) entry.push(item[2]);
  return entry;
}

function sanitizeTurn(item) {
  if (!item || typeof item !== "object") return null;
  if (item.role !== "user" && item.role !== "assistant") return null;
  const content = typeof item.content === "string" ? item.content.trim().slice(0, CHAT_CONTENT_MAX) : "";
  if (!content) return null;
  const turn = { role: item.role, content };
  if (item.role === "assistant" && typeof item.suggestion === "string" && item.suggestion.trim()) {
    turn.suggestion = item.suggestion.trim().slice(0, 80);
  }
  return turn;
}

export function loadProgress() {
  const raw = readRaw();
  if (!raw || typeof raw !== "object") return emptyProgress();
  const quests = {};
  if (raw.quests && typeof raw.quests === "object") {
    for (const [id, value] of Object.entries(raw.quests)) {
      if (typeof id === "string" && value === true) quests[id] = true;
    }
  }
  // A pre-v3 learner who had already written a prediction keeps that goal.
  if (Number.isFinite(raw.predictions) && raw.predictions > 0) quests["talk-it-through"] = true;
  return {
    discoveries: (Array.isArray(raw.discoveries) ? raw.discoveries : [])
      .map(sanitizeDiscovery)
      .filter(Boolean)
      .slice(-MAX_DISCOVERIES),
    extra: (Array.isArray(raw.extra) ? raw.extra : [])
      .map(sanitizeExtra)
      .filter(Boolean)
      .slice(-MAX_EXTRA),
    quests,
    chat: (Array.isArray(raw.chat) ? raw.chat : [])
      .map(sanitizeTurn)
      .filter(Boolean)
      .slice(-MAX_CHAT_TURNS),
  };
}

export function saveProgress(progress) {
  try {
    localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({
        discoveries: progress.discoveries.slice(-MAX_DISCOVERIES),
        extra: progress.extra.slice(-MAX_EXTRA),
        quests: progress.quests,
        chat: progress.chat.slice(-MAX_CHAT_TURNS),
      }),
    );
  } catch {
    // Running out of quota must never break the bench.
  }
}

export function clearProgress() {
  try {
    localStorage.removeItem(STORAGE_KEY);
    for (const key of LEGACY_KEYS) localStorage.removeItem(key);
  } catch {
    // Nothing to clean up when storage is unavailable.
  }
}

/* Reasoning preference.
   Kept out of the progress payload on purpose: it is a setting for this browser,
   not something the learner earned, so "清空进度" must not silently reset it.
   `null` means "not chosen yet" — the page then adopts whatever the server
   reports as its default. */
const THINKING_KEY = "chemistry-lab:thinking";

export function loadThinking() {
  try {
    const raw = localStorage.getItem(THINKING_KEY);
    if (raw === "on") return true;
    if (raw === "off") return false;
    return null;
  } catch {
    return null;
  }
}

export function saveThinking(enabled) {
  try {
    localStorage.setItem(THINKING_KEY, enabled ? "on" : "off");
  } catch {
    // A preference that cannot be stored still applies to this session.
  }
}
