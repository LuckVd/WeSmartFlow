import { escapeHtml, speak } from "../core/browser.js";
import { AGENT_HISTORY_MAX_TURNS, AGENT_HISTORY_TURN_MAX_CHARS } from "../core/agent-limits.js";
import { buildMoonlightFestivalMemory, getLessonMemory, restoreMoonlightFestivalMemory, saveLessonMemory } from "../core/course-memory.js";
import { getCourseStarsForLesson, renderCourseCompletion, renderCourseStars } from "../core/course-stars.js";
import { askFestivalAgent, canRunFestivalLocally } from "../core/festival-agent-client.js";
import { renderLessonInputDock } from "../core/lesson-input-dock.js";
import { getChallengeAccess, getSceneAccess } from "../core/scene-unlocks.js";
import { applyLearningChallengeReward, checkLearningAnswer, getLearningChallenge, resolveSpokenLearningAnswer } from "../core/learning-challenges.js";
import {
  FESTIVAL_CHALLENGES,
  FESTIVAL_COLORS,
  FESTIVAL_FOODS,
  FESTIVAL_INVITEES,
  FESTIVAL_RELICS,
  FESTIVAL_SHAPES,
  MOONLIGHT_LOCATIONS,
  applyFestivalResult,
  createMoonlightState,
  discoverFirefly,
  discoverFestivalSurprise,
  festivalOutcomeProgress,
  festivalProgress,
  festivalQuest,
  festivalRewardProgress,
  festivalTaskGuide,
  localFestivalIntent,
  moonlightPrompt,
  selectFlagPart,
  selectInvitee,
  selectTreat,
  startMoonlightLesson,
  visitMoonlightLocation,
} from "../core/moonlight-engine.js";
import { createSpeechInput } from "../core/speech-input.js";

const FOOD_ICONS = { cookie: "🍪", cake: "🧁", bread: "🥖" };
const SHAPE_ICONS = { star: "★", moon: "☾", circle: "●" };
const PERSON_ICONS = { Betty: "🥐", "Ms. Maple": "⭐", Coco: "🐶" };
const FESTIVAL_VOICE = { voice: "female", rate: 0.88, pitch: 1.1 };

function friendlyLocalResult(state, action, mode = "local") {
  const result = typeof action === "string" ? { intent: action } : action;
  const intent = result.intent;
  const destination = result.destination ?? state.location;
  const food = result.food ?? state.treats.food;
  const quantity = result.quantity ?? state.treats.quantity;
  const color = result.color ?? state.flag.color;
  const shape = result.shape ?? state.flag.shape;
  const invitee = result.invitee ?? state.selectedInvitee;
  const responses = {
    travel: ["Milo", `Let's explore ${MOONLIGHT_LOCATIONS[destination]}.`],
    order_treats: ["Betty", `${quantity} ${food}${quantity > 1 ? "s" : ""}—a kind choice for everyone!`],
    design_flag: ["Ms. Maple", `Your ${color} flag and ${shape} will shine in the square.`],
    locate_firefly: ["Coco", "Yes, you used a position word. Three little lights are hiding nearby!"],
    guide_fireflies: ["Coco", "They understand your two steps. Look—the lights are following us!"],
    invite_friend: [invitee, "I would love to come! What will we see at the festival?"],
    light_lantern: ["Milo", "Your words brought every part of the town together. The Moon Lantern is awake!"],
    greet: [state.location === "bakery" ? "Betty" : state.location === "school" ? "Ms. Maple" : "Coco", "Hello, festival helper! I'm glad you're here."],
    chat: ["Milo", "I like that idea. Tell me a little more, or try it in the world around you."],
  };
  const [speaker, reply] = responses[intent] ?? responses.chat;
  return { ...result, intent, speaker, reply, hint: "", recast: "", mode };
}

export function createMoonlightFestivalApp({ root, story }) {
  const state = restoreMoonlightFestivalMemory(
    createMoonlightState(story, getLessonMemory("missing-puppy")),
    getLessonMemory(story.id),
  );
  let memoryOpen = false;
  let memoryStudioOpen = false;
  let memoryPage = 0;
  let finaleRewardOpen = false;
  let memoryStudioMessage = "";
  let memoryStudioVoiceBase = "";
  let questOpen = false;
  let welcomeOpen = false;
  let rewardReveal = null;
  let voiceText = "";
  let agentController = null;
  let agentRunId = 0;
  let agentBusy = false;
  let agentCancelled = false;
  let agentStatus = "ready";
  let lastHeard = "";
  let restoreInputFocus = false;
  let ignoreNextVoiceFinal = false;
  let voiceSubmitting = false;
  let festivalInputDraft = "";

  const speechInput = createSpeechInput({
    onStart: () => {
      voiceSubmitting = false;
      if (memoryStudioOpen) {
        updateMemoryStudioVoiceSurface("Listening… Tell this page in your own words.", true, "");
        return;
      }
      voiceText = state.learning.activeId ? "Listening for your answer…" : "Listening…";
      if (!state.learning.activeId) festivalInputDraft = "";
      render();
    },
    onPartial: (text) => {
      if (memoryStudioOpen) {
        updateMemoryStudioVoiceSurface(text || "Listening…", true, text);
        return;
      }
      voiceText = text || "Listening…";
      updateVoiceSurface(state.learning.activeId ? null : text);
    },
    onSubmitStart: (text) => {
      if (memoryStudioOpen) {
        updateMemoryStudioVoiceSurface("Adding your words to this page…", false, text, true);
        return;
      }
      voiceSubmitting = true;
      voiceText = state.learning.activeId ? "Checking your answer…" : "Waiting for your words…";
      render();
    },
    onFinal: (text, alternatives = []) => {
      voiceSubmitting = false;
      if (ignoreNextVoiceFinal) { ignoreNextVoiceFinal = false; return; }
      if (text && memoryStudioOpen) {
        const line = `${memoryStudioVoiceBase}${memoryStudioVoiceBase && text ? " " : ""}${text}`.trim();
        saveMemoryStudioLine(line);
        memoryStudioMessage = "Your spoken words are saved on this page.";
        render();
        globalThis.requestAnimationFrame?.(() => root.querySelector("#moon-story-input")?.focus());
        return;
      }
      voiceText = state.learning.activeId ? "" : text ? "Waiting for Coco’s reply…" : "";
      if (text && state.learning.activeId) {
        const challenge = getLearningChallenge(story, state.learning.activeId);
        const question = challenge?.questions[state.learning.questionIndex];
        const candidates = [text, ...alternatives].filter((candidate, index, all) => candidate && all.indexOf(candidate) === index);
        const resolved = candidates.map((candidate) => resolveSpokenLearningAnswer(question, candidate));
        const answer = resolved.find((candidate) => checkLearningAnswer(question, candidate).correct) ?? resolved[0] ?? text;
        state.learning.voiceHeard = text;
        handleFestivalChallengeAnswer(answer);
        return;
      }
      if (text) {
        festivalInputDraft = text;
        void runInput(text, "voice");
      }
    },
    onEnd: (text) => {
      if (memoryStudioOpen && !text) { voiceSubmitting = false; memoryStudioMessage = "Tap the microphone when you are ready, or keep typing."; render(); return; }
      if (!text) { voiceSubmitting = false; voiceText = ""; render(); }
    },
    onError: (message) => {
      voiceSubmitting = false;
      if (memoryStudioOpen) { memoryStudioMessage = message; render(); return; }
      voiceText = message;
      render();
    },
  });

  function render() {
    const focusedId = root.contains(root.ownerDocument?.activeElement) ? root.ownerDocument.activeElement.id : "";
    const shouldRestoreInput = restoreInputFocus || focusedId === "festival-input";
    if (state.phase === "bridge") {
      root.innerHTML = renderBridge();
      return;
    }
    const progress = festivalProgress(state);
    root.innerHTML = `
      <main class="moon-app time-${state.time} place-${state.location} phase-${state.phase}" aria-busy="${state.busy || agentBusy}">
        ${renderHeader(progress)}
        <div class="moon-layout">
          <section class="moon-world" aria-label="${escapeHtml(MOONLIGHT_LOCATIONS[state.location])}">
            ${renderWorld()}
            ${renderLocationRail()}
          </section>
          ${renderCompanionPanel(progress)}
        </div>
        ${renderWelcomeGuide()}
        ${questOpen ? renderQuestMap() : ""}
        ${state.learning.activeId ? renderFestivalChallenge() : ""}
        ${rewardReveal ? renderRewardReveal() : ""}
        ${finaleRewardOpen ? renderFinaleReward() : ""}
        ${memoryStudioOpen ? renderMemoryStudio() : ""}
        ${memoryOpen ? renderMemory() : ""}
      </main>`;
    updateVoiceSurface();
    saveLessonMemory(story.id, buildMoonlightFestivalMemory(state));
    if (shouldRestoreInput && !agentBusy && !state.learning.activeId && state.phase !== "celebration") {
      restoreInputFocus = false;
      globalThis.requestAnimationFrame?.(() => root.querySelector("#festival-input")?.focus());
    } else if (shouldRestoreInput) {
      restoreInputFocus = true;
    }
  }

  function renderWelcomeGuide() {
    if (!welcomeOpen || state.location !== "town" || state.completedTasks.size) return "";
    return `<aside class="first-steps-card moon-first-steps" aria-label="How to start Lesson 2">
      <button class="first-steps-close" data-action="coach-close" aria-label="Close the welcome guide">×</button>
      <span class="first-steps-milo moon-first-steps-guide" aria-hidden="true">☾</span>
      <div><small>LESSON 2 · A FIVE-STEP STORY</small><strong>One clear step at a time.</strong><p>Restore three magics, invite a friend, then wake the Moon Lantern with your English.</p></div>
      <button class="first-steps-go moon-first-steps-go" data-location="bakery"><span>🥐</span><strong>Find Kindness</strong><small>Start at Moonbeam Bakery</small></button>
      <button class="first-steps-free" data-action="coach-close">I want to look around</button>
    </aside>`;
  }

  function renderBridge() {
    const memory = state.lessonOneMemory;
    const care = {
      towel: ["a warm scarf", "You kept me warm when I was wet."],
      snack: ["a little treat bag", "You shared food with me when I was hungry."],
      friends: ["a brave star badge", "You helped me feel brave with my friends."],
    }[memory?.careChoice] ?? ["my story ribbon", "You helped me find my way home."];
    return `<main class="moon-bridge">
      <a class="bridge-back" href="./index.html">← All lessons</a>
      <div class="bridge-book"><i></i><i></i><div class="bridge-page"><small>THE LAST PAGE OF LESSON 1</small><h1>Coco was home.</h1><p>${escapeHtml(memory?.childLines?.at(-1) || "Finally, Coco was safe with his friend.")}</p><span>But outside the Story House, the sky was changing…</span></div></div>
      <div class="bridge-sunset"><span class="setting-sun"></span><div class="bridge-town"><i></i><i></i><i></i><i></i></div><div class="bridge-coco">${renderCoco()}<small>${escapeHtml(care[0])}</small></div></div>
      <section class="bridge-copy"><p>LESSON 2 · THE STORY CONTINUES</p><h2>The town remembers you.</h2><blockquote>“${escapeHtml(care[1])}<br />Tonight, let's help the whole town!”</blockquote><button data-action="start">Step into the sunset <span>→</span></button></section>
    </main>`;
  }

  function renderHeader(progress) {
    const quest = festivalQuest(state);
    const optionalPractice = renderOptionalPractice();
    const courseHome = state.location === "town"
      ? `<a class="moon-brand moon-town-home town-home-link" href="./index.html" aria-label="Return to Magic English Town course home" title="Back to Magic English Town"><span class="town-home-mark"><i></i><i></i><i></i></span><span class="town-home-copy"><strong>Magic English Town</strong><small>Town Square</small></span><span class="town-home-cue" aria-hidden="true"><b>←</b><small>Town</small></span></a>`
      : `<span class="moon-home-space" aria-hidden="true"></span>`;
    return `<header class="moon-header floating-hud">
      ${courseHome}
      <div class="moon-quest-stack">
        <button class="moon-progress main-story-pill" data-action="quest" aria-label="Open the Moon Lantern main story"><span><i style="--progress:${progress.percent}%"></i></span><p><small>MAIN STORY · ${quest.chapter}/${quest.totalChapters}</small><strong>${escapeHtml(quest.title)}</strong></p><b>Story map →</b></button>
        ${optionalPractice ? `<div class="optional-challenge-slot hud-optional-challenge moon-hud-optional-challenge">${optionalPractice}</div>` : ""}
      </div>
    </header>`;
  }

  function renderLocationRail() {
    const places = [
      ["town", "⌂", "Square"], ["bakery", "🥐", "Bakery"], ["school", "☆", "School"], ["park", "♧", "Park"], ["storyhouse", "▤", "Stories"],
    ];
    return `<nav class="moon-rail" aria-label="Explore the evening town">${places.map(([id, icon, label]) => {
      const access = getSceneAccess(state, id);
      return `<button ${access.unlocked ? `data-location="${id}"` : "disabled"} title="${escapeHtml(access.unlocked ? label : access.reason)}" class="${state.location === id ? "active" : ""} ${state.completedTasks.has(id) ? "complete" : ""} ${access.unlocked ? "" : "locked"}"><span>${state.completedTasks.has(id) ? "✓" : access.unlocked ? icon : "🔒"}</span><small>${label}</small></button>`;
    }).join("")}</nav>`;
  }

  function renderWorld() {
    if (state.location === "bakery") return renderBakery();
    if (state.location === "school") return renderSchool();
    if (state.location === "park") return renderPark();
    if (state.location === "storyhouse") return renderStoryHouse();
    return renderTown();
  }

  function renderTown() {
    const celebration = state.phase === "celebration";
    const finale = state.phase === "finale";
    return `<div class="festival-scene town-festival ${celebration ? "is-lit" : ""}">
      <div class="moon-sky"><i></i><i></i><span></span></div>
      ${celebration ? renderFestivalFireworks() : ""}
      <div class="town-silhouette"><i></i><i></i><i></i><i></i><i></i></div>
      <div class="festival-square-ground"></div>
      ${renderTownDestinations()}
      <div class="moon-lantern ${celebration ? "lit" : ""}"><i></i><span>★</span><small>${celebration ? "YOUR ENGLISH LIGHT" : "THREE TOWN MAGICS"}</small></div>
      ${isSecretUnlocked("school") ? `<button class="festival-flags town-secret ${state.surprisesFound.has("school") ? "secret-found" : "secret-ready"}" data-surprise="school" aria-label="Explore the Moon Ribbon surprise"><i class="${state.flag.color}">${SHAPE_ICONS[state.flag.shape]}</i><i class="${state.flag.color}">${SHAPE_ICONS[state.flag.shape]}</i><i class="${state.flag.color}">${SHAPE_ICONS[state.flag.shape]}</i><b>${state.surprisesFound.has("school") ? "✓" : "?"}</b></button>` : ""}
      ${isSecretUnlocked("bakery") ? `<button class="festival-table town-secret ${state.surprisesFound.has("bakery") ? "secret-found" : "secret-ready"}" data-surprise="bakery" aria-label="Explore Betty's Moon Cake surprise"><span>${Array.from({ length: state.treats.quantity }, () => FOOD_ICONS[state.treats.food]).join("")}</span><small>Betty's sharing table</small><b>${state.surprisesFound.has("bakery") ? "✓ secret found" : "? tap for a secret"}</b></button>` : ""}
      ${isSecretUnlocked("park") ? `<button class="town-fireflies town-secret ${state.surprisesFound.has("park") ? "secret-found" : "secret-ready"}" data-surprise="park" aria-label="Explore the Firefly Constellation surprise">${Array.from({ length: celebration ? 10 : 5 }, (_, index) => `<i style="--i:${index};--firefly-x:${(index * 17 + 4) % 84}%;--firefly-y:${(index * 29) % 68}%"></i>`).join("")}<b>${state.surprisesFound.has("park") ? "✓" : "?"}</b></button>` : ""}
      <div class="town-coco ${celebration ? "celebrate" : ""}">${renderCoco()}<small>${celebration ? "We lit the town!" : finale ? "Everything is here!" : "Where first?"}</small></div>
      ${celebration ? `<div class="festival-guests" aria-label="Everyone celebrating together"><span>👩‍🍳<small>Betty</small></span><span>👩‍🏫<small>Ms. Maple</small></span><span>🧙<small>Milo</small></span><span>🐶<small>Coco</small></span></div>` : ""}
      <div class="scene-title"><p>${celebration ? "THE FESTIVAL IS ALIVE" : "TOWN SQUARE"}</p><h1>${celebration ? "Your words became moonlight." : finale ? "Bring the whole town together." : "The Moon Lantern is still dark."}</h1></div>
    </div>`;
  }

  function renderFestivalFireworks() {
    const bursts = [
      ["18%", "17%", "#ffd968", "0s"],
      ["42%", "11%", "#ff8eb3", ".65s"],
      ["69%", "18%", "#87e4ff", "1.3s"],
      ["84%", "9%", "#c8a4ff", "2s"],
    ];
    return `<div class="festival-fireworks" aria-hidden="true">${bursts.map(([x, y, color, delay]) => `<span class="festival-firework" style="--x:${x};--y:${y};--firework-color:${color};--delay:${delay}">${Array.from({ length: 12 }, (_, ray) => `<i style="--ray:${ray}"></i>`).join("")}</span>`).join("")}</div><div class="festival-confetti" aria-hidden="true">${Array.from({ length: 18 }, (_, index) => `<i style="--piece:${index}"></i>`).join("")}</div>`;
  }

  function renderTownDestinations() {
    const target = festivalQuest(state).targetLocation;
    const places = [
      ["bakery", "🥐", "Moonbeam Bakery", "Kindness Magic"],
      ["school", "☆", "Star School", "Color Magic"],
      ["park", "✨", "Whispering Park", "Light Magic"],
    ];
    return `<nav class="moon-town-destinations" aria-label="Choose a place in Town Square">${places.map(([id, icon, label, note]) => {
      const complete = state.completedTasks.has(id);
      const access = getSceneAccess(state, id);
      const recommended = target === id && !complete;
      const status = complete ? "Done" : access.unlocked ? recommended ? "Next" : "Open" : "Locked";
      return `<button ${access.unlocked ? `data-location="${id}"` : "disabled"} class="${recommended ? "featured" : ""} ${complete ? "complete" : ""} ${access.unlocked ? "" : "locked"}" aria-label="${escapeHtml(`${label} · ${status}`)}"><span>${complete ? "✓" : access.unlocked ? icon : "🔒"}</span><p><strong>${escapeHtml(label)}</strong><small>${complete ? `${note} restored` : access.unlocked ? recommended ? `NEXT STORY STOP · ${note}` : `OPEN TO EXPLORE · ${note}` : access.reason}</small></p><i>${status}</i></button>`;
    }).join("")}</nav>`;
  }

  function renderBakery() {
    return `<div class="festival-scene bakery-festival ${state.completedTasks.has("bakery") ? "scene-complete" : ""}">
      <div class="bakery-window"><i></i><span>☾</span></div><div class="bakery-awning"></div><div class="bakery-counter"></div>
      <div class="betty-character"><span>👩‍🍳</span><small>Betty remembers you</small></div>
      <div class="treat-shelf">${FESTIVAL_FOODS.map((food) => `<button data-treat="${food}" class="${state.treats.food === food ? "selected" : ""}"><span>${FOOD_ICONS[food]}</span><strong>${food}</strong></button>`).join("")}</div>
      <div class="quantity-tray"><small>HOW MANY?</small>${[1, 2, 3].map((number) => `<button data-quantity="${number}" class="${state.treats.quantity === number ? "selected" : ""}">${number}</button>`).join("")}</div>
      ${state.completedTasks.has("bakery") ? `<div class="world-reward"><span>✓</span><p><small>KINDNESS MAGIC</small><strong>${state.treats.quantity} ${state.treats.food}${state.treats.quantity > 1 ? "s" : ""} packed to share</strong></p></div>` : ""}
      <div class="scene-title"><p>MOONBEAM BAKERY</p><h1>${state.completedTasks.has("bakery") ? "The sharing basket is ready." : "Ask kindly for a festival treat."}</h1></div>
    </div>`;
  }

  function renderSchool() {
    return `<div class="festival-scene school-festival ${state.completedTasks.has("school") ? "scene-complete" : ""}">
      <div class="school-window"><span>☾</span><i></i></div><div class="class-board"><small>WELCOME HOME, COCO!</small><i></i><i></i></div>
      <div class="map-memory"><span>🐾 → 🌳</span><small>The Lesson 1 clue map</small></div>
      <div class="flag-workbench"><div class="flag-preview color-${state.flag.color}"><span>${SHAPE_ICONS[state.flag.shape]}</span><i></i></div><div class="flag-controls"><small>COLOR</small>${FESTIVAL_COLORS.map((color) => `<button data-flag-color="${color}" class="color-${color} ${state.flag.color === color ? "selected" : ""}" aria-label="${color}"></button>`).join("")}<small>SHAPE</small>${FESTIVAL_SHAPES.map((shape) => `<button data-flag-shape="${shape}" class="${state.flag.shape === shape ? "selected" : ""}">${SHAPE_ICONS[shape]}</button>`).join("")}</div></div>
      <div class="maple-character"><span>👩‍🏫</span><small>Ms. Maple</small></div>
      ${state.completedTasks.has("school") ? `<div class="world-reward"><span>✓</span><p><small>COLOR MAGIC</small><strong>Your ${state.flag.color} ${state.flag.shape} flag is ready</strong></p></div>` : ""}
      <div class="scene-title"><p>STAR SCHOOL</p><h1>${state.completedTasks.has("school") ? "Your design will fly above the square." : "Make something the town has never seen."}</h1></div>
    </div>`;
  }

  function renderPark() {
    const found = state.fireflies;
    return `<div class="festival-scene park-festival ${state.completedTasks.has("park") ? "scene-complete" : ""}">
      <div class="park-moon"></div><div class="old-tree"><i></i><i></i><i></i></div><div class="park-bush"></div><div class="park-fountain"><i></i></div>
      <button class="find-firefly at-tree ${found.has("tree") ? "found" : ""}" data-firefly="tree" aria-label="Firefly behind the old tree"><i></i><small>${found.has("tree") ? "behind the tree" : "?"}</small></button>
      <button class="find-firefly at-bush ${found.has("bush") ? "found" : ""}" data-firefly="bush" aria-label="Firefly under the bush"><i></i><small>${found.has("bush") ? "under the bush" : "?"}</small></button>
      <button class="find-firefly at-fountain ${found.has("fountain") ? "found" : ""}" data-firefly="fountain" aria-label="Firefly next to the fountain"><i></i><small>${found.has("fountain") ? "next to the fountain" : "?"}</small></button>
      <div class="park-coco brave">${renderCoco()}<small>I'm not scared here now.</small></div>
      ${state.completedTasks.has("park") ? `<div class="world-reward"><span>✓</span><p><small>LIGHT MAGIC</small><strong>The fireflies know your route</strong></p></div>` : ""}
      <div class="scene-title"><p>WHISPERING PARK · THE OLD TREE</p><h1>${state.completedTasks.has("park") ? "The old tree glows with a new memory." : found.size < 3 ? `Find ${3 - found.size} hidden light${3 - found.size === 1 ? "" : "s"}.` : "Now give the fireflies two directions."}</h1></div>
    </div>`;
  }

  function renderStoryHouse() {
    const lines = state.lessonOneMemory?.childLines ?? [];
    return `<div class="festival-scene storyhouse-festival"><div class="story-shelves"><i></i><i></i><i></i><i></i><i></i></div><div class="open-memory-book"><small>LESSON 1 · YOUR WORDS</small><p>${escapeHtml(lines.at(-1) || "I found Coco and helped him go home.")}</p><span>☾</span></div><div class="milo-story"><span>🧙</span><small>Milo</small></div><div class="scene-title"><p>STORY HOUSE</p><h1>Yesterday's story opened tonight's world.</h1></div></div>`;
  }

  function renderCompanionPanel(progress) {
    const finale = state.location === "town" && state.phase === "finale";
    const task = festivalTaskGuide(state);
    const guideIcon = state.guide.speaker === "Coco" ? "🐶" : state.guide.speaker === "Betty" ? "🥐" : state.guide.speaker === "Ms. Maple" ? "⭐" : "✦";
    const agentLabels = {
      ready: "Agent ready",
      instant: "Instant response",
      waiting: "Waiting for reply",
      online: "Agent connected",
      fallback: "Local mode",
    };
    return `<aside class="moon-companion moon-world-dock lesson-action-dock" aria-label="Current task and English input">
      <section class="moon-dock-guide lesson-dock-guide">
        <span>${guideIcon}</span>
        <p><small>${escapeHtml(state.guide.speaker)} · YOUR GUIDE<span class="agent-presence state-${agentStatus}"><i></i>${agentLabels[agentStatus]}</span></small><strong>${escapeHtml(state.guide.reply)}</strong><em>${escapeHtml(task.detail)}</em></p>
      </section>
      <section class="moon-task-card lesson-task-card kind-${task.kind}">
        <header><small>${escapeHtml(task.eyebrow)}</small><b>${escapeHtml(task.progress)}</b></header>
        <h2><span>${task.icon}</span>${escapeHtml(task.title)}</h2>
        <p>${escapeHtml(task.detail)}</p>
        <div class="moon-task-steps lesson-task-steps">${task.steps.map((step) => `<span>${escapeHtml(step)}</span>`).join("")}</div>
        ${renderTaskAction(task, finale)}
      </section>
      <section class="moon-dock-actions lesson-dock-actions">
        ${state.phase === "celebration" ? renderCelebrationActions() : `${renderInputDock(task)}<div class="optional-challenge-slot dock-optional-challenge moon-dock-optional-challenge">${renderOptionalPractice()}</div>`}
      </section>
    </aside>`;
  }

  function renderTaskAction(task, finale) {
    if (task.kind === "travel") return `<button class="moon-task-primary lesson-task-primary" data-location="${task.targetLocation}">${escapeHtml(task.actionLabel)} · ${escapeHtml(MOONLIGHT_LOCATIONS[task.targetLocation])} <span>→</span></button>`;
    if (task.kind === "tap") return `<div class="moon-task-tap-note"><span>👆</span><strong>${escapeHtml(task.actionLabel)}</strong><small>${escapeHtml(task.example)}</small></div>`;
    const controls = renderContextControls(finale);
    if (controls) return `<div class="moon-task-controls">${controls}</div>`;
    return `<div class="moon-task-example"><small>${escapeHtml(task.actionLabel)}</small><strong>“${escapeHtml(task.example)}”</strong></div>`;
  }

  function renderContextControls(finale) {
    if (finale && !state.invited.size) return `<div class="invite-picker"><small>1 · CHOOSE A FRIEND</small>${FESTIVAL_INVITEES.map((person) => `<button data-invitee="${person}" class="${state.selectedInvitee === person ? "selected" : ""}"><span>${PERSON_ICONS[person]}</span>${escapeHtml(person)}</button>`).join("")}</div><button class="sentence-seed invitation-seed" data-suggestion="${escapeHtml(state.selectedInvitee)}, would you like to come to the festival?">2 · Build my invitation →</button>`;
    if (state.location === "bakery" && !state.completedTasks.has("bakery")) return `<button class="sentence-seed" data-suggestion="Can I have ${state.treats.quantity} ${state.treats.food}${state.treats.quantity > 1 ? "s" : ""}, please?">Build my kind request →</button>`;
    if (state.location === "school" && !state.completedTasks.has("school")) return `<button class="sentence-seed" data-suggestion="My flag is ${state.flag.color}. It has a ${state.flag.shape} on it.">Describe my flag →</button>`;
    if (state.location === "park" && state.fireflies.size >= 3 && !state.completedTasks.has("park")) return `<button class="sentence-seed" data-suggestion="First fly to the fountain, then go to the lantern.">Build two directions →</button>`;
    if (finale && state.invited.size) return `<button class="sentence-seed" data-suggestion="First put up the ${state.flag.color} flag, then bring the fireflies to the lantern.">Build the final instruction →</button>`;
    return "";
  }

  function isSecretUnlocked(location) {
    return state.completedTasks.has(location) && state.learning.completed.has(FESTIVAL_CHALLENGES[location]);
  }

  function renderOptionalPractice() {
    const challengeId = FESTIVAL_CHALLENGES[state.location];
    if (!challengeId) return "";
    const challenge = getLearningChallenge(story, challengeId);
    const access = getChallengeAccess(story, state, challengeId);
    const complete = state.learning.completed.has(challengeId);
    const taskComplete = state.completedTasks.has(state.location);
    const reward = FESTIVAL_RELICS[state.location];
    if (!access.unlocked) return `<i class="scene-practice-locked"><span>🔒</span><b>Optional challenge waits for the story</b><small>${escapeHtml(access.reason)}</small></i>`;
    if (complete && taskComplete) return `<button type="button" class="scene-practice surprise-challenge complete" data-location="town"><span>🎁</span><p><b>Easter egg ready · ${escapeHtml(reward.relic)}</b><small>Hidden in Town Square</small></p><i>Find →</i></button>`;
    if (complete) return `<i class="scene-practice-complete">✓ Optional challenge complete · finish this task to reveal ${escapeHtml(reward.relic)}</i>`;
    return `<button type="button" class="scene-practice surprise-challenge" data-challenge="${challengeId}"><span>🎁</span><p><b>Optional challenge · Easter egg trail</b><small>${challenge.questions.length} questions · unlock ${escapeHtml(reward.relic)}</small></p><i>Start →</i></button>`;
  }

  function renderQuestMap() {
    const quest = festivalQuest(state);
    const rewards = festivalRewardProgress(state);
    const chapters = [
      ["🥐", "Share Kindness", "Choose treats and ask Betty politely", state.completedTasks.has("bakery"), quest.targetLocation === "bakery"],
      ["☆", "Create Color", "Design and describe Coco's welcome flag", state.completedTasks.has("school"), quest.targetLocation === "school"],
      ["✨", "Guide Light", "Find the fireflies and give two directions", state.completedTasks.has("park"), quest.targetLocation === "park"],
      ["💌", "Invite a friend", "Bring everyone together in Town Square", state.invited.size > 0, state.completedTasks.size === 3 && !state.invited.size],
      ["🏮", "Wake the lantern", "Give the final First…, then… plan", state.phase === "celebration", state.invited.size > 0 && state.phase !== "celebration"],
    ];
    return `<div class="moon-quest-backdrop"><article class="moon-quest-map" role="dialog" aria-modal="true" aria-labelledby="moon-quest-title">
      <button class="quest-close" data-action="quest-close" aria-label="Close story map">×</button>
      <header><span>☾</span><p><small>LESSON 2 · MAIN STORY</small><strong id="moon-quest-title">The Moon Lantern Quest</strong></p></header>
      <blockquote>Coco's welcome-home festival follows five clear story steps. Each new place unlocks when the previous town magic is restored.</blockquote>
      <section class="quest-chapter-path five-steps">${chapters.map(([icon, title, note, complete, current]) => `<div class="${complete ? "complete" : current ? "current" : ""}"><span>${complete ? "✓" : icon}</span><p><strong>${escapeHtml(title)}</strong><small>${escapeHtml(note)}</small></p></div>`).join("")}</section>
      <section class="quest-current-card"><small>${escapeHtml(quest.kicker)}</small><h2>${escapeHtml(quest.title)}</h2><p>${escapeHtml(quest.story)}</p></section>
      <section class="quest-reward-shelf"><header><p><small>OPTIONAL EASTER EGG TRAIL</small><strong>Three-question challenges reveal surprises in the Square</strong></p><span>${rewards.found.length}/${rewards.total} found</span></header><div>${Object.entries(FESTIVAL_RELICS).map(([id, reward]) => {
        const earned = state.completedTasks.has(id);
        const unlocked = isSecretUnlocked(id);
        const found = state.surprisesFound.has(id);
        const sceneAccess = getSceneAccess(state, id);
        const destination = unlocked ? "town" : id;
        const canOpen = getSceneAccess(state, destination).unlocked;
        return `<button ${canOpen ? `data-location="${destination}"` : "disabled"} class="${unlocked ? "unlocked" : "locked"} ${earned ? "earned" : ""} ${found ? "found" : ""}"><span>${earned ? reward.icon : "?"}</span><p><strong>${earned ? escapeHtml(reward.relic) : "Hidden Easter egg"}</strong><small>${found ? "Easter egg discovered!" : unlocked ? "Your Easter egg is waiting in the Square" : earned ? "Complete the optional 3-question challenge to reveal it" : escapeHtml(sceneAccess.reason || `Restore ${reward.magic} first`)}</small></p><i>${canOpen ? "→" : "🔒"}</i></button>`;
      }).join("")}</div></section>
      <footer><button class="quest-soft-action" data-action="quest-close">Keep exploring</button><button class="quest-primary-action" data-action="quest-go" data-target="${quest.targetLocation}">${escapeHtml(quest.cta)} <span>→</span></button></footer>
    </article></div>`;
  }

  function renderRewardReveal() {
    const reward = FESTIVAL_RELICS[rewardReveal.id];
    const surprise = rewardReveal.kind === "surprise";
    const challengeId = FESTIVAL_CHALLENGES[rewardReveal.id];
    const challengeComplete = state.learning.completed.has(challengeId);
    const nextLocation = Object.keys(FESTIVAL_RELICS).find((id) => !state.completedTasks.has(id)) ?? "town";
    const nextLabel = nextLocation === "town" ? "Carry all three magics to the Square" : `Continue to ${MOONLIGHT_LOCATIONS[nextLocation]}`;
    return `<div class="moon-reward-backdrop"><article class="moon-reward-reveal" role="dialog" aria-modal="true" aria-labelledby="moon-reward-title">
      <div class="reward-rays"></div><span class="reward-relic-icon">${reward.icon}</span>
      <small>${surprise ? "EASTER EGG FOUND · +2 MOON STARS" : `${escapeHtml(reward.magic)} RESTORED · ${state.completedTasks.size}/3`}</small>
      <h2 id="moon-reward-title">${surprise ? escapeHtml(reward.relic) : `${escapeHtml(reward.magic)} is glowing!`}</h2>
      <p>${surprise ? "The town rewarded your curiosity. This Easter egg is now part of your festival night." : challengeComplete ? `Main story step complete. Your optional ${escapeHtml(reward.relic)} Easter egg is now ready in Town Square.` : `Main story step complete. Continue now—or answer three optional questions to reveal the ${escapeHtml(reward.relic)} Easter egg.`}</p>
      <div class="reward-lantern-slots">${Object.entries(FESTIVAL_RELICS).map(([id, item]) => `<i class="${state.completedTasks.has(id) ? "lit" : ""}">${state.completedTasks.has(id) ? item.icon : "◇"}</i>`).join("")}</div>
      <div class="moon-reward-actions">
        ${!surprise && !challengeComplete ? `<button class="reward-bonus-action" data-action="reward-practice" data-challenge="${challengeId}">🎁 Unlock the ${escapeHtml(reward.relic)} <small>Optional · 3 questions · Easter egg reward</small></button>` : ""}
        <button data-action="reward-next" data-target="${surprise ? "town" : nextLocation}">${surprise ? "Back to the festival" : escapeHtml(nextLabel)} <span>→</span></button>
      </div>
    </article></div>`;
  }

  function renderFestivalChallenge() {
    const learning = state.learning;
    const challenge = getLearningChallenge(story, learning.activeId);
    if (!challenge) return "";
    const challengeLocation = Object.entries(FESTIVAL_CHALLENGES).find(([, id]) => id === learning.activeId)?.[0];
    const mainTaskComplete = challengeLocation ? state.completedTasks.has(challengeLocation) : false;
    if (learning.finished) return `<div class="challenge-backdrop"><section class="learning-modal challenge-success moon-challenge-success" role="dialog" aria-modal="true" aria-labelledby="moon-challenge-title">
      <div class="reward-seal"><span>${challenge.icon}</span><i>✓</i></div>
      <p class="challenge-kicker">EASTER EGG CHALLENGE COMPLETE · +2 MOON STARS</p>
      <h2 id="moon-challenge-title">${escapeHtml(challenge.reward)} unlocked!</h2>
      <p>${mainTaskComplete ? "Your main story was never paused. A new Easter egg is now waiting in Town Square." : "Your challenge reward is ready. Finish this place's main story step, and the Easter egg will appear in Town Square."}</p>
      <div class="success-actions"><button class="soft-action" data-action="challenge-close">${mainTaskComplete ? "Stay here" : "Continue the main story"}</button>${mainTaskComplete ? `<button class="primary-action" data-action="challenge-next">Find the Easter egg <span>→</span></button>` : ""}</div>
    </section></div>`;
    const question = challenge.questions[Math.min(learning.questionIndex, challenge.questions.length - 1)];
    const attempts = learning.attempts[`${learning.activeId}:${learning.questionIndex}`] ?? 0;
    const typeLabels = { choice: "Choose one", fill: "Fill the blank", dialogue: "Your turn to talk", description: "Describe it" };
    const answerArea = question.type === "choice"
      ? `<div class="challenge-options">${question.options.map((option, index) => `<button type="button" data-challenge-answer="${escapeHtml(option)}"><span>${String.fromCharCode(65 + index)}</span>${escapeHtml(option)}</button>`).join("")}</div>`
      : `<form id="moon-learning-form" class="challenge-input"><input name="answer" autocomplete="off" placeholder="${escapeHtml(question.placeholder || "Type your answer")}" aria-label="Your answer"><button>Check answer</button></form>`;
    const voiceAnswerPanel = learning.correct
      ? `<div class="challenge-voice-panel answered"><p><small class="challenge-voice-status" aria-live="polite">${learning.voiceHeard ? `I heard “${escapeHtml(learning.voiceHeard)}”. Answer checked!` : "Answer checked—great work!"}</small></p></div>`
      : `<div class="challenge-voice-panel ${voiceSubmitting ? "submitting" : speechInput.listening ? "listening" : ""}"><button type="button" class="listen-question" data-action="challenge-listen"><span>🔊</span><strong>Hear question</strong></button><button type="button" class="answer-by-voice ${voiceSubmitting ? "submitting" : speechInput.supported ? "" : "unsupported"}" data-action="voice" ${voiceSubmitting ? "disabled" : ""}><span>${voiceSubmitting ? "…" : speechInput.listening ? "■" : "🎙"}</span><strong>${voiceSubmitting ? "Checking" : speechInput.listening ? "Finish answer" : "Say answer"}</strong></button><p><small class="challenge-voice-status" aria-live="polite">${voiceText || (speechInput.supported ? question.type === "choice" ? "Say the answer, A/B/C, or first/second/third." : "Speak naturally; a short pause checks your answer." : "Voice is unavailable here; tap or type your answer.")}</small></p></div>`;
    return `<div class="challenge-backdrop"><section class="learning-modal moon-learning-modal" role="dialog" aria-modal="true" aria-labelledby="moon-challenge-title">
      <button class="challenge-close" data-action="challenge-close" aria-label="Close optional practice">×</button>
      <header class="challenge-header"><span class="challenge-icon">${challenge.icon}</span><div><p class="challenge-kicker">${escapeHtml(challenge.label)} · Question ${learning.questionIndex + 1}/${challenge.questions.length}</p><h2 id="moon-challenge-title">${escapeHtml(challenge.title)}</h2><p>${escapeHtml(challenge.intro)}</p></div></header>
      <div class="challenge-treasure-promise"><span>🎁</span><p><small>COMPLETE ALL ${challenge.questions.length} QUESTIONS</small><strong>Unlock a hidden Easter egg in Town Square</strong></p></div>
      <div class="challenge-progress">${challenge.questions.map((_, index) => `<i class="${index < learning.questionIndex ? "done" : index === learning.questionIndex ? "current" : ""}">${index < learning.questionIndex ? "✓" : index + 1}</i>`).join("")}</div>
      <div class="memory-strip"><small>Words to remember</small><div>${challenge.words.map((item) => `<button type="button" data-speak="${escapeHtml(item.word)}"><strong>${escapeHtml(item.word)}</strong><span>${escapeHtml(item.meaning)}</span><i>🔊</i><small>${escapeHtml(item.example)}</small></button>`).join("")}</div></div>
      <div class="question-card"><span class="question-type">${typeLabels[question.type]}</span><p>${escapeHtml(question.prompt)}</p><h3>${escapeHtml(question.sentence)}</h3>${answerArea}${voiceAnswerPanel}
        ${learning.feedback ? `<div class="challenge-feedback ${learning.correct ? "correct" : "try-again"}" role="status"><span>${learning.correct ? "✓" : "💡"}</span><p><strong>${learning.correct ? "Great work!" : attempts >= 2 ? "Try this clue" : "Almost—try again"}</strong>${escapeHtml(learning.feedback)}</p></div>` : ""}
        ${!learning.correct && attempts >= 2 ? `<button type="button" class="answer-rescue" data-challenge-answer="${escapeHtml(question.answers?.[0] || question.sampleAnswer)}"><span>✨</span><p><strong>Use a helping answer</strong><small>“${escapeHtml(question.answers?.[0] || question.sampleAnswer)}”</small></p></button>` : ""}
      </div>
      <footer class="challenge-footer"><button class="soft-action" data-action="challenge-close">Not now</button>${learning.correct ? `<button class="primary-action" data-action="challenge-continue">${learning.questionIndex < challenge.questions.length - 1 ? "Next question" : "Collect reward"} <span>→</span></button>` : `<button class="hint-action" data-action="challenge-hint">${learning.hintOpen ? "Hint is showing" : "I need a hint"}</button><span>Optional—wrong answers are okay.</span>`}</footer>
    </section></div>`;
  }

  function openFestivalChallenge(id) {
    if (!getLearningChallenge(story, id) || state.learning.completed.has(id)) return false;
    const access = getChallengeAccess(story, state, id);
    if (!access.unlocked) {
      state.guide = { speaker: "Milo", reply: "That challenge is still sleeping.", hint: access.reason };
      render();
      return false;
    }
    rewardReveal = null;
    questOpen = false;
    state.learning.activeId = id;
    state.learning.questionIndex = 0;
    state.learning.feedback = null;
    state.learning.correct = false;
    state.learning.finished = false;
    state.learning.hintOpen = false;
    state.learning.voiceHeard = "";
    render();
    globalThis.requestAnimationFrame?.(() => root.querySelector("#moon-learning-form input")?.focus());
    return true;
  }

  function resetFestivalChallenge() {
    state.learning.activeId = null;
    state.learning.questionIndex = 0;
    state.learning.feedback = null;
    state.learning.correct = false;
    state.learning.finished = false;
    state.learning.hintOpen = false;
    state.learning.voiceHeard = "";
  }

  function handleFestivalChallengeAnswer(rawAnswer) {
    const challenge = getLearningChallenge(story, state.learning.activeId);
    const question = challenge?.questions[state.learning.questionIndex];
    if (!question || state.learning.correct) return;
    const result = checkLearningAnswer(question, rawAnswer);
    const attemptKey = `${state.learning.activeId}:${state.learning.questionIndex}`;
    state.learning.attempts[attemptKey] = (state.learning.attempts[attemptKey] ?? 0) + 1;
    state.learning.correct = result.correct;
    state.learning.hintOpen = false;
    state.learning.feedback = result.correct
      ? result.correctedTo ? `Yes—“${result.correctedTo}”.` : "That answer carries the right meaning."
      : question.hint;
    if (result.correct) speak("Great work!", FESTIVAL_VOICE);
    render();
  }

  function continueFestivalChallenge() {
    const challenge = getLearningChallenge(story, state.learning.activeId);
    if (!challenge || !state.learning.correct) return;
    if (state.learning.questionIndex < challenge.questions.length - 1) {
      state.learning.questionIndex += 1;
      state.learning.feedback = null;
      state.learning.correct = false;
      state.learning.hintOpen = false;
      state.learning.voiceHeard = "";
    } else {
      applyLearningChallengeReward(state, story, state.learning.activeId);
      state.learning.finished = true;
      speak("You unlocked a secret in Town Square!", FESTIVAL_VOICE);
    }
    render();
  }

  function renderInputDock(task = festivalTaskGuide(state)) {
    const statusText = agentStatus === "fallback"
      ? "Town Agent offline · local mode still works"
      : agentBusy
        ? "Waiting for the town reply…"
        : speechInput.supported
          ? "Press Enter to send · voice sends after a short pause"
          : "Press Enter to send · voice unavailable here";
    return renderLessonInputDock({
      formId: "festival-form",
      inputId: "festival-input",
      statusId: "festival-input-status",
      inputName: "message",
      inputValue: festivalInputDraft,
      lastHeard,
      example: task.example,
      placeholder: "Say it your way…",
      optionalContent: "",
      agentBusy,
      voiceSubmitting,
      speechSupported: speechInput.supported,
      statusText: voiceText || statusText,
    });
  }

  function renderCelebrationActions() {
    const courseStars = getCourseStarsForLesson(story, state);
    const challengeId = FESTIVAL_CHALLENGES[state.location];
    const hiddenComplete = challengeId && state.learning.completed.has(challengeId);
    const hiddenAction = challengeId && !hiddenComplete
      ? `<button class="celebration-hidden-action" data-challenge="${challengeId}">🎁 Explore this hidden story</button>`
      : `<button class="celebration-hidden-action" data-action="quest">✨ Hidden story trail</button>`;
    const completion = state.memoryBookComplete
      ? renderCourseCompletion({ earned: courseStars, size: "small", className: "celebration-completion compact", homeHref: "./index.html" })
      : `<div class="storybook-finish-pending"><span>📖</span><p><small>MAIN STORY COMPLETE · ONE STEP LEFT</small><strong>Finish your storybook to complete Lesson 2</strong></p></div>`;
    return `<section class="celebration-actions">${completion}<h2>${state.memoryBookComplete ? "Your Moonlight Story is ready." : "Now make this story your own."}</h2><button data-action="memory">${state.memoryBookComplete ? "📖 Open my storybook" : "✎ Make my storybook"}</button>${hiddenAction}${state.memoryBookComplete ? "" : `<a href="./index.html">Return to the lesson road</a>`}</section>`;
  }

  function renderFinaleReward() {
    return `<div class="memory-backdrop moon-finale-backdrop"><article class="moon-finale-reward" role="dialog" aria-modal="true" aria-labelledby="moon-finale-title">
      <div class="finale-reward-sparkles" aria-hidden="true"><i></i><i></i><i></i><i></i><i></i></div>
      <div class="finale-medal"><span>☾</span><i>★</i></div>
      <p>MAIN STORY COMPLETE · STORYBOOK NEXT</p>
      <h2 id="moon-finale-title">Moonlight Story Keeper</h2>
      <blockquote>“Your English brought kindness, color, light, and every friend together.”</blockquote>
      <strong class="finale-star-message">Your celebration is ready for its keepsake story.</strong>
      <small class="finale-hidden-promise">Finish the storybook to mark this lesson Completed and reveal 1–3 course stars.</small>
      <div class="finale-reward-stats"><span><strong>Next</strong><small>storybook</small></span><span><strong>5/5</strong><small>story steps</small></span><span><strong>${state.englishTurns.length}</strong><small>English turns</small></span></div>
      <button class="finale-storybook-action" data-action="finale-memory">Make my celebration storybook <span>→</span></button>
      <button class="finale-watch-action" data-action="finale-close">Watch the fireworks together</button>
    </article></div>`;
  }

  function buildMemoryDrafts() {
    const outcomes = festivalOutcomeProgress(state, story);
    const sample = (id, fallback) => outcomes.find((outcome) => outcome.id === id)?.samples.at(-1)?.text || fallback;
    const invitees = [...state.invited].join(" and ") || state.selectedInvitee;
    return [
      `At sunset, Coco and I saw the dark Moon Lantern waiting in Town Square.`,
      `I shared ${state.treats.quantity} ${state.treats.food}${state.treats.quantity > 1 ? "s" : ""}, made a ${state.flag.color} ${state.flag.shape} flag, and guided three fireflies.`,
      `${sample("festival-voice", `I invited ${invitees} to the festival.`)} Soon everyone was together.`,
      `Finally, ${state.finalInstruction || "first we put up the flag, then we brought the fireflies to the lantern"}. Fireworks filled the sky!`,
    ];
  }

  function ensureMemoryDrafts() {
    const drafts = buildMemoryDrafts();
    state.memoryDraftLines = drafts;
    state.memoryLines = Array.from({ length: drafts.length }, (_, index) => state.memoryLines[index] || drafts[index]);
    state.memoryStep = Math.max(0, Math.min(state.memoryStep ?? 0, drafts.length - 1));
    return drafts;
  }

  function openMemoryStudio(step = state.memoryStep ?? 0) {
    ensureMemoryDrafts();
    memoryStudioOpen = true;
    memoryOpen = false;
    finaleRewardOpen = false;
    memoryStudioMessage = "Change the sentence, add your own words, or tell it with your voice.";
    state.memoryStep = Math.max(0, Math.min(step, story.writing.scenes.length - 1));
    render();
    globalThis.requestAnimationFrame?.(() => root.querySelector("#moon-story-input")?.focus());
  }

  function saveMemoryStudioLine(value = root.querySelector("#moon-story-input")?.value) {
    const text = String(value ?? "").trim();
    if (!text) return false;
    const drafts = ensureMemoryDrafts();
    state.memoryLines[state.memoryStep] = text;
    if (text !== drafts[state.memoryStep]) state.memoryEdited.add(state.memoryStep);
    else state.memoryEdited.delete(state.memoryStep);
    return true;
  }

  function renderMemoryStudio() {
    const drafts = ensureMemoryDrafts();
    const step = state.memoryStep;
    const item = story.writing.scenes[step];
    const line = state.memoryLines[step] || drafts[step];
    const edited = state.memoryEdited.has(step);
    const visualIcons = ["🏮 🐶", `${Array.from({ length: state.treats.quantity }, () => FOOD_ICONS[state.treats.food]).join("")} ${SHAPE_ICONS[state.flag.shape]} ✨`, `💌 ${PERSON_ICONS[state.selectedInvitee] || "🐶"} 🧙`, "🎆 🏮 🎇"];
    return `<div class="memory-backdrop moon-memory-studio-backdrop"><article class="moon-memory-studio" role="dialog" aria-modal="true" aria-labelledby="moon-studio-title">
      <button class="moon-studio-close" data-action="memory-studio-close" aria-label="Close story maker">×</button>
      <header><p><small>MAKE MY STORYBOOK · PAGE ${step + 1} OF ${story.writing.scenes.length}</small><strong id="moon-studio-title">${escapeHtml(item.title)}</strong></p><div class="moon-studio-progress">${story.writing.scenes.map((_, index) => `<i class="${index === step ? "current" : index < step || state.memoryEdited.has(index) ? "saved" : ""}">${index < step ? "✓" : index + 1}</i>`).join("")}</div></header>
      <div class="moon-studio-layout">
        <section class="moon-studio-preview"><small>${escapeHtml(item.place)}</small><div>${visualIcons[step]}</div><h2>${escapeHtml(item.question)}</h2><p>“${escapeHtml(line)}”</p><span>${edited ? "✓ This page has your own words" : "✎ Change a few words to make it yours"}</span></section>
        <section class="moon-studio-writing"><label for="moon-story-input"><small>YOUR STORY SENTENCE</small><strong>Make this page yours.</strong></label><textarea id="moon-story-input" maxlength="260" aria-label="Your story sentence">${escapeHtml(line)}</textarea><div class="moon-studio-suggestions">${item.suggestions.map((word) => `<button data-memory-suggestion="${escapeHtml(word)}">+ ${escapeHtml(word)}</button>`).join("")}</div><div class="moon-studio-voice"><button data-action="memory-voice" class="${voiceSubmitting ? "submitting" : speechInput.supported ? "" : "unsupported"}" ${voiceSubmitting ? "disabled" : ""}><span>${voiceSubmitting ? "…" : "🎙"}</span><strong>${voiceSubmitting ? "Saving" : "Tell this page"}</strong></button><small class="moon-studio-voice-status" aria-live="polite">${escapeHtml(memoryStudioMessage)}</small></div></section>
      </div>
      <footer>${step > 0 ? `<button class="studio-back" data-action="memory-studio-prev">← Save &amp; back</button>` : `<span></span>`}<button class="studio-listen" data-action="memory-studio-listen">🔊 Listen to my page</button><button class="studio-next" data-action="${step < story.writing.scenes.length - 1 ? "memory-studio-next" : "memory-studio-finish"}">${step < story.writing.scenes.length - 1 ? "Save & next →" : "Make my storybook →"}</button></footer>
    </article></div>`;
  }

  function addMemorySuggestion(word) {
    const input = root.querySelector("#moon-story-input");
    if (!input) return;
    const current = input.value.trim().replace(/[.!?]$/, "");
    const text = `${current}${current ? ", " : ""}${word}.`;
    input.value = text;
    saveMemoryStudioLine(text);
    memoryStudioMessage = "Great—your new words are now part of this page.";
    input.focus();
  }

  function updateMemoryStudioVoiceSurface(message, listening, transcript = null, submitting = false) {
    voiceSubmitting = submitting;
    memoryStudioMessage = message;
    const status = root.querySelector(".moon-studio-voice-status");
    const input = root.querySelector("#moon-story-input");
    const button = root.querySelector("[data-action='memory-voice']");
    if (status) status.textContent = message;
    if (button) {
      button.classList.toggle("listening", listening);
      button.classList.toggle("submitting", submitting);
      button.innerHTML = `<span>${submitting ? "…" : listening ? "■" : "🎙"}</span><strong>${submitting ? "Saving" : listening ? "Finish" : "Tell this page"}</strong>`;
    }
    if (transcript !== null && input) {
      const line = `${memoryStudioVoiceBase}${memoryStudioVoiceBase && transcript ? " " : ""}${transcript}`.trim();
      input.value = line;
      saveMemoryStudioLine(line);
    }
  }

  function renderMemory() {
    const outcomes = festivalOutcomeProgress(state, story);
    ensureMemoryDrafts();
    const courseStars = getCourseStarsForLesson(story, state);
    const totalPages = 6;
    const page = Math.max(0, Math.min(memoryPage, totalPages - 1));
    return `<div class="memory-backdrop"><article class="moon-memory moon-storybook" role="dialog" aria-modal="true" aria-labelledby="moon-memory-title">
      <button class="moon-book-close" data-action="close-memory" aria-label="Close storybook">×</button>
      <header><span>☾</span><p><small>MY CELEBRATION STORYBOOK</small><strong id="moon-memory-title">The Moonlight Festival</strong></p><div class="moon-book-tools"><span>Page ${page + 1} of ${totalPages}</span><button data-action="memory-read">🔊 Read this page</button></div></header>
      <div class="moon-book-shell"><i class="moon-book-page-stack"></i><section class="moon-book-page page-${page}" aria-label="Storybook page ${page + 1} of ${totalPages}">
        ${renderMemoryPage(page, outcomes)}
        ${page > 0 ? `<button class="moon-page-turn previous" data-action="memory-prev" aria-label="Previous storybook page"><span>‹</span><small>Back</small></button>` : ""}
        ${page < totalPages - 1 ? `<button class="moon-page-turn next" data-action="memory-next" aria-label="Next storybook page"><small>Turn page</small><span>›</span></button>` : `<button class="moon-page-turn next finish" data-action="close-memory"><small>Finish review</small><span>✓</span></button>`}
        <span class="moon-paper-number">${page + 1}</span>
      </section></div>
      <div class="moon-book-progress" aria-hidden="true">${Array.from({ length: totalPages }, (_, index) => `<i class="${index === page ? "current" : index < page ? "read" : ""}"></i>`).join("")}</div>
      <footer><span>${courseStars}/3 course stars · ${state.englishTurns.length} English turns · everyone together</span><button data-action="memory-review">Jump to review</button></footer>
    </article></div>`;
  }

  function renderMemoryPage(page, outcomes) {
    const invitees = [...state.invited].join(" and ") || state.selectedInvitee;
    const courseStars = getCourseStarsForLesson(story, state);
    if (page === 0) return `<div class="moon-book-cover"><div class="cover-fireworks">✦ <span>✷</span> ✦</div><div class="cover-lantern">★</div><p>MY MAGIC ENGLISH STORY</p><h2>The Welcome Home<br>Moonlight Festival</h2><span>Every page was made step by step with my own English.</span><div class="cover-cast"><i>👩‍🍳</i><i>👩‍🏫</i><i>🧙</i><i>🐶</i></div>${renderCourseStars({ earned: courseStars, size: "small", className: "cover-course-stars" })}<small>Turn the corner to read my story</small></div>`;
    if (page === 1) return `<div class="moon-book-chapter lantern-memory"><header><small>CHAPTER 1 · THE DARK LANTERN</small><h2>The town was waiting</h2><span>🏮</span></header><div class="chapter-picture"><b>🏮</b><i>🐶</i><em>☾</em></div><p>The Moon Lantern had forgotten how to shine, so Coco and I began a new adventure.</p><blockquote>“${escapeHtml(state.memoryLines[0])}”</blockquote><small class="chapter-power">This is the first page I made.</small></div>`;
    if (page === 2) return `<div class="moon-book-chapter magic-memory"><header><small>CHAPTER 2 · THREE KINDS OF MAGIC</small><h2>Everything we prepared</h2><span>✨</span></header><div class="chapter-picture"><b>${Array.from({ length: state.treats.quantity }, () => FOOD_ICONS[state.treats.food]).join("")}</b><b class="memory-flag color-${state.flag.color}">${SHAPE_ICONS[state.flag.shape]}</b><b>✨</b><em>☾</em></div><p>Kindness, Color, and Light came from the choices I made around the town.</p><blockquote>“${escapeHtml(state.memoryLines[1])}”</blockquote><small class="chapter-power">My choices shaped this chapter.</small></div>`;
    if (page === 3) return `<div class="moon-book-chapter invitation-memory"><header><small>CHAPTER 3 · A FRIEND JOINED US</small><h2>The empty place was filled</h2><span>💌</span></header><div class="chapter-picture together-picture"><b>${PERSON_ICONS[state.selectedInvitee] || "🐶"}</b><b>🧙</b><i>🐶</i><em>☾</em></div><p>I invited ${escapeHtml(invitees)}, and the festival became a place where everyone belonged.</p><blockquote>“${escapeHtml(state.memoryLines[2])}”</blockquote><small class="chapter-power">My invitation brought the town together.</small></div>`;
    if (page === 4) return `<div class="moon-book-chapter together-memory"><header><small>CHAPTER 4 · THE TOWN LIT UP</small><h2>My words became moonlight</h2><span>🎆</span></header><div class="chapter-picture together-picture"><b>👩‍🍳</b><b>👩‍🏫</b><b>🧙</b><b>🐶</b><em>★</em></div><p>Betty, Ms. Maple, Milo, and Coco watched the Moon Lantern wake beneath the fireworks.</p><blockquote>“${escapeHtml(state.memoryLines[3])}”</blockquote><small class="chapter-power">This ending came from my own English.</small></div>`;
    const reviewWords = [...new Set([state.treats.food, state.flag.color, state.flag.shape, "firefly", "first", "then", "invite", "lantern"])];
    return `<div class="moon-book-review"><p>LESSON 2 REVIEW · FINAL PAGE</p><h2>Look what I can do!</h2>${renderCourseCompletion({ earned: courseStars, className: "moon-book-completion", homeHref: "./index.html" })}<section>${outcomes.map((outcome) => `<div class="${outcome.complete ? "complete" : "practising"}"><span>${outcome.complete ? "✓" : outcome.icon}</span><p><strong>${escapeHtml(outcome.canDo)}</strong><small>${outcome.samples.at(-1)?.text ? `I said: “${escapeHtml(outcome.samples.at(-1).text)}”` : escapeHtml(outcome.reviewPrompt)}</small></p></div>`).join("")}</section><div class="moon-review-words"><small>WORDS TO REMEMBER · TAP TO HEAR</small>${reviewWords.map((word) => `<button data-speak="${escapeHtml(word)}">${escapeHtml(word)} <span>▶</span></button>`).join("")}</div><div class="moon-review-badge"><span>☾</span><p><small>MY LESSON 2 BADGE · ${courseStars}/3 STARS</small><strong>Moonlight Story Keeper</strong></p></div><button class="read-story-again" data-action="memory-first">Read my story again ↺</button></div>`;
  }

  function memoryPageNarration(page = memoryPage) {
    const outcomes = festivalOutcomeProgress(state, story);
    ensureMemoryDrafts();
    return [
      "My Magic English Story. The Welcome Home Moonlight Festival.",
      `Chapter one. The town was waiting. ${state.memoryLines[0]}`,
      `Chapter two. Everything we prepared. ${state.memoryLines[1]}`,
      `Chapter three. A friend joined us. ${state.memoryLines[2]}`,
      `Chapter four. My words became moonlight. ${state.memoryLines[3]}`,
      `Lesson two review. ${outcomes.map((outcome) => outcome.canDo).join(" ")} My badge is Moonlight Story Keeper.`,
    ][Math.max(0, Math.min(page, 5))];
  }

  function renderCoco() {
    return `<div class="moon-coco-rig" role="img" aria-label="Coco the puppy"><i class="coco-tail"></i><i class="coco-body"></i><i class="coco-head"><b></b><b></b><span>●</span><em></em></i><i class="coco-scarf"></i></div>`;
  }

  function updateVoiceSurface(transcript = null) {
    const target = root.querySelector(state.learning.activeId ? ".challenge-voice-status" : ".voice-status");
    if (target && voiceText) target.textContent = voiceText;
    if (!state.learning.activeId && transcript !== null) {
      festivalInputDraft = transcript;
      const input = root.querySelector("#festival-input");
      if (input) input.value = transcript;
    }
  }

  async function runInput(message, source = "text") {
    const text = String(message ?? "").trim();
    if (state.busy || agentBusy) return;
    if (!text) {
      state.guide = { speaker: "Milo", reply: "I didn't hear any words yet.", hint: moonlightPrompt(state) };
      render();
      return;
    }
    if (source === "voice") festivalInputDraft = text;
    lastHeard = text;
    restoreInputFocus = source === "text" || restoreInputFocus;
    speechInput.adaptToText(text);
    const runId = ++agentRunId;
    const completedBefore = new Set(state.completedTasks);
    const localResult = localFestivalIntent(state, text);
    let result = localResult;
    if (canRunFestivalLocally(localResult)) {
      result = friendlyLocalResult(state, localResult, "instant");
      agentStatus = "instant";
    } else {
      agentBusy = true;
      agentCancelled = false;
      agentStatus = "waiting";
      state.guide = { speaker: "Milo", reply: "I'm listening to the town…", hint: moonlightPrompt(state) };
      render();
      let cancelledRequest = false;
      agentController?.abort();
      agentController = new AbortController();
      try {
        result = await askFestivalAgent({ message: text, source, state, history: state.history, signal: agentController.signal });
        agentStatus = "online";
      } catch {
        if (agentCancelled) {
          cancelledRequest = true;
          agentStatus = "ready";
        } else {
          result = friendlyLocalResult(state, localResult, "local");
          agentStatus = "fallback";
        }
      } finally {
        if (runId === agentRunId) {
          agentBusy = false;
          agentController = null;
        }
      }
      if (runId !== agentRunId) return;
      if (cancelledRequest) {
        voiceText = "";
        state.guide = { speaker: "Milo", reply: "Okay—we stopped that reply.", hint: "You can type a shorter idea or speak again whenever you like." };
        render();
        return;
      }
    }
    if (runId !== agentRunId) return;
    if (result.intent === "travel") {
      const access = getSceneAccess(state, result.destination);
      if (!access.unlocked) {
        voiceText = "";
        state.guide = { speaker: "Milo", reply: "That place is waiting for a later story step.", hint: access.reason };
        render();
        return;
      }
    }
    const phaseBeforeResult = state.phase;
    const applied = applyFestivalResult(state, result, text, source);
    if (phaseBeforeResult !== "celebration" && state.phase === "celebration") {
      finaleRewardOpen = true;
      memoryPage = 0;
    }
    const newlyCompleted = [...state.completedTasks].find((task) => !completedBefore.has(task));
    if (newlyCompleted) rewardReveal = { kind: "relic", id: newlyCompleted };
    if (applied.intent === "light_lantern" && state.phase !== "celebration") {
      state.guide = { speaker: "Milo", reply: "The lantern is almost ready, but one friend should be here to share the light.", hint: moonlightPrompt(state) };
    }
    if (state.phase === "celebration") {
      saveLessonMemory(story.id, buildMoonlightFestivalMemory(state));
      speak("Your English lit the Moon Lantern. Welcome to the Moonlight Festival!", FESTIVAL_VOICE);
    } else if (result.reply) speak(result.reply, FESTIVAL_VOICE);
    state.history.push(
      { role: "user", content: text.slice(0, AGENT_HISTORY_TURN_MAX_CHARS) },
      { role: "assistant", content: String(result.reply || applied.intent).slice(0, AGENT_HISTORY_TURN_MAX_CHARS) },
    );
    if (state.history.length > AGENT_HISTORY_MAX_TURNS) state.history.splice(0, state.history.length - AGENT_HISTORY_MAX_TURNS);
    voiceText = "";
    render();
  }

  function fillSuggestion(text) {
    const input = root.querySelector("#festival-input");
    if (!input) return;
    festivalInputDraft = text;
    input.value = text;
    input.focus();
  }

  function returnToTownHome() {
    agentRunId += 1;
    agentCancelled = agentBusy;
    agentController?.abort();
    agentController = null;
    agentBusy = false;
    agentStatus = "ready";
    if (speechInput.listening) {
      ignoreNextVoiceFinal = true;
      speechInput.cancel();
    }
    state.busy = false;
    memoryOpen = false;
    memoryStudioOpen = false;
    memoryPage = 0;
    finaleRewardOpen = false;
    questOpen = false;
    welcomeOpen = false;
    rewardReveal = null;
    resetFestivalChallenge();
    voiceText = "";
    festivalInputDraft = "";
    visitMoonlightLocation(state, "town");
    state.guide = {
      speaker: "Milo",
      reply: "We are back at Town Square. Everything you made is still safe.",
      hint: moonlightPrompt(state),
    };
    render();
  }

  function handleClick(event) {
    const immediateAction = event.target.closest("[data-action]")?.dataset.action;
    if (immediateAction === "home") { returnToTownHome(); return; }
    if (agentBusy) return;
    const challengeAnswer = event.target.closest("[data-challenge-answer]")?.dataset.challengeAnswer;
    if (challengeAnswer) { handleFestivalChallengeAnswer(challengeAnswer); return; }
    const challengeId = event.target.closest("[data-challenge]")?.dataset.challenge;
    if (challengeId) { openFestivalChallenge(challengeId); return; }
    const speakText = event.target.closest("[data-speak]")?.dataset.speak;
    if (speakText) { speak(speakText, FESTIVAL_VOICE); return; }
    const location = event.target.closest("[data-location]")?.dataset.location;
    if (location) { questOpen = false; welcomeOpen = false; visitMoonlightLocation(state, location); render(); return; }
    const surprise = event.target.closest("[data-surprise]")?.dataset.surprise;
    if (surprise) {
      const found = discoverFestivalSurprise(state, surprise);
      if (found) rewardReveal = { kind: "surprise", id: surprise };
      else state.guide = { speaker: "Milo", reply: "You already discovered this festival secret!", hint: moonlightPrompt(state) };
      render();
      return;
    }
    const treat = event.target.closest("[data-treat]")?.dataset.treat;
    if (treat) { selectTreat(state, treat); state.guide.hint = moonlightPrompt(state); render(); return; }
    const quantity = event.target.closest("[data-quantity]")?.dataset.quantity;
    if (quantity) { selectTreat(state, state.treats.food, Number(quantity)); state.guide.hint = moonlightPrompt(state); render(); return; }
    const color = event.target.closest("[data-flag-color]")?.dataset.flagColor;
    if (color) { selectFlagPart(state, "color", color); state.guide.hint = moonlightPrompt(state); render(); return; }
    const shape = event.target.closest("[data-flag-shape]")?.dataset.flagShape;
    if (shape) { selectFlagPart(state, "shape", shape); state.guide.hint = moonlightPrompt(state); render(); return; }
    const firefly = event.target.closest("[data-firefly]")?.dataset.firefly;
    if (firefly) { const added = discoverFirefly(state, firefly); state.guide = { speaker: "Coco", reply: added ? "A tiny light found us!" : "This firefly is already following you.", hint: moonlightPrompt(state) }; render(); return; }
    const invitee = event.target.closest("[data-invitee]")?.dataset.invitee;
    if (invitee) { selectInvitee(state, invitee); state.guide.hint = moonlightPrompt(state); render(); return; }
    const suggestion = event.target.closest("[data-suggestion]")?.dataset.suggestion;
    if (suggestion) { fillSuggestion(suggestion); return; }
    const memorySuggestion = event.target.closest("[data-memory-suggestion]")?.dataset.memorySuggestion;
    if (memorySuggestion) { addMemorySuggestion(memorySuggestion); return; }
    const action = event.target.closest("[data-action]")?.dataset.action;
    if (action === "start") {
      startMoonlightLesson(state);
      questOpen = false;
      welcomeOpen = true;
      speak("Welcome back. Coco's festival needs five story steps. Let's begin with Kindness Magic at the Bakery.", FESTIVAL_VOICE);
      render();
      return;
    }
    if (action === "coach-close") { welcomeOpen = false; render(); return; }
    if (action === "memory-voice") {
      if (voiceSubmitting) return;
      if (!speechInput.supported) { memoryStudioMessage = "Voice is unavailable here—your typed story is safe."; render(); return; }
      if (speechInput.listening) speechInput.stop();
      else {
        memoryStudioVoiceBase = root.querySelector("#moon-story-input")?.value.trim() || "";
        if (!speechInput.start()) { memoryStudioMessage = "The microphone did not start. Keep typing, or try once more."; render(); }
      }
      return;
    }
    if (action === "voice") { if (voiceSubmitting || agentBusy) return; if (speechInput.listening) speechInput.stop(); else if (!speechInput.start()) { voiceText = "Microphone unavailable—typing still works."; updateVoiceSurface(); } return; }
    if (action === "quest") { questOpen = true; render(); return; }
    if (action === "quest-close") { questOpen = false; render(); return; }
    if (action === "quest-go") {
      const target = event.target.closest("[data-target]")?.dataset.target;
      questOpen = false;
      if (target && target !== state.location) visitMoonlightLocation(state, target);
      render();
      return;
    }
    if (action === "reward-next") {
      const target = event.target.closest("[data-target]")?.dataset.target;
      rewardReveal = null;
      if (target && target !== state.location) visitMoonlightLocation(state, target);
      render();
      return;
    }
    if (action === "reward-practice") {
      const id = event.target.closest("[data-challenge]")?.dataset.challenge;
      if (id) openFestivalChallenge(id);
      return;
    }
    if (action === "challenge-close") { resetFestivalChallenge(); render(); return; }
    if (action === "challenge-hint") {
      const challenge = getLearningChallenge(story, state.learning.activeId);
      const question = challenge?.questions[state.learning.questionIndex];
      state.learning.hintOpen = true;
      state.learning.feedback = question?.hint || "Try the words at the top.";
      render();
      return;
    }
    if (action === "challenge-listen") {
      const challenge = getLearningChallenge(story, state.learning.activeId);
      const question = challenge?.questions[state.learning.questionIndex];
      if (question) speak(`${question.prompt} ${question.sentence}`, FESTIVAL_VOICE);
      return;
    }
    if (action === "challenge-continue") { continueFestivalChallenge(); return; }
    if (action === "challenge-next") {
      const locationId = Object.entries(FESTIVAL_CHALLENGES).find(([, id]) => id === state.learning.activeId)?.[0];
      resetFestivalChallenge();
      if (locationId) {
        visitMoonlightLocation(state, "town");
        state.guide = { speaker: "Milo", reply: `${FESTIVAL_RELICS[locationId].relic} is hiding in the Square. Look for the glowing question mark!`, hint: "Tap the new Easter egg in Town Square." };
      }
      render();
      return;
    }
    if (action === "finale-memory") { openMemoryStudio(0); return; }
    if (action === "finale-close") { finaleRewardOpen = false; render(); return; }
    if (action === "memory") { if (state.memoryBookComplete) { memoryOpen = true; memoryPage = 0; questOpen = false; render(); } else openMemoryStudio(); return; }
    if (action === "memory-review") { if (!state.memoryBookComplete) { openMemoryStudio(); return; } finaleRewardOpen = false; memoryOpen = true; memoryPage = 5; questOpen = false; render(); return; }
    if (action === "memory-studio-prev" || action === "memory-studio-next") {
      if (!saveMemoryStudioLine()) { memoryStudioMessage = "Keep one sentence so this page has a story."; render(); return; }
      state.memoryStep = Math.max(0, Math.min(story.writing.scenes.length - 1, state.memoryStep + (action === "memory-studio-next" ? 1 : -1)));
      memoryStudioMessage = "Change the sentence, add your own words, or tell it with your voice.";
      render();
      globalThis.requestAnimationFrame?.(() => root.querySelector("#moon-story-input")?.focus());
      return;
    }
    if (action === "memory-studio-finish") {
      if (!saveMemoryStudioLine()) { memoryStudioMessage = "Keep one sentence so this page has a story."; render(); return; }
      if (!state.memoryEdited.size) {
        memoryStudioMessage = "Add one short piece of your own English before making the book.";
        render();
        globalThis.requestAnimationFrame?.(() => root.querySelector("#moon-story-input")?.focus());
        return;
      }
      state.memoryBookComplete = true;
      memoryStudioOpen = false;
      memoryOpen = true;
      memoryPage = 0;
      saveLessonMemory(story.id, buildMoonlightFestivalMemory(state));
      render();
      return;
    }
    if (action === "memory-studio-listen") {
      const line = root.querySelector("#moon-story-input")?.value.trim();
      if (line) { saveMemoryStudioLine(line); speak(line, FESTIVAL_VOICE); }
      return;
    }
    if (action === "memory-studio-close") { memoryStudioOpen = false; render(); return; }
    if (action === "memory-prev") { memoryPage = Math.max(0, memoryPage - 1); render(); return; }
    if (action === "memory-next") { memoryPage = Math.min(5, memoryPage + 1); render(); return; }
    if (action === "memory-first") { memoryPage = 0; render(); return; }
    if (action === "memory-read") { speak(memoryPageNarration(), FESTIVAL_VOICE); return; }
    if (action === "close-memory") { memoryOpen = false; render(); }
  }

  function handleKeydown(event) {
    if (event.key === "Escape" && finaleRewardOpen) { finaleRewardOpen = false; render(); return; }
    if (event.key === "Escape" && memoryStudioOpen) { memoryStudioOpen = false; render(); return; }
    if (event.key === "Escape" && memoryOpen) { memoryOpen = false; render(); return; }
    if (!memoryOpen || event.target.matches?.("input,textarea")) return;
    if (event.key === "ArrowLeft") { event.preventDefault(); memoryPage = Math.max(0, memoryPage - 1); render(); }
    if (event.key === "ArrowRight") { event.preventDefault(); memoryPage = Math.min(5, memoryPage + 1); render(); }
  }

  function handleSubmit(event) {
    if (event.target.id === "moon-learning-form") {
      event.preventDefault();
      const input = event.target.querySelector("input[name='answer']");
      handleFestivalChallengeAnswer(input?.value);
      return;
    }
    if (event.target.id !== "festival-form") return;
    event.preventDefault();
    const input = event.target.querySelector("#festival-input");
    const message = input?.value.trim();
    festivalInputDraft = "";
    if (input) input.value = "";
    restoreInputFocus = true;
    void runInput(message, "text");
  }

  function handleInput(event) {
    if (event.target.id === "festival-input") festivalInputDraft = event.target.value;
    if (event.target.id === "moon-story-input") saveMemoryStudioLine(event.target.value);
  }

  root.addEventListener("click", handleClick);
  root.addEventListener("submit", handleSubmit);
  root.addEventListener("input", handleInput);
  root.addEventListener("keydown", handleKeydown);

  return {
    state,
    render,
    runInput,
    returnToTown: returnToTownHome,
    openMemory(page = 0) {
      finaleRewardOpen = false;
      memoryStudioOpen = false;
      memoryPage = Math.max(0, Math.min(5, page));
      memoryOpen = true;
      render();
    },
    openMemoryStudio,
  };
}
