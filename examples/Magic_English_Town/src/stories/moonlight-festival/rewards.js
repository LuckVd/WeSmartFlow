export function applyMoonlightFestivalReward(state, _story, challengeId) {
  state.learning ??= {};
  state.learning.completed ??= new Set();
  if (state.learning.completed.has(challengeId)) return false;
  state.stars = (state.stars ?? 0) + 2;
  return true;
}
