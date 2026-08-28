import { getAdventureProgress, getLessonOutcomeProgress } from "./story-engine.js";
import { AGENT_HISTORY_MAX_TURNS, AGENT_REQUEST_TIMEOUT_MS } from "./agent-limits.js";

const VALID_INTENTS = new Set([
  "travel", "help", "hide_coco", "greet_coco", "name_petshop_object", "place_object",
  "ask_baker", "order_food", "ask_teacher", "name_color", "inspect_clue",
  "inspect_town_clue", "town_observation", "find_coco", "clarify_tree",
  "care_coco", "open_story", "greet", "chat",
]);
const WORLD_LOCATIONS = new Set(["town", "petshop", "bakery", "school", "park", "storyhouse"]);
const FAST_LOCAL_INTENTS = new Set([
  "travel", "help", "hide_coco", "name_petshop_object", "place_object", "ask_baker", "order_food",
  "ask_teacher", "name_color", "inspect_clue", "inspect_town_clue",
  "town_observation", "find_coco", "care_coco", "open_story",
]);
const API_BASE = (import.meta.env?.VITE_MAGIC_TOWN_API_BASE ?? "").replace(/\/$/, "");

export function buildAgentContext(state) {
  const adventure = getAdventureProgress(state);
  return {
    story_id: state.storyId ?? "unknown-story",
    story_title: state.storyTitle ?? "Unknown story",
    story_runtime: state.storyRuntime ?? "magic-town-v1",
    story_premise: state.storyPremise ?? "",
    location: state.location,
    quest_stage: state.questStage,
    clues: [...state.clues],
    visited: [...state.visited],
    care_choice: state.careChoice,
    side_activities: [...state.sideActivities].slice(-20),
    object_positions: { ...(state.objectPositions ?? {}) },
    adventure_progress: {
      points: adventure.points,
      target: adventure.target,
      total: adventure.total,
      ready: adventure.ready,
      stage: state.questStage,
      rewarded_actions: [...(state.pointRewards ?? [])].filter((key) => key.startsWith(`${state.questStage}:`)).length,
      explored_areas: adventure.requirements.areas,
      missing: adventure.requirements.missing,
      english_turns: adventure.requirements.participation,
    },
    care_options: [...(state.careOptions ?? [])],
    learning_progress: {
      position_words: [...(state.mastery?.positionWords ?? [])],
      manners: [...(state.mastery?.manners ?? [])],
      colors: [...(state.mastery?.colors ?? [])],
      park_clues: [...(state.mastery?.parkClues ?? [])],
    },
    lesson_progress: getLessonOutcomeProgress(state).map((outcome) => ({
      id: outcome.id,
      title: outcome.title,
      count: outcome.count,
      required: outcome.required,
      complete: outcome.complete,
    })),
    recent_events: state.eventLog.slice(-10).map((item) => item.event),
  };
}

export function normalizeAgentResponse(value) {
  if (!value || typeof value !== "object" || !VALID_INTENTS.has(value.intent)) {
    throw new Error("The Town Agent returned an unknown action.");
  }
  if (typeof value.reply !== "string" || !value.reply.trim()) {
    throw new Error("The Town Agent returned no dialogue.");
  }
  const hasRequiredArgument = {
    travel: () => WORLD_LOCATIONS.has(value.destination),
    hide_coco: () => ["box", "table"].includes(value.destination),
    name_petshop_object: () => ["box", "table", "ball"].includes(value.object),
    place_object: () => new Set(["ball:on:table", "ball:in:box", "ball:under:table", "ball:on:floor"]).has(`${value.object}:${value.relation}:${value.destination}`),
    order_food: () => ["bread", "cake", "cookie"].includes(value.food),
    name_color: () => ["blue", "red", "yellow", "green"].includes(value.color),
    inspect_clue: () => ["tracks", "puddle", "bush"].includes(value.clue),
    care_coco: () => ["towel", "snack", "friends"].includes(value.care),
  }[value.intent];
  if (hasRequiredArgument && !hasRequiredArgument()) {
    throw new Error("The Town Agent omitted an action detail.");
  }
  return {
    ...value,
    understood: true,
    mode: "agent",
    speaker: typeof value.speaker === "string" ? value.speaker : "Milo",
    reply: value.reply.trim(),
    hint: typeof value.hint === "string" ? value.hint.trim() : "",
    recast: typeof value.recast === "string" ? value.recast.trim() : "",
  };
}

export function getSpokenReply(result, fallback = "") {
  const line = result?.mode === "agent" ? result.reply : fallback;
  return typeof line === "string" ? line.trim() : "";
}

export function canRunLocally(result) {
  return Boolean(result?.understood && FAST_LOCAL_INTENTS.has(result.intent));
}

export async function askWorldAgent({ message, source, state, history = [], timeout = AGENT_REQUEST_TIMEOUT_MS, signal = null }) {
  const controller = new AbortController();
  const cancelFromOutside = () => controller.abort();
  signal?.addEventListener("abort", cancelFromOutside, { once: true });
  const timer = setTimeout(() => controller.abort(), timeout);
  try {
    const response = await fetch(`${API_BASE}/api/demo/magic-town/agent`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message,
        source,
        context: buildAgentContext(state),
        history: history.slice(-AGENT_HISTORY_MAX_TURNS),
      }),
      signal: controller.signal,
    });
    if (!response.ok) throw new Error(`Town Agent unavailable (${response.status})`);
    return normalizeAgentResponse(await response.json());
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener("abort", cancelFromOutside);
  }
}
