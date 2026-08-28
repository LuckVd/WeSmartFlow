import { getChallengeAccess } from "./scene-unlocks.js";

const normalize = (value) => String(value ?? "")
  .trim()
  .toLowerCase()
  .replace(/[.!?,;:'"]/g, " ")
  .replace(/\s+/g, " ")
  .trim();

function editDistance(left, right) {
  const previous = Array.from({ length: right.length + 1 }, (_, index) => index);
  for (let leftIndex = 1; leftIndex <= left.length; leftIndex += 1) {
    let diagonal = previous[0];
    previous[0] = leftIndex;
    for (let rightIndex = 1; rightIndex <= right.length; rightIndex += 1) {
      const above = previous[rightIndex];
      previous[rightIndex] = left[leftIndex - 1] === right[rightIndex - 1]
        ? diagonal
        : Math.min(diagonal, above, previous[rightIndex - 1]) + 1;
      diagonal = above;
    }
  }
  return previous[right.length];
}

const SPOKEN_ALIASES = new Map([
  ["too", "to"],
  ["two", "to"],
  ["won", "one"],
  ["read", "red"],
  ["blew", "blue"],
  ["inn", "in"],
]);

const MEANING_FAMILIES = [
  ["put", "place", "move"],
  ["give", "share", "feed"],
  ["snack", "food", "treat"],
  ["coco", "dog", "puppy"],
  ["dry", "warm"],
  ["behind", "back"],
  ["go", "visit"],
  ["find", "found"],
];

function canonicalSpokenWord(word) {
  return SPOKEN_ALIASES.get(word) ?? word;
}

function sameMeaningFamily(left, right) {
  return MEANING_FAMILIES.some((family) => family.includes(left) && family.includes(right));
}

function lightlyStem(word) {
  if (word.length > 5 && word.endsWith("ing")) return word.slice(0, -3);
  if (word.length > 4 && word.endsWith("ed")) return word.slice(0, -2);
  if (word.length > 4 && word.endsWith("es")) return word.slice(0, -2);
  if (word.length > 3 && word.endsWith("s")) return word.slice(0, -1);
  return word;
}

function wordsAreClose(rawToken, rawExpected) {
  const token = canonicalSpokenWord(rawToken);
  const expected = canonicalSpokenWord(rawExpected);
  if (token === expected || sameMeaningFamily(token, expected)) return true;
  if (lightlyStem(token) === lightlyStem(expected)) return true;
  return Math.max(token.length, expected.length) >= 4
    && Math.min(token.length, expected.length) >= 3
    && editDistance(token, expected) <= 1;
}

function answerMatchesMeaning(answer, expected) {
  const normalizedExpected = normalize(expected);
  if (!normalizedExpected) return false;
  if (normalizedExpected.includes(" ")) return ` ${answer} `.includes(` ${normalizedExpected} `);
  return answer.split(" ").some((token) => wordsAreClose(token, normalizedExpected));
}

export function getLearningChallenge(story, id) {
  return story?.learning?.challenges?.[id] ?? null;
}

export function checkLearningAnswer(question, rawAnswer) {
  const answer = normalize(rawAnswer);
  if (!answer) return { correct: false, empty: true };
  if (["description", "dialogue"].includes(question.type)) {
    const groupMatches = question.requiredGroups.map((group) => group.some((word) => answerMatchesMeaning(answer, word)));
    const matchedGroups = groupMatches.filter(Boolean).length;
    const requiredGroups = question.requiredGroups.length;
    const minimumGroups = question.type === "dialogue" && requiredGroups >= 3 ? requiredGroups - 1 : requiredGroups;
    const correct = matchedGroups >= minimumGroups;
    return { correct, answer, matchedGroups, requiredGroups, partialAccepted: correct && matchedGroups < requiredGroups };
  }
  const exactAnswer = question.answers.find((expected) => normalize(expected) === answer);
  if (exactAnswer) return { correct: true, answer };
  if (question.type === "fill" && !answer.includes(" ")) {
    const correctedTo = question.answers
      .map((expected) => normalize(expected))
      .find((expected) => expected.length >= 4 && !expected.includes(" ") && editDistance(answer, expected) === 1);
    if (correctedTo) return { correct: true, answer, correctedTo };
  }
  return { correct: false, answer };
}

export function resolveSpokenLearningAnswer(question, rawAnswer) {
  const spoken = normalize(rawAnswer);
  if (!spoken || !question) return rawAnswer;
  if (question.type === "choice" && Array.isArray(question.options)) {
    const directOption = question.options.find((option) => {
      const normalizedOption = normalize(option);
      return spoken === normalizedOption || ` ${spoken} `.includes(` ${normalizedOption} `);
    });
    if (directOption) return directOption;
    const choices = [
      ["a", "option a", "answer a", "i choose a", "first", "first one", "number one", "1", "第一个", "选 a", "选a"],
      ["b", "option b", "answer b", "i choose b", "second", "second one", "number two", "2", "第二个", "选 b", "选b"],
      ["c", "option c", "answer c", "i choose c", "third", "third one", "number three", "3", "第三个", "选 c", "选c"],
    ];
    const optionIndex = choices.findIndex((phrases) => phrases.includes(spoken));
    return optionIndex >= 0 && question.options[optionIndex] ? question.options[optionIndex] : rawAnswer;
  }
  if (question.type === "fill" && Array.isArray(question.answers)) {
    const tokens = spoken.split(" ");
    const matchedAnswer = question.answers.find((expected) => {
      const normalizedExpected = normalize(expected);
      if (` ${spoken} `.includes(` ${normalizedExpected} `)) return true;
      return !normalizedExpected.includes(" ") && tokens.some((token) => wordsAreClose(token, normalizedExpected));
    });
    if (matchedAnswer) return normalize(matchedAnswer);
  }
  return rawAnswer;
}

export function applyLearningChallengeReward(state, story, id) {
  if (!getLearningChallenge(story, id) || state.learning.completed.has(id)) return false;
  if (!getChallengeAccess(story, state, id).unlocked) return false;
  const applied = story.learning.applyReward(state, story, id);
  if (applied === false) return false;
  state.learning.completed.add(id);
  return true;
}
