import { missingPuppyStory } from "./missing-puppy.js";
import { moonlightFestivalStory } from "./moonlight-festival.js";
import { createStoryRegistry } from "../story-kit/story-registry.js";

const storyRegistry = createStoryRegistry([missingPuppyStory, moonlightFestivalStory], missingPuppyStory.id);

const defaultStoryId = storyRegistry.defaultStoryId;

export function getStory(storyId = defaultStoryId) {
  return storyRegistry.get(storyId);
}

export const listStories = () => storyRegistry.list();
