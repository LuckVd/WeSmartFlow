import { storySummary } from "./define-story.js";

export function createStoryRegistry(storyPackages, defaultStoryId) {
  const byId = new Map();
  for (const story of storyPackages) {
    if (byId.has(story.id)) throw new Error(`Duplicate story id: ${story.id}`);
    byId.set(story.id, story);
  }
  if (!byId.has(defaultStoryId)) throw new Error(`Unknown default story: ${defaultStoryId}`);

  return Object.freeze({
    defaultStoryId,
    get(storyId = defaultStoryId) { return byId.get(storyId) ?? byId.get(defaultStoryId); },
    has(storyId) { return byId.has(storyId); },
    list() { return [...byId.values()].map(storySummary); },
  });
}
