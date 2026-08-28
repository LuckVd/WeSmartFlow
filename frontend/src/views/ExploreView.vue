<template>
  <div class="explore-page page-std">
    <header class="page-header explore-header">
      <div>
        <div class="eyebrow"><span>🔥</span> 全新内容</div>
        <h1 class="page-title">探索</h1>
        <p class="page-subtitle">从感兴趣的主题出发，在故事和实践中学习。</p>
      </div>
    </header>

    <nav class="breadcrumbs" aria-label="当前位置">
      <strong>探索</strong><span aria-hidden="true">›</span
      ><b>{{ activeCategory?.title }}</b>
    </nav>

    <div
      v-if="categories.length > 1"
      class="category-tabs"
      aria-label="学习分类"
    >
      <button
        v-for="category in categories"
        :key="category.id"
        type="button"
        :class="{ active: category.id === activeCategoryId }"
        :aria-pressed="category.id === activeCategoryId"
        @click="selectCategory(category.id)"
      >
        <span>{{ category.icon }}</span
        >{{ category.title }}
      </button>
    </div>

    <section v-if="activeCategory" class="category-intro">
      <div class="category-icon" aria-hidden="true">
        {{ activeCategory.icon }}
      </div>
      <div>
        <small>{{ activeCategory.kicker }}</small>
        <h2>{{ activeCategory.title }}</h2>
        <p>{{ activeCategory.description }}</p>
      </div>
      <span>{{ activeTopics.length }} 个主题</span>
    </section>

    <div v-if="activeTopics.length" class="topic-grid">
      <ExploreTopicCard
        v-for="topic in activeTopics"
        :key="topic.id"
        :topic="topic"
        @select="openTopic"
      />
    </div>
    <p v-else class="empty-state">这个分类的学习主题正在准备中。</p>

    <ExploreTopicDrawer
      v-if="selectedTopic"
      :topic="selectedTopic"
      @close="closeTopic"
    />
  </div>
</template>

<script setup>
import { computed, nextTick, ref } from "vue";
import ExploreTopicCard from "../features/explore/ExploreTopicCard.vue";
import ExploreTopicDrawer from "../features/explore/ExploreTopicDrawer.vue";
import { categories, topicsForCategory } from "../features/explore/catalog.js";

const activeCategoryId = ref(categories[0]?.id ?? "");
const selectedTopic = ref(null);
let triggerElement = null;

const activeCategory = computed(() =>
  categories.find((category) => category.id === activeCategoryId.value),
);
const activeTopics = computed(() => topicsForCategory(activeCategoryId.value));

function selectCategory(categoryId) {
  activeCategoryId.value = categoryId;
  closeTopic();
}

function openTopic(topic, event) {
  triggerElement = event.currentTarget;
  selectedTopic.value = topic;
}

function closeTopic() {
  if (!selectedTopic.value) return;
  selectedTopic.value = null;
  nextTick(() => triggerElement?.focus());
}
</script>

<style scoped>
.explore-page {
  min-width: 0;
  min-height: 100%;
  overflow: hidden;
}
.explore-header {
  margin-bottom: 14px;
}
.eyebrow {
  margin-bottom: 8px;
  display: flex;
  align-items: center;
  gap: 6px;
  color: #fb923c;
  font-size: 10px;
  font-weight: 800;
  letter-spacing: 0.12em;
}
.eyebrow span {
  font-size: 15px;
  filter: drop-shadow(0 0 8px rgb(249 115 22 / 45%));
}
.breadcrumbs {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--text-muted);
  font-size: 11px;
}
.breadcrumbs strong {
  color: var(--text-secondary);
}
.breadcrumbs b {
  color: var(--brand-light);
  font-weight: 600;
}
.category-tabs {
  margin-top: 16px;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.category-tabs button {
  min-height: 36px;
  padding: 7px 12px;
  display: flex;
  align-items: center;
  gap: 7px;
  border: 1px solid var(--border);
  border-radius: 10px;
  color: var(--text-secondary);
  background: var(--bg-card);
  font: inherit;
  font-size: 11px;
  cursor: pointer;
}
.category-tabs button.active {
  border-color: rgb(129 140 248 / 48%);
  color: var(--brand-light);
  background: var(--brand-dim);
}
.category-tabs button:focus-visible {
  outline: 2px solid var(--brand-light);
  outline-offset: 3px;
}
.category-tabs span {
  font-weight: 800;
}
.category-intro {
  margin-top: 18px;
  padding: 18px 20px;
  display: grid;
  grid-template-columns: 48px minmax(0, 1fr) auto;
  gap: 14px;
  align-items: center;
  border: 1px solid var(--border);
  border-radius: 16px;
  background: linear-gradient(110deg, var(--bg-card), var(--brand-dim));
}
.category-icon {
  width: 48px;
  height: 48px;
  display: grid;
  place-items: center;
  border-radius: 14px;
  color: #fff;
  background: var(--gradient-brand);
  font-size: 16px;
  font-weight: 800;
  box-shadow: 0 9px 22px var(--brand-glow);
}
.category-intro small {
  color: var(--brand-light);
  font-size: 8px;
  font-weight: 800;
  letter-spacing: 0.15em;
}
.category-intro h2 {
  margin: 2px 0;
  font-size: 18px;
}
.category-intro p {
  color: var(--text-secondary);
  font-size: 12px;
}
.category-intro > span {
  color: var(--text-muted);
  font-size: 11px;
  white-space: nowrap;
}
.topic-grid {
  margin-top: 18px;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 16px;
}
.empty-state {
  margin-top: 18px;
  padding: 28px;
  border: 1px dashed var(--border);
  border-radius: 16px;
  color: var(--text-muted);
  text-align: center;
  font-size: 12px;
}
@media (max-width: 700px) {
  .explore-page {
    padding: 20px 14px;
  }
  .category-intro {
    grid-template-columns: 44px minmax(0, 1fr);
  }
  .category-intro > span {
    grid-column: 2;
  }
  .topic-grid {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
