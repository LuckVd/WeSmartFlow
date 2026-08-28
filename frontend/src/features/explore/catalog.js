import rawCatalog from "@explore-catalog";

const DEFAULT_THEME = Object.freeze({
  primary: "#7059d3",
  primaryDark: "#5944a8",
  skyStart: "#50457f",
  skyEnd: "#725da7",
  land: "#547064",
  landAlt: "#5d806d",
  moon: "#ffe18e",
  surface: "#fffaf0",
  surfaceText: "#443a59",
  panel: "#fffdf8",
  muted: "#807584",
  line: "#e5dac9",
  soft: "#f0eafa",
  footer: "rgb(255 250 240 / 94%)",
});

export const topics = rawCatalog.topics.filter(
  (topic) => topic.published !== false,
);
export const categories = rawCatalog.categories.filter((category) =>
  topics.some((topic) => topic.categoryId === category.id),
);

export function topicsForCategory(categoryId) {
  return topics.filter((topic) => topic.categoryId === categoryId);
}

export function topicTheme(topic) {
  const theme = { ...DEFAULT_THEME, ...topic.theme };
  return {
    "--topic-primary": theme.primary,
    "--topic-primary-dark": theme.primaryDark,
    "--topic-sky-start": theme.skyStart,
    "--topic-sky-end": theme.skyEnd,
    "--topic-land": theme.land,
    "--topic-land-alt": theme.landAlt,
    "--topic-moon": theme.moon,
    "--topic-surface": theme.surface,
    "--topic-surface-text": theme.surfaceText,
    "--topic-panel": theme.panel,
    "--topic-muted": theme.muted,
    "--topic-line": theme.line,
    "--topic-soft": theme.soft,
    "--topic-footer": theme.footer,
  };
}
