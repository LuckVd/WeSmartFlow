import { readFileSync } from "node:fs";
import { dirname, isAbsolute, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";

export const examplesDir = dirname(fileURLToPath(import.meta.url));
const catalogPath = resolve(examplesDir, "explore-catalog.json");

export const CATALOG_VERSION = 2;
const COVER_KINDS = new Set(["symbol", "storybook", "image"]);
const SECTION_LAYOUTS = new Set(["grid", "list"]);
const ROOT_FIELDS = new Set(["version", "categories", "topics"]);
const CATEGORY_FIELDS = new Set(["id", "title", "kicker", "icon", "description"]);
const TOPIC_FIELDS = new Set([
  "id",
  "categoryId",
  "title",
  "type",
  "author",
  "badge",
  "published",
  "summary",
  "href",
  "launchLabel",
  "facts",
  "tags",
  "hero",
  "cover",
  "theme",
  "sections",
  "audience",
  "persistence",
  "build",
]);
const HERO_FIELDS = new Set(["kicker", "description", "symbol", "sparkles"]);
const COVER_FIELDS = new Set(["kind", "src", "alt"]);
const SECTION_FIELDS = new Set(["title", "layout", "items"]);
const SECTION_ITEM_FIELDS = new Set(["label", "title", "detail"]);
const AUDIENCE_FIELDS = new Set(["title", "description"]);
const BUILD_FIELDS = new Set([
  "runner",
  "script",
  "packageDir",
  "outputDir",
  "entryFile",
]);
const THEME_FIELDS = new Set([
  "primary",
  "primaryDark",
  "skyStart",
  "skyEnd",
  "land",
  "landAlt",
  "moon",
  "surface",
  "surfaceText",
  "panel",
  "muted",
  "line",
  "soft",
  "footer",
]);

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function requireString(value, label) {
  assert(typeof value === "string" && value.trim(), `${label} 必须是非空字符串`);
}

function requireObject(value, label) {
  assert(value && typeof value === "object" && !Array.isArray(value), `${label} 必须是对象`);
}

function requireKnownFields(value, allowedFields, label) {
  for (const field of Object.keys(value)) {
    assert(allowedFields.has(field), `${label} 包含未知字段：${field}`);
  }
}

function requireId(value, label) {
  requireString(value, label);
  assert(/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(value), `${label} 必须使用小写 kebab-case`);
}

function requireRelativePath(value, label) {
  requireString(value, label);
  const segments = value.replaceAll("\\", "/").split("/");
  assert(
    !isAbsolute(value) && !segments.includes("") && !segments.includes(".") && !segments.includes(".."),
    `${label} 必须是规范的目录内相对路径`,
  );
}

function requireStringList(value, label) {
  assert(Array.isArray(value), `${label} 必须是数组`);
  value.forEach((item, index) => requireString(item, `${label}[${index}]`));
}

function isAbsoluteUrl(value) {
  return /^https?:\/\//i.test(value);
}

function validateHref(href, label) {
  requireString(href, label);
  const url = new URL(href, "http://catalog.local");
  assert(["http:", "https:"].includes(url.protocol), `${label} 只允许站内路径或 http(s) 地址`);
  assert(
    isAbsoluteUrl(href) || (href.startsWith("/") && !href.startsWith("//") && !href.includes("\\")),
    `${label} 的站内入口必须是以单个 / 开头的规范路径`,
  );
  return url;
}

function validateCategory(category, index) {
  const label = `categories[${index}]`;
  requireObject(category, label);
  requireKnownFields(category, CATEGORY_FIELDS, label);
  requireId(category.id, `${label}.id`);
  ["title", "kicker", "icon", "description"].forEach((field) =>
    requireString(category[field], `${label}.${field}`),
  );
}

function validateCover(topic) {
  const { cover } = topic;
  requireObject(cover, `${topic.id}.cover`);
  requireKnownFields(cover, COVER_FIELDS, `${topic.id}.cover`);
  requireString(cover.kind, `${topic.id}.cover.kind`);
  assert(COVER_KINDS.has(cover.kind), `${topic.id}.cover.kind 不受支持：${cover.kind}`);
  if (cover.kind === "image") {
    validateHref(cover.src, `${topic.id}.cover.src`);
    requireString(cover.alt, `${topic.id}.cover.alt`);
  } else {
    assert(
      cover.src === undefined && cover.alt === undefined,
      `${topic.id}.cover 仅 image 类型可设置 src 和 alt`,
    );
  }
}

function validateSections(topic) {
  assert(Array.isArray(topic.sections), `${topic.id}.sections 必须是数组`);
  const sectionTitles = new Set();
  topic.sections.forEach((section, sectionIndex) => {
    const label = `${topic.id}.sections[${sectionIndex}]`;
    requireObject(section, label);
    requireKnownFields(section, SECTION_FIELDS, label);
    requireString(section.title, `${label}.title`);
    assert(!sectionTitles.has(section.title), `${topic.id}.sections 标题重复：${section.title}`);
    sectionTitles.add(section.title);
    requireString(section.layout, `${label}.layout`);
    assert(SECTION_LAYOUTS.has(section.layout), `${label}.layout 不受支持：${section.layout}`);
    assert(Array.isArray(section.items), `${label}.items 必须是数组`);
    section.items.forEach((item, itemIndex) => {
      requireObject(item, `${label}.items[${itemIndex}]`);
      requireKnownFields(item, SECTION_ITEM_FIELDS, `${label}.items[${itemIndex}]`);
      ["label", "title", "detail"].forEach((field) =>
        requireString(item[field], `${label}.items[${itemIndex}].${field}`),
      );
    });
  });
}

function validateBuild(topic, hrefUrl) {
  if (!topic.build) return;
  const { build } = topic;
  requireObject(build, `${topic.id}.build`);
  requireKnownFields(build, BUILD_FIELDS, `${topic.id}.build`);
  ["runner", "script", "packageDir", "outputDir", "entryFile"].forEach((field) =>
    requireString(build[field], `${topic.id}.build.${field}`),
  );
  assert(build.runner === "npm", `${topic.id}.build.runner 暂只支持 npm`);
  assert(/^[a-zA-Z0-9:_-]+$/.test(build.script), `${topic.id}.build.script 含有无效字符`);
  requireRelativePath(build.packageDir, `${topic.id}.build.packageDir`);
  requireRelativePath(build.outputDir, `${topic.id}.build.outputDir`);
  requireRelativePath(build.entryFile, `${topic.id}.build.entryFile`);
  assert(!build.outputDir.startsWith(".examples-staging"), `${topic.id}.build.outputDir 使用了保留目录`);
  assert(!isAbsoluteUrl(topic.href), `${topic.id}.build 只能用于站内入口`);
  const expectedPrefix = `/${build.outputDir.replace(/^\/+|\/+$/g, "")}/`;
  assert(
    hrefUrl.pathname.startsWith(expectedPrefix),
    `${topic.id}.href 必须以 ${expectedPrefix} 开头，与 build.outputDir 保持一致`,
  );
}

function validateTopic(topic, index, categoryIds) {
  const label = `topics[${index}]`;
  requireObject(topic, label);
  requireKnownFields(topic, TOPIC_FIELDS, label);
  requireId(topic.id, `${label}.id`);
  ["categoryId", "title", "type", "author", "summary", "href", "launchLabel"].forEach((field) =>
    requireString(topic[field], `${label}.${field}`),
  );
  assert(categoryIds.has(topic.categoryId), `${topic.id} 引用了不存在的分类：${topic.categoryId}`);
  if (topic.published !== undefined) {
    assert(typeof topic.published === "boolean", `${topic.id}.published 必须是布尔值`);
  }
  if (topic.badge !== undefined) requireString(topic.badge, `${topic.id}.badge`);
  if (topic.persistence !== undefined) requireString(topic.persistence, `${topic.id}.persistence`);

  const hrefUrl = validateHref(topic.href, `${topic.id}.href`);
  requireStringList(topic.facts, `${topic.id}.facts`);
  requireStringList(topic.tags, `${topic.id}.tags`);

  requireObject(topic.hero, `${topic.id}.hero`);
  requireKnownFields(topic.hero, HERO_FIELDS, `${topic.id}.hero`);
  ["kicker", "description", "symbol"].forEach((field) =>
    requireString(topic.hero[field], `${topic.id}.hero.${field}`),
  );
  if (topic.hero.sparkles !== undefined) {
    assert(typeof topic.hero.sparkles === "string", `${topic.id}.hero.sparkles 必须是字符串`);
  }

  if (topic.audience !== undefined) {
    requireObject(topic.audience, `${topic.id}.audience`);
    requireKnownFields(topic.audience, AUDIENCE_FIELDS, `${topic.id}.audience`);
    requireString(topic.audience.title, `${topic.id}.audience.title`);
    requireString(topic.audience.description, `${topic.id}.audience.description`);
  }

  if (topic.theme !== undefined) {
    requireObject(topic.theme, `${topic.id}.theme`);
    for (const [field, value] of Object.entries(topic.theme)) {
      assert(THEME_FIELDS.has(field), `${topic.id}.theme 包含未知字段：${field}`);
      requireString(value, `${topic.id}.theme.${field}`);
    }
  }

  validateCover(topic);
  validateSections(topic);
  validateBuild(topic, hrefUrl);
}

export function validateCatalog(catalog) {
  requireObject(catalog, "探索目录");
  requireKnownFields(catalog, ROOT_FIELDS, "探索目录");
  assert(catalog.version === CATALOG_VERSION, `仅支持 version: ${CATALOG_VERSION} 的探索目录`);
  assert(Array.isArray(catalog.categories), "explore-catalog.json 缺少 categories 数组");
  assert(Array.isArray(catalog.topics), "explore-catalog.json 缺少 topics 数组");

  const categoryIds = new Set();
  catalog.categories.forEach((category, index) => {
    validateCategory(category, index);
    assert(!categoryIds.has(category.id), `分类 id 重复：${category.id}`);
    categoryIds.add(category.id);
  });

  const topicIds = new Set();
  const outputDirs = new Set();
  catalog.topics.forEach((topic, index) => {
    validateTopic(topic, index, categoryIds);
    assert(!topicIds.has(topic.id), `主题 id 重复：${topic.id}`);
    topicIds.add(topic.id);
    if (topic.build) {
      const outputDir = topic.build.outputDir.replace(/^\/+|\/+$/g, "");
      for (const existingDir of outputDirs) {
        assert(
          outputDir !== existingDir &&
            !outputDir.startsWith(`${existingDir}/`) &&
            !existingDir.startsWith(`${outputDir}/`),
          `构建输出目录重复或相互嵌套：${outputDir} 与 ${existingDir}`,
        );
      }
      outputDirs.add(outputDir);
    }
  });
  return catalog;
}

export function loadCatalog(path = catalogPath) {
  let catalog;
  try {
    catalog = JSON.parse(readFileSync(path, "utf8"));
  } catch (error) {
    throw new Error(`无法读取探索目录 ${path}：${error.message}`, { cause: error });
  }
  return validateCatalog(catalog);
}

export function resolveChildPath(root, relativePath, label) {
  requireRelativePath(relativePath, label);
  const target = resolve(root, relativePath);
  assert(target !== root && target.startsWith(`${root}${sep}`), `${label} 必须位于 ${root} 的子目录中`);
  return target;
}

export function getBuildableTopics(catalog) {
  return catalog.topics.filter((topic) => topic.build);
}
