import { createMagicTownApp } from "../app.js";
import { createMoonlightFestivalApp } from "./moonlight-festival.js";

const runtimes = new Map([
  ["magic-town-v1", createMagicTownApp],
  ["moonlight-festival-v1", createMoonlightFestivalApp],
]);

export function createStoryGame({ root, story }) {
  const createRuntime = runtimes.get(story.runtime);
  if (!createRuntime) throw new Error(`Unknown story runtime: ${story.runtime}`);
  return createRuntime({ root, story });
}

export function listStoryRuntimes() {
  return [...runtimes.keys()];
}
