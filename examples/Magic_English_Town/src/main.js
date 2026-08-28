import "./style.css";
import "./moonlight.css";
import "./lesson-dock.css";
import "./course-stars.css";
import "./ui-scale.css";
import { clearLessonMemory } from "./core/course-memory.js";
import { renderCourseHub } from "./course-hub.js";
import { getStory, listStories } from "./stories/index.js";
import { createStoryGame } from "./runtimes/index.js";

const params = new URLSearchParams(window.location.search);
const root = document.querySelector("#app");
const storyId = params.get("story");
const story = storyId ? getStory(storyId) : null;
const platformKey = "magic-english-town:wesmartflow-entry";

try {
  if (params.get("source") === "wesmartflow") sessionStorage.setItem(platformKey, "1");
} catch { /* Storage can be unavailable in privacy mode. */ }

if (story && params.get("restart") === "1") {
  clearLessonMemory(story.id);
  params.delete("restart");
  const cleanQuery = params.toString();
  window.history?.replaceState?.({}, "", `${window.location.pathname}${cleanQuery ? `?${cleanQuery}` : ""}`);
}

let platformHref = "";
try { platformHref = sessionStorage.getItem(platformKey) ? "/#/explore" : ""; } catch { /* Use the standalone course hub. */ }

if (!story) renderCourseHub(root, listStories(), { platformHref });
else createStoryGame({ root, story }).render();
