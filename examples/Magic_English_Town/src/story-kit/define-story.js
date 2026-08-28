const STORY_ID = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;
const QUESTION_TYPES = new Set(["choice", "fill", "dialogue", "description"]);

function invariant(condition, message) {
  if (!condition) throw new Error(`Invalid story package: ${message}`);
}

function validateChallenges(challenges) {
  invariant(challenges && typeof challenges === "object", "learning.challenges is required");
  for (const [id, challenge] of Object.entries(challenges)) {
    invariant(STORY_ID.test(id), `challenge id “${id}” must use kebab-case`);
    invariant(challenge?.title && challenge?.reward, `challenge “${id}” needs title and reward`);
    invariant(Array.isArray(challenge.questions) && challenge.questions.length > 0, `challenge “${id}” needs questions`);
    challenge.questions.forEach((question, index) => {
      invariant(QUESTION_TYPES.has(question.type), `challenge “${id}” question ${index + 1} has an unsupported type`);
      invariant(question.prompt, `challenge “${id}” question ${index + 1} needs a prompt`);
    });
  }
}

function validateOutcomes(outcomes = []) {
  invariant(Array.isArray(outcomes), "learning.outcomes must be an array");
  const ids = new Set();
  outcomes.forEach((outcome, index) => {
    invariant(STORY_ID.test(outcome?.id || ""), `learning outcome ${index + 1} needs a kebab-case id`);
    invariant(!ids.has(outcome.id), `learning outcome id “${outcome.id}” is duplicated`);
    ids.add(outcome.id);
    invariant(outcome.icon && outcome.title && outcome.canDo && outcome.reviewPrompt, `learning outcome “${outcome.id}” needs icon, title, canDo, and reviewPrompt`);
    invariant(Array.isArray(outcome.criteria) && outcome.criteria.length > 0, `learning outcome “${outcome.id}” needs criteria`);
    outcome.criteria.forEach((criterion, criterionIndex) => {
      invariant(criterion?.prefix && Number.isInteger(criterion.required) && criterion.required > 0, `learning outcome “${outcome.id}” criterion ${criterionIndex + 1} needs prefix and a positive required count`);
    });
  });
}

export function defineStory(definition) {
  invariant(definition && typeof definition === "object", "definition is required");
  invariant(STORY_ID.test(definition.id || ""), "id must use kebab-case");
  invariant(definition.runtime, "runtime is required");
  invariant(definition.title, "title is required");
  invariant(definition.version >= 1, "version must be at least 1");
  invariant(definition.vocabulary && Object.keys(definition.vocabulary).length > 0, "vocabulary is required");
  invariant(Array.isArray(definition.writing?.scenes) && definition.writing.scenes.length > 0, "writing.scenes is required");
  validateOutcomes(definition.learning?.outcomes);
  validateChallenges(definition.learning?.challenges);
  invariant(typeof definition.learning?.applyReward === "function", "learning.applyReward is required");

  return Object.freeze({
    author: "Magic English Town",
    description: "",
    progression: {},
    agent: {},
    ...definition,
  });
}

export function storySummary(story) {
  return {
    id: story.id,
    title: story.title,
    author: story.author,
    description: story.description,
    runtime: story.runtime,
    version: story.version,
    course: story.course ?? null,
  };
}
