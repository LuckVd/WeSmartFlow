import { getCourseStarsForLesson } from "./course-stars.js";
import { firstUnlockedLocation } from "./scene-unlocks.js";

const STORAGE_KEY = "magic-english-town:course-memory:v1";

function storageOrNull(storage) {
  if (storage) return storage;
  if (typeof window === "undefined") return null;
  try { return window.localStorage; } catch { return null; }
}

export function readCourseMemory(storage = null) {
  const target = storageOrNull(storage);
  if (!target) return { lessons: {} };
  try {
    const value = JSON.parse(target.getItem(STORAGE_KEY) || "{}");
    return value && typeof value === "object" && value.lessons && typeof value.lessons === "object" ? value : { lessons: {} };
  } catch {
    return { lessons: {} };
  }
}

export function saveLessonMemory(lessonId, memory, storage = null) {
  const target = storageOrNull(storage);
  const course = readCourseMemory(target);
  course.lessons[lessonId] = { ...(course.lessons[lessonId] ?? {}), ...memory, updatedAt: Date.now() };
  if (target) target.setItem(STORAGE_KEY, JSON.stringify(course));
  return course.lessons[lessonId];
}

export function getLessonMemory(lessonId, storage = null) {
  return readCourseMemory(storage).lessons[lessonId] ?? null;
}

export function clearLessonMemory(lessonId, storage = null) {
  const target = storageOrNull(storage);
  const course = readCourseMemory(target);
  if (!Object.prototype.hasOwnProperty.call(course.lessons, lessonId)) return false;
  delete course.lessons[lessonId];
  if (target) target.setItem(STORAGE_KEY, JSON.stringify(course));
  return true;
}

function list(value) {
  return Array.isArray(value) ? value : [];
}

function items(value) {
  return value && typeof value[Symbol.iterator] === "function" ? [...value] : [];
}

function setMap(value, keys) {
  return Object.fromEntries(keys.map((key) => [key, list(value?.[key])]));
}

function restoreSetMap(target, saved) {
  Object.keys(target ?? {}).forEach((key) => { target[key] = new Set(list(saved?.[key])); });
}

export function buildMissingPuppyMemory(state) {
  const firstStage = state.progression?.stages?.[0] ?? "meet";
  const hasProgress = state.questStage !== firstStage
    || items(state.visited).length > 1
    || items(state.clues).length > 0
    || (state.adventureScore ?? 0) > 0
    || (state.learnerContributions?.length ?? 0) > 0
    || items(state.sideActivities).length > 0
    || (state.storyLines ?? []).some(Boolean);
  return {
    complete: state.questStage === "complete",
    courseStars: getCourseStarsForLesson("missing-puppy", state),
    careChoice: state.careChoice ?? null,
    visited: items(state.visited),
    usedWords: items(state.usedWords).slice(0, 20),
    childLines: items(state.storyLines).filter(Boolean).slice(0, 4),
    englishTurns: (state.learnerContributions ?? []).map((item) => item.text).filter(Boolean).slice(-8),
    stars: state.adventureScore ?? 0,
    resume: {
      version: 1,
      hasProgress,
      scene: state.scene,
      location: state.location,
      questStage: state.questStage,
      careChoice: state.careChoice,
      clues: items(state.clues),
      visited: items(state.visited),
      discoveries: items(state.discoveries),
      sideActivities: items(state.sideActivities),
      adventurePoints: { ...state.adventurePoints },
      adventureScore: state.adventureScore,
      pointRewards: items(state.pointRewards),
      learnerContributions: (state.learnerContributions ?? []).slice(-30),
      lessonEvidence: setMap(state.lessonEvidence, Object.keys(state.lessonEvidence ?? {})),
      lessonSamples: { ...state.lessonSamples },
      careOptions: items(state.careOptions),
      objectPositions: { ...state.objectPositions },
      mastery: setMap(state.mastery, Object.keys(state.mastery ?? {})),
      discovered: items(state.discovered),
      usedWords: items(state.usedWords),
      wordEvidence: { ...state.wordEvidence },
      learningCompleted: items(state.learning?.completed),
      dogPlace: state.dogPlace,
      dogSize: state.dogSize,
      dogWet: state.dogWet,
      dogScared: state.dogScared,
      storyLines: items(state.storyLines),
      storyDraftLines: items(state.storyDraftLines),
      storyEdited: items(state.storyEdited),
      storyVisuals: state.storyVisuals ?? [],
      storyPlayed: items(state.storyPlayed),
      currentStoryStep: state.currentStoryStep,
      bookPage: state.bookPage,
      revisionCount: state.revisionCount,
    },
  };
}

export function restoreMissingPuppyMemory(state, memory) {
  const saved = memory?.resume;
  if (!saved?.hasProgress) return state;
  const scalarKeys = ["scene", "location", "questStage", "careChoice", "adventureScore", "dogPlace", "dogSize", "dogWet", "dogScared", "currentStoryStep", "bookPage", "revisionCount"];
  scalarKeys.forEach((key) => { if (saved[key] !== undefined) state[key] = saved[key]; });
  ["clues", "visited", "discoveries", "sideActivities", "pointRewards", "careOptions", "discovered", "usedWords", "storyEdited", "storyPlayed"].forEach((key) => {
    state[key] = new Set(list(saved[key]));
  });
  state.adventurePoints = { ...state.adventurePoints, ...(saved.adventurePoints ?? {}) };
  state.learnerContributions = list(saved.learnerContributions).slice(-30);
  restoreSetMap(state.lessonEvidence, saved.lessonEvidence);
  state.lessonSamples = { ...state.lessonSamples, ...(saved.lessonSamples ?? {}) };
  state.objectPositions = { ...state.objectPositions, ...(saved.objectPositions ?? {}) };
  restoreSetMap(state.mastery, saved.mastery);
  state.wordEvidence = { ...(saved.wordEvidence ?? {}) };
  state.learning.completed = new Set(list(saved.learningCompleted));
  state.learning.activeId = null;
  state.learning.feedback = null;
  state.storyLines = list(saved.storyLines).length === state.storyLines.length ? [...saved.storyLines] : state.storyLines;
  state.storyDraftLines = list(saved.storyDraftLines).length === state.storyDraftLines.length ? [...saved.storyDraftLines] : state.storyDraftLines;
  state.storyVisuals = list(saved.storyVisuals).length === state.storyVisuals.length ? saved.storyVisuals : state.storyVisuals;
  state.busy = false;
  state.wordPocketOpen = false;
  state.explorationOpen = false;
  state.storyBeatOpen = false;
  state.coachOpen = false;
  state.easterEggOpen = null;
  state.location = firstUnlockedLocation(state, state.location);
  state.guide = {
    speaker: "Milo",
    text: "Welcome back—your place in the adventure was saved.",
    hint: "Continue from here, or choose another place in town.",
    tone: "welcome",
  };
  return state;
}

export function buildMoonlightFestivalMemory(state) {
  const complete = state.phase === "celebration" && Boolean(state.memoryBookComplete);
  return {
    complete,
    courseStars: getCourseStarsForLesson("moonlight-festival", state),
    treats: { ...state.treats },
    flag: { ...state.flag },
    invited: [...state.invited],
    finalInstruction: state.finalInstruction,
    englishTurns: state.englishTurns.map((item) => item.text).slice(-10),
    surprisesFound: [...state.surprisesFound],
    stars: state.stars,
    resume: {
      version: 1,
      hasProgress: state.phase !== "bridge",
      phase: state.phase,
      location: state.location,
      time: state.time,
      completedTasks: [...state.completedTasks],
      visited: [...state.visited],
      englishTurns: state.englishTurns.slice(-30),
      evidence: setMap(state.evidence, Object.keys(state.evidence)),
      samples: { ...state.samples },
      stars: state.stars,
      treats: { ...state.treats },
      flag: { ...state.flag },
      fireflies: [...state.fireflies],
      surprisesFound: [...state.surprisesFound],
      learningCompleted: items(state.learning?.completed),
      selectedInvitee: state.selectedInvitee,
      invited: [...state.invited],
      finalInstruction: state.finalInstruction,
      memoryStep: state.memoryStep,
      memoryDraftLines: items(state.memoryDraftLines),
      memoryLines: items(state.memoryLines),
      memoryEdited: items(state.memoryEdited),
      memoryBookComplete: Boolean(state.memoryBookComplete),
    },
  };
}

export function restoreMoonlightFestivalMemory(state, memory) {
  const saved = memory?.resume;
  if (!saved?.hasProgress) return state;
  ["phase", "location", "time", "stars", "selectedInvitee", "finalInstruction", "memoryStep", "memoryBookComplete"].forEach((key) => {
    if (saved[key] !== undefined) state[key] = saved[key];
  });
  ["completedTasks", "visited", "fireflies", "surprisesFound", "invited"].forEach((key) => {
    state[key] = new Set(list(saved[key]));
  });
  state.englishTurns = list(saved.englishTurns).slice(-30);
  restoreSetMap(state.evidence, saved.evidence);
  state.samples = { ...state.samples, ...(saved.samples ?? {}) };
  state.treats = { ...state.treats, ...(saved.treats ?? {}) };
  state.flag = { ...state.flag, ...(saved.flag ?? {}) };
  state.learning.completed = new Set(list(saved.learningCompleted));
  const savedMemoryDrafts = list(saved.memoryDraftLines);
  const savedMemoryLines = list(saved.memoryLines);
  if (savedMemoryDrafts.length) state.memoryDraftLines = Array.from({ length: state.memoryDraftLines.length }, (_, index) => savedMemoryDrafts[index] ?? "");
  if (savedMemoryLines.length) state.memoryLines = Array.from({ length: state.memoryLines.length }, (_, index) => savedMemoryLines[index] ?? "");
  state.memoryEdited = new Set(list(saved.memoryEdited));
  state.learning.activeId = null;
  state.learning.feedback = null;
  state.learning.correct = false;
  state.learning.finished = false;
  state.busy = false;
  state.location = firstUnlockedLocation(state, state.location);
  state.guide = {
    speaker: "Milo",
    reply: "Welcome back—your Moonlight Festival progress was saved.",
    hint: "Continue from here, or revisit any place in town.",
  };
  return state;
}
