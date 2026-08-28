import { escapeHtml } from "./browser.js";

export const COURSE_STAR_MAX = 3;

const LESSON_HIDDEN_CHALLENGES = {
  "missing-puppy": null,
  "moonlight-festival": ["bakery-kindness", "school-colors", "park-fireflies"],
};

function values(value) {
  return value && typeof value[Symbol.iterator] === "function" ? [...value] : [];
}

function safeClasses(className) {
  return String(className).split(/\s+/).filter(Boolean).map((name) => name.replace(/[^a-z0-9_-]/gi, "")).join(" ");
}

function lessonComplete(lessonId, source, resume) {
  if (source?.complete) return true;
  if (lessonId === "missing-puppy") return (source?.questStage ?? resume.questStage) === "complete";
  if (lessonId === "moonlight-festival") {
    return (source?.phase ?? resume.phase) === "celebration"
      && Boolean(source?.memoryBookComplete ?? resume.memoryBookComplete);
  }
  return Boolean(source?.complete ?? resume.complete);
}

export function calculateCourseStars({ complete = false, hiddenCompleted = 0, hiddenTotal = 3 } = {}) {
  if (!complete) return 0;
  const completed = Math.max(0, Number(hiddenCompleted) || 0);
  const total = Math.max(1, Number(hiddenTotal) || 1);
  if (completed === 0) return 1;
  return completed >= total ? COURSE_STAR_MAX : 2;
}

export function getCourseStarsForLesson(storyOrId, source = {}) {
  const lessonId = typeof storyOrId === "string" ? storyOrId : storyOrId?.id;
  const rating = typeof storyOrId === "object" ? storyOrId?.course?.rating ?? {} : {};
  const resume = source?.resume ?? source ?? {};
  const complete = lessonComplete(lessonId, source, resume);
  const learningCompleted = new Set(values(source?.learning?.completed ?? resume.learningCompleted));
  const configuredChallenges = rating.hiddenChallengeIds ?? LESSON_HIDDEN_CHALLENGES[lessonId];
  if (configuredChallenges) {
    const legacyPlaces = new Set(values(source?.surprisesFound ?? resume.surprisesFound));
    const hiddenCompleted = configuredChallenges.filter((id) => {
      const place = id.split("-")[0];
      return learningCompleted.has(id) || legacyPlaces.has(place);
    }).length;
    return calculateCourseStars({ complete, hiddenCompleted, hiddenTotal: configuredChallenges.length });
  }
  if (lessonId === "missing-puppy") {
    const hiddenTotal = Math.max(1, Number(rating.hiddenChallengeCount) || 3);
    return calculateCourseStars({ complete, hiddenCompleted: Math.min(learningCompleted.size, hiddenTotal), hiddenTotal });
  }
  return calculateCourseStars({
    complete,
    hiddenCompleted: Number(source?.hiddenStoriesCompleted ?? resume.hiddenStoriesCompleted),
    hiddenTotal: Number(rating.hiddenChallengeCount ?? source?.hiddenStoryTotal ?? resume.hiddenStoryTotal) || 3,
  });
}

export function getCourseStarHint(earned, { lessonLabel = "lesson" } = {}) {
  const stars = Math.max(0, Math.min(COURSE_STAR_MAX, Number(earned) || 0));
  if (stars === 0) return `Finish the ${lessonLabel} storybook to reveal your stars.`;
  if (stars === 1) return "Main story complete · explore hidden stories for more stars";
  if (stars === 2) return "Hidden story found · complete the hidden trail for full stars";
  return "All hidden stories discovered · full stars!";
}

export function renderCourseStars({ earned = 0, max = COURSE_STAR_MAX, size = "medium", className = "", label = "course stars", showCount = false } = {}) {
  const total = Math.max(1, Number(max) || COURSE_STAR_MAX);
  const score = Math.max(0, Math.min(total, Number(earned) || 0));
  const safeSize = ["small", "medium", "large"].includes(size) ? size : "medium";
  const safeClassName = safeClasses(className);
  const stars = Array.from({ length: total }, (_, index) => {
    const earnedStar = index < score;
    return `<i class="course-star ${earnedStar ? "earned" : "unearned"}" aria-hidden="true"><span>${earnedStar ? "★" : "☆"}</span></i>`;
  }).join("");
  return `<div class="course-stars size-${safeSize}${safeClassName ? ` ${safeClassName}` : ""}" role="img" aria-label="${score} of ${total} ${escapeHtml(label)}">${stars}${showCount ? `<b class="course-star-count">${score}/${total}</b>` : ""}</div>`;
}

export function renderCourseCompletion({ earned = 0, title = "Completed", eyebrow = "LESSON COMPLETE", hint = getCourseStarHint(earned), size = "medium", className = "", showCount = true, homeHref = "", homeLabel = "Back to course home" } = {}) {
  const safeClassName = safeClasses(className);
  const homeAction = homeHref
    ? `<a class="course-completion-home" href="${escapeHtml(homeHref)}"><span aria-hidden="true">⌂</span>${escapeHtml(homeLabel)}</a>`
    : "";
  return `<section class="course-completion${safeClassName ? ` ${safeClassName}` : ""}" aria-label="${escapeHtml(`${title}, ${earned} of ${COURSE_STAR_MAX} course stars`)}"><header><i aria-hidden="true">✓</i><p><small>${escapeHtml(eyebrow)}</small><strong>${escapeHtml(title)}</strong></p></header>${renderCourseStars({ earned, size, showCount })}${hint ? `<p class="course-completion-hint">${escapeHtml(hint)}</p>` : ""}${homeAction}</section>`;
}
