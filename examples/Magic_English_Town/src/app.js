import { escapeHtml, speak } from "./core/browser.js";
import { askWorldAgent, canRunLocally, getSpokenReply } from "./core/agent-client.js";
import { AGENT_HISTORY_MAX_TURNS, AGENT_HISTORY_TURN_MAX_CHARS } from "./core/agent-limits.js";
import { renderLessonInputDock } from "./core/lesson-input-dock.js";
import { getChallengeAccess, getSceneAccess } from "./core/scene-unlocks.js";
import { createSpeechInput } from "./core/speech-input.js";
import { buildMissingPuppyMemory, getLessonMemory, restoreMissingPuppyMemory, saveLessonMemory } from "./core/course-memory.js";
import { getCourseStarsForLesson, renderCourseCompletion, renderCourseStars } from "./core/course-stars.js";
import { applyLearningChallengeReward, checkLearningAnswer, getLearningChallenge, resolveSpokenLearningAnswer } from "./core/learning-challenges.js";
import {
  EASTER_EGG_MILESTONES,
  LOCATION_LABELS,
  addClue,
  awardAdventurePoints,
  buildStoryDrafts,
  canFindCoco,
  collectWord,
  completeCare,
  completeStory,
  createStoryState,
  findCoco,
  getAdventureProgress,
  getEasterEggProgress,
  getGuidedStoryStep,
  getLessonOutcomeProgress,
  getLessonProgress,
  getParticipationProgress,
  getPackedFood,
  interpretWorldCommand,
  hasEasterEgg,
  isCaringEnglish,
  masteryCount,
  moveWorldObject,
  packFoodForCoco,
  performHideChoice,
  recordMastery,
  recordLearnerContribution,
  saveStoryLine,
  startSearchQuest,
  visitLocation,
  writingFeedback,
} from "./core/story-engine.js";

const wait = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));

export function createMagicTownApp({ root, story }) {
  const state = restoreMissingPuppyMemory(createStoryState(story), getLessonMemory(story.id));
  let toastTimer = null;
  let rewardToastTimer = null;
  let pendingRewardToast = null;
  let bookPointerStart = null;
  let lastVoiceFinal = "";
  let agentBusy = false;
  let agentAbortController = null;
  let agentCancelled = false;
  let agentStatus = "ready";
  let fallbackAnnounced = false;
  let restoreWorldInputFocus = false;
  let storyVoiceBase = "";
  let ignoreNextVoiceFinal = false;
  let ignoredVoiceSession = false;
  let voiceSubmitting = false;
  let worldInputDraft = "";
  const agentHistory = [];

  const speechInput = createSpeechInput({
    onStart: () => state.learning?.activeId ? updateLearningVoiceSurface("Listening… Speak naturally; pause for a moment to submit.", true, "") : state.scene === "story" ? updateStoryVoiceSurface("Listening… Keep telling your page.", true, "") : updateVoiceSurface("Listening… Say it your way.", true, ""),
    onPartial: (text) => state.learning?.activeId ? updateLearningVoiceSurface(text || "Listening…", true, text) : state.scene === "story" ? updateStoryVoiceSurface(text || "Listening…", true, text) : updateVoiceSurface(text || "Listening…", true, text),
    onSubmitStart: (text) => {
      if (state.learning?.activeId) updateLearningVoiceSurface("Waiting for your answer…", false, text, true);
      else if (state.scene === "story") updateStoryVoiceSurface("Waiting to add your words…", false, text, true);
      else updateVoiceSurface("Waiting for a reply…", false, text, true);
    },
    onFinal: (text, alternatives = []) => {
      voiceSubmitting = false;
      if (ignoreNextVoiceFinal) { ignoreNextVoiceFinal = false; ignoredVoiceSession = true; return; }
      if (!text || text === lastVoiceFinal) return;
      lastVoiceFinal = text;
      if (state.learning?.activeId) {
        const challenge = getLearningChallenge(story, state.learning.activeId);
        const question = challenge?.questions[state.learning.questionIndex];
        state.learning.voiceHeard = text;
        const candidates = [text, ...alternatives].filter((candidate, index, all) => candidate && all.indexOf(candidate) === index);
        const resolvedCandidates = candidates.map((candidate) => resolveSpokenLearningAnswer(question, candidate));
        const bestAnswer = resolvedCandidates.find((candidate) => checkLearningAnswer(question, candidate).correct) ?? resolvedCandidates[0] ?? text;
        handleLearningAnswer(bestAnswer, { voice: true });
        return;
      }
      if (state.scene === "story") {
        const nextLine = `${storyVoiceBase}${storyVoiceBase && text ? " " : ""}${text}`.trim();
        saveStoryLine(state, story, state.currentStoryStep, nextLine);
        render();
        requestAnimationFrame(() => root.querySelector("#story-input")?.focus());
        return;
      }
      updateVoiceSurface("Got it — doing that now.", false, text);
      void runWorldInput(text, "voice");
    },
    onEnd: (heard) => {
      voiceSubmitting = false;
      if (ignoredVoiceSession) { ignoredVoiceSession = false; return; }
      if (ignoreNextVoiceFinal && !heard) { ignoreNextVoiceFinal = false; return; }
      if (state.learning?.activeId) updateLearningVoiceSurface(heard ? `I heard “${heard}”.` : "Tap the microphone and say your answer.", false);
      else if (state.scene === "story") updateStoryVoiceSurface(heard ? "Added to your page." : "Tap the microphone and tell this page.", false);
      else if (!heard) updateVoiceSurface("Tap the microphone to speak", false);
    },
    onError: (message) => {
      voiceSubmitting = false;
      if (state.learning?.activeId) updateLearningVoiceSurface(message, false);
      else if (state.scene === "story") updateStoryVoiceSurface(message, false);
      else updateVoiceSurface(message, false);
      showToast(message);
    },
  });

  function render() {
    const focusedId = root.contains(root.ownerDocument?.activeElement) ? root.ownerDocument.activeElement.id : "";
    const shouldRestoreWorldInput = restoreWorldInputFocus || focusedId === "world-input";
    const shouldRestoreStoryInput = focusedId === "story-input";
    root.innerHTML = `
      <main class="immersive-app scene-${state.scene} location-${state.location}" aria-busy="${state.busy}">
        ${renderHud()}
        <section class="story-viewport">${renderScene()}</section>
        ${renderCoachCard()}
        ${state.scene === "world" ? renderWorldNav() : ""}
        ${state.wordPocketOpen ? renderWordPocket() : ""}
        ${state.explorationOpen ? renderExplorationBoard() : ""}
        ${state.storyBeatOpen ? renderStoryBeat() : ""}
        ${state.learning?.activeId ? renderLearningChallenge() : ""}
        ${state.easterEggOpen ? renderEasterEggPanel() : ""}
        <div class="toast" id="toast" role="status" aria-live="polite" aria-atomic="true">
          <span class="toast-icon" aria-hidden="true">✓</span><div class="toast-copy"><strong></strong><p></p></div><button data-action="toast-close" aria-label="Close message">×</button><i class="toast-progress" aria-hidden="true"></i>
        </div>
      </main>
    `;
    restoreWorldInputFocus = false;
    saveLessonMemory(story.id, buildMissingPuppyMemory(state));
    if (shouldRestoreWorldInput && state.scene === "world" && !agentBusy) requestAnimationFrame(() => root.querySelector("#world-input")?.focus());
    if (shouldRestoreStoryInput && state.scene === "story") requestAnimationFrame(() => root.querySelector("#story-input")?.focus());
  }

  function renderHud() {
    const quest = questSummary();
    const surprise = getEasterEggProgress(state);
    const lesson = getLessonProgress(state, story);
    const optionalChallenge = state.scene === "world" ? renderOptionalChallenge() : "";
    const courseHome = state.scene === "world" && state.location === "town" ? `
        <a class="hud-brand town-home-link" href="./index.html" aria-label="Return to Magic English Town course home" title="Back to Magic English Town">
          <span class="brand-paw town-home-mark"><i></i><i></i><i></i></span>
          <span class="town-home-copy"><strong>Magic English Town</strong><small>Town Square</small></span>
          <span class="town-home-cue" aria-hidden="true"><b>←</b><small>Town</small></span>
        </a>` : `<span class="hud-home-space" aria-hidden="true"></span>`;
    return `
      <div class="hud open-world-hud">
        ${courseHome}
        <div class="quest-stack">
          <button class="quest-pill stage-${state.questStage} ${quest.ready ? "is-ready" : ""}" data-action="quest-next" style="--quest-progress:${quest.progress}%" aria-live="polite" aria-label="${quest.ready ? "Continue the unlocked story" : "Open the exploration journal"}: ${escapeHtml(mainStoryNextStep())}">
            <span>${quest.ready ? "✓" : state.questStage === "care" ? "♥" : "★"}</span>
            <div><small>${quest.ready ? `Story ready · ${lesson.completed}/${lesson.total} English powers` : `Lesson 1 · ${lesson.completed}/${lesson.total} English powers`}</small><strong>${quest.title}</strong></div>
            <i><em>${escapeHtml(quest.meta)}</em><b>${quest.ready ? "Continue story" : "View ideas"} →</b></i>
          </button>
          ${optionalChallenge ? `<div class="optional-challenge-slot hud-optional-challenge">${optionalChallenge}</div>` : ""}
        </div>
        <div class="hud-tools">
          <button class="surprise-button ${surprise.complete ? "complete" : ""}" data-action="surprise-trail" aria-label="Open surprise trail"><span>${surprise.complete ? "✨" : "★"}</span><div><small>Next surprise</small><strong>${surprise.next ? `${surprise.next.stars - surprise.total} ★` : "All found"}</strong></div></button>
          <button class="word-pocket-button" data-action="toggle-pocket"><span>✦</span><div><small>English powers</small><strong>${lesson.completed}/${lesson.total}</strong></div></button>
        </div>
      </div>
    `;
  }

  function renderOptionalChallenge() {
    const sceneChallengeId = bonusChallengeForCurrentContext();
    const sceneChallenge = getLearningChallenge(story, sceneChallengeId);
    const challengeLock = lockedChallengeForCurrentContext();
    return sceneChallenge
      ? `<button type="button" class="scene-practice surprise-challenge" data-action="bonus-challenge"><span>🎁</span><p><b>Optional challenge · Easter egg trail</b><small>${sceneChallenge.questions.length} questions · earn stars toward a town surprise</small></p><i>Start →</i></button>`
      : challengeLock
        ? `<i class="scene-practice-locked"><span>🔒</span><b>Optional challenge waits for the story</b><small>${escapeHtml(challengeLock.reason)}</small></i>`
        : `<i class="scene-practice-complete">✓ Optional challenge complete · surprise stars collected</i>`;
  }

  function questSummary() {
    const trail = getGuidedStoryStep(state);
    const adventure = getAdventureProgress(state);
    const chapter = {
      meet: { step: 1, kicker: "Meet Coco" },
      search: { step: 2, kicker: "Find Coco" },
      care: { step: 3, kicker: "Help Coco" },
      home: { step: 4, kicker: "Make a story" },
      complete: { step: 5, kicker: "The end" },
    }[state.questStage];
    const ready = trail.mode === "story" || ["home", "complete"].includes(state.questStage);
    const participation = adventure.requirements.participation;
    const lesson = getLessonProgress(state, story);
    const meta = `${lesson.completed}/${lesson.total} powers · ${adventure.total} bonus ★`;
    return { ...chapter, title: trail.title, meta, progress: trail.progress, ready, total: adventure.total };
  }

  function renderScene() {
    if (state.scene === "story") return renderStoryStudio();
    if (state.scene === "book") return renderStorybook();
    if (state.location === "town") return renderTown();
    if (state.location === "petshop") return renderPetShop();
    if (state.location === "park") return renderPark();
    return renderCommunityPlace();
  }

  function renderCoachCard() {
    if (!state.coachOpen || state.scene !== "world" || state.location !== "town" || state.questStage !== "meet" || state.pointRewards.size) return "";
    return `
      <aside class="first-steps-card" aria-label="How to start">
        <button class="first-steps-close" data-action="coach-close" aria-label="Close the welcome guide">×</button>
        <span class="first-steps-milo">${renderMilo()}</span>
        <div><small>LESSON 1 · YOUR FIRST ADVENTURE</small><strong>Play, listen, then use English.</strong><p>Meet Coco and grow your first English Power.</p></div>
        <button class="first-steps-go" data-location="petshop"><span>🐾</span><strong>Meet Coco</strong><small>Start with a friendly place</small></button>
        <button class="first-steps-free" data-action="coach-close">I want to look around</button>
      </aside>`;
  }

  function renderTown() {
    const trail = getGuidedStoryStep(state);
    const storyReady = ["home", "complete"].includes(state.questStage);
    const cocoInTown = ["meet", "complete"].includes(state.questStage);
    const caring = state.questStage === "care";
    const caringActionsReady = caring && cocoCareStatus().checkInComplete;
    const fountainWords = [...state.discovered]
      .map((key) => story.vocabulary[key]?.label)
      .filter(Boolean)
      .slice(-3);
    if (!fountainWords.length) fountainWords.push("hello", "friend", "star");
    return `
      <div class="town-stage open-town-stage">
        <div class="scene-world town-world">
          <div class="town-sky"><div class="sun"></div><i class="cloud one"></i><i class="cloud two"></i><i class="cloud three"></i></div>
          <div class="town-hills back"></div><div class="town-hills front"></div><div class="town-road"></div>
          <div class="open-town-copy">
            <p class="eyebrow">A little world that listens</p>
            <h1>${state.questStage === "complete" ? "Coco is home.<br />Where next?" : "Where should we<br />go today?"}</h1>
            <p>${state.questStage === "complete" ? "The story is complete, and the whole town still remembers your adventure." : "Follow the glowing story route. New places wake up when the adventure reaches them."}</p>
          </div>
          ${renderTownPlace("bakery", "🥐", "Moonbeam Bakery", trail.location === "bakery" ? trail.title : caringActionsReady ? "A warm snack for Coco" : caring ? "Check on Coco in the Park first" : "Order a treat", "place-bakery", trail.location === "bakery")}
          ${renderTownPlace("school", "☆", "Star School", trail.location === "school" ? trail.title : caringActionsReady ? "Tell his friends he's safe" : caring ? "Check on Coco in the Park first" : "Words and colors", "place-school", trail.location === "school")}
          ${renderTownPlace("storyhouse", "⌂", "Story House", trail.location === "storyhouse" ? trail.title : storyReady ? "Your story is ready" : "Stories live here", "place-story", trail.location === "storyhouse")}
          ${renderTownPlace("park", "♧", "Whispering Park", trail.location === "park" ? trail.title : "Paths and secrets", "place-park", trail.location === "park")}
          ${renderTownPlace("petshop", "🐾", "Pet Shop", trail.location === "petshop" ? trail.title : state.questStage === "meet" ? "Coco is waiting" : caringActionsReady ? "A soft towel is here" : caring ? "Check on Coco in the Park first" : "Where it began", "place-petshop", trail.location === "petshop")}
          ${cocoInTown ? `<button class="town-coco open-town-coco" data-utterance="Can I pet Coco?" aria-label="Talk to and pet Coco">${renderCoco("happy")}</button>` : state.questStage === "search" ? `<button class="town-butterfly" data-utterance="I see the blue butterfly" aria-label="Follow the blue butterfly">🦋<small>follow me</small></button>` : ""}
          <button class="town-fountain" data-utterance="The fountain has water" aria-label="Explore the town fountain"><span>♒</span><small>fountain</small></button>
          ${hasEasterEgg(state, "word-fountain") ? `<button class="fountain-words" data-easter-id="word-fountain" aria-label="Open the Whispering Fountain surprise">${fountainWords.map((word) => `<i>${escapeHtml(word)}</i>`).join("")}</button>` : ""}
          ${hasEasterEgg(state, "night-story") ? `<button class="town-fireflies" data-easter-id="night-story" aria-label="Listen to the firefly story"><i></i><i></i><i></i><strong>secret story</strong></button>` : ""}
        </div>
        ${renderWorldDock()}
      </div>
    `;
  }

  function renderTownPlace(location, icon, label, note, className, featured = false) {
    const visited = state.visited.has(location);
    const access = getSceneAccess(state, location);
    return `<button class="town-place ${className} ${featured && access.unlocked ? "featured" : ""} ${visited ? "visited" : ""} ${access.unlocked ? "" : "locked"}" ${access.unlocked ? `data-location="${location}"` : "disabled"} aria-label="${escapeHtml(`${label} · ${access.unlocked ? note : access.reason}`)}"><span>${access.unlocked ? icon : "🔒"}</span><strong>${label}</strong><small>${access.unlocked ? note : access.reason}</small>${visited ? "<i>✓ visited</i>" : access.unlocked ? "" : "<i>Story locked</i>"}</button>`;
  }

  function renderPetShop() {
    const cocoVisible = ["meet", "care", "home", "complete"].includes(state.questStage) || state.escapeBeat;
    const positionCount = masteryCount(state, "positionWords");
    const adventure = getAdventureProgress(state);
    const positionPower = getLessonOutcomeProgress(state, story).find((outcome) => outcome.id === "position-power");
    const petshopTitle = state.questStage === "meet" ? adventure.ready ? "Position Power complete" : `Position Power · ${positionPower?.count ?? 0}/${positionPower?.required ?? 3}` : state.questStage === "care" ? "A soft towel for Coco" : state.questStage === "search" ? "The butterfly trail" : "Coco is safe";
    const ballPlace = state.objectPositions?.ball ?? "floor";
    const ballLabels = { floor: "on the floor", table: "on the table", box: "in the box", "under-table": "under the table" };
    const nextBallCommand = { floor: "Put the ball on the table", table: "Put the ball in the box", box: "Put the ball under the table", "under-table": "Put the ball on the floor" }[ballPlace];
    return `
      <div class="petshop-stage world-location-stage">
        <div class="scene-world petshop-world">
          <div class="room-wall"><i></i><i></i><i></i></div><div class="room-window"><span></span></div><div class="room-shelf"><i></i><i></i><i></i></div>
          <div class="shop-door ${state.escapeBeat ? "opening" : ""}"><i></i><span class="door-light"></span></div><div class="door-bell ${state.escapeBeat ? "ringing" : ""}">●</div>
          <button class="room-table explore-object" data-utterance="table" aria-label="Explore the table"><span></span><i></i><i></i></button>
          <button class="room-box explore-object" data-utterance="box" aria-label="Explore the box"><span></span></button>
          <button class="red-ball explore-object at-${ballPlace} ${ballPlace === "floor" ? "" : "has-moved"} ${state.questStage === "meet" && positionCount < 2 ? "learning-target" : ""}" data-place="${ballLabels[ballPlace]}" data-utterance="${nextBallCommand}" aria-label="Move the red ball; it is ${ballLabels[ballPlace]}"></button><div class="room-rug"></div>
          ${state.questStage === "care" && cocoCareStatus().checkInComplete ? `<button class="room-towel" data-utterance="Let's dry Coco with a towel" aria-label="Dry Coco with a towel"><span>▱</span><small>towel</small></button>` : ""}
          ${cocoVisible ? `<button class="coco-character at-${state.dogPlace} ${state.escapeBeat ? "is-escaping" : "is-inviting"}" data-utterance="Can I pet Coco?" aria-label="Talk to and pet Coco">${renderCoco("happy")}</button>` : `<div class="butterfly-trail"><i></i><i></i><i></i><span>🦋</span></div>`}
          ${state.lastSentence && cocoVisible ? `<div class="world-sentence"><span>✦</span><strong>${state.lastSentence}</strong></div>` : ""}
          <div class="scene-label"><small>Open world · Pet Shop</small><strong>${petshopTitle}</strong></div>
        </div>
        ${renderWorldDock()}
      </div>
    `;
  }

  function renderPark() {
    const searching = state.questStage === "search";
    const found = ["care", "home", "complete"].includes(state.questStage);
    const packedFood = getPackedFood(state);
    const trail = getGuidedStoryStep(state);
    return `
      <div class="park-stage world-location-stage">
        <div class="scene-world park-world">
          <div class="park-sky"><i class="cloud one"></i><i class="cloud two"></i></div><div class="park-moon"></div><div class="park-hill far"></div><div class="park-hill near"></div><div class="park-ground"></div>
          <button class="oak-tree open-clue ${state.clues.has("bush") ? "done" : ""}" data-utterance="I hear a sound behind the tree" aria-label="Explore the old tree"><span class="trunk"></span><span class="leaves"></span></button>
          <button class="park-clue paw-trail active ${state.clues.has("tracks") ? "done" : ""}" data-utterance="I found paw prints" aria-label="Explore the paw prints"><i></i><i></i><i></i><i></i></button>
          <button class="park-clue puddle active ${state.clues.has("puddle") ? "done" : ""}" data-utterance="The puddle is wet" aria-label="Explore the puddle"><span></span></button>
          <button class="park-clue shaking-bush active ${state.clues.has("bush") ? "done" : ""}" data-utterance="I hear a sound in the bush" aria-label="Explore the bush"><span></span></button>
          <div class="park-bench"><span></span><i></i><i></i></div>
          <button class="park-coco ${found ? "revealed" : "hidden"}" data-utterance="Can I pet Coco?" aria-label="Comfort Coco">${renderCoco(state.dogScared ? "scared" : "happy", state.dogWet)}</button>
          ${searching && state.clues.has("map") ? `<button class="park-map-route" data-utterance="The blue map points behind the old tree"><span>🗺️</span><strong>School trail map</strong><small>Blue arrow → old tree</small></button>` : ""}
          ${state.questStage === "care" && cocoCareStatus().checkInComplete && packedFood ? `<button class="park-care-pack" data-utterance="Give Coco the ${packedFood}"><span>${packedFood === "cake" ? "🧁" : packedFood === "cookie" ? "🍪" : "🥖"}</span><strong>Betty packed this</strong><small>Give the ${packedFood} to Coco</small></button>` : ""}
          ${hasEasterEgg(state, "moon-garden") ? `<button class="moon-garden-gate" data-easter-id="moon-garden" aria-label="Enter the secret Moon Garden"><span>🌙</span><strong>Moon Garden</strong><small>secret path</small></button>` : ""}
          <div class="scene-label light"><small>Open world · Whispering Park</small><strong>${found ? "Coco is safe" : searching ? "Follow any clue" : "A quiet place to explore"}</strong></div>
          ${found ? `<div class="world-sentence light"><span>✦</span><strong>Coco is behind the tree!</strong></div>` : ""}
          ${state.questStage === "care" ? renderCocoCarePath() : `<div class="clue-counter"><small>${searching ? "Clues found" : "Your clues"}</small><strong>${state.clues.size}</strong><span>${found ? "This is where you found Coco" : canFindCoco(state) ? "Your evidence points to the old tree" : "Explore different places and follow a Park clue"}</span></div>`}
        </div>
        ${renderWorldDock()}
      </div>
    `;
  }

  function cocoCareStatus() {
    const outcomes = getLessonOutcomeProgress(state, story);
    const report = outcomes.find((item) => item.id === "coco-report");
    const caringWords = outcomes.find((item) => item.id === "caring-words");
    const ideaCount = Math.min(state.careOptions.size, 2);
    return {
      report,
      caringWords,
      ideaCount,
      checkInComplete: Boolean(report?.complete && caringWords?.complete),
    };
  }

  function renderCocoCarePath() {
    const { report, caringWords, ideaCount } = cocoCareStatus();
    const steps = [
      ["Look & describe", "Say how Coco looks or feels", Boolean(report?.complete), `${report?.count ?? 0}/${report?.required ?? 2}`],
      ["Say kind words", "Help Coco feel safe", Boolean(caringWords?.complete), `${caringWords?.count ?? 0}/${caringWords?.required ?? 1}`],
      ["Find two ways to help", "Then choose the story ending", ideaCount >= 2, `${ideaCount}/2`],
    ];
    const current = Math.max(0, steps.findIndex((step) => !step[2]));
    return `<aside class="coco-care-path" aria-label="Coco care steps"><header><small>COCO IS FOUND · DO THESE IN ORDER</small><strong>Help Coco, one step at a time</strong></header>${steps.map(([title, detail, complete, count], index) => `<div class="${complete ? "complete" : index === current ? "current" : "waiting"}"><span>${complete ? "✓" : index + 1}</span><p><strong>${escapeHtml(title)}</strong><small>${escapeHtml(detail)}</small></p><i>${escapeHtml(count)}</i></div>`).join("")}</aside>`;
  }

  function renderCommunityPlace() {
    const storyReady = ["home", "complete"].includes(state.questStage);
    const packedFood = getPackedFood(state);
    const colorCount = masteryCount(state, "colors");
    const hasBlue = state.mastery?.colors?.has("blue");
    const hasBranchReward = (state.location === "bakery" && Boolean(packedFood))
      || (state.location === "school" && state.clues.has("school"));
    const data = {
      bakery: { icon: "🥐", eyebrow: "Moonbeam Bakery", title: "Warm words, warm bread", character: "Betty the Baker", decor: "🥖", tone: "gold" },
      school: { icon: "☆", eyebrow: "Star School", title: "Words are hiding everywhere", character: "Ms. Maple", decor: "ABC", tone: "blue" },
      storyhouse: { icon: "⌂", eyebrow: "Story House", title: storyReady ? "Your adventure is ready" : "Every adventure leaves a story", character: "Milo", decor: "📖", tone: "violet" },
    }[state.location];
    const characterUtterance = state.location === "bakery"
      ? state.questStage === "search" ? "Have you seen Coco?" : state.questStage === "care" ? "A warm snack for Coco" : "Hello Betty"
      : state.location === "school"
        ? state.questStage === "search" ? "Did you see Coco?" : state.questStage === "care" ? "Coco is safe" : "Hello Ms. Maple"
        : "Hello Milo";
    return `
      <div class="community-stage tone-${data.tone}">
        <div class="scene-world community-world ${hasBranchReward ? "has-branch-reward" : ""}">
          <div class="community-window"><i></i><span></span></div><div class="community-shelf"><i></i><i></i><i></i></div>
          <div class="community-sign"><span>${data.icon}</span><small>Open world</small><strong>${data.eyebrow}</strong></div>
          <button class="community-character" data-utterance="${characterUtterance}" aria-label="Talk to ${data.character}"><div>${data.decor}</div><strong>${data.character}</strong><small>Tap to talk</small></button>
          ${state.location === "bakery" ? `<button class="scene-evidence bakery-evidence ${state.clues.has("baker") ? "done" : state.questStage === "search" ? "active" : ""}" data-utterance="I found a flour paw print" aria-label="Explore the flour paw print"><span>🐾</span><strong>${state.clues.has("baker") ? "Clue found" : "Flour paw print"}</strong><small>${state.clues.has("baker") ? "It points toward the park" : "Tap it or describe what you see"}</small></button>` : ""}
          ${state.location === "school" ? `<button class="scene-evidence school-evidence ${state.clues.has("school") ? "done" : state.questStage === "search" ? "active" : ""}" data-utterance="I found paw prints on the blue board" aria-label="Explore the chalk paw trail"><span>🐾</span><strong>${state.clues.has("school") ? "Trail noticed" : "Chalk paw trail"}</strong><small>${state.clues.has("school") ? (state.clues.has("map") ? "The blue route is complete" : "Try a color word next") : "Tap it or describe what you see"}</small></button>` : ""}
          ${state.location === "bakery" ? `<div class="bakery-tray ${state.questStage === "search" && !packedFood ? "learning-target" : ""}"><button data-utterance="${state.questStage === "search" ? "Pack one bread for Coco, please" : "One bread, please"}">🥖<small>bread</small></button><button data-utterance="${state.questStage === "search" ? "Pack one cake for Coco, please" : "Can I have one cake, please?"}">🧁<small>cake</small></button><button data-utterance="${state.questStage === "search" ? "Pack one cookie for Coco, please" : "One cookie, please"}">🍪<small>cookie</small></button></div>${packedFood ? `<div class="branch-reward bakery-reward"><span>✓</span><strong>Helpful item found</strong><small>${packedFood} packed for Coco</small></div>` : ""}` : ""}
          ${state.location === "bakery" && hasEasterEgg(state, "rainbow-cake") ? `<button class="rainbow-cake" data-easter-id="rainbow-cake" aria-label="Open the Rainbow Cake surprise"><span>🌈</span><strong>Secret cake</strong><small>Tap to discover</small></button>` : ""}
          ${state.location === "school" ? `<div class="color-wall ${state.questStage === "search" && state.clues.has("school") && !state.clues.has("map") ? "learning-target" : ""}"><button data-utterance="The butterfly is blue" class="blue ${state.clues.has("school") && !hasBlue ? "next-color" : ""}">blue</button><button data-utterance="The ball is red" class="red ${state.clues.has("school") && hasBlue && colorCount < 2 ? "next-color" : ""}">red</button><button data-utterance="The sun is yellow" class="yellow">yellow</button></div>` : ""}
          ${state.location === "school" && state.clues.has("school") ? `<div class="branch-reward school-mission ${state.clues.has("map") ? "complete" : ""}"><span>${state.clues.has("map") ? "✓" : Math.min(colorCount, 2)}</span><strong>${state.clues.has("map") ? "Color key unlocked" : `Color code · ${Math.min(colorCount, 2)}/2`}</strong><small>${state.clues.has("map") ? "The blue map points to the old tree" : hasBlue ? "Blue found—name one different color" : "Find blue, then one more color"}</small></div>` : ""}
          ${state.location === "storyhouse" ? `<div class="story-memory"><span>${state.clues.size}</span><p><small>Clues remembered</small>${storyReady ? "Milo can turn your real journey into a first draft." : state.questStage === "care" ? "Coco is safe. Help him feel better before going home." : "Find Coco, then your journey will become a book."}</p>${storyReady ? `<button data-action="open-story">${state.questStage === "complete" ? "Read my story again" : "Make my story"} →</button>` : `<button data-action="quest-next">Continue the adventure →</button>`}</div>` : ""}
          <div class="community-title"><p class="eyebrow">${data.eyebrow}</p><h1>${data.title}</h1></div>
        </div>
        ${renderWorldDock()}
      </div>
    `;
  }

  function renderWorldDock() {
    const phrases = contextPhrases();
    const trail = getGuidedStoryStep(state);
    const task = smartQuestHint();
    const voiceExample = phrases[0] || mainStoryNextStep();
    const participation = getParticipationProgress(state);
    const lesson = getLessonProgress(state, story);
    const activeOutcomeId = state.questStage === "meet" ? "position-power" : state.questStage === "search" ? "clue-talk" : state.questStage === "care" ? (lesson.outcomes.find((item) => ["coco-report", "caring-words"].includes(item.id) && !item.complete)?.id || "caring-words") : null;
    const activeOutcome = lesson.outcomes.find((item) => item.id === activeOutcomeId);
    const contributionSaved = state.lastContribution?.stage === state.questStage;
    const guidedPlaceholder = {
      "meet-coco": "Where should Coco hide?",
      "bakery-clue": "What do you see glowing?",
      "bakery-food": "Which food should Betty pack?",
      "school-clue": "What marks do you see?",
      "school-map": "What color was the butterfly?",
      "find-coco": "Where is Coco?",
      "report-coco": "Coco is wet and scared.",
      "speak-care": "Coco, you are safe now.",
      "care-coco-food": "How will you help Coco?",
      "care-coco-towel": "How will you help Coco?",
      "make-story": "Ready to make your story?",
      "read-story": "Open your finished story…",
    }[trail.id];
    const locationPlaceholder = {
      town: "Where do you want to go?",
      petshop: state.questStage === "meet" ? "Tell Coco where to hide…" : state.questStage === "care" ? "How can we help Coco?" : "Name something you see…",
      bakery: "Ask about Coco, or order something…",
      school: "Ask about Coco, or name a color…",
      park: "Describe a clue, or say where Coco is…",
      storyhouse: "Tell Milo what you remember…",
    }[state.location];
    const placeholder = state.location === trail.location && guidedPlaceholder ? guidedPlaceholder : locationPlaceholder;
    const taskPlace = LOCATION_LABELS[task.location] || LOCATION_LABELS[state.location];
    const atTaskPlace = state.location === task.location;
    const agentLabels = {
      ready: "Agent ready",
      instant: "Instant response",
      waiting: "Waiting for reply",
      online: "Agent connected",
      fallback: "Local mode",
    };
    const inputCredit = activeOutcome
      ? `<i class="input-credit ${activeOutcome.complete ? "complete" : ""}">${activeOutcome.complete ? `✓ ${escapeHtml(activeOutcome.title)} learned` : contributionSaved ? `✓ Your words saved · ${activeOutcome.count}/${activeOutcome.required}` : `${escapeHtml(activeOutcome.title)} · ${activeOutcome.count}/${activeOutcome.required}`}</i>`
      : "";
    const optionalPractice = renderOptionalChallenge();
    const conversationDock = renderLessonInputDock({
      formId: "world-form",
      inputId: "world-input",
      statusId: "world-input-status",
      inputValue: worldInputDraft,
      lastHeard: state.lastHeard,
      example: voiceExample,
      placeholder,
      optionalContent: inputCredit,
      agentBusy,
      voiceSubmitting,
      speechSupported: speechInput.supported,
      statusText: agentBusy ? "Waiting for Coco’s reply…" : speechInput.supported ? "Press Enter to send · voice sends after a short pause" : "Press Enter to send · voice unavailable here",
    });
    const taskSteps = {
      "report-coco": ["1 · Look at Coco", "2 · Describe one detail"],
      "speak-care": ["1 · Talk to Coco", "2 · Say one kind sentence"],
      "explore-care": ["1 · Visit a caring place", "2 · Find two helpful ideas"],
    }[trail.id] || [atTaskPlace ? "1 · Look or choose in the scene" : `1 · Go to ${taskPlace}`, "2 · Speak or type your English"];
    return `
      <section class="world-dock lesson-action-dock" aria-label="Current task and English input">
        <section class="lesson-dock-guide">
          <div class="guide-avatar">${renderMilo()}</div>
          <div class="guide-copy"><small>${escapeHtml(state.guide.speaker)} · YOUR GUIDE<span class="agent-presence state-${agentStatus}"><i></i>${agentLabels[agentStatus]}</span></small><h2>${escapeHtml(state.guide.text)}</h2><p>${escapeHtml(state.guide.hint)}</p></div>
        </section>
        <section class="lesson-task-card kind-${task.kind}">
          <header><small>LESSON 1 · CURRENT TASK</small><b>${escapeHtml(taskPlace)}</b></header>
          <h2><span>${task.icon}</span>${escapeHtml(task.title)}</h2>
          <p>${escapeHtml(task.detail)}</p>
          <div class="lesson-task-steps"><span>${escapeHtml(taskSteps[0])}</span><span>${escapeHtml(taskSteps[1])}</span></div>
          ${atTaskPlace ? "" : `<button class="lesson-task-primary" data-location="${task.location}">${escapeHtml(task.cta)} <span>→</span></button>`}
        </section>
        <section class="lesson-dock-actions">
          ${conversationDock}
          <div class="optional-challenge-slot dock-optional-challenge">${optionalPractice}</div>
        </section>
      </section>
    `;
  }

  function mainStoryNextStep() {
    return getGuidedStoryStep(state).title;
  }

  function smartQuestHint() {
    const trail = getGuidedStoryStep(state);
    const progress = getAdventureProgress(state);
    const participation = progress.requirements.participation;
    const place = LOCATION_LABELS[trail.location];
    if (trail.mode === "story" || trail.action === "open_story") {
      return {
        kind: "ready",
        icon: "✨",
        title: "The story is ready!",
        detail: "Continue when you feel ready.",
        location: trail.location,
        target: trail.target,
        cta: state.location === trail.location ? "Continue story" : `Go to ${place}`,
      };
    }
    const powerGuidance = {
      "move-ball": { kind: "explore", icon: "🔴", title: "Move the red ball", detail: "Try two places: on the table, in the box, or under the table.", recommendedTitle: "Move the red ball" },
      "describe-ball": { kind: "english", icon: "🎙️", title: "Tell Coco where the ball is", detail: "Use your own words. Try: “The ball is in the box.”", recommendedTitle: "Move the red ball" },
      "report-coco": { kind: "english", icon: "🔍", title: "Describe Coco", detail: trail.hint, recommendedTitle: null },
      "speak-care": { kind: "english", icon: "💛", title: "Say something kind to Coco", detail: "Try: “I can help you” or “Don't be scared.”", recommendedTitle: null },
    }[trail.id];
    if (powerGuidance) return {
      ...powerGuidance,
      location: trail.location,
      target: trail.target,
      cta: state.location === trail.location ? "Try it now" : `Go to ${place}`,
    };
    if (participation?.target && !participation.complete) {
      const friendlyEnglish = {
        meet: ["Say hello to Coco", "Try: “Hello, Coco!”", "Talk to Coco"],
        search: ({
          bakery: ["Ask Betty about Coco", "Try: “Have you seen Coco?”", "Ask around Bakery"],
          school: ["Tell Ms. Maple what you see", "Try: “I see paw prints.”", "Explore Star School"],
          park: ["Describe one Park clue", "Try: “The puddle is wet.”", "Investigate the Park"],
          town: ["Describe something in Town", "Try: “I see a blue butterfly.”", "Look around Town"],
        })[trail.location],
        care: ["Say something kind to Coco", "Try: “Coco, you are safe.”", null],
      }[state.questStage] || [trail.prompt, "One short sentence is enough.", null];
      return {
        kind: "english",
        icon: "🎙️",
        title: friendlyEnglish[0],
        detail: friendlyEnglish[1],
        location: trail.location,
        target: "#world-input",
        cta: state.location === trail.location ? "Try it now" : `Go to ${place}`,
        recommendedTitle: friendlyEnglish[2],
      };
    }
    if (progress.points < progress.target) {
      const hardSearchGate = state.questStage === "search" && (!progress.requirements.hasParkEvidence || !progress.requirements.hasTreeEvidence);
      const idea = (hardSearchGate ? explorationIdeas().find((item) => !item.done && item.location === trail.location) : null)
        || explorationIdeas().find((item) => !item.done && item.location === state.location)
        || explorationIdeas().find((item) => !item.done && item.location === trail.location)
        || explorationIdeas().find((item) => !item.done);
      if (idea) return {
        kind: "explore",
        icon: idea.icon,
        title: idea.title,
        detail: idea.note,
        location: idea.location,
        target: idea.location === trail.location ? trail.target : "#world-input",
        cta: state.location === idea.location ? "Try it now" : `Go to ${LOCATION_LABELS[idea.location]}`,
        recommendedTitle: idea.title,
      };
    }
    return {
      kind: "clue",
      icon: "🔎",
      title: state.questStage === "search" ? "Find one more Park clue" : progress.requirements.missing[0] || trail.prompt,
      detail: state.questStage === "search" ? "Look for paw prints, water, or a sound." : "Try one new idea.",
      location: trail.location,
      target: trail.target,
      cta: state.location === trail.location ? "Show me where" : `Go to ${place}`,
    };
  }

  function answerMainStoryQuestion() {
    const guidance = smartQuestHint();
    setGuide("Milo", guidance.title, guidance.detail, "story");
    render();
    speak(`${guidance.title} ${guidance.detail}`);
  }

  function phraseActionReceipt(result) {
    if (result.intent === "place_object") {
      const sentence = {
        "ball:on:table": "The ball is on the table.",
        "ball:in:box": "The ball is in the box.",
        "ball:under:table": "The ball is under the table.",
        "ball:on:floor": "The ball is on the floor.",
      }[`${result.object}:${result.relation}:${result.destination}`];
      if (sentence) return `${sentence} Say or type it yourself to save the English turn.`;
    }
    return "The action worked. Say or type your own English to save this turn.";
  }

  function contextPhrases() {
    if (state.location === "town") return state.questStage === "search" ? ["I see the blue butterfly", "Visit the bakery", "Let's go to the park"] : ["Go to the Pet Shop", "Visit the bakery", "Look at the fountain"];
    if (state.location === "petshop") {
      if (state.questStage === "meet") return masteryCount(state, "positionWords") < 2
        ? ["Put the ball on the table", "Put the ball in the box", "Put the ball under the table"]
        : ["Coco, hide in the box!", "Coco, hide under the table!", "Put the ball on the floor"];
      if (state.questStage === "care") return ["Let's dry Coco with a towel", "Use a towel for Coco", "Go to the bakery"];
      return ["Put the ball on the table", "Put the ball in the box", "Put the ball under the table"];
    }
    if (state.location === "bakery") {
      if (state.questStage === "search") return [state.clues.has("baker") ? "Pack one cake for Coco, please" : "I found a flour paw print", "Have you seen Coco?", "Go to the school"];
      if (state.questStage === "care") return ["A warm snack for Coco", "Coco is hungry", "Go to the Pet Shop"];
      return ["One bread, please", "One cookie, please", "Go to the Pet Shop"];
    }
    if (state.location === "school") {
      if (state.questStage === "search") {
        const colors = state.mastery?.colors ?? new Set();
        const colorPhrase = !colors.has("blue") ? "The butterfly is blue" : colors.size < 2 ? "The ball is red" : "Go to the park";
        return [state.clues.has("school") ? colorPhrase : "I found paw prints on the blue board", "Did you see Coco?", state.clues.has("map") ? "Go to the park" : "The sun is yellow"];
      }
      if (state.questStage === "care") return ["Coco is safe!", "Welcome back, Coco!", "Go to the bakery"];
      return ["The butterfly is blue", "Hello, teacher", "Go to the Pet Shop"];
    }
    if (state.location === "park") {
      const packedFood = getPackedFood(state);
      const careStep = getGuidedStoryStep(state).id;
      if (state.questStage === "care" && careStep === "report-coco") return [state.dogWet ? "Coco is wet" : "Coco is scared", "Coco is behind the tree", "He looks scared"];
      if (state.questStage === "care" && careStep === "speak-care") return ["Coco, you are safe now", "I can help you", "Don't be scared"];
      if (state.questStage === "care" && packedFood) return [`Give Coco the ${packedFood}`, "Take Coco to the Pet Shop", "Go back to town"];
      const phrases = ["I found paw prints", "The puddle is wet", "I hear a sound in the bush"];
      if (canFindCoco(state) && state.questStage === "search") phrases.push("Coco is behind the tree!");
      return phrases;
    }
    return ["home", "complete"].includes(state.questStage) ? [state.questStage === "complete" ? "Read my story" : "Make my story", "Go back to town"] : ["Go back to town", "Go to the Pet Shop"];
  }

  function renderWorldNav() {
    const places = [["town", "⌂", "Town"], ["petshop", "🐾", "Pets"], ["bakery", "🥐", "Bakery"], ["school", "☆", "School"], ["park", "♧", "Park"], ["storyhouse", "▤", "Story"]];
    return `<nav class="world-nav" aria-label="Town places">${places.map(([location, icon, label]) => {
      const access = getSceneAccess(state, location);
      return `<button class="${state.location === location ? "current" : ""} ${access.unlocked ? "" : "locked"}" ${access.unlocked ? `data-location="${location}"` : "disabled"} title="${escapeHtml(access.unlocked ? label : access.reason)}"><span>${access.unlocked ? icon : "🔒"}</span><small>${label}</small>${state.visited.has(location) ? "<i></i>" : ""}</button>`;
    }).join("")}</nav>`;
  }

  function explorationIdeas() {
    if (state.questStage === "meet") return [
      { icon: "🎙️", title: "Talk to Coco", note: "Say hello in your own way", location: "petshop", done: state.pointRewards.has("meet:greet-coco") },
      { icon: "🔴", title: "Move the red ball", note: "Try on, in, or under", location: "petshop", done: [...state.pointRewards].some((key) => key.startsWith("meet:ball-")) },
      { icon: "👀", title: "Name what you see", note: "Find the box, table, or ball", location: "petshop", done: [...state.pointRewards].some((key) => key.startsWith("meet:petshop-object-")) },
    ];
    if (state.questStage === "search") {
      const hasTreeEvidence = state.clues.has("bush") || state.clues.has("map");
      return [
        { icon: "🥐", title: "Ask around Bakery", note: "Find a clue or make a polite order", location: "bakery", done: state.clues.has("baker") || masteryCount(state, "manners") > 0 },
        { icon: "🎨", title: "Explore Star School", note: "Notice tracks or use a color word", location: "school", done: state.clues.has("school") || masteryCount(state, "colors") > 0 },
        { icon: "🔎", title: "Investigate the Park", note: hasTreeEvidence ? "The clues now point to the old tree" : masteryCount(state, "parkClues") > 0 ? "One clue found—what is near the old tree?" : "Describe tracks, water, or a sound", location: "park", done: hasTreeEvidence },
        { icon: "🦋", title: "Look around Town", note: "Follow the butterfly or inspect the fountain", location: "town", done: state.clues.has("square") || state.sideActivities.has("town-fountain") },
      ];
    }
    if (state.questStage === "care") return [
      { icon: "🧺", title: "Find something warm", note: "The Pet Shop has a soft towel", location: "petshop", done: state.careOptions.has("towel") },
      { icon: "🍪", title: "Find a snack", note: "Ask Betty for food for Coco", location: "bakery", done: state.careOptions.has("snack") },
      { icon: "⭐", title: "Tell Coco's friends", note: "Let the class know he is safe", location: "school", done: state.careOptions.has("friends") },
    ];
    return [];
  }

  function renderLessonPowers(compact = false) {
    const lesson = getLessonProgress(state, story);
    return `<div class="lesson-powers ${compact ? "compact" : ""}" aria-label="English powers learned">${lesson.outcomes.map((outcome) => `<div class="${outcome.complete ? "complete" : ""}"><span>${outcome.complete ? "✓" : outcome.icon}</span><p><strong>${escapeHtml(outcome.title)}</strong>${compact ? "" : `<small>${escapeHtml(outcome.canDo)}</small>`}</p><i>${outcome.count}/${outcome.required}</i></div>`).join("")}</div>`;
  }

  function renderExplorationBoard() {
    const progress = getAdventureProgress(state);
    const ideas = explorationIdeas();
    const bonusId = bonusChallengeForCurrentContext();
    const challengeLock = lockedChallengeForCurrentContext();
    const guidance = smartQuestHint();
    const recommendedIndex = ideas.findIndex((idea) => !idea.done && idea.title === guidance.recommendedTitle);
    return `
        <aside class="exploration-board" aria-labelledby="explore-title" data-stop-close>
          <button class="challenge-close" data-action="exploration-close" aria-label="Close adventure journal">×</button>
          <header><span>🧭</span><div><p class="challenge-kicker">Lesson 1 compass · ${progress.total} bonus ★</p><h2 id="explore-title">${progress.ready ? "Your story is ready" : "Choose your own direction"}</h2><p>${progress.ready ? "Continue the story now, or stay and explore a little longer." : "Grow your English Powers in any order the story allows."}</p></div></header>
          ${renderLessonPowers(true)}
          <section class="next-step-card kind-${guidance.kind}">
            <div class="next-step-icon">${guidance.icon}</div><div class="next-step-copy"><small>NEXT STEP</small><h3>${escapeHtml(guidance.title)}</h3><p>${escapeHtml(guidance.detail)}</p></div>
            <div class="next-step-stars"><span>ABC</span><strong>${getLessonProgress(state, story).completed}</strong><small>/ ${getLessonProgress(state, story).total}</small></div>
            <button class="next-step-action" data-action="guided-next">${escapeHtml(guidance.cta)} <span>→</span></button>
          </section>
          <div class="exploration-ideas">${ideas.map((idea, index) => {
            const access = getSceneAccess(state, idea.location);
            return `<button ${access.unlocked ? `data-location="${idea.location}"` : "disabled"} class="${idea.done ? "done" : ""} ${index === recommendedIndex ? "recommended" : ""} ${access.unlocked ? "" : "locked"}">${index === recommendedIndex && access.unlocked ? "<b>TRY THIS</b>" : ""}<span>${idea.done ? "✓" : access.unlocked ? idea.icon : "🔒"}</span><p><strong>${escapeHtml(idea.title)}</strong><small>${escapeHtml(access.unlocked ? idea.note : access.reason)}</small></p><i>${access.unlocked ? "→" : ""}</i></button>`;
          }).join("")}</div>
          <div class="journal-footer"><button class="soft-action" data-action="exploration-close">Keep exploring</button>${bonusId ? `<button class="bonus-action treasure" data-action="bonus-challenge"><span>🎁</span><p><strong>Optional challenge · Easter egg trail</strong><small>Finish the questions to earn surprise stars</small></p></button>` : challengeLock ? `<div class="bonus-action locked"><span>🔒</span><p><strong>Challenge not unlocked yet</strong><small>${escapeHtml(challengeLock.reason)}</small></p></div>` : `<div class="bonus-action completed"><span>✓</span><p><strong>Optional challenge complete</strong><small>Your surprise stars have been added</small></p></div>`}</div>
        </aside>`;
  }

  async function followGuidedNext() {
    const trail = getGuidedStoryStep(state);
    const guidance = smartQuestHint();
    if (guidance.kind === "ready") {
      state.explorationOpen = false;
      render();
      await followQuest();
      return;
    }
    state.explorationOpen = false;
    if (state.location !== guidance.location) await goToLocation(guidance.location);
    else render();
    requestAnimationFrame(() => {
      const target = root.querySelector(guidance.target || trail.target) || root.querySelector("#world-input");
      target?.focus?.({ preventScroll: true });
      target?.animate?.([
        { filter: "brightness(1)", transform: "scale(1)" },
        { filter: "brightness(1.12) drop-shadow(0 0 16px rgba(255,220,74,.9))", transform: "scale(1.04)" },
        { filter: "brightness(1)", transform: "scale(1)" },
      ], { duration: 900, easing: "ease-out" });
    });
  }

  function renderStoryBeat() {
    if (state.questStage === "meet") return `
      <div class="challenge-backdrop story-beat-backdrop"><section class="story-beat-modal" role="dialog" aria-modal="true" aria-labelledby="story-beat-title" data-stop-close>
        <button class="challenge-close" data-action="story-beat-close" aria-label="Close story">×</button><span class="story-beat-icon">🐶</span><p class="challenge-kicker">Main story · Hide-and-seek</p><h2 id="story-beat-title">Coco is ready to play!</h2><p>You explored the Pet Shop together. Now choose where Coco should hide.</p><div class="story-beat-choices"><button data-story-choice="box"><span>📦</span><strong>In the box</strong><small>“Coco, hide in the box!”</small></button><button data-story-choice="table"><span>🪑</span><strong>Under the table</strong><small>“Coco, hide under the table!”</small></button></div></section></div>`;
    if (state.questStage === "search") return `
      <div class="challenge-backdrop story-beat-backdrop"><section class="story-beat-modal" role="dialog" aria-modal="true" aria-labelledby="story-beat-title" data-stop-close>
        <button class="challenge-close" data-action="story-beat-close" aria-label="Close story">×</button><span class="story-beat-icon">🔎</span><p class="challenge-kicker">Main story · Your best guess</p><h2 id="story-beat-title">Where is Coco?</h2><p>Your conversations and clues brought you to the old tree. Choose your final guess.</p><div class="story-beat-choices three"><button data-story-choice="bakery"><span>🥐</span><strong>At the Bakery</strong></button><button data-story-choice="tree"><span>🌳</span><strong>Behind the tree</strong></button><button data-story-choice="school"><span>⭐</span><strong>Inside the School</strong></button></div></section></div>`;
    const labels = { towel: ["🧺", "Dry Coco", "Use the soft towel"], snack: ["🍪", "Feed Coco", "Share a warm snack"], friends: ["⭐", "Cheer for Coco", "Tell his friends he is safe"] };
    const choices = [...state.careOptions];
    return `
      <div class="challenge-backdrop story-beat-backdrop"><section class="story-beat-modal" role="dialog" aria-modal="true" aria-labelledby="story-beat-title" data-stop-close>
        <button class="challenge-close" data-action="story-beat-close" aria-label="Close story">×</button><span class="story-beat-icon">💛</span><p class="challenge-kicker">Main story · A caring ending</p><h2 id="story-beat-title">How will you help Coco?</h2><p>You discovered several kind ideas. Choose one for your story.</p><div class="story-beat-choices">${choices.map((choice) => `<button data-story-choice="${choice}"><span>${labels[choice][0]}</span><strong>${labels[choice][1]}</strong><small>${labels[choice][2]}</small></button>`).join("")}</div></section></div>`;
  }

  function rewardExploration(key, label, points = 1) {
    const reward = awardAdventurePoints(state, key, points);
    if (!reward.added) {
      if (reward.target && !reward.ready) showToast("You already tried that — a different discovery can earn another star.", "gentle");
      return reward;
    }
    state.coachOpen = false;
    queueRewardToast(reward.awarded, label, reward);
    announceEasterEggs(reward.newlyUnlocked);
    if (reward.ready) setGuide("Milo", "Main story unlocked!", "The glowing Story Trail at the top is ready whenever you are.", "story");
    return reward;
  }

  function challengeCandidatesForCurrentContext() {
    return {
      town: ["town-guide"],
      petshop: state.questStage === "care" ? ["care-coco-towel", "position-practice", "meet-coco"] : ["position-practice", "meet-coco"],
      bakery: state.questStage === "care" ? ["care-coco-food", "bakery-food", "bakery-clue"] : ["bakery-food", "bakery-clue"],
      school: ["school-map", "school-clue"],
      park: ["park-investigation", "find-coco"],
      storyhouse: ["story-memory", "make-story"],
    }[state.location] || [];
  }

  function bonusChallengeForCurrentContext() {
    return challengeCandidatesForCurrentContext().find((id) => !state.learning.completed.has(id) && getChallengeAccess(story, state, id).unlocked) || null;
  }

  function lockedChallengeForCurrentContext() {
    const id = challengeCandidatesForCurrentContext().find((challengeId) => !state.learning.completed.has(challengeId) && !getChallengeAccess(story, state, challengeId).unlocked);
    return id ? getChallengeAccess(story, state, id) : null;
  }

  function renderLearningChallenge() {
    const learning = state.learning;
    const challenge = getLearningChallenge(story, learning.activeId);
    if (!challenge) return "";
    const question = challenge.questions[Math.min(learning.questionIndex, challenge.questions.length - 1)];
    const attempts = learning.attempts[`${learning.activeId}:${learning.questionIndex}`] ?? 0;
    const rescueAnswer = question.answers?.[0] || question.sampleAnswer || (question.requiredGroups ? question.requiredGroups.map((group) => group[0]).join(" ") : "");
    const typeLabels = { choice: "Choose one", fill: "Fill the blank", dialogue: "Your turn to talk", description: "Describe the scene" };
    const visibleFeedback = learning.feedback || (learning.hintOpen ? question.hint : "");
    const chatHistory = learning.history?.length ? `<div class="challenge-chat-history"><small>CONVERSATION SO FAR</small>${learning.history.slice(-3).map((turn) => `<div><p><b>${escapeHtml(turn.speaker)}</b>${escapeHtml(turn.npc)}</p><p class="learner-turn"><b>You</b>${escapeHtml(turn.learner)}</p></div>`).join("")}</div>` : "";
    const dialoguePrompt = question.npcLine ? `<div class="dialogue-prompt"><span>${challenge.icon}</span><p><small>${escapeHtml(question.speaker || "Milo")}</small><strong>${escapeHtml(question.npcLine)}</strong></p></div>` : "";
    const answerArea = question.type === "choice"
      ? `<div class="challenge-options">${question.options.map((option, index) => `<button type="button" data-challenge-answer="${escapeHtml(option)}"><span>${String.fromCharCode(65 + index)}</span>${escapeHtml(option)}</button>`).join("")}</div>`
      : `<form id="learning-form" class="challenge-input"><input name="answer" autocomplete="off" placeholder="${escapeHtml(question.placeholder)}" aria-label="Your answer"><button>Check answer</button></form>`;
    const voiceAnswerPanel = learning.correct
      ? `<div class="challenge-voice-panel answered"><p><small class="challenge-voice-status" aria-live="polite">${learning.voiceHeard ? `I heard “${escapeHtml(learning.voiceHeard)}”. Answer checked!` : "Answer checked—great work!"}</small></p></div>`
      : `<div class="challenge-voice-panel ${voiceSubmitting ? "submitting" : speechInput.listening ? "listening" : ""}"><button type="button" class="listen-question" data-action="challenge-listen"><span>🔊</span><strong>Hear question</strong></button><button type="button" class="answer-by-voice ${voiceSubmitting ? "submitting" : speechInput.supported ? "" : "unsupported"}" data-action="challenge-voice" ${voiceSubmitting ? "disabled" : ""}><span>${voiceSubmitting ? "…" : speechInput.listening ? "■" : "🎙"}</span><strong>${voiceSubmitting ? "Waiting" : speechInput.listening ? "Finish answer" : "Say answer"}</strong></button><p><small class="challenge-voice-status" aria-live="polite">${voiceSubmitting ? "Waiting for your answer…" : learning.voiceHeard ? `I heard “${escapeHtml(learning.voiceHeard)}”.` : speechInput.supported ? question.type === "choice" ? "Say the words, A/B/C, or first/second/third. A short pause submits." : "Speak naturally. A short pause submits automatically." : "Voice is unavailable here; tap or type your answer."}</small></p></div>`;
    if (learning.finished) {
      return `
        <div class="challenge-backdrop">
          <section class="learning-modal challenge-success" role="dialog" aria-modal="true" aria-labelledby="challenge-title" data-stop-close>
            <div class="success-confetti" aria-hidden="true"><i>★</i><i>✦</i><i>●</i><i>★</i><i>✦</i></div>
            <div class="reward-seal"><span>${challenge.icon}</span><i>✓</i></div>
            <p class="challenge-kicker">Optional challenge complete · Surprise stars earned!</p>
            <h2 id="challenge-title">You unlocked the<br>${escapeHtml(challenge.reward)}!</h2>
            <p>You practised useful English and moved closer to the next hidden town surprise.</p>
            <div class="success-actions"><button class="soft-action" data-action="challenge-close">Back to exploring</button><button class="primary-action" data-action="challenge-next">Check star progress <span>→</span></button></div>
          </section>
        </div>`;
    }
    return `
      <div class="challenge-backdrop">
        <section class="learning-modal" role="dialog" aria-modal="true" aria-labelledby="challenge-title" data-stop-close>
          <button class="challenge-close" data-action="challenge-close" aria-label="Close task">×</button>
          <header class="challenge-header">
            <span class="challenge-icon">${challenge.icon}</span>
            <div><p class="challenge-kicker">${escapeHtml(challenge.label)} · Task ${learning.questionIndex + 1}/${challenge.questions.length}</p><h2 id="challenge-title">${escapeHtml(challenge.title)}</h2><p>${escapeHtml(challenge.intro)}</p></div>
          </header>
          <div class="challenge-treasure-promise"><span>🎁</span><p><small>COMPLETE ALL ${challenge.questions.length} QUESTIONS</small><strong>Earn stars toward a hidden town Easter egg</strong></p></div>
          <div class="challenge-progress" aria-label="Question progress">${challenge.questions.map((_, index) => `<i class="${index < learning.questionIndex ? "done" : index === learning.questionIndex ? "current" : ""}">${index < learning.questionIndex ? "✓" : index + 1}</i>`).join("")}</div>
          ${chatHistory}
          <div class="memory-strip"><small>Words to remember</small><div class="${challenge.words.length === 1 ? "single" : ""}">${challenge.words.map((item) => `<button data-speak="${escapeHtml(item.word)}"><strong>${escapeHtml(item.word)}</strong><span>${escapeHtml(item.meaning)}</span><i>🔊</i><small>${escapeHtml(item.example)}</small></button>`).join("")}</div></div>
          <div class="question-card">
            <span class="question-type">${typeLabels[question.type]}</span>
            ${dialoguePrompt}
            <p>${escapeHtml(question.prompt)}</p>
            ${question.visual ? `<div class="question-visual" aria-hidden="true">${question.visual}</div>` : ""}
            <h3>${escapeHtml(question.sentence)}</h3>
            ${answerArea}
            ${voiceAnswerPanel}
            ${visibleFeedback ? `<div class="challenge-feedback ${learning.correct ? "correct" : "try-again"}" role="status"><span>${learning.correct ? "✓" : "💡"}</span><p><strong>${learning.correct ? escapeHtml(question.speaker || "Great job!") : learning.hintOpen && !learning.feedback ? "A gentle hint" : attempts >= 2 ? "Here's a bigger hint" : "Almost—try again"}</strong>${escapeHtml(visibleFeedback)}</p></div>` : ""}
            ${!learning.correct && attempts >= 2 && rescueAnswer ? `<button type="button" class="answer-rescue" data-challenge-answer="${escapeHtml(rescueAnswer)}"><span>✨</span><p><strong>Use a helping answer</strong><small>“${escapeHtml(rescueAnswer)}” — tap to continue</small></p></button>` : ""}
          </div>
          <footer class="challenge-footer"><button class="soft-action" data-action="challenge-close">Not now</button>${learning.correct ? `<button class="primary-action" data-action="challenge-continue">${learning.questionIndex < challenge.questions.length - 1 ? "Continue the conversation" : "Collect reward"} <span>→</span></button>` : `<button class="hint-action" data-action="challenge-hint">${learning.hintOpen ? "Hint is showing" : "I need a hint"}</button><span>Wrong answers are okay.</span>`}</footer>
        </section>
      </div>`;
  }

  function resetLearningModal() {
    state.learning.activeId = null;
    state.learning.questionIndex = 0;
    state.learning.feedback = null;
    state.learning.correct = false;
    state.learning.finished = false;
    state.learning.voiceHeard = "";
    state.learning.history = [];
    state.learning.hintOpen = false;
  }

  function openLearningChallenge(id) {
    if (!getLearningChallenge(story, id)) return false;
    const access = getChallengeAccess(story, state, id);
    if (!access.unlocked) { showToast(access.reason, "gentle"); return false; }
    if (speechInput.listening) { ignoreNextVoiceFinal = true; speechInput.cancel(); }
    state.wordPocketOpen = false;
    state.learning.activeId = id;
    state.learning.questionIndex = 0;
    state.learning.feedback = null;
    state.learning.correct = false;
    state.learning.finished = false;
    state.learning.voiceHeard = "";
    state.learning.history = [];
    state.learning.hintOpen = false;
    render();
    requestAnimationFrame(() => root.querySelector("#learning-form input")?.focus());
    return true;
  }

  function handleLearningAnswer(rawAnswer, { voice = false } = {}) {
    const learning = state.learning;
    const challenge = getLearningChallenge(story, learning.activeId);
    const question = challenge?.questions[learning.questionIndex];
    if (!question || learning.correct || learning.finished) return;
    if (!voice) learning.voiceHeard = "";
    const result = checkLearningAnswer(question, rawAnswer);
    const attemptKey = `${learning.activeId}:${learning.questionIndex}`;
    learning.attempts[attemptKey] = (learning.attempts[attemptKey] ?? 0) + 1;
    if (result.correct) {
      learning.correct = true;
      const friendlyReply = question.successReply || "You used the right English. Ready for the next step!";
      learning.feedback = result.correctedTo
        ? `I understood “${result.correctedTo}”. ${friendlyReply}`
        : result.partialAccepted
          ? `I understood your idea. That is enough to keep the conversation moving! ${friendlyReply}`
          : friendlyReply;
      learning.history ??= [];
      if (!learning.history.some((turn) => turn.questionIndex === learning.questionIndex)) learning.history.push({ questionIndex: learning.questionIndex, speaker: question.speaker || "Milo", npc: question.npcLine || question.prompt, learner: String(rawAnswer).trim(), reply: friendlyReply });
    } else {
      learning.correct = false;
      const answerHelp = question.answers?.[0] ? ` Try “${question.answers[0]}”.` : ` ${question.hint}`;
      learning.feedback = result.empty ? "Take your time—type, tap, or say an answer when you are ready." : learning.attempts[attemptKey] >= 2 ? `${question.retryReply || question.hint}${answerHelp}` : question.retryReply || question.hint;
    }
    render();
    if (voice) speak(result.correct ? question.successReply || "Great job!" : result.empty ? "Take your time. I am listening." : question.retryReply || "Almost. Try once more.");
    requestAnimationFrame(() => root.querySelector("#learning-form input")?.focus());
  }

  function applyLearningReward(id) {
    const unlockedBefore = new Set(getEasterEggProgress(state).unlocked.map((item) => item.id));
    if (!applyLearningChallengeReward(state, story, id)) return;
    const newlyUnlocked = getEasterEggProgress(state).unlocked.filter((item) => !unlockedBefore.has(item.id));
    announceEasterEggs(newlyUnlocked);
    const next = getGuidedStoryStep(state);
    setGuide("Milo", `You unlocked the ${getLearningChallenge(story, id).reward}!`, next.prompt || "The story is ready to continue.", "story");
  }

  function continueLearningChallenge() {
    const learning = state.learning;
    const challenge = getLearningChallenge(story, learning.activeId);
    if (!challenge || !learning.correct) return;
    if (learning.questionIndex < challenge.questions.length - 1) {
      learning.questionIndex += 1;
      learning.feedback = null;
      learning.correct = false;
      learning.voiceHeard = "";
      learning.hintOpen = false;
      render();
      requestAnimationFrame(() => root.querySelector("#learning-form input")?.focus());
      return;
    }
    applyLearningReward(learning.activeId);
    learning.finished = true;
    learning.correct = false;
    render();
  }

  async function finishLearningChallenge(goNext) {
    const completedId = state.learning.activeId;
    if (speechInput.listening) { ignoreNextVoiceFinal = true; speechInput.cancel(); }
    resetLearningModal();
    render();
    if (!goNext) return;
    if (completedId === "make-story") { await openStoryStudio(); return; }
    await followQuest();
  }

  function setGuide(speaker, text, hint, tone = "normal") {
    state.guide = { speaker, text, hint, tone };
  }

  function setLocationGuide(location) {
    const careCheckInPending = state.questStage === "care" && !cocoCareStatus().checkInComplete;
    if (location === "town") {
      const copy = {
        meet: ["The Pet Shop is glowing first.", "Meet Coco there; the next part of town will unlock when your story begins."],
        search: ["Coco could be anywhere in town.", "Ask people, follow clues, or trust your own idea."],
        care: careCheckInPending ? ["Coco is waiting for you in Whispering Park.", "Finish his two-step check-in: describe one detail, then say something kind."] : ["Coco feels safer now.", "Choose any caring place: Pet Shop, Bakery, or School."],
        home: ["Coco feels much better now.", "Take him to Story House to turn the journey into a book."],
        complete: ["Coco is home, and the town remembers you.", "Keep exploring, collect more words, or reread your story."],
      }[state.questStage];
      setGuide("Milo", copy[0], copy[1]);
    }
    if (location === "petshop") {
      if (state.questStage === "meet" && !getAdventureProgress(state).ready) setGuide("Coco", "Let's explore the Pet Shop together!", "Talk to me, name something, or move the ball. Different actions earn Adventure Stars.");
      else if (state.questStage === "meet") setGuide("Coco", "We earned enough stars—our story is ready!", "Open the green story card whenever you want to play hide-and-seek.");
      else if (careCheckInPending) setGuide("Milo", "The towel will wait.", "Return to Coco in Whispering Park and finish the highlighted check-in step first.");
      else if (state.questStage === "care") setGuide("Milo", "Coco is wet and shivering. The Pet Shop has a soft towel.", "Say how you want to help, or choose a different caring place.");
      else if (state.questStage === "search") setGuide("Milo", "The blue butterfly flew toward the town square.", "Move the ball with your voice, explore another object, or ask around town.");
      else setGuide("Coco", "Woof! This is where our adventure began.", "Try putting the ball on the table, in the box, or under the table.");
    }
    if (location === "bakery") {
      const packedFood = getPackedFood(state);
      if (state.questStage === "search" && packedFood) setGuide("Betty", `Your ${packedFood} is packed for Coco.`, "Keep it with you. If Coco is hungry when you find him, you can use it in the park.");
      else if (state.questStage === "search") setGuide("Betty", "Welcome, explorer! Look around or ask me anything.", "A clue and useful food words are both here. Explore them in any order.");
      else if (careCheckInPending) setGuide("Betty", "I will keep Coco's snack warm.", "Return to Whispering Park and finish checking on Coco first.");
      else if (state.questStage === "care") setGuide("Betty", "Poor Coco looks hungry after that long run.", "Ask for a warm snack for Coco, or help him somewhere else.");
      else if (["home", "complete"].includes(state.questStage)) setGuide("Betty", "I'm glad Coco is safe!", "The bakery is still open—what would you like?");
      else setGuide("Betty", "Welcome! What would you like today?", "Try asking for bread, cake, or a cookie.");
    }
    if (location === "school") {
      if (state.questStage === "search" && state.clues.has("map")) setGuide("Ms. Maple", "Your blue trail map is ready!", "Take it to the park. Its arrow will point toward the old tree.");
      else if (state.questStage === "search" && state.clues.has("school")) setGuide("Ms. Maple", "I can mark Coco's route, but I need the butterfly's color.", "Name the color you saw to finish the trail map.");
      else if (state.questStage === "search") setGuide("Ms. Maple", "The classroom is full of useful clues and color words.", "Describe anything you notice. You do not need to finish another place first.");
      else if (careCheckInPending) setGuide("Ms. Maple", "We will wait for your Coco report.", "Return to Whispering Park: describe Coco, then say something kind to him.");
      else if (state.questStage === "care") setGuide("Ms. Maple", "Everyone is worried about Coco.", "Tell the class he is safe, and his friends will cheer.");
      else if (["home", "complete"].includes(state.questStage)) setGuide("Ms. Maple", "Our brave explorer brought Coco home!", "Stay for colors, or visit another place.");
      else setGuide("Ms. Maple", "Welcome to our color wall!", "Name a color, or explore another place.");
    }
    if (location === "park") {
      const packedFood = getPackedFood(state);
      const careStep = getGuidedStoryStep(state);
      if (state.questStage === "search" && state.clues.has("map")) setGuide("Milo", "Ms. Maple's blue map points toward the old tree!", "Tap the map card, follow another clue, or make your guess.");
      else if (state.questStage === "search") setGuide("Milo", "No fixed path here—follow anything that feels useful.", "Each different clue or description earns progress. The story unlocks when you have explored enough.");
      else if (state.questStage === "care" && careStep.id === "report-coco") setGuide("Milo", "First, look closely at Coco.", careStep.hint);
      else if (state.questStage === "care" && careStep.id === "speak-care") setGuide("Coco", "You described me. Now I need to hear your kind words.", careStep.hint);
      else if (state.questStage === "care" && packedFood) setGuide("Coco", `Thank you—I feel safer now. Is that the ${packedFood} Betty packed?`, "Your check-in is complete. Now find two ways to help me.");
      else if (state.questStage === "care") setGuide("Coco", "Thank you—I feel safer now.", "Your check-in is complete. Now visit town and find two ways to help me.");
      else if (["home", "complete"].includes(state.questStage)) setGuide("Coco", "This is the old tree where you found me!", "You can revisit every clue or keep exploring town.");
      else setGuide("Milo", "The park is peaceful. Coco is still waiting at the Pet Shop.", "Explore freely, or return to the main story.");
    }
    if (location === "storyhouse") {
      if (["home", "complete"].includes(state.questStage)) setGuide("Milo", state.questStage === "complete" ? "Your finished story is waiting on the shelf." : "I remember the places you visited and the clues you found.", state.questStage === "complete" ? "Read it again, or return to the open town." : "Your first draft is ready whenever you are.");
      else if (careCheckInPending) setGuide("Milo", "The next page starts beside Coco.", "Return to Whispering Park and finish his check-in first.");
      else if (state.questStage === "care") setGuide("Milo", "The story needs one last moment of kindness.", "Help Coco at the Pet Shop, Bakery, or School, then bring him home.");
      else setGuide("Milo", "This house turns real adventures into stories.", "Find Coco first, then come back with your memories.");
    }
  }

  async function goToLocation(location) {
    if (!LOCATION_LABELS[location] || state.busy || agentBusy) return;
    const access = getSceneAccess(state, location);
    if (!access.unlocked) { showToast(access.reason, "gentle"); return; }
    state.coachOpen = false;
    state.busy = true;
    await animateElement(".story-viewport", [{ opacity: 1, transform: "scale(1)" }, { opacity: 0, transform: "scale(1.01)" }], { duration: 120 });
    visitLocation(state, location);
    setLocationGuide(location);
    state.busy = false;
    render();
    await animateElement(".story-viewport", [{ opacity: 0, transform: "translateY(6px)" }, { opacity: 1, transform: "translateY(0)" }], { duration: 180 });
  }

  function returnToTownHome() {
    if (agentBusy) cancelAgentRequest();
    if (speechInput.listening) {
      ignoreNextVoiceFinal = true;
      speechInput.cancel();
    }
    clearTimeout(toastTimer);
    state.busy = false;
    state.scene = "world";
    state.location = "town";
    state.coachOpen = false;
    state.wordPocketOpen = false;
    state.explorationOpen = false;
    state.storyBeatOpen = false;
    state.easterEggOpen = null;
    resetLearningModal();
    setLocationGuide("town");
    render();
    showToast("Back at Town Square. Your story progress is safe.", "action");
  }

  async function followQuest() {
    const trail = getGuidedStoryStep(state);
    if (trail.id === "read-story" || trail.action === "open_story") {
      if (state.location !== trail.location) await goToLocation(trail.location);
      return openStoryStudio();
    }
    if (trail.mode === "explore") {
      state.explorationOpen = true;
      state.storyBeatOpen = false;
      render();
      return;
    }
    if (state.location !== trail.location) await goToLocation(trail.location);
    state.storyBeatOpen = true;
    state.explorationOpen = false;
    render();
    return;
  }

  async function runWorldInput(rawText, source = "text") {
    const message = rawText.trim();
    if (state.busy || agentBusy || state.scene !== "world") return;
    if (!message) {
      setGuide("Milo", "I didn't hear any words yet.", helpForLocation());
      render();
      return;
    }
    state.coachOpen = false;
    state.lastHeard = message;
    speechInput.adaptToText(message);
    updateHeardReceipt(message);

    const localResult = interpretWorldCommand(state, message);
    const caringExpression = state.questStage === "care" && isCaringEnglish(message, localResult.intent);
    const guidedParkCheckIn = state.questStage === "care"
      && state.location === "park"
      && (localResult.intent === "describe_coco" || caringExpression);
    let result = localResult;
    if (canRunLocally(localResult) || guidedParkCheckIn || (source === "phrase" && localResult.understood)) {
      result = { ...localResult, mode: "instant" };
      agentStatus = "instant";
      updateAgentSurface("instant");
    } else {
      agentBusy = true;
      agentCancelled = false;
      agentAbortController = new AbortController();
      updateAgentSurface("waiting");
      let cancelledRequest = false;
      try {
        result = await askWorldAgent({ message, source, state, history: agentHistory, signal: agentAbortController.signal });
        agentStatus = "online";
      } catch (error) {
        if (agentCancelled) {
          cancelledRequest = true;
          agentStatus = "ready";
        } else {
          result = localResult;
          agentStatus = "fallback";
          if (!fallbackAnnounced) {
            fallbackAnnounced = true;
            showToast("Town Agent is offline — the local world still works.");
          }
        }
      } finally {
        agentBusy = false;
        agentAbortController = null;
        updateAgentSurface(agentStatus);
      }
      if (cancelledRequest) {
        setGuide("Milo", "Okay—we stopped that reply.", "You can explore, type a shorter idea, or speak again whenever you like.");
        render();
        return;
      }
    }

    result.text ||= message;
    if (!result.understood && caringExpression) {
      result = { ...result, understood: true, intent: "greet_coco", gesture: "comfort", mode: "instant", reply: "That makes me feel cared for.", text: message };
    }
    const completedPowersBefore = new Set(getLessonOutcomeProgress(state, story).filter((item) => item.complete).map((item) => item.id));
    const contribution = result.understood || caringExpression
      ? recordLearnerContribution(state, { text: message, source, intent: result.intent, location: state.location, stage: state.questStage }, story)
      : { added: false };
    if (contribution.added) state.lastContribution = contribution.contribution;
    const newlyLearnedPower = getLessonOutcomeProgress(state, story).find((item) => item.complete && !completedPowersBefore.has(item.id));
    if (source === "phrase" && getParticipationProgress(state).target && !getParticipationProgress(state).complete) {
      const receipt = phraseActionReceipt(result);
      setTimeout(() => showToast(receipt, "action"), 700);
    } else if (contribution.added && state.questStage === "care") {
      showToast("✓ Caring English saved—Coco heard your own words!", "reward");
    } else if (newlyLearnedPower) {
      showToast(`✓ ${newlyLearnedPower.title} learned with your own English!`, "reward");
    }
    if (!result.understood) {
      setGuide("Milo", `I heard “${message}.”`, helpForLocation());
      render();
      showToast("Try a place, an object, or one short idea.");
      return;
    }
    rememberAgentTurn(message, result);
    if (result.intent === "travel") return goToLocation(result.destination);
    if (result.intent === "help") { answerMainStoryQuestion(); return; }
    if (result.intent === "hide_coco") { await hideCocoAndBegin(result); return; }
    if (result.intent === "greet_coco") {
      const comforting = result.gesture === "comfort" || /\b(pet|pat|hug|stroke)\b|摸|抱/.test(result.text || "");
      const careStep = state.questStage === "care" ? getGuidedStoryStep(state) : null;
      const reply = state.questStage === "meet"
        ? [comforting ? "Coco leans closer and wags his tail." : "Woof! Let's play hide-and-seek!", "Move the ball, notice something nearby, or keep talking to Coco.", comforting ? "Coco is happy to see you!" : "Let's play hide and seek!"]
        : state.questStage === "search"
          ? ["Coco has already chased the butterfly into town.", "Ask someone in town where he went.", "Coco ran into town."]
          : state.questStage === "care"
            ? careStep?.id === "report-coco"
              ? ["Coco hears your kind words and stays close.", "Now finish the check-in: describe how Coco looks or feels.", "Your kind words help. Now look closely at Coco."]
              : careStep?.id === "speak-care"
                ? ["Coco takes a small breath and feels safer beside you.", "Say one kind sentence in your own words.", "That gentle care helps Coco feel safe."]
                : ["Coco takes a small breath and feels safe beside you.", "Check-in complete! Now visit town and find two ways to help Coco.", "Thank you. I feel safe with you."]
            : [comforting ? "Coco gives you a happy tail wag." : "Woof! I'm safe and ready to play again!", "Name an object here, or keep exploring town.", "I'm safe and ready to play!"];
      if (state.questStage === "meet") rewardExploration("greet-coco", "Talked with Coco");
      setAgentGuide(result, "Coco", reply[0], reply[1]);
      speakAgentReply(result, reply[2]);
      render();
      if (comforting) await animateElement(state.location === "park" ? ".park-coco" : state.location === "town" ? ".town-coco" : ".coco-character", [{ translate: "0 0" }, { translate: "0 -7px" }, { translate: "0 0" }], { duration: 520 });
      return;
    }
    if (result.intent === "name_petshop_object") { collectWord(state, story, result.object, "free_exploration"); state.sideActivities.add(`petshop-${result.object}`); if (state.questStage === "meet") rewardExploration(`petshop-object-${result.object}`, `Found the ${result.object}`); setAgentGuide(result, "Milo", `Yes—a ${result.object}!`, `You noticed it by yourself. Try another object, or continue the story.`); speakAgentReply(result, "Nice spotting!"); render(); return; }
    if (result.intent === "place_object") { await handleObjectPlacement(result); return; }
    if (result.intent === "ask_baker") { handleBakerClue(result); return; }
    if (result.intent === "order_food") { handleFoodOrder(result); return; }
    if (result.intent === "ask_teacher") { handleSchoolClue(result); return; }
    if (result.intent === "name_color") { handleColor(result); return; }
    if (result.intent === "inspect_clue") { handleParkClue(result.clue, result); return; }
    if (result.intent === "inspect_town_clue") { handleTownClue(result); return; }
    if (result.intent === "town_observation") { handleTownObservation(result); return; }
    if (result.intent === "find_coco") { await revealCoco(result); return; }
    if (result.intent === "care_coco") { await handleCareChoice(result); return; }
    if (result.intent === "describe_coco") {
      const nextCareStep = getGuidedStoryStep(state);
      const hint = nextCareStep.id === "report-coco"
        ? nextCareStep.hint
        : nextCareStep.id === "speak-care"
          ? "Great observation. Now say one kind sentence, such as “Coco, you are safe now.”"
          : "Coco's check-in is complete. Now find two ways to help him.";
      setAgentGuide(result, "Milo", result.recast || "You described Coco clearly.", hint);
      speakAgentReply(result, result.recast);
      render();
      showToast("✓ Coco Report updated from your own words!", "reward");
      return;
    }
    if (result.intent === "clarify_tree") { setAgentGuide(result, "Milo", "The tree feels important. Where exactly is Coco?", "Try using behind, beside, or under. Look closely at the moving leaves."); render(); speakAgentReply(result); return; }
    if (result.intent === "open_story") { await openStoryStudio(); return; }
    if (result.intent === "greet") { setAgentGuide(result, "Milo", "Hello, explorer!", helpForLocation()); speakAgentReply(result, "Hello, explorer!"); render(); return; }
    if (result.intent === "chat") { setAgentGuide(result, "Milo", "Tell me more—I'm listening.", helpForLocation()); speakAgentReply(result); render(); return; }
    if (source === "voice") showToast("Your voice reached the town.");
  }

  function rememberAgentTurn(message, result) {
    agentHistory.push({ role: "user", content: message.slice(0, AGENT_HISTORY_TURN_MAX_CHARS) });
    agentHistory.push({ role: "assistant", content: (result.reply || result.recast || result.intent).slice(0, AGENT_HISTORY_TURN_MAX_CHARS) });
    if (agentHistory.length > AGENT_HISTORY_MAX_TURNS) agentHistory.splice(0, agentHistory.length - AGENT_HISTORY_MAX_TURNS);
  }

  function setAgentGuide(result, speaker, text, hint) {
    if (result.mode === "agent") setGuide(result.speaker || speaker, result.reply || text, result.hint || hint, "agent");
    else setGuide(speaker, text, hint);
  }

  function speakAgentReply(result, fallback = "") {
    const line = getSpokenReply(result, fallback);
    if (line) speak(line);
  }

  function helpForLocation() {
    const trail = getGuidedStoryStep(state);
    if (trail.location === state.location) return trail.hint;
    if (state.questStage === "care" && !cocoCareStatus().checkInComplete) return "Return to Coco in Whispering Park and finish the highlighted check-in step.";
    return {
      town: "Try “Go to the bakery” or tap any building.",
      petshop: state.questStage === "meet" ? "Try “in the box” or “under the table.”" : state.questStage === "care" ? "Try “dry Coco with a towel.”" : "Name the box, table, or ball—or visit someone in town.",
      bakery: state.questStage === "care" ? "Try “a warm snack for Coco.”" : "Ask “Have you seen Coco?” or order cake, bread, or a cookie.",
      school: state.questStage === "care" ? "Try “Coco is safe!”" : "Ask about Coco, paw prints, or name a color.",
      park: "Describe the tracks, puddle, bush, or Coco's position.",
      storyhouse: "Make your story, or return to town.",
    }[state.location];
  }

  async function hideCocoAndBegin(result) {
    state.busy = true;
    const adventure = getAdventureProgress(state);
    if (!adventure.ready) {
      const action = performHideChoice(state, story, result.destination);
      setGuide("Coco", action?.sentence || "I found a hiding place!", `Keep exploring together first. This chapter has ${adventure.displayPoints}/${adventure.target} stars, and your permanent total is ${adventure.total}.`);
      render();
      speak("Almost ready! Let's explore a little more together.");
      await animateElement(".coco-character", [{ transform: "translateY(0)" }, { transform: "translateY(-12px)" }, { transform: "translateY(0)" }], { duration: 600 });
      state.busy = false;
      render();
      return;
    }
    startSearchQuest(state, story, result.destination);
    state.escapeBeat = true;
    setAgentGuide(result, "Coco", result.recast, "Your words moved Coco!");
    render();
    speakAgentReply(result, "Great hiding place, Coco!");
    await animateElement(".coco-character", [{ transform: "translateY(0)" }, { transform: "translateY(-14px)" }, { transform: "translateY(0)" }], { duration: 650 });
    await wait(350);
    setGuide("Milo", "A blue butterfly flew through the open door!", "Coco chased it into town. The clearest trail begins with a glowing paw print at Moonbeam Bakery.");
    render();
    speak("A blue butterfly! Coco, wait!");
    await Promise.all([
      animateElement(".shop-door", [{ transform: "perspective(500px) rotateY(0)" }, { transform: "perspective(500px) rotateY(-58deg)" }], { duration: 650 }),
      animateElement(".coco-character", [{ transform: "translate(0,0) scale(1)" }, { transform: "translate(-130px,-18px) scale(.8)" }, { transform: "translate(-440px,-40px) scale(.3)", opacity: 0 }], { duration: 950 }),
    ]);
    state.escapeBeat = false;
    state.busy = false;
    render();
  }

  function handleBakerClue(result) {
    if (state.questStage === "care") { setAgentGuide(result, "Betty", "Coco is safe, but he looks hungry.", "You can ask for a warm snack for Coco."); render(); speakAgentReply(result); return; }
    if (["home", "complete"].includes(state.questStage)) { setAgentGuide(result, "Betty", "Coco is safe now—what wonderful news!", "You can still order something for yourself."); render(); speakAgentReply(result); return; }
    if (state.questStage !== "search") { setAgentGuide(result, "Betty", "Coco? He is playing at the Pet Shop today.", "You can visit him whenever you like."); render(); speakAgentReply(result); return; }
    const foundPrint = /flour|paw|print/i.test(result.text || "");
    const clue = addClue(state, story, "baker");
    if (foundPrint) {
      state.sideActivities.add("bakery-flour-print");
      collectWord(state, story, "tracks", "world_action");
      state.usedWords.add("tracks");
    }
    const reply = foundPrint ? "Those tiny flour prints point toward Whispering Park!" : "I saw an orange puppy chasing a blue butterfly toward the park.";
    rewardExploration(foundPrint ? "bakery-flour-print" : "ask-baker", foundPrint ? "Found the Bakery clue" : "Asked Betty about Coco");
    setAgentGuide(result, "Betty", reply, clue.added ? "That is a real clue. Now pack something for Coco in case he is hungry." : "The trail still points to the park. Shall I pack something for Coco?");
    speakAgentReply(result, foundPrint ? "Good eyes! The trail points toward the park." : "I saw an orange puppy chasing a blue butterfly toward Whispering Park.");
    render();
  }

  async function handleObjectPlacement(result) {
    const positionBefore = getLessonOutcomeProgress(state, story).find((item) => item.id === "position-power");
    const action = moveWorldObject(state, story, result.object, result.destination, result.relation);
    if (!action) return;
    if (state.questStage === "meet") rewardExploration(`ball-${result.relation}`, `Used “${result.relation}”`);
    const positionCount = masteryCount(state, "positionWords");
    const nextIdeas = {
      table: "Now try putting it in the box, or under the table.",
      box: "Can you move it under the table next?",
      "under-table": "Try bringing it back onto the floor.",
      floor: "The room is reset. Where should the ball go now?",
    };
    const positionAfter = getLessonOutcomeProgress(state, story).find((item) => item.id === "position-power");
    if (state.questStage === "meet" && getAdventureProgress(state).ready) setGuide("Coco", "Position Power complete—woof!", "You moved the ball and described its position with your own English.");
    else if (state.questStage === "meet" && positionAfter?.parts[0]?.complete) setGuide("Coco", "Great moving! Now tell me where the ball is.", `Try: “${action.sentence}”`);
    else if (state.questStage === "meet") setGuide("Coco", `Great move! You used ${positionCount} position ${positionCount === 1 ? "word" : "words"}.`, "Move the ball to one different place next.");
    else setAgentGuide(result, "Coco", "Great move—woof! The room changed.", nextIdeas[action.position]);
    if (!positionBefore?.complete && positionAfter?.complete) showToast("✓ Position Power complete! Your English moved the world.", "reward");
    render();
    speakAgentReply(result, "Great move!");
    await animateElement(".red-ball", [{ transform: "translateY(-18px) scale(.82)" }, { transform: "translateY(3px) scale(1.08)" }, { transform: "translateY(0) scale(1)" }], { duration: 520 });
  }

  function handleFoodOrder(result) {
    state.sideActivities.add(`ordered-${result.food}`);
    collectWord(state, story, result.food, "conversation");
    state.usedWords.add(result.food);
    const polite = /\b(please|can i|could i|may i)\b|请/i.test(result.text || "");
    if (state.questStage === "search") rewardExploration(`food-${result.food}`, `Used the word “${result.food}”`);
    if (state.questStage === "search" && !polite) {
      setGuide("Betty", `Good choice—the ${result.food} is ready.`, `One magic word is missing. Try “Pack one ${result.food} for Coco, please.”`);
      speak("Almost! Add the magic word, please.");
      render();
      return;
    }
    if (state.questStage === "search") { packFoodForCoco(state, result.food); rewardExploration("polite-request", "Made a polite request"); }
    const isPacked = state.questStage === "search";
    setAgentGuide(result, "Betty", isPacked ? `I packed the ${result.food} for Coco.` : `Here is your ${result.food}.`, isPacked ? "Keep it safe. Next, follow the story trail to Star School." : `A natural way to ask is: “${result.recast}”`);
    speakAgentReply(result, isPacked ? "It's packed and ready for Coco!" : `Here is your ${result.food}.`);
    render();
  }

  function handleSchoolClue(result) {
    if (state.questStage === "care") { setAgentGuide(result, "Ms. Maple", "You found Coco! Is he safe?", "Tell the class “Coco is safe!” and everyone will cheer."); render(); speakAgentReply(result); return; }
    if (["home", "complete"].includes(state.questStage)) { setAgentGuide(result, "Ms. Maple", "The whole class is happy Coco came home.", "Stay and name some colors if you like."); render(); speakAgentReply(result); return; }
    if (state.questStage !== "search") { setAgentGuide(result, "Ms. Maple", "Coco is still at the Pet Shop.", "Visit him, or stay and explore some colors."); render(); speakAgentReply(result); return; }
    const foundTrail = /board|chalk|paw|print|track/i.test(result.text || "");
    const clue = addClue(state, story, "school");
    if (foundTrail) state.sideActivities.add("school-chalk-trail");
    const reply = foundTrail ? "The chalk paw trail turns toward Whispering Park." : "We saw little paw prints turn toward Whispering Park.";
    rewardExploration(foundTrail ? "school-chalk-trail" : "ask-teacher", foundTrail ? "Found the School clue" : "Asked Ms. Maple about Coco");
    setAgentGuide(result, "Ms. Maple", reply, clue.added ? "Now name the butterfly's color, and I will mark that route on a trail map." : "The trail is still here. Can you finish the map?");
    speakAgentReply(result, foundTrail ? "You found the chalk trail!" : "We saw little paw prints turn toward Whispering Park.");
    render();
  }

  function handleColor(result) {
    state.sideActivities.add(`color-${result.color}`);
    recordMastery(state, "colors", result.color);
    if (result.color === "blue") { collectWord(state, story, "blue", "conversation"); state.usedWords.add("blue"); }
    const colors = state.mastery?.colors ?? new Set();
    const hasBlue = colors.has("blue");
    const mapReady = state.questStage === "search" && state.clues.has("school") && hasBlue && colors.size >= 2;
    const mapClue = mapReady ? addClue(state, story, "map") : null;
    if (state.questStage === "search") rewardExploration(`color-${result.color}`, `Used the color “${result.color}”`);
    if (mapReady) state.sideActivities.add("school-map");
    const reply = mapReady ? "Color code complete! I marked Coco's blue route on the map." : !state.clues.has("school") ? result.recast : hasBlue ? "Blue is correct. We need one different color too." : "That is one color. Now find the butterfly's blue color.";
    const hint = mapReady ? (mapClue.added ? "The Color Key is unlocked. Take the map to the park and test it against two clues." : "Your map still points toward the old tree.") : !state.clues.has("school") ? "Find the chalk paw trail first to start the color code." : `Color code: ${Math.min(colors.size, 2)}/2.`;
    setGuide("Ms. Maple", reply, hint);
    speakAgentReply(result, mapReady ? "You unlocked the Color Key!" : hasBlue ? "Blue found! One more color." : "Keep looking for blue.");
    render();
  }

  function handleTownClue(result) {
    const clue = addClue(state, story, "square");
    rewardExploration("town-butterfly", "Followed the blue butterfly");
    setAgentGuide(result, "Milo", "The blue butterfly is fluttering toward Whispering Park!", clue.added ? (canFindCoco(state) ? "You have enough clues to follow your hunch." : "That gives us a direction. You can follow it or ask around.") : "It still seems to be leading toward the park.");
    speakAgentReply(result, "The blue butterfly is flying toward Whispering Park.");
    render();
  }

  function handleTownObservation(result) {
    state.sideActivities.add("town-fountain");
    collectWord(state, story, "fountain", "free_exploration");
    state.usedWords.add("fountain");
    if (state.questStage === "search") rewardExploration("town-fountain", "Explored the fountain");
    setAgentGuide(result, "Milo", "The fountain splashes in the middle of town.", "You found a word without leaving the square. Where should we wander next?");
    speakAgentReply(result, "Nice find!");
    render();
  }

  async function handleCareChoice(result) {
    if (state.questStage !== "care" || !["towel", "snack", "friends"].includes(result.care)) return;
    if (!cocoCareStatus().checkInComplete) {
      const trail = getGuidedStoryStep(state);
      setGuide("Milo", "Let's finish Coco's check-in first.", trail.id === "report-coco" ? trail.hint : "Say one kind sentence to Coco before choosing how to help.", "story");
      render();
      showToast("Return to Coco in the Park and finish the highlighted step.", "gentle");
      return;
    }
    state.careOptions.add(result.care);
    const labels = { towel: "Found a soft towel", snack: "Found a snack for Coco", friends: "Told Coco's friends" };
    rewardExploration(`care-${result.care}`, labels[result.care]);
    const messages = {
      towel: ["Coco", "A soft towel could make me warm and dry!", "That is one caring idea. You can keep exploring for another."],
      snack: ["Betty", "A warm snack could help Coco feel strong again.", "That is one caring idea. You can keep exploring for another."],
      friends: ["Ms. Maple", "Coco's friends would love to know he is safe.", "That is one caring idea. You can keep exploring for another."],
    };
    setAgentGuide(result, ...messages[result.care]);
    speakAgentReply(result, messages[result.care][1]);
    render();
  }

  function handleParkClue(clueId, result) {
    if (state.questStage !== "search") {
      if (["care", "home", "complete"].includes(state.questStage)) setAgentGuide(result, "Coco", "I remember this clue from our adventure!", state.questStage === "care" ? "Now choose a place in town to help me feel better." : "The park still remembers what happened here.");
      else setAgentGuide(result, "Milo", "You noticed something interesting.", "Coco is still at the Pet Shop. This place will remember that you explored it.");
      state.sideActivities.add(`park-${clueId}`);
      render(); speakAgentReply(result);
      return;
    }
    const clue = addClue(state, story, clueId);
    rewardExploration(`park-${clueId}`, `Investigated ${clueId === "tracks" ? "paw prints" : `the ${clueId}`}`);
    const messages = {
      tracks: ["Fresh paw prints lead deeper into the park.", "tracks"],
      puddle: ["The paw prints cross the puddle. Coco must be wet.", "wet"],
      bush: ["A frightened little sound comes from behind the old tree.", "behind the tree"],
    };
    const [text] = messages[clueId];
    setAgentGuide(result, "Milo", text, clue.added ? (canFindCoco(state) ? "You have enough clues to make a guess—but you can keep exploring." : "One more clue may help.") : "You already noticed this. Try another path or make a guess.");
    speakAgentReply(result, text);
    render();
  }

  async function revealCoco(result) {
    if (state.questStage !== "search") { setGuide("Milo", ["care", "home", "complete"].includes(state.questStage) ? "Yes—this is where you found Coco." : "Coco is not missing yet. Go meet him at the Pet Shop.", helpForLocation()); render(); return; }
    const adventure = getAdventureProgress(state);
    if (!canFindCoco(state) || !adventure.ready) {
      const trail = getGuidedStoryStep(state);
      setGuide("Milo", adventure.requirements.participation?.complete ? "That is a brave guess, but our evidence key is not ready yet." : "That is a good guess. I still need to hear your English in another place.", trail.hint);
      render();
      return;
    }
    state.busy = true;
    findCoco(state, story, result.text);
    setAgentGuide(result, "Coco", "Woof! You found me!", "First, look closely and describe one detail. Is Coco wet or scared?");
    render();
    await Promise.all([
      animateElement(".oak-tree", [{ translate: "0 0" }, { translate: "-18px 0" }], { duration: 700 }),
      animateElement(".park-coco", [{ translate: "-45px 0", scale: .65, opacity: 0 }, { translate: "0 0", scale: 1, opacity: 1 }], { duration: 900 }),
    ]);
    speakAgentReply(result, "Coco is behind the tree! You found me! First, look closely. Is Coco wet or scared?");
    state.busy = false;
    render();
  }

  function updateVoiceSurface(message, listening, transcript = null, submitting = false) {
    voiceSubmitting = submitting;
    const status = root.querySelector(".voice-status");
    const button = root.querySelector(".mic-button");
    const input = root.querySelector("#world-input");
    if (status) status.textContent = message;
    if (button) {
      button.classList.toggle("listening", listening);
      button.classList.toggle("submitting", submitting);
      button.disabled = submitting;
      button.setAttribute("aria-label", submitting ? "Waiting to submit voice input" : listening ? "Finish voice input now" : "Start voice input; the command runs when you finish speaking");
      button.innerHTML = `<span aria-hidden="true">${submitting ? "…" : listening ? "■" : "🎙"}</span><b>${submitting ? "Waiting" : listening ? "Finish" : "Speak"}</b>`;
    }
    if (transcript !== null) {
      worldInputDraft = transcript;
      if (input) input.value = transcript;
    }
  }

  function updateStoryVoiceSurface(message, listening, transcript = null, submitting = false) {
    voiceSubmitting = submitting;
    const status = root.querySelector(".story-voice-status");
    const button = root.querySelector(".story-mic-button");
    const input = root.querySelector("#story-input");
    if (status) status.textContent = message;
    if (button) {
      button.classList.toggle("listening", listening);
      button.classList.toggle("submitting", submitting);
      button.disabled = submitting;
      button.setAttribute("aria-label", submitting ? "Adding spoken words to the story" : listening ? "Finish story voice input" : "Tell this page with your voice");
      button.innerHTML = `<span>${submitting ? "…" : listening ? "■" : "🎙"}</span><strong>${submitting ? "Waiting" : listening ? "Finish" : "Tell this page"}</strong>`;
    }
    if (input && transcript !== null) input.value = `${storyVoiceBase}${storyVoiceBase && transcript ? " " : ""}${transcript}`.trim();
  }

  function updateLearningVoiceSurface(message, listening, transcript = null, submitting = false) {
    voiceSubmitting = submitting;
    const status = root.querySelector(".challenge-voice-status");
    const button = root.querySelector(".answer-by-voice");
    const input = root.querySelector("#learning-form input");
    const panel = root.querySelector(".challenge-voice-panel");
    if (status) status.textContent = message;
    if (panel) panel.classList.toggle("listening", listening);
    if (panel) panel.classList.toggle("submitting", submitting);
    if (button) {
      button.classList.toggle("listening", listening);
      button.classList.toggle("submitting", submitting);
      button.disabled = submitting;
      button.innerHTML = `<span>${submitting ? "…" : listening ? "■" : "🎙"}</span><strong>${submitting ? "Waiting" : listening ? "Finish answer" : "Say answer"}</strong>`;
    }
    if (input && transcript !== null) input.value = transcript;
  }

  function readLearningQuestion() {
    const challenge = getLearningChallenge(story, state.learning?.activeId);
    const question = challenge?.questions[state.learning?.questionIndex];
    if (!question) return;
    if (speechInput.listening) { showToast("Finish your spoken answer first."); return; }
    const options = question.type === "choice" ? question.options.map((option, index) => `${String.fromCharCode(65 + index)}. ${option}.`).join(" ") : "";
    speak([question.npcLine, question.prompt, question.sentence, options].filter(Boolean).join(" "));
    updateLearningVoiceSurface("Listen, then tap Say answer when you are ready.", false);
  }

  function updateHeardReceipt(message) {
    const receipt = root.querySelector(".voice-example");
    if (!receipt) return;
    receipt.classList.add("heard");
    const label = receipt.querySelector("small");
    const line = receipt.querySelector("span");
    if (label) label.textContent = "You said";
    if (line) line.textContent = `“${message}”`;
  }

  function cancelAgentRequest() {
    if (!agentBusy || !agentAbortController) return;
    agentCancelled = true;
    agentAbortController.abort();
  }

  function updateAgentSurface(statusName) {
    voiceSubmitting = false;
    agentStatus = statusName;
    const app = root.querySelector(".immersive-app");
    const presence = root.querySelector(".agent-presence");
    const input = root.querySelector("#world-input");
    const mic = root.querySelector(".mic-button");
    const voiceStatus = root.querySelector(".voice-status");
    const labels = { ready: "Agent ready", instant: "Instant response", waiting: "Waiting for reply", online: "Agent connected", fallback: "Local mode" };
    if (presence) {
      presence.className = `agent-presence state-${statusName}`;
      presence.innerHTML = `<i></i>${labels[statusName]}`;
    }
    if (input) {
      input.setAttribute("aria-busy", String(statusName === "waiting"));
      input.disabled = statusName === "waiting";
    }
    if (mic) {
      const waiting = statusName === "waiting";
      mic.dataset.action = "voice";
      mic.classList.remove("is-cancel");
      mic.classList.toggle("submitting", waiting);
      mic.disabled = waiting;
      mic.classList.toggle("unsupported", !waiting && !speechInput.supported);
      mic.setAttribute("aria-label", waiting ? "Waiting for the Agent reply" : speechInput.supported ? "Start voice input; the command runs when you finish speaking" : "Voice input is unavailable");
      mic.innerHTML = `<span aria-hidden="true">${waiting ? "…" : "🎙"}</span><b>${waiting ? "Waiting" : "Speak"}</b>`;
    }
    if (voiceStatus) voiceStatus.textContent = statusName === "waiting" ? "Waiting for Coco’s reply…" : speechInput.supported ? "Press Enter, or speak and pause to run" : "Press Enter to run · voice unavailable here";
    if (app) {
      app.setAttribute("aria-busy", String(statusName === "waiting" || state.busy));
    }
  }

  function renderStoryStudio() {
    const item = story.writing.scenes[state.currentStoryStep];
    const visual = state.storyVisuals[state.currentStoryStep];
    const line = state.storyLines[state.currentStoryStep];
    const authoredPages = state.storyEdited?.size ?? 0;
    return `
      <div class="studio-stage studio-scene-${state.currentStoryStep}">
        <div class="studio-header"><button class="studio-back" data-action="back-world">← Town</button><div><p class="eyebrow">Your real adventure · Scene ${state.currentStoryStep + 1} of ${story.writing.scenes.length}</p><h1>${item.title}</h1></div><div class="studio-progress" aria-label="Story scene progress">${story.writing.scenes.map((_, index) => `<i class="${index < state.currentStoryStep ? "complete" : ""} ${index === state.currentStoryStep ? "current" : ""}">${index < state.currentStoryStep ? "✓" : index + 1}</i>`).join("")}</div><span>${item.place}</span></div>
        ${renderStoryVisual(visual, line)}
        <div class="studio-panel">
          <div class="studio-question"><small>${authoredPages ? "Your words are in the story" : "Milo made a first draft"}</small><h2>Make this part yours.</h2><p aria-live="polite">${writingFeedback(story, line, visual, state.currentStoryStep)}</p><div class="authorship-check ${authoredPages ? "complete" : state.storyNeedsWriting ? "needed" : ""}"><span>${authoredPages ? "✓" : "✎"}</span><p><strong>${authoredPages ? `${authoredPages} page${authoredPages === 1 ? "" : "s"} personalized` : "Add your own English"}</strong><small>${authoredPages ? "Your writing will appear in the finished book." : "Change at least three words, or write one short sentence on any page."}</small></p></div></div>
          <div class="studio-writing"><textarea id="story-input" maxlength="220" aria-label="Your story sentence">${escapeHtml(line)}</textarea><div class="suggestion-chips">${item.suggestions.map((word) => `<button data-suggestion="${word}">+ ${word}</button>`).join("")}</div><div class="story-voice-tools"><button type="button" class="story-mic-button ${voiceSubmitting ? "submitting" : speechInput.supported ? "" : "unsupported"}" data-action="story-voice" ${voiceSubmitting ? "disabled" : ""}><span>${voiceSubmitting ? "…" : "🎙"}</span><strong>${voiceSubmitting ? "Waiting" : "Tell this page"}</strong></button><small class="story-voice-status" aria-live="polite">${voiceSubmitting ? "Waiting to add your spoken words…" : speechInput.supported ? "Speak naturally; your words will be added without being read back." : "Voice unavailable here—typing still works."}</small></div></div>
          <div class="studio-actions"><button class="play-words" data-action="play-story">▶ Listen to my page</button>${state.currentStoryStep > 0 ? `<button data-action="previous-story">← Save &amp; back</button>` : ""}${state.currentStoryStep < story.writing.scenes.length - 1 ? `<button data-action="next-story">Save &amp; next →</button>` : `<button class="finish-story" data-action="finish-story">Make my storybook →</button>`}</div>
        </div>
      </div>
    `;
  }

  function renderStoryVisual(visual, line, sceneIndex = state.currentStoryStep) {
    const classes = [`visual-scene-${sceneIndex}`, visual.running ? "running" : "", visual.inPark ? "in-park" : "", visual.behindTree ? "behind-tree" : "", `size-${visual.size}`, visual.wet ? "wet" : "", visual.scared ? "scared" : "", visual.home ? "at-home" : ""].filter(Boolean).join(" ");
    return `<div class="story-visual ${classes}"><div class="visual-sky"><i></i><i></i></div><div class="visual-path"></div><div class="visual-rain"></div><div class="visual-shop"><i></i></div><div class="visual-tree"></div><div class="visual-home"><i></i></div><div class="visual-coco">${renderCoco(visual.scared ? "scared" : "happy", visual.wet)}</div><div class="visual-details">${visual.size !== "normal" ? `<span>${visual.size}</span>` : ""}${visual.wet ? `<span>wet</span>` : ""}${visual.scared ? `<span>scared</span>` : ""}${visual.behindTree ? `<span>behind the tree</span>` : ""}</div><p>${line ? escapeHtml(line) : "Your sentence will become this world."}</p></div>`;
  }

  async function openStoryStudio() {
    if (!["home", "complete"].includes(state.questStage)) return followQuest();
    if (state.questStage === "complete") {
      state.scene = "book";
      state.bookPage = 0;
      render();
      return;
    }
    if (!state.eventLog.some((event) => event.event === "story_draft_created")) buildStoryDrafts(state);
    state.scene = "story";
    render();
  }

  async function playStorySentence() {
    const input = root.querySelector("#story-input");
    if (!input?.value.trim()) { showToast("Keep one sentence so this page has a story."); return; }
    const spokenLine = input.value.trim();
    state.busy = true;
    const visual = saveStoryLine(state, story, state.currentStoryStep, spokenLine);
    render();
    const keyframes = visual.running ? [{ transform: "translateX(-70px)" }, { transform: "translateX(70px) translateY(-6px)" }, { transform: "translateX(0)" }] : [{ transform: "scale(.92)", opacity: .6 }, { transform: "scale(1.06)", opacity: 1 }, { transform: "scale(1)" }];
    await animateElement(".visual-coco", keyframes, { duration: 900 });
    speak(spokenLine);
    state.busy = false;
    render();
  }

  async function changeStoryScene(direction) {
    const input = root.querySelector("#story-input");
    if (!input?.value.trim()) { showToast("Keep one sentence so this page has a story."); return; }
    saveStoryLine(state, story, state.currentStoryStep, input.value.trim());
    const next = Math.max(0, Math.min(story.writing.scenes.length - 1, state.currentStoryStep + direction));
    if (next === state.currentStoryStep) return;
    state.currentStoryStep = next;
    render();
  }

  async function finishStory() {
    const input = root.querySelector("#story-input");
    if (!input?.value.trim()) { showToast("Keep one sentence so this page has a story."); return; }
    saveStoryLine(state, story, state.currentStoryStep, input.value.trim());
    if (!completeStory(state)) {
      state.storyNeedsWriting = true;
      render();
      showToast("Add one short piece of your own English before making the book.", "gentle");
      requestAnimationFrame(() => root.querySelector("#story-input")?.focus());
      return;
    }
    state.scene = "book";
    state.bookPage = 0;
    saveLessonMemory(story.id, buildMissingPuppyMemory(state));
    render();
    await animateElement(".flipbook-page", [{ opacity: 0, transform: "scale(.92)" }, { opacity: 1, transform: "scale(1)" }], { duration: 550 });
  }

  function renderStorybook() {
    const usedWords = [...state.usedWords].filter((word) => story.vocabulary[word]).slice(0, 12);
    const secretPage = hasEasterEgg(state, "secret-book-page");
    const totalPages = story.writing.scenes.length + 2 + (secretPage ? 1 : 0);
    const page = Math.max(0, Math.min(state.bookPage, totalPages - 1));
    return `
      <div class="storybook-stage">
        <div class="celebration"><i></i><i></i><i></i><i></i><i></i></div>
        <div class="storybook-title">
          <div><p class="eyebrow">Built from your journey</p><h1>${story.title}</h1></div>
          <div class="storybook-title-actions"><span aria-live="polite">Page ${page + 1} of ${totalPages}</span><button data-action="read-page">🔊 Read this page</button></div>
        </div>
        <div class="flipbook-shell">
          <div class="page-stack" aria-hidden="true"><i></i><i></i><i></i></div>
          <article class="flipbook-page book-page-${page}" data-book-page="${page}" aria-label="Storybook page ${page + 1} of ${totalPages}">
            <div class="book-spine"></div>
            ${renderFlipbookPage(page, usedWords)}
            ${page > 0 ? `<button class="page-corner previous" data-action="book-prev" aria-label="Previous page"><span>‹</span><small>Back</small></button>` : ""}
            ${page < totalPages - 1 ? `<button class="page-corner next" data-action="book-next" aria-label="Next page"><small>Turn page</small><span>›</span></button>` : ""}
            <span class="paper-number">${page + 1}</span>
          </article>
        </div>
        <div class="flipbook-progress" aria-hidden="true">${Array.from({ length: totalPages }, (_, index) => `<i class="${index === page ? "current" : ""} ${index < page ? "read" : ""}"></i>`).join("")}</div>
        <p class="flipbook-hint">Turn a corner, swipe, use ← →, or listen to the page.</p>
        <div class="book-actions"><button data-action="back-world">Explore town</button><button data-action="lesson-review">Review my English</button><button data-action="restart">New adventure</button><button data-action="print">Print my story</button></div>
        <section class="print-book" aria-hidden="true"><h1>${story.title}</h1>${state.storyLines.map((line, index) => `<article><h2>${index + 1}. ${story.writing.scenes[index].title}</h2><p>${escapeHtml(line)}</p></article>`).join("")}${secretPage ? `<article><h2>Secret page · The Town Remembers</h2><p>Coco followed the words, stars, and kindness from our adventure all the way home.</p></article>` : ""}</section>
      </div>
    `;
  }

  function renderFlipbookPage(page, usedWords) {
    if (page === 0) {
      const courseStars = getCourseStarsForLesson(story, state);
      return `<div class="flipbook-cover"><div class="cover-moon"></div><div class="cover-oak"></div><div class="cover-coco">${renderCoco("happy")}</div><div class="cover-stickers"><span>🗺 ${state.visited.size} places</span><span>🔎 ${state.clues.size} clues</span><span>💬 ${state.learnerContributions?.length ?? 0} English turns</span><span>✨ ${usedWords.length} words</span></div><p>My Magic Story</p><h2>${story.title}</h2><span>Every choice and sentence inside came from your adventure.</span>${renderCourseStars({ earned: courseStars, size: "small", className: "lesson-one-cover-stars" })}${renderBookRoute()}<small>Turn the corner to begin</small></div>`;
    }
    if (page <= story.writing.scenes.length) {
      const index = page - 1;
      return `<div class="flipbook-story-page"><header><small>Chapter ${index + 1}</small><h2>${story.writing.scenes[index].title}</h2><span>${story.writing.scenes[index].place}</span></header>${renderStoryVisual(state.storyVisuals[index], state.storyLines[index], index)}<blockquote>${escapeHtml(state.storyLines[index])}</blockquote>${renderPageStickers(index)}</div>`;
    }
    if (hasEasterEgg(state, "secret-book-page") && page === story.writing.scenes.length + 1) {
      const secrets = getEasterEggProgress(state).unlocked;
      return `<div class="flipbook-secret-page"><span>📖✨</span><p class="eyebrow">18-star secret page</p><h2>The Town Remembers</h2><p>Coco followed the words, stars, and kindness from your adventure all the way home.</p><div>${secrets.map((item) => `<i title="${escapeHtml(item.title)}">${item.icon}</i>`).join("")}</div><small>You found ${secrets.length} hidden surprises.</small></div>`;
    }
    const badge = careBadge();
    const learningBadges = masteryBadges();
    const courseStars = getCourseStarsForLesson(story, state);
    return `<div class="flipbook-ending"><div class="ending-milo milo-orb">${renderMilo()}</div><p class="eyebrow">Lesson 1 storybook finished</p><h2>Look what you can do!</h2>${renderCourseCompletion({ earned: courseStars, className: "lesson-one-course-rating", homeHref: "./index.html" })}${renderLessonReviewSummary()}<div class="ending-achievement"><span>${badge.icon}</span><p><small>Your story badge</small><strong>${badge.title}</strong></p></div>${renderAdventureRecap()}<div class="adventure-stats"><span><strong>${getAdventureProgress(state).total}</strong><small>bonus stars</small></span><span><strong>${state.visited.size}</strong><small>places</small></span><span><strong>${state.clues.size}</strong><small>clues</small></span><span><strong>${usedWords.length}</strong><small>words</small></span></div><div class="word-garden"><small>Words from your adventure</small>${usedWords.map((word) => `<button data-speak="${story.vocabulary[word].label}">${story.vocabulary[word].label}<span>▶</span></button>`).join("")}</div><div class="ending-review-actions"><a class="next-lesson-link" href="?story=moonlight-festival">Continue into the sunset →</a><button class="review-english" data-action="lesson-review">Play my lesson review</button><button class="read-again" data-action="book-first">Read my story again ↺</button></div></div>`;
  }

  function renderLessonReviewSummary() {
    const lesson = getLessonProgress(state, story);
    return `<section class="lesson-review-summary"><p>You used English to find and help Coco.</p>${lesson.outcomes.map((outcome) => {
      const sample = outcome.samples.find((item) => item.support === "independent")?.text;
      return `<div class="${outcome.complete ? "complete" : "practising"}"><span>${outcome.complete ? "✓" : outcome.icon}</span><p><strong>${escapeHtml(outcome.canDo)}</strong><small>${sample ? `You said: “${escapeHtml(sample)}”` : escapeHtml(outcome.reviewPrompt)}</small></p></div>`;
    }).join("")}</section>`;
  }

  function renderBookRoute() {
    const icons = { town: "⌂", petshop: "🐾", bakery: "🥐", school: "☆", park: "♧", storyhouse: "▤" };
    const route = [...state.visited].slice(0, 6);
    return `<div class="book-route"><small>MY ADVENTURE ROUTE</small><div>${route.map((place, index) => `<span title="${LOCATION_LABELS[place]}"><i>${icons[place]}</i>${index < route.length - 1 ? "<b>→</b>" : ""}</span>`).join("")}</div></div>`;
  }

  function renderAdventureRecap() {
    const hidingPlace = state.eventLog.find((event) => event.event === "main_quest_started")?.destination === "table" ? "under the table" : "in the box";
    const clueNames = { baker: "flour paw print", school: "chalk paw trail", map: "blue trail map", tracks: "paw prints", puddle: "wet puddle", bush: "old tree sound", square: "blue butterfly" };
    const clue = clueNames[[...state.clues][0]] || "town clues";
    return `<div class="adventure-recap" aria-label="My story choices"><small>MY CHOICES SHAPED THE STORY</small><div><span>🐶 Coco hid <strong>${hidingPlace}</strong></span><span>🔎 I followed <strong>${clue}</strong></span><span>${careBadge().icon} <strong>${careBadge().moment}</strong></span></div></div>`;
  }

  function renderPageStickers(index) {
    const clueLabels = { baker: state.sideActivities.has("bakery-flour-print") ? "Flour paw print" : "Bakery clue", school: state.sideActivities.has("school-chalk-trail") ? "Chalk paw trail" : "School clue", map: "Blue trail map", tracks: "Paw prints", puddle: "Wet puddle", bush: "Old tree", square: "Blue butterfly" };
    const care = careBadge();
    const hidingPlace = state.eventLog.find((event) => event.event === "main_quest_started")?.destination;
    const stickers = [
      [`🐶 Coco`, hidingPlace === "table" ? "🪑 Under the table" : "📦 In the box"],
      [...state.visited].filter((place) => !["town", "storyhouse"].includes(place)).slice(0, 3).map((place) => `📍 ${LOCATION_LABELS[place]}`),
      [...state.clues].slice(0, 3).map((clue) => `🔎 ${clueLabels[clue] || clue}`),
      [`${care.icon} ${care.moment}`, "🏠 Home together"],
    ][index].filter(Boolean);
    return `<div class="page-stickers" aria-label="Memories from this chapter">${stickers.map((item) => `<span>${escapeHtml(item)}</span>`).join("")}</div>`;
  }

  function careBadge() {
    const packedFood = getPackedFood(state);
    return {
      towel: { icon: "🧺", title: "Warm-Heart Helper", moment: "Coco became warm and dry" },
      snack: { icon: "🥨", title: "Kindness Baker", moment: packedFood ? `Coco enjoyed Betty's ${packedFood}` : "Coco enjoyed a warm snack" },
      friends: { icon: "⭐", title: "Brave Friend", moment: "Everyone welcomed Coco home" },
    }[state.careChoice] || { icon: "💜", title: "Coco's Best Friend", moment: "Coco felt safe" };
  }

  function masteryBadges() {
    const badges = [
      ["positionWords", 2, "📍", "Position Key"],
      ["manners", 1, "💬", "Polite Key"],
      ["colors", 2, "🎨", "Color Key"],
      ["parkClues", 2, "🔎", "Detective Key"],
    ];
    return badges.filter(([area, required]) => masteryCount(state, area) >= required).map(([, , icon, label]) => ({ icon, label }));
  }

  function readCurrentBookPage() {
    const secretPage = hasEasterEgg(state, "secret-book-page");
    const totalPages = story.writing.scenes.length + 2 + (secretPage ? 1 : 0);
    const page = Math.max(0, Math.min(state.bookPage, totalPages - 1));
    const line = page === 0
      ? `Welcome to ${story.title}. This story was made from your real adventure through ${state.visited.size} places.`
      : page <= story.writing.scenes.length
        ? `${story.writing.scenes[page - 1].title}. ${state.storyLines[page - 1]}`
        : secretPage && page === story.writing.scenes.length + 1
          ? "Secret page. The Town Remembers. Coco followed the words, stars, and kindness from your adventure all the way home."
        : `You brought Coco home, earned ${getAdventureProgress(state).total} stars, and became a ${careBadge().title}. The end.`;
    const book = root.querySelector(".flipbook-page");
    book?.classList.add("is-reading");
    speak(line);
    setTimeout(() => book?.classList.remove("is-reading"), 2400);
  }

  async function turnBook(direction) {
    if (state.busy || state.scene !== "book") return;
    const total = story.writing.scenes.length + 2 + (hasEasterEgg(state, "secret-book-page") ? 1 : 0);
    const next = Math.max(0, Math.min(total - 1, state.bookPage + direction));
    if (next === state.bookPage) return;
    state.busy = true;
    await animateElement(".flipbook-page", [{ transform: "perspective(1200px) rotateY(0)", opacity: 1 }, { transform: `perspective(1200px) rotateY(${direction > 0 ? -72 : 72}deg)`, opacity: .2 }], { duration: 330 });
    state.bookPage = next;
    render();
    await animateElement(".flipbook-page", [{ opacity: .2 }, { transform: "perspective(1200px) rotateY(0)", opacity: 1 }], { duration: 350 });
    state.busy = false;
    render();
  }

  function renderWordPocket() {
    const words = [...state.discovered].filter((word) => story.vocabulary[word]);
    return `<div class="pocket-backdrop" data-action="toggle-pocket"><aside class="word-pocket" role="dialog" aria-modal="true" aria-label="My English Powers" data-stop-close><button class="close-pocket" data-action="toggle-pocket" aria-label="Close English powers">×</button><p class="eyebrow">Lesson 1 · What I can do</p><h2>My English Powers</h2><p>Your own words and actions make each power grow.</p>${renderLessonPowers()}<h3>Words from my journey</h3><div>${words.length ? words.map((key) => `<button data-speak="${story.vocabulary[key].label}"><span>${story.vocabulary[key].label}</span><small>${story.vocabulary[key].hint}</small><i>▶</i></button>`).join("") : `<div class="empty-pocket"><span>✦</span><p>Explore the town and use English to collect words.</p></div>`}</div></aside></div>`;
  }

  function renderEasterEggPanel() {
    const progress = getEasterEggProgress(state);
    if (state.easterEggOpen === "trail") {
      return `<div class="challenge-backdrop surprise-backdrop"><aside class="surprise-panel" role="dialog" aria-modal="true" aria-label="Surprise Trail" data-stop-close>
        <button class="challenge-close" data-action="surprise-close" aria-label="Close Surprise Trail">×</button>
        <header><span>✨</span><div><p class="challenge-kicker">Adventure Stars · ${progress.total} collected</p><h2>Surprise Trail</h2><p>${progress.next ? `${progress.next.stars - progress.total} more stars until ${progress.next.title}.` : "You found every secret in Magic English Town!"}</p></div></header>
        <div class="surprise-progress"><i style="--surprise-progress:${progress.percent}%"></i></div>
        <div class="surprise-grid">${EASTER_EGG_MILESTONES.map((item) => {
          const unlocked = progress.total >= item.stars;
          return `<button ${unlocked ? `data-easter-id="${item.id}"` : "disabled"} class="${unlocked ? "unlocked" : "locked"}"><span>${unlocked ? item.icon : "?"}</span><p><small>${item.stars} ★</small><strong>${unlocked ? item.title : "Mystery surprise"}</strong><i>${unlocked ? item.description : `${item.stars - progress.total} more stars`}</i></p></button>`;
        }).join("")}</div>
        <footer><button class="soft-action" data-action="surprise-close">Back to town</button><small>Surprises are optional. The main story never waits for them.</small></footer>
      </aside></div>`;
    }
    const item = EASTER_EGG_MILESTONES.find((egg) => egg.id === state.easterEggOpen);
    if (!item || !hasEasterEgg(state, item.id)) return "";
    const stories = {
      "word-fountain": ["The fountain remembers your words!", "Every new English word becomes a glowing bubble above Town Square."],
      "rainbow-cake": ["Betty's secret recipe", "The cake changes color when you name something kind. Betty calls it the Friendship Swirl."],
      "coco-cape": ["Coco, town explorer!", "Coco's little cape appears wherever he is visible. It was stitched from moonlight and brave words."],
      "moon-garden": ["A path behind the old tree", "Silver flowers open when they hear English. Coco finds one shaped like a tiny paw."],
      "night-story": ["The fireflies remember", "One quiet night, Coco followed three fireflies home. Each carried a word from your adventure, so he could never feel lost again."],
      "secret-book-page": ["A page only explorers can find", "Your finished Storybook now keeps a secret memory of every surprise you unlocked."],
    }[item.id];
    return `<div class="challenge-backdrop surprise-backdrop"><aside class="surprise-panel surprise-detail egg-${item.id}" role="dialog" aria-modal="true" aria-label="${escapeHtml(item.title)}" data-stop-close>
      <button class="challenge-close" data-action="surprise-close" aria-label="Close surprise">×</button><span class="surprise-art">${item.icon}</span><p class="challenge-kicker">Secret unlocked · ${item.stars} stars</p><h2>${escapeHtml(stories[0])}</h2><p>${escapeHtml(stories[1])}</p>
      <div class="surprise-sparkles"><i></i><i></i><i></i><i></i></div>
      <footer><button class="soft-action" data-action="surprise-trail">See all surprises</button><button class="primary-action" data-action="surprise-close">Keep exploring →</button></footer>
    </aside></div>`;
  }

  function renderMilo() {
    return `<svg viewBox="0 0 64 64" role="img" aria-label="Milo the story guide"><path d="M13 21 17 8l12 10h6L47 8l4 13c5 5 7 11 7 18 0 12-11 20-26 20S6 51 6 39c0-7 2-13 7-18Z" fill="currentColor"/><circle cx="23" cy="35" r="8" fill="#fff"/><circle cx="41" cy="35" r="8" fill="#fff"/><circle cx="25" cy="36" r="3" fill="#3a3068"/><circle cx="39" cy="36" r="3" fill="#3a3068"/><path d="m28 44 4 4 4-4" fill="#f4c966"/></svg>`;
  }

  function renderCoco(mood = "happy", wet = false) {
    const cape = hasEasterEgg(state, "coco-cape");
    return `<svg class="coco-rig mood-${mood} ${wet ? "is-wet" : ""} ${cape ? "has-magic-cape" : ""}" viewBox="0 0 240 200" role="img" aria-label="Coco the puppy${cape ? " wearing a magic cape" : ""}"><ellipse class="coco-shadow" cx="123" cy="181" rx="72" ry="12"/><path class="magic-cape" d="M151 95 Q205 107 211 166 Q176 151 143 150 Z"/><g class="coco-tail"><path d="M184 119 C225 92 224 137 199 145"/></g><g class="coco-body"><ellipse cx="132" cy="132" rx="69" ry="48"/><path class="chest" d="M80 113 C98 99 119 113 120 166 C93 171 71 153 80 113"/></g><g class="coco-legs"><rect x="79" y="147" width="29" height="38" rx="14"/><rect x="145" y="147" width="29" height="38" rx="14"/><ellipse cx="91" cy="181" rx="20" ry="7"/><ellipse cx="158" cy="181" rx="20" ry="7"/></g><g class="coco-head"><path class="ear left" d="M61 56 C28 48 31 103 69 111 C74 93 75 74 61 56"/><path class="ear right" d="M166 55 C201 45 201 100 165 111 C158 91 157 72 166 55"/><ellipse cx="115" cy="79" rx="60" ry="55"/><ellipse class="muzzle" cx="116" cy="99" rx="33" ry="25"/><ellipse class="eye left" cx="92" cy="72" rx="7" ry="10"/><ellipse class="eye right" cx="140" cy="72" rx="7" ry="10"/><circle class="eye-shine left" cx="94" cy="69" r="2"/><circle class="eye-shine right" cx="142" cy="69" r="2"/><path class="brow left" d="M82 56 Q92 49 102 56"/><path class="brow right" d="M130 56 Q140 49 150 56"/><ellipse class="nose" cx="116" cy="92" rx="11" ry="8"/><path class="mouth" d="M116 100 Q105 112 96 104 M116 100 Q127 112 136 104"/><path class="tongue" d="M109 107 Q116 124 124 107"/></g><g class="water-drops"><path d="M62 54 Q53 66 62 72 Q71 66 62 54"/><path d="M179 72 Q170 84 179 90 Q188 84 179 72"/><path d="M49 120 Q40 132 49 138 Q58 132 49 120"/></g></svg>`;
  }

  async function animateElement(selector, keyframes, options = {}) {
    const element = root.querySelector(selector);
    const reduced = typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    const duration = reduced ? 1 : (options.duration ?? 500);
    if (!element?.animate) { await wait(duration); return; }
    const animation = element.animate(keyframes, { duration, easing: options.easing ?? "cubic-bezier(.22,.8,.22,1)", fill: "forwards" });
    await animation.finished.catch(() => {});
  }

  function addSuggestion(word) {
    const input = root.querySelector("#story-input");
    if (!input || input.value.toLowerCase().includes(word.toLowerCase())) return;
    let value = input.value.trim();
    if (state.currentStoryStep === 2 && ["small", "wet", "scared"].includes(word.toLowerCase())) value = value.replace(/\b(a|the)\s+((?:small,?\s*|wet,?\s*|scared,?\s*|little,?\s*)*)dog\b/i, (_, article, details) => `${article} ${details}${word}, dog`);
    else if (word.toLowerCase() === "finally") value = `Finally, ${value.charAt(0).toLowerCase()}${value.slice(1)}`;
    else value = `${value.replace(/[.]$/, "")}, ${word}.`;
    input.value = value;
    input.focus();
  }

  async function resolveStoryChoice(choice) {
    if (state.questStage === "meet" && ["box", "table"].includes(choice)) {
      state.storyBeatOpen = false;
      const recast = choice === "box" ? "Coco, hide in the box!" : "Coco, hide under the table!";
      await hideCocoAndBegin({ understood: true, intent: "hide_coco", destination: choice, recast, text: recast, mode: "instant" });
      return;
    }
    if (state.questStage === "search") {
      if (choice !== "tree") { showToast("Good guess! Your clues point toward the old tree—try once more."); return; }
      state.storyBeatOpen = false;
      setGuide("Milo", "Your guess fits every clue!", "Now say or type it in your own words: “Coco is behind the tree.”");
      render();
      requestAnimationFrame(() => root.querySelector("#world-input")?.focus());
      return;
    }
    if (state.questStage === "care" && state.careOptions.has(choice)) {
      state.storyBeatOpen = false;
      const care = completeCare(state, story, choice);
      if (!care) return;
      const messages = {
        towel: ["Coco", "Warm and dry—woof! Thank you!"],
        snack: ["Coco", "That snack was just what I needed!"],
        friends: ["Ms. Maple", "The whole class cheers: Welcome home, Coco!"],
      };
      setGuide(messages[choice][0], messages[choice][1], "Coco is ready to go home to Story House.", "story");
      speak(messages[choice][1]);
      render();
    }
  }

  async function handleClick(event) {
    const immediateAction = event.target.closest("[data-action]")?.dataset.action;
    if (immediateAction === "home") { returnToTownHome(); return; }
    if (immediateAction === "toast-close") { clearTimeout(toastTimer); root.querySelector("#toast")?.classList.remove("show"); return; }
    if (agentBusy) return;
    const protectedPanel = event.target.closest("[data-stop-close]");
    if (protectedPanel) {
      const localTarget = event.target.closest("[data-action],[data-speak],[data-challenge-answer],[data-location],[data-story-choice],[data-easter-id]");
      if (!localTarget || !protectedPanel.contains(localTarget)) return;
    }
    const speakButton = event.target.closest("[data-speak]");
    if (speakButton) { speak(speakButton.dataset.speak); return; }
    const challengeAnswer = event.target.closest("[data-challenge-answer]");
    if (challengeAnswer) { handleLearningAnswer(challengeAnswer.dataset.challengeAnswer); return; }
    const storyChoice = event.target.closest("[data-story-choice]");
    if (storyChoice) { await resolveStoryChoice(storyChoice.dataset.storyChoice); return; }
    const easterEgg = event.target.closest("[data-easter-id]");
    if (easterEgg) {
      const id = easterEgg.dataset.easterId;
      if (!hasEasterEgg(state, id)) { showToast("Keep exploring and earning stars to reveal this surprise.", "gentle"); return; }
      state.easterEggOpen = id;
      render();
      return;
    }
    const location = event.target.closest("[data-location]");
    if (location) { state.explorationOpen = false; await goToLocation(location.dataset.location); return; }
    const utterance = event.target.closest("[data-utterance]");
    if (utterance) { await runWorldInput(utterance.dataset.utterance, "phrase"); return; }
    const suggestion = event.target.closest("[data-suggestion]");
    if (suggestion) { addSuggestion(suggestion.dataset.suggestion); return; }
    const actionElement = event.target.closest("[data-action]");
    if (!actionElement) return;
    const action = actionElement.dataset.action;
    if (action === "quest-next") { await followQuest(); return; }
    if (action === "guided-next") { await followGuidedNext(); return; }
    if (action === "coach-close") { state.coachOpen = false; render(); return; }
    if (action === "exploration-close") { state.explorationOpen = false; render(); return; }
    if (action === "story-beat-close") { state.storyBeatOpen = false; render(); return; }
    if (action === "quest-story") { state.explorationOpen = false; render(); await followQuest(); return; }
    if (action === "bonus-challenge") { const challengeId = bonusChallengeForCurrentContext(); state.explorationOpen = false; if (challengeId) openLearningChallenge(challengeId); else render(); return; }
    if (action === "challenge-listen") { readLearningQuestion(); return; }
    if (action === "challenge-hint") { state.learning.hintOpen = true; render(); requestAnimationFrame(() => root.querySelector("#learning-form input")?.focus()); return; }
    if (action === "challenge-voice") { if (voiceSubmitting) return; if (!speechInput.supported) { showToast("Voice answers are unavailable here. You can still tap or type your answer."); return; } if (speechInput.listening) speechInput.stop(); else { state.learning.voiceHeard = ""; lastVoiceFinal = ""; updateLearningVoiceSurface("Starting microphone…", true, ""); if (!speechInput.start()) updateLearningVoiceSurface("I couldn't start the microphone. Try once more, or type your answer.", false); } return; }
    if (action === "challenge-close") { await finishLearningChallenge(false); return; }
    if (action === "challenge-continue") { continueLearningChallenge(); return; }
    if (action === "challenge-next") { await finishLearningChallenge(true); return; }
    if (action === "toggle-pocket") { state.wordPocketOpen = !state.wordPocketOpen; render(); return; }
    if (action === "surprise-trail") { state.easterEggOpen = "trail"; state.wordPocketOpen = false; render(); return; }
    if (action === "surprise-close") { state.easterEggOpen = null; render(); return; }
    if (action === "voice") { if (voiceSubmitting) return; if (!speechInput.supported) { showToast("Voice input is unavailable here. Type your idea and press Enter.", "gentle"); return; } if (speechInput.listening) speechInput.stop(); else { lastVoiceFinal = ""; if (!speechInput.start()) { updateVoiceSurface("The microphone didn't start. Tap once more, or type and press Enter.", false); showToast("Microphone not started — typing still works.", "gentle"); } } return; }
    if (action === "story-voice") { if (voiceSubmitting) return; if (!speechInput.supported) { showToast("Voice input is unavailable here. You can still type your story.", "gentle"); return; } if (speechInput.listening) speechInput.stop(); else { storyVoiceBase = root.querySelector("#story-input")?.value.trim() || ""; lastVoiceFinal = ""; if (!speechInput.start()) { updateStoryVoiceSurface("The microphone didn't start. Tap once more, or keep typing.", false); showToast("Microphone not started — your typed story is safe.", "gentle"); } } return; }
    if (action === "open-story") { await openStoryStudio(); return; }
    if (action === "lesson-review") { openLearningChallenge("story-memory"); return; }
    if (action === "back-world") { returnToTownHome(); return; }
    if (action === "play-story") { await playStorySentence(); return; }
    if (action === "previous-story") { await changeStoryScene(-1); return; }
    if (action === "next-story") { await changeStoryScene(1); return; }
    if (action === "finish-story") { await finishStory(); return; }
    if (action === "read-page") { readCurrentBookPage(); return; }
    if (action === "book-prev") { await turnBook(-1); return; }
    if (action === "book-next") { await turnBook(1); return; }
    if (action === "book-first") { state.bookPage = 0; render(); return; }
    if (action === "restart") { Object.assign(state, createStoryState(story)); setLocationGuide("town"); render(); return; }
    if (action === "print") window.print();
  }

  async function handleSubmit(event) {
    event.preventDefault();
    if (event.target.id === "learning-form") {
      handleLearningAnswer(new FormData(event.target).get("answer"));
      return;
    }
    if (event.target.id === "world-form") {
      const input = event.target.querySelector("#world-input");
      const message = input.value.trim();
      worldInputDraft = "";
      input.value = "";
      restoreWorldInputFocus = true;
      await runWorldInput(message, "text");
    }
  }

  function handleInput(event) {
    if (event.target.id === "world-input") worldInputDraft = event.target.value;
  }

  function handleKeydown(event) {
    if (event.key === "Escape" && state.easterEggOpen) { state.easterEggOpen = null; render(); return; }
    if (event.key === "Escape" && state.learning?.activeId) { resetLearningModal(); render(); return; }
    if (event.key === "Escape" && state.storyBeatOpen) { state.storyBeatOpen = false; render(); return; }
    if (event.key === "Escape" && state.explorationOpen) { state.explorationOpen = false; render(); return; }
    if (event.key === "Escape" && state.wordPocketOpen) { state.wordPocketOpen = false; render(); return; }
    if (state.scene !== "book" || event.target.matches?.("input,textarea")) return;
    if (event.key === "ArrowLeft") { event.preventDefault(); void turnBook(-1); }
    if (event.key === "ArrowRight") { event.preventDefault(); void turnBook(1); }
  }

  function handlePointerDown(event) {
    if (state.scene !== "book" || event.target.closest("button") || !event.target.closest(".flipbook-page")) return;
    bookPointerStart = { x: event.clientX, y: event.clientY };
  }

  function handlePointerUp(event) {
    if (!bookPointerStart || state.scene !== "book") return;
    const deltaX = event.clientX - bookPointerStart.x;
    const deltaY = event.clientY - bookPointerStart.y;
    bookPointerStart = null;
    if (Math.abs(deltaX) >= 48 && Math.abs(deltaX) > Math.abs(deltaY)) void turnBook(deltaX < 0 ? 1 : -1);
  }

  function showToast(message, kind = "normal") {
    clearTimeout(toastTimer);
    requestAnimationFrame(() => {
      const toast = root.querySelector("#toast");
      if (!toast) return;
      const config = {
        normal: { title: "Milo says", icon: "●" },
        gentle: { title: "Try this", icon: "💡" },
        reward: { title: "Star earned!", icon: "★" },
        action: { title: "Action complete!", icon: "✓" },
        easter: { title: "Surprise unlocked!", icon: "✨" },
      }[kind] || { title: "Milo says", icon: "●" };
      let title = config.title;
      let detail = String(message || "").trim();
      if (kind === "reward" && /caring english saved/i.test(detail)) {
        title = "English saved!";
        detail = "Coco heard your own words!";
      }
      if (kind === "easter") detail = detail.replace(/^✨\s*Surprise unlocked:\s*/i, "");
      toast.querySelector(".toast-icon").textContent = config.icon;
      toast.querySelector(".toast-copy strong").textContent = title;
      toast.querySelector(".toast-copy p").textContent = detail;
      toast.className = `toast toast-${kind}`;
      void toast.offsetWidth;
      toast.classList.add("show");
      toastTimer = setTimeout(() => toast.classList.remove("show"), 3800);
    });
  }

  function queueRewardToast(points, label, progress) {
    pendingRewardToast ??= { points: 0, labels: [], total: progress.total, chapter: progress.displayPoints, target: progress.target, ready: progress.ready };
    pendingRewardToast.points += points;
    pendingRewardToast.total = progress.total;
    pendingRewardToast.chapter = progress.displayPoints;
    pendingRewardToast.target = progress.target;
    pendingRewardToast.ready ||= progress.ready;
    if (!pendingRewardToast.labels.includes(label)) pendingRewardToast.labels.push(label);
    clearTimeout(rewardToastTimer);
    rewardToastTimer = setTimeout(() => {
      const reward = pendingRewardToast;
      pendingRewardToast = null;
      if (!reward) return;
      const summary = reward.labels.slice(0, 2).join(" + ");
      const progressText = reward.ready ? "Main story unlocked!" : `${reward.chapter}/${reward.target} chapter stars`;
      showToast(`+${reward.points} ★ ${summary} · ${progressText}`, "reward");
    }, 40);
  }

  function announceEasterEggs(items = []) {
    if (!items.length) return;
    const item = items.at(-1);
    setTimeout(() => {
      showToast(`✨ Surprise unlocked: ${item.title}! Open the Surprise Trail to see it.`, "easter");
    }, 1050);
  }

  root.addEventListener("click", handleClick);
  root.addEventListener("submit", handleSubmit);
  root.addEventListener("input", handleInput);
  root.addEventListener("keydown", handleKeydown);
  root.addEventListener("pointerdown", handlePointerDown);
  root.addEventListener("pointerup", handlePointerUp);

  return { render, state, speechInput, returnToTown: returnToTownHome };
}
