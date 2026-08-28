import { AGENT_HISTORY_MAX_TURNS, AGENT_REQUEST_TIMEOUT_MS } from "./agent-limits.js";

const API_BASE = (import.meta.env?.VITE_MAGIC_TOWN_API_BASE ?? "").replace(/\/$/, "");

const VALID_INTENTS = new Set([
  "travel", "order_treats", "design_flag", "locate_firefly", "guide_fireflies",
  "invite_friend", "light_lantern", "greet", "chat",
]);
const FESTIVAL_LOCATIONS = new Set(["town", "bakery", "school", "park", "storyhouse"]);
const FESTIVAL_FOODS = new Set(["cookie", "cake", "bread"]);
const FESTIVAL_COLORS = new Set(["blue", "yellow", "purple"]);
const FESTIVAL_SHAPES = new Set(["star", "moon", "circle"]);
const FESTIVAL_INVITEES = new Set(["Betty", "Ms. Maple", "Coco"]);
const FAST_LOCAL_INTENTS = new Set([
  "travel", "order_treats", "design_flag", "locate_firefly",
  "guide_fireflies", "invite_friend", "light_lantern",
]);

export function buildFestivalAgentContext(state) {
  return {
    story_id: state.storyId,
    story_title: state.storyTitle,
    story_premise: state.storyPremise,
    location: state.location,
    phase: state.phase,
    completed_tasks: [...state.completedTasks],
    visited: [...state.visited],
    treats: { ...state.treats },
    flag: { ...state.flag },
    fireflies_found: [...state.fireflies],
    selected_invitee: state.selectedInvitee,
    invited: [...state.invited],
    current_goal: state.guide?.hint ?? "",
    task_progress: {
      completed_count: state.completedTasks.size,
      fireflies_found: state.fireflies.size,
      fireflies_required: 3,
      invitation_complete: state.invited.size > 0,
      finale_ready: state.completedTasks.size >= 3 && state.invited.size > 0,
    },
    lesson_one_memory: state.lessonOneMemory ? {
      complete: Boolean(state.lessonOneMemory.complete),
      care_choice: state.lessonOneMemory.careChoice ?? null,
      child_lines: (state.lessonOneMemory.childLines ?? []).slice(0, 4),
    } : null,
  };
}

export function normalizeFestivalAgentResponse(value) {
  if (!value || typeof value !== "object" || !VALID_INTENTS.has(value.intent)) throw new Error("The Festival Agent returned an unknown action.");
  if (typeof value.reply !== "string" || !value.reply.trim()) throw new Error("The Festival Agent returned no dialogue.");
  const hasRequiredArgument = {
    travel: () => FESTIVAL_LOCATIONS.has(value.destination),
    order_treats: () => FESTIVAL_FOODS.has(value.food) && Number.isInteger(value.quantity) && value.quantity >= 1 && value.quantity <= 3,
    design_flag: () => FESTIVAL_COLORS.has(value.color) && FESTIVAL_SHAPES.has(value.shape),
    invite_friend: () => FESTIVAL_INVITEES.has(value.invitee),
  }[value.intent];
  if (hasRequiredArgument && !hasRequiredArgument()) throw new Error("The Festival Agent omitted an action detail.");
  return {
    ...value,
    reply: value.reply.trim(),
    hint: typeof value.hint === "string" ? value.hint.trim() : "",
    recast: typeof value.recast === "string" ? value.recast.trim() : "",
    mode: "agent",
  };
}

export function canRunFestivalLocally(result) {
  return Boolean(result && FAST_LOCAL_INTENTS.has(result.intent));
}

export async function askFestivalAgent({ message, source, state, history = [], signal = null, timeout = AGENT_REQUEST_TIMEOUT_MS }) {
  const controller = new AbortController();
  const abort = () => controller.abort();
  signal?.addEventListener("abort", abort, { once: true });
  const timer = setTimeout(() => controller.abort(), timeout);
  try {
    const response = await fetch(`${API_BASE}/api/demo/magic-town/festival-agent`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message,
        source,
        context: buildFestivalAgentContext(state),
        history: history.slice(-AGENT_HISTORY_MAX_TURNS),
      }),
      signal: controller.signal,
    });
    if (!response.ok) throw new Error(`Festival Agent unavailable (${response.status})`);
    return normalizeFestivalAgentResponse(await response.json());
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener("abort", abort);
  }
}
