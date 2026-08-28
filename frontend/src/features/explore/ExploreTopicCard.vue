<template>
  <button
    class="topic-card"
    type="button"
    :style="topicTheme(topic)"
    :aria-label="`查看${topic.title}课程介绍`"
    @click="$emit('select', topic, $event)"
  >
    <div class="topic-art" :class="`cover-${topic.cover.kind}`">
      <img
        v-if="topic.cover.kind === 'image'"
        :src="topic.cover.src"
        :alt="topic.cover.alt"
      />

      <template v-else-if="topic.cover.kind === 'storybook'">
        <i class="moon" aria-hidden="true" />
        <i class="star star-one" aria-hidden="true">✦</i>
        <i class="star star-two" aria-hidden="true">•</i>
        <div class="topic-symbol" aria-hidden="true">
          {{ topic.hero.symbol }}
        </div>
        <span class="lantern" aria-hidden="true">{{ topic.hero.symbol }}</span>
        <div class="hills" aria-hidden="true"><i /><i /><i /></div>
      </template>

      <template v-else>
        <i class="abstract-grid" aria-hidden="true" />
        <i class="orbit orbit-one" aria-hidden="true" />
        <i class="orbit orbit-two" aria-hidden="true" />
        <div class="abstract-symbol" aria-hidden="true">
          {{ topic.hero.symbol }}
        </div>
      </template>
    </div>

    <div class="topic-copy">
      <div class="topic-meta">
        <span>{{ topic.type }}</span>
        <b v-if="topic.badge">{{ topic.badge }}</b>
      </div>
      <h3>{{ topic.title }}</h3>
      <span class="topic-author">作者 · {{ topic.author }}</span>
      <p>{{ topic.summary }}</p>
      <div class="topic-facts">
        <span v-for="fact in topic.facts" :key="fact">{{ fact }}</span>
      </div>
      <strong class="topic-more"
        >查看课程介绍 <span aria-hidden="true">→</span></strong
      >
    </div>
  </button>
</template>

<script setup>
import { topicTheme } from "./catalog.js";

defineProps({ topic: { type: Object, required: true } });
defineEmits(["select"]);
</script>

<style scoped>
.topic-card {
  width: 100%;
  max-width: 390px;
  min-width: 0;
  padding: 0;
  overflow: hidden;
  border: 1px solid var(--border);
  border-radius: 18px;
  color: var(--text-primary);
  background: var(--bg-card);
  box-shadow: var(--shadow-sm);
  text-align: left;
  font: inherit;
  cursor: pointer;
  transition:
    transform 0.2s ease,
    border-color 0.2s ease,
    box-shadow 0.2s ease;
}

.topic-card:focus-visible {
  outline: 2px solid var(--brand-light);
  outline-offset: 3px;
}

.topic-art {
  height: 170px;
  position: relative;
  overflow: hidden;
}

.cover-image {
  background: var(--topic-panel);
}

.cover-image img {
  width: 100%;
  height: 100%;
  display: block;
  object-fit: cover;
}

.cover-storybook {
  background: linear-gradient(
    180deg,
    var(--topic-sky-start) 0 61%,
    var(--topic-land-alt) 61%
  );
}

.cover-storybook .moon {
  width: 55px;
  height: 55px;
  position: absolute;
  right: 27px;
  top: 22px;
  border-radius: 50%;
  background: var(--topic-moon);
  box-shadow:
    0 0 0 14px rgb(255 225 142 / 9%),
    0 0 34px rgb(255 225 142 / 35%);
}

.cover-storybook .star {
  position: absolute;
  color: #fff2a8;
  font-style: normal;
}

.star-one {
  left: 22%;
  top: 29px;
}

.star-two {
  left: 57%;
  top: 21px;
}

.topic-symbol {
  width: 63px;
  height: 63px;
  position: absolute;
  left: 26px;
  top: 25px;
  display: grid;
  place-items: center;
  border-radius: 20px;
  color: #fff;
  background: var(--topic-primary);
  box-shadow: inset 0 0 0 1px rgb(255 255 255 / 20%);
  font-size: 25px;
}

.lantern {
  width: 58px;
  height: 72px;
  position: absolute;
  z-index: 1;
  left: 51%;
  bottom: 20px;
  display: grid;
  place-items: center;
  border: 5px solid #3c345f;
  border-radius: 26px 26px 14px 14px;
  color: #645886;
  background: #b1a7b4;
  font-size: 25px;
  transform: translateX(-50%);
}

.hills {
  height: 62px;
  position: absolute;
  inset: auto -5% 0;
  display: flex;
  align-items: end;
  justify-content: space-around;
}

.hills i {
  width: 38%;
  height: 48px;
  border-radius: 50% 50% 0 0;
  background: var(--topic-land);
}

.hills i:nth-child(2) {
  height: 38px;
  background: var(--topic-land-alt);
}

.hills i:last-child {
  height: 55px;
}

.cover-symbol {
  background: linear-gradient(
    135deg,
    var(--topic-sky-start),
    var(--topic-sky-end)
  );
  background:
    radial-gradient(
      circle at 78% 25%,
      color-mix(in srgb, var(--topic-moon) 44%, transparent) 0 8%,
      transparent 9%
    ),
    linear-gradient(135deg, var(--topic-sky-start), var(--topic-sky-end));
}

.abstract-grid {
  position: absolute;
  inset: 0;
  opacity: 0.22;
  background-image:
    linear-gradient(rgb(255 255 255 / 32%) 1px, transparent 1px),
    linear-gradient(90deg, rgb(255 255 255 / 32%) 1px, transparent 1px);
  background-size: 26px 26px;
  -webkit-mask-image: linear-gradient(90deg, #000, transparent 78%);
  mask-image: linear-gradient(90deg, #000, transparent 78%);
}

.orbit {
  position: absolute;
  border: 1px solid rgb(255 255 255 / 36%);
  border-radius: 50%;
  transform: rotate(-18deg);
}

.orbit-one {
  width: 210px;
  height: 86px;
  right: -35px;
  bottom: 16px;
}

.orbit-two {
  width: 145px;
  height: 145px;
  right: 15px;
  bottom: -68px;
}

.abstract-symbol {
  width: 76px;
  height: 76px;
  position: absolute;
  left: 30px;
  top: 47px;
  display: grid;
  place-items: center;
  border: 1px solid rgb(255 255 255 / 28%);
  border-radius: 24px;
  color: #fff;
  background: rgb(112 89 211 / 74%);
  background: color-mix(in srgb, var(--topic-primary) 74%, transparent);
  box-shadow: 0 16px 35px rgb(0 0 0 / 18%);
  font-size: 31px;
  -webkit-backdrop-filter: blur(8px);
  backdrop-filter: blur(8px);
}

.topic-copy {
  padding: 17px 18px 18px;
}

.topic-meta {
  display: flex;
  justify-content: space-between;
  color: var(--brand-light);
  font-size: 9px;
  font-weight: 800;
  letter-spacing: 0.08em;
}

.topic-meta b {
  padding: 2px 6px;
  border-radius: 6px;
  color: #fff7ed;
  background: linear-gradient(135deg, #f97316, #ef4444);
  font-size: 8px;
}

.topic-copy h3 {
  margin: 7px 0 5px;
  font-size: 19px;
  overflow-wrap: anywhere;
}

.topic-author {
  margin-bottom: 6px;
  display: block;
  color: var(--text-muted);
  font-size: 9px;
  font-weight: 600;
  letter-spacing: 0.03em;
}

.topic-copy > p {
  min-height: 40px;
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 1.55;
}

.topic-facts {
  margin-top: 13px;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.topic-facts span {
  padding: 4px 7px;
  border-radius: 7px;
  color: var(--text-secondary);
  background: var(--bg-hover);
  font-size: 9px;
}

.topic-more {
  margin-top: 14px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  color: var(--brand-light);
  font-size: 11px;
}

.topic-more span {
  font-size: 16px;
}

@media (hover: hover) {
  .topic-card:hover {
    border-color: rgb(129 140 248 / 48%);
    box-shadow: 0 18px 42px rgb(15 10 41 / 24%);
    transform: translateY(-3px);
  }
}

@media (max-width: 420px) {
  .topic-art {
    height: 150px;
  }

  .topic-copy {
    padding: 15px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .topic-card {
    transition: none;
  }
}
</style>
