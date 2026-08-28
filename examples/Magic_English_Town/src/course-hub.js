import { escapeHtml } from "./core/browser.js";
import { getLessonMemory } from "./core/course-memory.js";
import { getCourseStarsForLesson, renderCourseCompletion } from "./core/course-stars.js";

const COURSE_ART = {
  "missing-puppy": { number: "01", icon: "🐾", color: "mint", label: "A daytime search" },
  "moonlight-festival": { number: "02", icon: "🌙", color: "violet", label: "An evening celebration" },
};

const PLACE_NAMES = {
  town: "Town Square",
  petshop: "Pet Shop",
  bakery: "Moonbeam Bakery",
  school: "Star School",
  park: "Whispering Park",
  storyhouse: "Story House",
};

function savedProgress(story, memory) {
  const resume = memory?.resume;
  if (!resume?.hasProgress || memory?.complete) return null;
  const place = PLACE_NAMES[resume.location] ?? "the town";
  if (story.id === "moonlight-festival") {
    const count = Array.isArray(resume.completedTasks) ? resume.completedTasks.length : 0;
    return { icon: "☾", title: "Your festival progress is saved", detail: `${count}/3 town magics · Continue at ${place}` };
  }
  return { icon: "✦", title: "Your adventure is saved", detail: `Continue from ${place}` };
}

export function renderCourseHub(root, stories, { platformHref = "" } = {}) {
  const lessonOne = getLessonMemory("missing-puppy");
  root.innerHTML = `
    <main class="course-hub">
      <div class="hub-sky"><i></i><i></i><i></i><span class="hub-moon"></span></div>
      <header class="hub-header">
        <div class="hub-brand"><span>✦</span><div><small>SEASON ONE</small><strong>Magic English Town</strong></div></div>
        ${platformHref ? `<a class="hub-platform-back" href="${platformHref}">← Back to WeSmartFlow Explore</a>` : ""}
      </header>
      <section class="hub-intro">
        <p>YOUR LIVING ENGLISH WORLD</p>
        <h1>Every lesson becomes<br />part of the same town.</h1>
        <span>Explore the world, speak with Agent friends, create stories, and return to characters who remember you.</span>
      </section>
      <section class="lesson-road" aria-label="Season one lessons">
        ${stories.map((story, index) => {
          const art = COURSE_ART[story.id] ?? { number: String(index + 1).padStart(2, "0"), icon: "✦", color: "violet", label: "A new adventure" };
          const course = story.course ?? {};
          const memory = getLessonMemory(story.id);
          const saved = savedProgress(story, memory);
          const continued = story.id === "moonlight-festival" && lessonOne?.complete;
          const hasMemory = Boolean(memory?.resume?.hasProgress || memory?.complete);
          const courseStars = memory?.complete ? getCourseStarsForLesson(story, memory) : 0;
          const continueLabel = memory?.complete ? "Continue exploring" : saved ? "Continue adventure" : continued ? "Continue with Coco" : "Start lesson";
          return `<article class="lesson-card tone-${art.color} ${memory?.complete ? "is-complete" : ""}">
            <div class="lesson-card-art"><span>${art.icon}</span><i></i><i></i><small>${art.label}</small></div>
            <div class="lesson-card-copy">
              <p>LESSON ${course.lesson ?? index + 1} · ${escapeHtml(course.theme ?? "Explore with English")}</p>
              <h2>${escapeHtml(course.shortTitle ?? story.title)}</h2>
              <span>${escapeHtml(story.description)}</span>
              ${memory?.complete ? renderCourseCompletion({ earned: courseStars, className: "lesson-completion-status compact", size: "small" }) : ""}
              ${saved ? `<div class="memory-thread saved-thread"><b>${saved.icon}</b><p><strong>${saved.title}</strong><small>${escapeHtml(saved.detail)}</small></p></div>` : continued ? `<div class="memory-thread"><b>🐶</b><p><strong>Coco remembers Lesson 1</strong><small>Your choices will follow you into the evening town.</small></p></div>` : ""}
              <div class="lesson-card-actions">
                <a class="lesson-continue" href="?story=${encodeURIComponent(story.id)}"><span>${continueLabel}</span><b>→</b></a>
                <a class="lesson-restart" href="?story=${encodeURIComponent(story.id)}&restart=1" data-restart-lesson="${escapeHtml(course.shortTitle ?? story.title)}"><span>${hasMemory ? "Restart lesson" : "Start from beginning"}</span><b>↺</b></a>
              </div>
            </div>
            <em>${art.number}</em>
          </article>`;
        }).join("")}
      </section>
      <footer class="hub-footer"><span>More adventures will grow from the choices you make here.</span><div><i></i><i></i><i></i><i></i></div></footer>
    </main>`;
  root.onclick = (event) => {
    const restart = event.target.closest?.("[data-restart-lesson]");
    if (!restart) return;
    const lessonName = restart.dataset.restartLesson || "this lesson";
    if (!window.confirm(`Restart ${lessonName}? Only this lesson's saved progress will be cleared.`)) event.preventDefault();
  };
}
