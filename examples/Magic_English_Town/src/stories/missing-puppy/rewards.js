import {
  addClue,
  awardAdventurePoints,
  collectWord,
  moveWorldObject,
  packFoodForCoco,
  recordMastery,
} from "../../core/story-engine.js";

export function applyMissingPuppyChallengeReward(state, story, id) {
  if (id === "town-guide") {
    state.sideActivities.add("town-guide");
    ["fountain", "park"].forEach((word) => collectWord(state, story, word, "assessment"));
  }
  if (id === "position-practice") {
    moveWorldObject(state, story, "ball", "table", "on");
    moveWorldObject(state, story, "ball", "box", "in");
  }
  if (id === "meet-coco") ["dog", "in", "box"].forEach((word) => collectWord(state, story, word, "assessment"));
  if (id === "bakery-clue") {
    addClue(state, story, "baker");
    state.sideActivities.add("bakery-flour-print");
    collectWord(state, story, "tracks", "assessment");
  }
  if (id === "bakery-food") {
    collectWord(state, story, "cake", "assessment");
    state.usedWords.add("cake");
    packFoodForCoco(state, "cake");
  }
  if (id === "school-clue") {
    addClue(state, story, "school");
    state.sideActivities.add("school-chalk-trail");
  }
  if (id === "school-map") {
    recordMastery(state, "colors", "blue");
    recordMastery(state, "colors", "red");
    state.sideActivities.add("color-blue");
    addClue(state, story, "map");
  }
  if (id === "park-investigation") {
    addClue(state, story, "tracks");
    addClue(state, story, "puddle");
  }
  if (id === "find-coco") ["behind", "tree"].forEach((word) => collectWord(state, story, word, "assessment"));
  if (id === "care-coco-food") state.careOptions.add("snack");
  if (id === "care-coco-towel") state.careOptions.add("towel");
  if (id === "make-story") {
    ["safe", "home"].forEach((word) => {
      collectWord(state, story, word, "assessment");
      state.usedWords.add(word);
    });
  }
  if (id === "story-memory") {
    state.sideActivities.add("story-memory");
    ["safe", "home"].forEach((word) => {
      collectWord(state, story, word, "assessment");
      state.usedWords.add(word);
    });
  }
  awardAdventurePoints(state, `english-challenge:${id}`, id.startsWith("care-coco") ? 1 : 2);
  return true;
}
