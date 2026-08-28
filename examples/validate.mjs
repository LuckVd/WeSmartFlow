import { loadCatalog } from "./catalog.mjs";

try {
  const catalog = loadCatalog();
  const visibleCount = catalog.topics.filter((topic) => topic.published !== false).length;
  console.log(`[explore] 目录有效：${catalog.categories.length} 个分类，${visibleCount} 个已发布主题`);
} catch (error) {
  console.error(`[explore] ${error.message}`);
  process.exit(1);
}
