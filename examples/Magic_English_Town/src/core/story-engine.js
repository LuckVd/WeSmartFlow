import { getSceneAccess } from "./scene-unlocks.js";

const LOCATION_ALIASES = {
  town: ["town", "square", "map"],
  petshop: ["pet shop", "petshop", "pets"],
  bakery: ["bakery", "moonbeam bakery"],
  school: ["school", "star school"],
  park: ["park", "whispering park"],
  storyhouse: ["story house", "storyhouse", "storybook"],
};

export const LOCATION_LABELS = {
  town: "Town Square",
  petshop: "Pet Shop",
  bakery: "Moonbeam Bakery",
  school: "Star School",
  park: "Whispering Park",
  storyhouse: "Story House",
};

export const EASTER_EGG_MILESTONES = [
  { id: "word-fountain", stars: 3, icon: "💫", title: "Whispering Fountain", description: "Your English words float above the fountain." },
  { id: "rainbow-cake", stars: 6, icon: "🌈", title: "Rainbow Cake", description: "Betty baked a secret cake at Moonbeam Bakery." },
  { id: "coco-cape", stars: 9, icon: "🦸", title: "Coco's Magic Cape", description: "Coco wears a tiny explorer cape around town." },
  { id: "moon-garden", stars: 12, icon: "🌙", title: "Moon Garden", description: "A hidden moonlit path appears in Whispering Park." },
  { id: "night-story", stars: 15, icon: "✨", title: "Firefly Story", description: "The town tells a tiny secret story after dark." },
  { id: "secret-book-page", stars: 18, icon: "📖", title: "Secret Storybook Page", description: "A surprise memory is added to your finished book." },
];

const DEFAULT_PROGRESSION = {
  stages: ["meet", "search", "care", "home", "complete"],
  adventurePointTargets: { meet: 3, search: 6, care: 2, home: 0, complete: 0 },
  participationTargets: { meet: 1, search: 2, care: 1 },
  starsGateMainStory: true,
};

export function createStoryState(story) {
  const progression = {
    stages: [...(story.progression?.stages ?? DEFAULT_PROGRESSION.stages)],
    adventurePointTargets: { ...DEFAULT_PROGRESSION.adventurePointTargets, ...(story.progression?.adventurePointTargets ?? {}) },
    participationTargets: { ...DEFAULT_PROGRESSION.participationTargets, ...(story.progression?.participationTargets ?? {}) },
    starsGateMainStory: story.progression?.starsGateMainStory ?? DEFAULT_PROGRESSION.starsGateMainStory,
  };
  const startLocation = story.world?.startLocation ?? "town";
  const firstStage = progression.stages[0] ?? "meet";
  return {
    storyId: story.id,
    storyTitle: story.title,
    storyRuntime: story.runtime,
    storyPremise: story.agent?.premise ?? "",
    progression,
    storyStages: [...progression.stages],
    sceneUnlocks: story.world?.sceneUnlocks ?? {},
    scene: "world",
    location: startLocation,
    busy: false,
    questStage: firstStage,
    careChoice: null,
    clues: new Set(),
    visited: new Set([startLocation]),
    discoveries: new Set(),
    sideActivities: new Set(),
    adventurePoints: Object.fromEntries(progression.stages.map((stage) => [stage, 0])),
    adventureScore: 0,
    pointRewards: new Set(),
    easterEggOpen: null,
    learnerContributions: [],
    lessonOutcomes: (story.learning?.outcomes ?? []).map((outcome) => ({ ...outcome, criteria: outcome.criteria.map((criterion) => ({ ...criterion })) })),
    lessonEvidence: Object.fromEntries((story.learning?.outcomes ?? []).map((outcome) => [outcome.id, new Set()])),
    lessonSamples: Object.fromEntries((story.learning?.outcomes ?? []).map((outcome) => [outcome.id, []])),
    careOptions: new Set(),
    objectPositions: { ball: "floor" },
    mastery: {
      positionWords: new Set(),
      manners: new Set(),
      colors: new Set(),
      parkClues: new Set(),
    },
    discovered: new Set(),
    usedWords: new Set(),
    wordEvidence: {},
    wordPocketOpen: false,
    explorationOpen: false,
    storyBeatOpen: false,
    coachOpen: true,
    learning: {
      activeId: null,
      questionIndex: 0,
      feedback: null,
      correct: false,
      finished: false,
      voiceHeard: "",
      history: [],
      hintOpen: false,
      attempts: {},
      completed: new Set(),
    },
    dogPlace: "center",
    dogSize: "normal",
    dogWet: false,
    dogScared: false,
    lastSentence: "",
    lastRecast: "",
    lastHeard: "",
    guide: {
      speaker: "Milo",
      text: "Coco is waiting at the Pet Shop. This is where today's story begins.",
      hint: "Follow the glowing route; new places unlock as the story moves forward.",
      tone: "welcome",
    },
    storyLines: story.writing.scenes.map(() => ""),
    storyDraftLines: story.writing.scenes.map(() => ""),
    storyEdited: new Set(),
    storyNeedsWriting: false,
    storyVisuals: story.writing.scenes.map((_, index) => analyzeStorySentence("", index)),
    storyPlayed: new Set(),
    currentStoryStep: 0,
    bookPage: 0,
    revisionCount: 0,
    eventLog: [],
  };
}

export function logEvent(state, event, details = {}) {
  state.eventLog.push({ event, ...details, at: Date.now() });
}

export function collectWord(state, story, wordKey, evidence = "discovered") {
  if (!story.vocabulary[wordKey]) return null;
  const isNew = !state.discovered.has(wordKey);
  state.discovered.add(wordKey);
  const current = state.wordEvidence[wordKey] ?? [];
  if (!current.includes(evidence)) state.wordEvidence[wordKey] = [...current, evidence];
  logEvent(state, "word_collected", { wordKey, evidence, isNew });
  return { isNew, word: story.vocabulary[wordKey] };
}

export function visitLocation(state, location) {
  if (!LOCATION_LABELS[location]) return false;
  if (!getSceneAccess(state, location).unlocked) return false;
  state.location = location;
  state.scene = "world";
  state.visited.add(location);
  logEvent(state, "location_visited", { location });
  return true;
}

export function recordMastery(state, area, evidence) {
  const badgeByArea = { positionWords: "badge-position", manners: "badge-polite", colors: "badge-colors", parkClues: "badge-detective" };
  const requiredByArea = { positionWords: 2, manners: 1, colors: 2, parkClues: 2 };
  state.mastery ??= {};
  state.mastery[area] ??= new Set();
  state.mastery[area].add(evidence);
  const count = state.mastery[area].size;
  if (count >= requiredByArea[area]) state.sideActivities.add(badgeByArea[area]);
  logEvent(state, "mastery_evidence", { area, evidence, count, complete: count >= requiredByArea[area] });
  return { area, count, required: requiredByArea[area], complete: count >= requiredByArea[area] };
}

export function masteryCount(state, area) {
  return state.mastery?.[area]?.size ?? 0;
}

export function recordLessonEvidence(state, story, outcomeId, evidence, { text = "", support = "independent" } = {}) {
  const outcome = story.learning?.outcomes?.find((item) => item.id === outcomeId);
  if (!outcome || !evidence) return { added: false, complete: false };
  state.lessonEvidence ??= {};
  state.lessonEvidence[outcomeId] ??= new Set();
  const before = state.lessonEvidence[outcomeId].size;
  state.lessonEvidence[outcomeId].add(evidence);
  state.lessonSamples ??= {};
  state.lessonSamples[outcomeId] ??= [];
  const cleanSample = String(text).trim();
  if (cleanSample && !state.lessonSamples[outcomeId].some((item) => item.text === cleanSample)) {
    state.lessonSamples[outcomeId].push({ text: cleanSample, support });
  }
  const progress = getLessonOutcomeProgress(state, story).find((item) => item.id === outcomeId);
  const added = state.lessonEvidence[outcomeId].size > before;
  if (added) logEvent(state, "lesson_evidence", { outcomeId, evidence, support, complete: progress?.complete ?? false });
  return { added, ...(progress ?? { complete: false }) };
}

export function getLessonOutcomeProgress(state, story = null) {
  const outcomes = story?.learning?.outcomes ?? state.lessonOutcomes ?? [];
  return outcomes.map((outcome) => {
    const evidence = [...(state.lessonEvidence?.[outcome.id] ?? [])];
    const criteria = outcome.criteria ?? [];
    const parts = criteria.map((criterion) => {
      const count = evidence.filter((item) => item.startsWith(criterion.prefix)).length;
      return { ...criterion, count: Math.min(count, criterion.required), complete: count >= criterion.required };
    });
    return {
      ...outcome,
      evidence,
      count: parts.reduce((sum, item) => sum + item.count, 0),
      required: parts.reduce((sum, item) => sum + item.required, 0),
      complete: parts.every((item) => item.complete),
      parts,
      samples: state.lessonSamples?.[outcome.id] ?? [],
    };
  });
}

export function getLessonProgress(state, story) {
  const outcomes = getLessonOutcomeProgress(state, story);
  const completed = outcomes.filter((outcome) => outcome.complete).length;
  return { outcomes, completed, total: outcomes.length, complete: Boolean(outcomes.length) && completed === outcomes.length };
}

const NON_CONTRIBUTION_INTENTS = new Set(["travel", "help"]);

function englishWords(value) {
  return String(value ?? "").toLowerCase().match(/[a-z]+(?:'[a-z]+)?/g) ?? [];
}

export function isCaringEnglish(value, intent = "") {
  if (englishWords(value).length < 2) return false;
  if (intent === "care_coco") return true;
  const text = cleanText(value);
  return hasAny(text, [
    "are you okay", "are you ok", "coco is okay", "coco is safe", "you are safe",
    "don't be scared", "dont be scared", "do not be scared", "don't be afraid", "do not be afraid",
    "i love coco", "love you", "we love you", "i am here", "i'm here", "i am with you", "we are here",
    "feel better", "get well", "you will be okay", "you'll be okay", "be brave", "take care",
    "i will help", "i'll help", "i can help", "can i help", "let me help", "good boy", "poor coco",
    "dry coco", "dry him", "keep coco warm", "keep you warm", "with a towel",
    "snack for coco", "food for coco", "feed coco", "give coco", "give you food",
    "pet coco", "pat coco", "hug coco", "stroke coco",
  ]);
}

export function recordLearnerContribution(state, { text, source, intent, location = state.location, stage = state.questStage } = {}, story = null) {
  if (!["text", "voice"].includes(source) || NON_CONTRIBUTION_INTENTS.has(intent) || englishWords(text).length < 2) return { added: false, reason: "not-authored-english" };
  if (stage === "meet" && location !== "petshop") return { added: false, reason: "wrong-context" };
  const normalized = cleanText(text);
  if (story) {
    const positions = ["on", "in", "under", "behind"].filter((word) => englishWords(normalized).includes(word));
    if (stage === "meet" && location === "petshop" && positions.length && hasAny(normalized, ["ball", "box", "table"])) {
      positions.forEach((position) => recordLessonEvidence(state, story, "position-power", `say:${position}`, { text, support: "independent" }));
    }
    if (stage === "search") recordLessonEvidence(state, story, "clue-talk", `place:${location}`, { text, support: "independent" });
    if (["search", "care"].includes(stage) && normalized.includes("behind") && normalized.includes("tree")) {
      recordLessonEvidence(state, story, "coco-report", "place:behind-tree", { text, support: "independent" });
    }
    if (["search", "care"].includes(stage)) {
      if (hasAny(normalized, ["wet"])) recordLessonEvidence(state, story, "coco-report", "feeling:wet", { text, support: "independent" });
      if (hasAny(normalized, ["scared", "afraid"])) recordLessonEvidence(state, story, "coco-report", "feeling:scared", { text, support: "independent" });
    }
    const cocoReport = getLessonOutcomeProgress(state, story).find((item) => item.id === "coco-report");
    if (stage === "care" && isCaringEnglish(text, intent) && (!cocoReport || cocoReport.complete)) {
      recordLessonEvidence(state, story, "caring-words", `care:${normalized}`, { text, support: "independent" });
    }
  }
  if (stage === "care" && !isCaringEnglish(text, intent)) return { added: false, reason: "not-caring-english" };
  state.learnerContributions ??= [];
  const duplicate = state.learnerContributions.some((item) => item.stage === stage && item.location === location && item.text === normalized);
  if (duplicate) return { added: false, reason: "duplicate" };
  const contribution = { stage, location, intent, source, text: normalized };
  state.learnerContributions.push(contribution);
  logEvent(state, "learner_contribution", contribution);
  return { added: true, contribution };
}

export function getParticipationProgress(state, stage = state.questStage) {
  const target = state.progression?.participationTargets?.[stage] ?? DEFAULT_PROGRESSION.participationTargets[stage] ?? 0;
  const contributions = (state.learnerContributions ?? []).filter((item) => item.stage === stage);
  const count = stage === "search" ? new Set(contributions.map((item) => item.location)).size : contributions.length;
  const prompts = {
    meet: "say or type one English sentence to Coco",
    search: `ask or describe clues in ${target} different places`,
    care: "say or type one caring English sentence for Coco",
  };
  return { count: Math.min(count, target), total: count, target, complete: count >= target, prompt: prompts[stage] || "" };
}

export const ADVENTURE_POINT_TARGETS = DEFAULT_PROGRESSION.adventurePointTargets;

function adventureTarget(state, stage) {
  return state.progression?.adventurePointTargets?.[stage] ?? ADVENTURE_POINT_TARGETS[stage] ?? 0;
}

export function getEasterEggProgress(state) {
  const total = state.adventureScore ?? Object.values(state.adventurePoints ?? {}).reduce((sum, value) => sum + value, 0);
  const unlocked = EASTER_EGG_MILESTONES.filter((item) => total >= item.stars);
  const next = EASTER_EGG_MILESTONES.find((item) => total < item.stars) ?? null;
  const previousStars = unlocked.at(-1)?.stars ?? 0;
  const percent = next ? Math.min(100, Math.round(((total - previousStars) / (next.stars - previousStars)) * 100)) : 100;
  return { total, unlocked, next, previousStars, percent, complete: !next };
}

export function hasEasterEgg(state, id) {
  return getEasterEggProgress(state).unlocked.some((item) => item.id === id);
}

function rewardKeyFromToken(token, stage) {
  return token.startsWith(`${stage}:`) ? token.slice(stage.length + 1) : "";
}

function rewardArea(key) {
  if (/bakery|baker|food-|polite-request/.test(key)) return "bakery";
  if (/school|teacher|color-/.test(key)) return "school";
  if (/park-|park-investigation/.test(key)) return "park";
  if (/town-/.test(key)) return "town";
  return "";
}

export function getAdventureRequirements(state, stage = state.questStage) {
  const keys = [...(state.pointRewards ?? [])].map((token) => rewardKeyFromToken(token, stage)).filter(Boolean);
  const participation = getParticipationProgress(state, stage);
  const outcome = (id) => getLessonOutcomeProgress(state).find((item) => item.id === id);
  if (stage === "meet") {
    const activityTypes = new Set(keys.map((key) => key === "greet-coco" ? "conversation" : key.startsWith("ball-") ? "movement" : key.startsWith("petshop-object-") ? "observation" : key.startsWith("english-challenge:") ? "practice" : "").filter(Boolean));
    const positionPower = outcome("position-power");
    const missing = [];
    if (positionPower && !positionPower.complete) {
      if (!positionPower.parts[0]?.complete) missing.push("move the ball to two different positions");
      if (!positionPower.parts[1]?.complete) missing.push("describe where the ball is in your own words");
    } else if (!positionPower && activityTypes.size < 2) missing.push("try one different kind of Pet Shop interaction");
    return { complete: missing.length === 0, missing, activityTypes: [...activityTypes], areas: [], participation, outcome: positionPower };
  }
  if (stage === "search") {
    const areas = new Set(keys.map(rewardArea).filter(Boolean));
    const hasParkEvidence = masteryCount(state, "parkClues") >= 1;
    const hasTreeEvidence = state.clues?.has("bush") || state.clues?.has("map");
    const missing = [];
    if (areas.size < 3) missing.push(`explore ${3 - areas.size} more ${3 - areas.size === 1 ? "place" : "places"}`);
    if (!hasParkEvidence) missing.push("investigate one Park clue");
    if (hasParkEvidence && !hasTreeEvidence) missing.push("find a clue that points to the old tree");
    const clueTalk = outcome("clue-talk");
    if (clueTalk ? !clueTalk.complete : !participation.complete) missing.push(`${participation.prompt} (${participation.count}/${participation.target})`);
    return { complete: missing.length === 0, missing, activityTypes: [], areas: [...areas], hasParkEvidence, hasTreeEvidence, participation, outcome: clueTalk };
  }
  if (stage === "care") {
    const optionCount = state.careOptions?.size ?? 0;
    const missing = optionCount >= 2 ? [] : [`find ${2 - optionCount} more caring ${2 - optionCount === 1 ? "idea" : "ideas"}`];
    const cocoReport = outcome("coco-report");
    const caringWords = outcome("caring-words");
    if (cocoReport && !cocoReport.complete) missing.push("say where Coco is and how he feels");
    if (caringWords ? !caringWords.complete : !participation.complete) missing.push(participation.prompt);
    return { complete: missing.length === 0, missing, activityTypes: [], areas: [], optionCount, participation, outcomes: [cocoReport, caringWords].filter(Boolean) };
  }
  return { complete: true, missing: [], activityTypes: [], areas: [], participation };
}

export function awardAdventurePoints(state, rewardKey, points = 1, stage = state.questStage) {
  const target = adventureTarget(state, stage);
  const token = `${stage}:${rewardKey}`;
  state.pointRewards ??= new Set();
  state.adventurePoints ??= {};
  if (!rewardKey || state.pointRewards.has(token)) {
    const progress = getAdventureProgress(state, stage);
    return { added: false, awarded: 0, newlyUnlocked: [], ...progress };
  }
  const previousTotal = getEasterEggProgress(state).total;
  state.pointRewards.add(token);
  const previous = state.adventurePoints[stage] ?? 0;
  state.adventurePoints[stage] = previous + Math.max(1, points);
  state.adventureScore = (state.adventureScore ?? Object.values(state.adventurePoints).reduce((sum, value) => sum + value, 0) - state.adventurePoints[stage]) + (state.adventurePoints[stage] - previous);
  const current = state.adventurePoints[stage];
  const awarded = current - previous;
  const progress = getAdventureProgress(state, stage);
  const newlyUnlocked = EASTER_EGG_MILESTONES.filter((item) => previousTotal < item.stars && progress.total >= item.stars);
  logEvent(state, "adventure_points_earned", { stage, rewardKey, added: awarded, current, total: progress.total, target });
  newlyUnlocked.forEach((item) => logEvent(state, "easter_egg_unlocked", { id: item.id, stars: item.stars }));
  return { added: true, awarded, newlyUnlocked, ...progress };
}

export function getAdventureProgress(state, stage = state.questStage) {
  const target = adventureTarget(state, stage);
  const points = state.adventurePoints?.[stage] ?? 0;
  const requirements = getAdventureRequirements(state, stage);
  const total = state.adventureScore ?? Object.values(state.adventurePoints ?? {}).reduce((sum, value) => sum + value, 0);
  return {
    stage,
    points,
    displayPoints: target ? Math.min(target, points) : points,
    target,
    ready: target === 0 || (requirements.complete && (!state.progression?.starsGateMainStory || points >= target)),
    percent: target ? Math.min(100, Math.round((points / target) * 100)) : 100,
    total,
    requirements,
  };
}

export function getGuidedStoryStep(state) {
  const at = state.location;
  const step = (id, location, title, prompt, hint, progress, target = "") => ({ id, location, title, prompt, hint, progress, target, meta: LOCATION_LABELS[location] });
  if (state.questStage === "meet") {
    const adventure = getAdventureProgress(state);
    if (!adventure.ready) {
      const positionPower = adventure.requirements.outcome;
      if (!positionPower?.parts[0]?.complete) return { ...step("move-ball", "petshop", `Build Position Power · ${positionPower?.count ?? 0}/${positionPower?.required ?? 3}`, "Move the red ball to two different places.", "Try on the table, in the box, or under the table.", 8 + adventure.percent * .12, ".red-ball"), challenge: "Position Power", done: positionPower?.count ?? 0, required: positionPower?.required ?? 3, mode: "explore" };
      return { ...step("describe-ball", "petshop", `Use your Position Power · ${positionPower?.count ?? 2}/${positionPower?.required ?? 3}`, "Say or type where the ball is in your own words.", "Try: “The ball is under the table.” Tapped examples move the ball, but your own words save the power.", 14, "#world-input"), challenge: "Position Power", done: positionPower?.count ?? 2, required: positionPower?.required ?? 3, mode: "explore" };
    }
    return { ...step("meet-coco", "petshop", "Position Power complete!", "You moved and described the ball with English.", "Choose Coco's hiding place and watch what happens next.", 18, ".coco-character"), mode: "story", ready: true };
  }
  if (state.questStage === "search") {
    const adventure = getAdventureProgress(state);
    if (!adventure.ready) {
      const unlockedSearchPlaces = ["bakery", "school", "park", "town"].filter((location) => getSceneAccess(state, location).unlocked);
      const exploredAreas = new Set(adventure.requirements.areas);
      const participation = adventure.requirements.participation;
      if (!participation.complete) {
        const spokenPlaces = new Set((state.learnerContributions ?? []).filter((item) => item.stage === "search").map((item) => item.location));
        const nextSpeakingPlace = unlockedSearchPlaces.find((location) => !spokenPlaces.has(location)) || unlockedSearchPlaces.at(-1) || "town";
        const examples = { bakery: "Try “Have you seen Coco?”", school: "Try “I see paw prints.”", park: "Try “The puddle is wet.”", town: "Try “I see a blue butterfly.”" };
        return { ...step("speak-search", nextSpeakingPlace, `Use English in the search · ${participation.count}/${participation.target} places`, "Ask a character or describe a clue in your own words.", `${examples[nextSpeakingPlace]} Type or speak it yourself; tapping an example does not count.`, 20 + adventure.percent * .5, "#world-input"), challenge: "Your English", done: participation.count, required: participation.target, mode: "explore" };
      }
      const parkReady = getSceneAccess(state, "park").unlocked;
      const nextLocation = parkReady && (!adventure.requirements.hasParkEvidence || !adventure.requirements.hasTreeEvidence)
        ? "park"
        : unlockedSearchPlaces.find((location) => !exploredAreas.has(location)) || unlockedSearchPlaces.at(-1) || "town";
      const target = { bakery: ".bakery-evidence", school: ".school-evidence", town: ".town-butterfly", park: ".paw-trail" }[nextLocation];
      return { ...step("explore-search", nextLocation, `Search the town · ${adventure.displayPoints}/${adventure.target} stars`, "Every new clue, useful word, and conversation adds to your search.", adventure.requirements.missing[0] || "Follow each clue to wake the next part of town.", 20 + adventure.percent * .5, target), challenge: "Adventure Stars", done: adventure.displayPoints, required: adventure.target, mode: "explore" };
    }
    return { ...step("find-coco", "park", "Story unlocked: Make your guess", "Your exploration has revealed enough of Coco's trail.", "Continue the story and choose where Coco is hiding.", 76, ".oak-tree"), mode: "story", ready: true };
  }
  if (state.questStage === "care") {
    const adventure = getAdventureProgress(state);
    if (!adventure.ready) {
      const participation = adventure.requirements.participation;
      const [cocoReport, caringWords] = adventure.requirements.outcomes ?? [];
      if (cocoReport && !cocoReport.complete) return { ...step("report-coco", "park", `Describe Coco · ${cocoReport.count}/${cocoReport.required}`, "Tell Milo where Coco is and how he feels.", cocoReport.parts[0]?.complete ? "You found the place. Now try: “Coco is wet” or “Coco is scared.”" : "Try: “Coco is behind the tree. He is wet and scared.”", 80, "#world-input"), challenge: "Coco Report", done: cocoReport.count, required: cocoReport.required, mode: "explore" };
      if (caringWords && !caringWords.complete) return { ...step("speak-care", "park", `Say something kind · ${participation.count}/${participation.target}`, "Coco needs to hear one caring English sentence from you.", "Try “I can help you”, “Don't be scared”, or “You are safe now.”", 84, "#world-input"), challenge: "Caring Words", done: participation.count, required: participation.target, mode: "explore" };
      const nextLocation = !state.careOptions?.has("towel") ? "petshop" : !state.careOptions?.has("snack") ? "bakery" : "school";
      return { ...step("explore-care", nextLocation, `Find ways to help · ${adventure.displayPoints}/${adventure.target} stars`, "Explore the town and collect two caring ideas for Coco.", adventure.requirements.missing[0] || "Try a towel, a snack, or tell his friends that he is safe.", 78 + adventure.percent * .1, nextLocation === "petshop" ? ".room-towel" : nextLocation === "bakery" ? ".bakery-tray" : ".community-character"), challenge: "Kindness Stars", done: adventure.displayPoints, required: adventure.target, mode: "explore" };
    }
    return { ...step("care-coco-ready", "park", "Caring Words complete!", "You described Coco and found more than one way to help.", "Choose one caring idea for the story ending.", 90, ".park-coco"), mode: "story", ready: true };
  }
  if (state.questStage === "home") return { ...step("make-story", "storyhouse", at === "storyhouse" ? "Make your story" : "Take Coco to Story House", "Milo remembers every choice from your adventure.", "Open the story and make each page yours.", 95, ".story-memory"), action: "open_story" };
  return { ...step("read-story", "storyhouse", at === "storyhouse" ? "Read your story again" : "Visit your finished story", "Your storybook is waiting on the shelf.", "Open it whenever you want, or keep exploring town.", 100, ".story-memory"), action: "open_story" };
}

export function performHideChoice(state, story, destination) {
  const actions = {
    box: { place: "box", sentence: "Coco is in the box.", words: ["dog", "in", "box"] },
    table: { place: "table", sentence: "Coco is under the table.", words: ["dog", "under", "table"] },
  };
  const action = actions[destination];
  if (!action) return null;
  action.words.forEach((word) => {
    collectWord(state, story, word, "world_action");
    state.usedWords.add(word);
  });
  state.dogPlace = action.place;
  state.lastSentence = action.sentence;
  state.lastRecast = "";
  logEvent(state, "world_action", { type: "hide_coco", destination, sentence: action.sentence });
  return action;
}

export function startSearchQuest(state, story, destination) {
  const action = performHideChoice(state, story, destination);
  if (!action) return null;
  state.questStage = "search";
  collectWord(state, story, "butterfly", "story_event");
  state.usedWords.add("butterfly");
  logEvent(state, "main_quest_started", { destination });
  return action;
}

function cleanText(value) {
  return value.trim().toLowerCase().replace(/[.!?,;:]+/g, " ").replace(/\s+/g, " ").trim();
}

function hasAny(text, terms) {
  return terms.some((term) => text.includes(term));
}

function findTravelDestination(text) {
  const asksToTravel = hasAny(text, ["go", "visit", "take me", "let's", "lets", "back", "open"]);
  for (const [location, aliases] of Object.entries(LOCATION_ALIASES)) {
    if (aliases.some((alias) => text === alias || text.includes(alias)) && (asksToTravel || text.split(" ").length <= 3)) return location;
  }
  return null;
}

function parseHideCommand(text) {
  const wantsBox = hasAny(` ${text} `, [" in box ", " in the box ", " inside box ", " inside the box ", " into box ", " into the box "]);
  const wantsTable = hasAny(text, ["under table", "under the table", "beneath table", "beneath the table"]);
  if (wantsBox) return "box";
  if (wantsTable) return "table";
  return null;
}

function parseObjectPlacement(text) {
  if (!hasAny(text, ["ball", "red ball", "球"])) return null;
  const underTable = hasAny(text, ["under the table", "under table", "beneath the table", "beneath table"])
    || (hasAny(text, ["桌", "桌子"]) && hasAny(text, ["下面", "下边", "底下", "下"]));
  const onTable = hasAny(text, ["on the table", "on table", "onto the table", "tabletop", "on the desk"])
    || (hasAny(text, ["桌", "桌子"]) && hasAny(text, ["上面", "桌上", "桌子上", "上边"]));
  const inBox = hasAny(text, ["in the box", "in box", "inside the box", "inside box", "into the box"])
    || (hasAny(text, ["盒", "盒子", "箱", "箱子"]) && hasAny(text, ["里面", "里边", "里", "内"]));
  const onFloor = hasAny(text, ["on the floor", "on floor", "to the floor", "on the ground"])
    || hasAny(text, ["地上", "地板上"]);
  if (underTable) return { object: "ball", destination: "table", relation: "under", recast: "Put the ball under the table." };
  if (onTable) return { object: "ball", destination: "table", relation: "on", recast: "Put the ball on the table." };
  if (inBox) return { object: "ball", destination: "box", relation: "in", recast: "Put the ball in the box." };
  if (onFloor) return { object: "ball", destination: "floor", relation: "on", recast: "Put the ball on the floor." };
  return null;
}

export function interpretWorldCommand(state, rawText) {
  const text = cleanText(rawText);
  if (!text) return { understood: false, empty: true, reply: "I didn't hear any words yet." };
  const destination = findTravelDestination(text);
  if (destination) return { understood: true, intent: "travel", destination, text };
  if (hasAny(text, [
    "help", "what can i do", "what should i do", "what do i do", "what do i do next",
    "what now", "where should i go", "where do i go next", "next step", "next task",
    "main story", "story mission", "hint", "我该做什么", "我应该做什么", "接下来做什么",
    "接下来干什么", "下一步", "下一个任务", "主线", "任务是什么", "我该去哪", "怎么玩",
  ])) return { understood: true, intent: "help", text };
  if (hasAny(text, ["pet coco", "pat coco", "hug coco", "stroke coco", "摸摸 coco", "抱抱 coco", "摸 coco", "抱 coco"])) {
    return { understood: true, intent: "greet_coco", gesture: "comfort", text, recast: "Can I gently pet Coco?" };
  }

  if (state.location === "town") {
    if (state.questStage === "search" && hasAny(text, ["blue butterfly", "see butterfly", "follow butterfly", "butterfly trail"])) {
      return { understood: true, intent: "inspect_town_clue", clue: "square", text };
    }
    if (hasAny(text, ["fountain", "water", "coin", "wish"])) return { understood: true, intent: "town_observation", object: "fountain", text };
  }

  if (state.location === "petshop") {
    if (state.questStage === "care" && hasAny(text, ["towel", "dry coco", "dry him", "warm coco", "warm him"])) {
      return { understood: true, intent: "care_coco", care: "towel", text, recast: "Let's dry Coco with a soft towel." };
    }
    const placement = parseObjectPlacement(text);
    if (placement) return { understood: true, intent: "place_object", text, ...placement };
    const hideDestination = parseHideCommand(text);
    if (state.questStage === "meet" && hideDestination) {
      return { understood: true, intent: "hide_coco", destination: hideDestination, text, recast: hideDestination === "box" ? "Coco, hide in the box!" : "Coco, hide under the table!" };
    }
    if (hasAny(text, ["hello", "hi", "hey", "coco", "puppy", "dog"])) return { understood: true, intent: "greet_coco", text };
    if (hasAny(text, ["box", "table", "ball"])) {
      return { understood: true, intent: "name_petshop_object", object: text.includes("box") ? "box" : text.includes("table") ? "table" : "ball", text };
    }
  }

  if (state.location === "bakery") {
    if (state.questStage === "care" && hasAny(text, ["snack for coco", "food for coco", "feed coco", "coco is hungry", "bun for coco", "cake for coco"])) {
      return { understood: true, intent: "care_coco", care: "snack", text, recast: "Let's give Coco a warm snack." };
    }
    if (hasAny(text, ["coco", "dog", "puppy", "seen him", "where is he", "where did he", "orange puppy", "flour print", "flour paw", "paw print", "pawprint"])) return { understood: true, intent: "ask_baker", text };
    const food = hasAny(text, ["cake", "cupcake"]) ? "cake" : hasAny(text, ["bread", "bun"]) ? "bread" : hasAny(text, ["cookie", "biscuit"]) ? "cookie" : null;
    if (food) return { understood: true, intent: "order_food", food, text, recast: `Can I have one ${food}, please?` };
  }

  if (state.location === "school") {
    if (state.questStage === "care" && hasAny(text, ["coco is safe", "coco is okay", "friends", "cheer", "welcome coco", "welcome back", "we found coco"])) {
      return { understood: true, intent: "care_coco", care: "friends", text, recast: "Coco is safe! Welcome back, Coco!" };
    }
    if (hasAny(text, ["coco", "dog", "puppy", "tracks", "prints", "paw", "where did he"])) return { understood: true, intent: "ask_teacher", text };
    const color = ["blue", "red", "yellow", "green"].find((value) => text.includes(value));
    if (color) return { understood: true, intent: "name_color", color, text, recast: `The butterfly is ${color}.` };
  }

  if (state.location === "park") {
    const packedFood = getPackedFood(state);
    if (state.questStage === "care" && packedFood && hasAny(text, ["give coco", "feed coco", "snack", "food", packedFood])) {
      return { understood: true, intent: "care_coco", care: "snack", food: packedFood, text, recast: `Let's give Coco the ${packedFood} Betty packed.` };
    }
    if (state.questStage === "care" && isCaringEnglish(text)) {
      return { understood: true, intent: "greet_coco", gesture: "comfort", text, recast: "Coco, you are safe now. I am here with you." };
    }
    if (state.questStage === "care" && hasAny(text, ["wet", "scared", "afraid", "behind the tree"])) {
      const feelings = [text.includes("wet") ? "wet" : "", hasAny(text, ["scared", "afraid"]) ? "scared" : ""].filter(Boolean).join(" and ");
      return { understood: true, intent: "describe_coco", text, recast: feelings ? `Coco is ${feelings}.` : "Coco is behind the tree." };
    }
    if (text.includes("behind") && text.includes("tree")) return { understood: true, intent: "find_coco", text, recast: "Coco is behind the tree!" };
    if (hasAny(text, ["puddle", "water", "wet"])) return { understood: true, intent: "inspect_clue", clue: "puddle", text };
    if (hasAny(text, ["bush", "sound", "noise", "hear"])) return { understood: true, intent: "inspect_clue", clue: "bush", text };
    if (hasAny(text, ["track", "paw", "print", "trail"])) return { understood: true, intent: "inspect_clue", clue: "tracks", text };
    if (hasAny(text, ["coco", "dog", "puppy", "he", "him"]) && text.includes("tree")) return { understood: true, intent: "clarify_tree", text };
  }

  if (state.location === "storyhouse" && ["home", "complete"].includes(state.questStage) && hasAny(text, ["make my story", "make a story", "open my story", "start my story", "read my story"])) {
    return { understood: true, intent: "open_story", text };
  }

  if (hasAny(text, ["hello", "hi", "hey"])) return { understood: true, intent: "greet", text };
  return { understood: false, text };
}

export function moveWorldObject(state, story, object, destination, relation) {
  const positions = {
    "ball:on:table": { position: "table", sentence: "The ball is on the table.", words: ["ball", "on", "table"] },
    "ball:in:box": { position: "box", sentence: "The ball is in the box.", words: ["ball", "in", "box"] },
    "ball:under:table": { position: "under-table", sentence: "The ball is under the table.", words: ["ball", "under", "table"] },
    "ball:on:floor": { position: "floor", sentence: "The ball is on the floor.", words: ["ball", "on", "floor"] },
  };
  const action = positions[`${object}:${relation}:${destination}`];
  if (!action) return null;
  state.objectPositions ??= {};
  state.objectPositions[object] = action.position;
  for (const item of [...state.sideActivities]) {
    if (item.startsWith(`${object}-at-`)) state.sideActivities.delete(item);
  }
  state.sideActivities.add(`${object}-at-${action.position}`);
  recordMastery(state, "positionWords", relation);
  recordLessonEvidence(state, story, "position-power", `move:${relation}`, { text: action.sentence, support: "guided-action" });
  action.words.forEach((word) => {
    collectWord(state, story, word, "world_action");
    state.usedWords.add(word);
  });
  state.lastSentence = action.sentence;
  state.lastRecast = "";
  logEvent(state, "world_object_moved", { object, destination, relation, position: action.position, sentence: action.sentence });
  return action;
}

export function addClue(state, story, clue) {
  const clueWords = {
    baker: ["butterfly"],
    school: ["tracks"],
    tracks: ["tracks", "park"],
    puddle: ["wet"],
    bush: ["scared", "behind", "tree"],
    square: ["butterfly", "blue"],
    map: ["blue", "behind", "tree", "park"],
  };
  if (!clueWords[clue]) return { added: false, clue };
  const isNew = !state.clues.has(clue);
  state.clues.add(clue);
  if (["tracks", "puddle", "bush"].includes(clue)) recordMastery(state, "parkClues", clue);
  clueWords[clue].forEach((word) => {
    collectWord(state, story, word, "clue");
    state.usedWords.add(word);
  });
  logEvent(state, "clue_found", { clue, isNew, clueCount: state.clues.size });
  return { added: isNew, clue, clueCount: state.clues.size };
}

export function canFindCoco(state) {
  return (state.clues.has("map") && masteryCount(state, "parkClues") >= 2) || (state.questStage === "search" && getAdventureProgress(state).ready);
}

export function packFoodForCoco(state, food) {
  if (!["bread", "cake", "cookie"].includes(food)) return null;
  for (const item of [...state.sideActivities]) {
    if (item.startsWith("packed-")) state.sideActivities.delete(item);
  }
  state.sideActivities.add(`ordered-${food}`);
  state.sideActivities.add(`packed-${food}`);
  recordMastery(state, "manners", "please");
  logEvent(state, "food_packed_for_coco", { food });
  return food;
}

export function getPackedFood(state) {
  return [...state.sideActivities].find((item) => item.startsWith("packed-"))?.replace("packed-", "") ?? null;
}

export function findCoco(state, story, rawText = "Coco is behind the tree.") {
  const text = cleanText(rawText);
  if (!(text.includes("behind") && text.includes("tree"))) return { understood: false };
  ["dog", "behind", "tree", "found"].forEach((word) => {
    collectWord(state, story, word, "free_recall");
    state.usedWords.add(word);
  });
  state.questStage = "care";
  state.dogPlace = "tree";
  state.dogWet = state.clues.has("puddle");
  state.dogScared = state.clues.has("bush");
  state.lastSentence = "Coco is behind the tree!";
  logEvent(state, "coco_found", { text, clues: [...state.clues] });
  return { understood: true, sentence: state.lastSentence };
}

export function completeCare(state, story, care) {
  const packedFood = getPackedFood(state);
  const options = {
    towel: { sentence: "We dried Coco with a soft towel.", words: ["wet", "towel", "safe"] },
    snack: { sentence: packedFood ? `We gave Coco the ${packedFood} Betty packed.` : "We gave Coco a warm snack.", words: ["hungry", "snack", "safe"] },
    friends: { sentence: "Our friends cheered because Coco was safe.", words: ["friends", "safe"] },
  };
  const choice = options[care];
  if (!choice || state.questStage !== "care") return null;
  state.careChoice = care;
  state.questStage = "home";
  state.lastSentence = choice.sentence;
  choice.words.forEach((word) => {
    collectWord(state, story, word, "kindness");
    state.usedWords.add(word);
  });
  logEvent(state, "coco_cared_for", { care, sentence: choice.sentence });
  return choice;
}

export function completeStory(state) {
  if (!['home', 'complete'].includes(state.questStage)) return false;
  if (state.questStage === "home" && !(state.storyEdited?.size > 0)) return false;
  state.questStage = "complete";
  logEvent(state, "main_story_completed", { careChoice: state.careChoice, clues: [...state.clues] });
  return true;
}

export function analyzeStorySentence(line, sceneIndex = 0) {
  const text = cleanText(line);
  return {
    sceneIndex,
    hasText: Boolean(text),
    running: hasAny(text, ["run", "ran", "running", "chased"]),
    inPark: text.includes("park"),
    behindTree: text.includes("behind") && text.includes("tree"),
    size: hasAny(text, ["small", "tiny", "little"]) ? "small" : hasAny(text, ["big", "large"]) ? "big" : "normal",
    wet: text.includes("wet") || text.includes("rain") || text.includes("puddle"),
    scared: hasAny(text, ["scared", "afraid", "shaking"]),
    found: hasAny(text, ["found", "find", "safe"]),
    home: text.includes("home") || text.includes("story house"),
    genericDog: Boolean(text) && hasAny(text, ["dog", "coco", "puppy"]) && !hasAny(text, ["small", "tiny", "little", "big", "wet", "scared", "afraid", "behind", "in the"]),
  };
}

function includesWholeWord(text, word) {
  const escaped = word.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return new RegExp(`(^|\\s)${escaped}(?=\\s|$)`, "i").test(cleanText(text));
}

export function isMeaningfulStoryRevision(draft, nextLine) {
  const draftWords = englishWords(draft);
  const nextWords = englishWords(nextLine);
  if (nextWords.length < 3 || cleanText(draft) === cleanText(nextLine)) return false;
  const counts = (words) => words.reduce((result, word) => result.set(word, (result.get(word) ?? 0) + 1), new Map());
  const before = counts(draftWords);
  const after = counts(nextWords);
  const vocabulary = new Set([...before.keys(), ...after.keys()]);
  const changedWords = [...vocabulary].reduce((total, word) => total + Math.abs((before.get(word) ?? 0) - (after.get(word) ?? 0)), 0);
  return changedWords >= 3;
}

export function saveStoryLine(state, story, index, line) {
  const cleanLine = line.trim();
  const previous = state.storyLines[index];
  const visual = analyzeStorySentence(cleanLine, index);
  state.storyLines[index] = cleanLine;
  state.storyVisuals[index] = visual;
  state.storyPlayed.add(index);
  state.storyEdited ??= new Set();
  if (isMeaningfulStoryRevision(state.storyDraftLines?.[index] ?? "", cleanLine)) state.storyEdited.add(index);
  else state.storyEdited.delete(index);
  if (state.storyEdited.size) state.storyNeedsWriting = false;
  if (previous && previous !== cleanLine) {
    state.revisionCount += 1;
    logEvent(state, "story_sentence_revised", { index, before: previous, after: cleanLine });
  } else {
    logEvent(state, "story_sentence_played", { index, sentence: cleanLine });
  }
  for (const word of Object.keys(story.vocabulary)) {
    if (includesWholeWord(cleanLine, word)) {
      collectWord(state, story, word, "writing");
      state.usedWords.add(word);
    }
  }
  return visual;
}

export function writingFeedback(story, line, visual, index) {
  if (!line) return "Your adventure has already made a first draft. Change any detail you like.";
  const expectations = [visual.running, visual.inPark || /ask|look|track/i.test(line), visual.behindTree || visual.wet || visual.scared, visual.found || visual.home];
  if (!expectations[index]) {
    return ["What made Coco leave? Try ran, chased, or butterfly.", "Add one place or clue from your search.", "Add where Coco was, or what he looked like.", "Tell us how Coco became safe or went home."][index];
  }
  return "That matches your adventure. Play it to see the picture respond.";
}

export function buildStoryDrafts(state) {
  const rememberedWords = (stage) => (state.learnerContributions ?? []).find((item) => item.stage === stage)?.text;
  const asSentence = (value) => value ? `${value.charAt(0).toUpperCase()}${value.slice(1).replace(/[.!?]+$/, "")}.` : "";
  const searchDetails = [];
  if (state.clues.has("baker")) searchDetails.push(state.sideActivities.has("bakery-flour-print") ? "followed a floury paw print at the bakery" : "asked the baker for help");
  if (state.clues.has("school")) searchDetails.push(state.sideActivities.has("school-chalk-trail") ? "found a chalk paw trail at school" : "talked to the teacher");
  const orderedFood = [...state.sideActivities].find((item) => item.startsWith("ordered-"))?.replace("ordered-", "");
  const packedFood = getPackedFood(state);
  if (packedFood) searchDetails.push(`packed a ${packedFood} for Coco`);
  else if (orderedFood) searchDetails.push(`bought a ${orderedFood}`);
  if (state.clues.has("map")) searchDetails.push("used the school's blue trail map");
  if (state.clues.has("tracks")) searchDetails.push("followed Coco's tracks");
  if (state.clues.has("square")) searchDetails.push("followed the blue butterfly through town");
  if (state.sideActivities.has("color-blue")) searchDetails.push("named the blue butterfly at school");
  const remembered = searchDetails.slice(0, 4);
  const joinedDetails = remembered.length > 1 ? `${remembered.slice(0, -1).join(", ")} and ${remembered.at(-1)}` : remembered[0];
  const searchAction = joinedDetails ? `I ${joinedDetails} on the way to the park.` : "I looked for Coco all around Magic English Town.";
  const searchWords = asSentence(rememberedWords("search"));
  const searchLine = searchWords ? `I asked, “${searchWords}” ${searchAction}` : searchAction;
  const details = ["small", state.clues.has("puddle") ? "wet" : "", state.clues.has("bush") ? "scared" : ""].filter(Boolean).join(" ");
  const endingAction = {
    towel: "I dried Coco with a soft towel, and we went home together.",
    snack: packedFood ? `I gave Coco the ${packedFood} Betty packed, and we went home together.` : "I gave Coco a warm snack, and we went home together.",
    friends: "Our friends cheered for Coco, and we went home together.",
  }[state.careChoice] ?? "Finally, I found Coco and we went home together.";
  const meetWords = asSentence(rememberedWords("meet"));
  const careWords = asSentence(rememberedWords("care"));
  const opening = meetWords ? `I said, “${meetWords}” Then Coco chased a blue butterfly out of the Pet Shop.` : "Coco chased a blue butterfly out of the Pet Shop.";
  const ending = careWords ? `I said, “${careWords}” ${endingAction}` : endingAction;
  const drafts = [opening, searchLine, `I found a ${details} dog behind the old tree.`, ending];
  state.storyLines = drafts;
  state.storyDraftLines = [...drafts];
  state.storyEdited = new Set();
  state.storyNeedsWriting = false;
  state.storyVisuals = drafts.map((line, index) => analyzeStorySentence(line, index));
  state.storyPlayed = new Set();
  state.currentStoryStep = 0;
  logEvent(state, "story_draft_created", { clues: [...state.clues], activities: [...state.sideActivities] });
  return drafts;
}
