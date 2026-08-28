function collectionHas(value, expected) {
  if (value instanceof Set) return value.has(expected);
  if (Array.isArray(value)) return value.includes(expected);
  return false;
}

function stageIndex(state, stage) {
  const stages = state.storyStages ?? state.progression?.stages ?? [];
  return stages.indexOf(stage);
}

function currentStage(state) {
  return state.questStage ?? state.phase ?? "";
}

function conditionMet(state, condition = {}) {
  if (condition.stageAtLeast) {
    const wanted = stageIndex(state, condition.stageAtLeast);
    const current = stageIndex(state, currentStage(state));
    return wanted >= 0 && current >= wanted;
  }
  if (condition.set && condition.has !== undefined) return collectionHas(state[condition.set], condition.has);
  if (condition.field) return state[condition.field] === condition.equals;
  return false;
}

function ruleMet(state, rule = {}) {
  if (rule.fromStage && !conditionMet(state, { stageAtLeast: rule.fromStage })) return false;
  if (rule.stages && !rule.stages.includes(currentStage(state))) return false;
  if (rule.allOf && !rule.allOf.every((condition) => conditionMet(state, condition))) return false;
  if (rule.anyOf && !rule.anyOf.some((condition) => conditionMet(state, condition))) return false;
  return true;
}

export function getSceneAccess(state, location) {
  const rule = state.sceneUnlocks?.[location];
  if (!rule || ruleMet(state, rule)) return { unlocked: true, reason: "" };
  return {
    unlocked: false,
    reason: rule.lockedHint || "Continue the main story to unlock this place.",
  };
}

export function getChallengeAccess(story, state, challengeId) {
  const rule = story.learning?.challengeUnlocks?.[challengeId];
  if (!rule) return { unlocked: true, reason: "" };
  const scene = rule.location ? getSceneAccess(state, rule.location) : { unlocked: true, reason: "" };
  if (!scene.unlocked) return scene;
  if (ruleMet(state, rule)) return { unlocked: true, reason: "" };
  return {
    unlocked: false,
    reason: rule.lockedHint || "Finish the current main-story step first.",
  };
}

export function firstUnlockedLocation(state, preferred = "town") {
  if (getSceneAccess(state, preferred).unlocked) return preferred;
  return Object.keys(state.sceneUnlocks ?? {}).find((location) => getSceneAccess(state, location).unlocked) ?? "town";
}
