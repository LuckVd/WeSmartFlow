<template>
  <Teleport to="body">
    <transition name="drawer" appear>
      <div
        class="drawer-backdrop"
        role="presentation"
        @click.self="$emit('close')"
      >
        <aside
          ref="drawerElement"
          class="topic-drawer"
          :style="topicTheme(topic)"
          role="dialog"
          aria-modal="true"
          :aria-labelledby="titleId"
          :aria-describedby="descriptionId"
        >
          <button
            ref="closeButton"
            class="drawer-close"
            aria-label="关闭课程介绍"
            @click="$emit('close')"
          >
            ×
          </button>

          <div class="drawer-hero" :class="`cover-${topic.cover.kind}`">
            <img
              v-if="topic.cover.kind === 'image'"
              class="hero-cover-image"
              :src="topic.cover.src"
              alt=""
            />
            <div class="hero-stars" aria-hidden="true">
              {{ topic.hero.sparkles }}
            </div>
            <div class="hero-mark" aria-hidden="true">
              {{ topic.hero.symbol }}
            </div>
            <small>{{ topic.hero.kicker }}</small>
            <h2 :id="titleId">{{ topic.title }}</h2>
            <span class="hero-author">作者 · {{ topic.author }}</span>
            <p :id="descriptionId">{{ topic.hero.description }}</p>
          </div>

          <div class="drawer-content">
            <div v-if="topic.tags.length" class="course-tags">
              <span v-for="tag in topic.tags" :key="tag">{{ tag }}</span>
            </div>

            <section
              v-for="section in topic.sections"
              :key="section.title"
              class="topic-section"
              :class="`layout-${section.layout}`"
            >
              <small>{{ section.title }}</small>
              <div class="section-items">
                <div
                  v-for="item in section.items"
                  :key="`${item.label}-${item.title}`"
                  class="section-item"
                >
                  <span aria-hidden="true">{{ item.label }}</span>
                  <p>
                    <strong>{{ item.title }}</strong>
                    <b>{{ item.detail }}</b>
                  </p>
                </div>
              </div>
            </section>

            <section v-if="topic.audience" class="audience-note">
              <span aria-hidden="true">✦</span>
              <p>
                <strong>{{ topic.audience.title }}</strong>
                <b>{{ topic.audience.description }}</b>
              </p>
            </section>
          </div>

          <footer :class="{ 'without-persistence': !topic.persistence }">
            <p v-if="topic.persistence">
              <span>✓</span> {{ topic.persistence }}
            </p>
            <a :href="topic.href"
              >{{ topic.launchLabel }} <span aria-hidden="true">→</span></a
            >
          </footer>
        </aside>
      </div>
    </transition>
  </Teleport>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from "vue";
import { topicTheme } from "./catalog.js";

const props = defineProps({ topic: { type: Object, required: true } });
const emit = defineEmits(["close"]);
const drawerElement = ref(null);
const closeButton = ref(null);
const titleId = computed(() => `explore-topic-${props.topic.id}-title`);
const descriptionId = computed(
  () => `explore-topic-${props.topic.id}-description`,
);
let previousBodyOverflow = "";

function handleKeydown(event) {
  if (event.key === "Escape") {
    emit("close");
    return;
  }
  if (event.key !== "Tab") return;

  const focusable = drawerElement.value?.querySelectorAll(
    'a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])',
  );
  if (!focusable?.length) return;

  const first = focusable[0];
  const last = focusable[focusable.length - 1];
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault();
    first.focus();
  }
}

onMounted(async () => {
  previousBodyOverflow = document.body.style.overflow;
  document.body.style.overflow = "hidden";
  window.addEventListener("keydown", handleKeydown);
  await nextTick();
  closeButton.value?.focus();
});

onBeforeUnmount(() => {
  window.removeEventListener("keydown", handleKeydown);
  document.body.style.overflow = previousBodyOverflow;
});
</script>

<style scoped>
.drawer-backdrop {
  position: fixed;
  z-index: 200;
  inset: 0;
  display: flex;
  justify-content: flex-end;
  background: rgb(7 8 12 / 58%);
  -webkit-backdrop-filter: blur(4px);
  backdrop-filter: blur(4px);
}

.topic-drawer {
  width: min(520px, 100%);
  height: 100vh;
  height: 100dvh;
  position: relative;
  overflow-y: auto;
  overscroll-behavior: contain;
  display: flex;
  flex-direction: column;
  color: var(--topic-surface-text);
  background: var(--topic-surface);
  box-shadow: -24px 0 70px rgb(8 6 22 / 38%);
}

.drawer-close {
  width: 38px;
  height: 38px;
  position: absolute;
  z-index: 5;
  right: max(16px, env(safe-area-inset-right));
  top: max(16px, env(safe-area-inset-top));
  border: 1px solid rgb(255 255 255 / 48%);
  border-radius: 12px;
  color: #fff;
  background: rgb(45 35 84 / 46%);
  font-size: 22px;
  cursor: pointer;
}

.drawer-close:focus-visible {
  outline: 2px solid #fff;
  outline-offset: 3px;
}

.drawer-hero {
  min-height: 235px;
  padding: 42px 38px 30px;
  position: relative;
  overflow: hidden;
  flex: none;
  color: #fff;
  background: linear-gradient(
    145deg,
    var(--topic-sky-start),
    var(--topic-sky-end)
  );
}

.cover-storybook {
  background:
    radial-gradient(circle at 82% 20%, rgb(255 224 137 / 36%), transparent 18%),
    linear-gradient(
      145deg,
      var(--topic-sky-start),
      var(--topic-sky-end) 68%,
      #cb8b78
    );
}

.cover-storybook::after {
  content: "";
  width: 220px;
  height: 80px;
  position: absolute;
  right: -35px;
  bottom: -33px;
  border-radius: 50% 50% 0 0;
  background: var(--topic-land);
}

.cover-symbol::before,
.cover-symbol::after {
  content: "";
  position: absolute;
  right: -55px;
  border: 1px solid rgb(255 255 255 / 24%);
  border-radius: 50%;
  transform: rotate(-18deg);
}

.cover-symbol::before {
  width: 290px;
  height: 120px;
  top: 32px;
}

.cover-symbol::after {
  width: 210px;
  height: 210px;
  bottom: -125px;
}

.cover-image::after {
  content: "";
  position: absolute;
  inset: 0;
  background: linear-gradient(90deg, rgb(20 16 40 / 78%), rgb(20 16 40 / 20%));
}

.hero-cover-image {
  width: 100%;
  height: 100%;
  position: absolute;
  inset: 0;
  object-fit: cover;
}

.hero-stars,
.hero-mark,
.drawer-hero > small,
.drawer-hero > h2,
.drawer-hero > .hero-author,
.drawer-hero > p {
  position: relative;
  z-index: 2;
}

.hero-stars {
  position: absolute;
  right: 54px;
  top: 70px;
  color: var(--topic-moon);
  letter-spacing: 12px;
}

.hero-mark {
  width: 54px;
  height: 54px;
  margin-bottom: 18px;
  display: grid;
  place-items: center;
  border: 1px solid rgb(255 255 255 / 16%);
  border-radius: 17px;
  color: #fff;
  background: var(--topic-primary);
  box-shadow: 0 10px 28px rgb(0 0 0 / 14%);
  font-size: 23px;
}

.drawer-hero small {
  color: var(--topic-moon);
  font-size: 8px;
  font-weight: 900;
  letter-spacing: 0.18em;
}

.drawer-hero h2 {
  margin: 5px 0 7px;
  font-size: 30px;
  line-height: 1.1;
  overflow-wrap: anywhere;
}

.hero-author {
  margin-bottom: 7px;
  display: block;
  color: rgb(255 255 255 / 72%);
  font-size: 9px;
  font-weight: 700;
  letter-spacing: 0.06em;
}

.drawer-hero p {
  max-width: 330px;
  color: #e8e2f2;
  font-size: 12px;
}

.drawer-content {
  padding: 22px 28px;
  display: grid;
  gap: 22px;
}

.course-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 7px;
}

.course-tags span {
  padding: 5px 8px;
  border: 1px solid var(--topic-line);
  border-radius: 9px;
  color: var(--topic-surface-text);
  background: var(--topic-panel);
  font-size: 9px;
  font-weight: 700;
}

.topic-section > small {
  display: block;
  margin-bottom: 10px;
  color: var(--topic-primary-dark);
  font-size: 9px;
  font-weight: 900;
  letter-spacing: 0.12em;
}

.section-items {
  display: grid;
  gap: 8px;
}

.layout-grid .section-items {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.section-item {
  min-width: 0;
  padding: 10px;
  display: grid;
  grid-template-columns: 34px minmax(0, 1fr);
  gap: 9px;
  align-items: center;
  border: 1px solid var(--topic-line);
  border-radius: 13px;
  background: var(--topic-panel);
}

.section-item > span {
  width: 33px;
  height: 33px;
  display: grid;
  place-items: center;
  border-radius: 10px;
  color: var(--topic-surface-text);
  background: var(--topic-soft);
  font-size: 10px;
  font-weight: 900;
}

.layout-list .section-item > span {
  color: #fff;
  background: var(--topic-primary);
}

.section-item p,
.audience-note p {
  min-width: 0;
}

.section-item strong,
.section-item b,
.audience-note strong,
.audience-note b {
  display: block;
  overflow-wrap: anywhere;
}

.section-item strong,
.audience-note strong {
  font-size: 10px;
}

.section-item b,
.audience-note b {
  margin-top: 2px;
  color: var(--topic-muted);
  font-size: 8px;
  font-weight: 500;
  line-height: 1.45;
}

.audience-note {
  padding: 13px;
  display: grid;
  grid-template-columns: 35px minmax(0, 1fr);
  gap: 10px;
  align-items: center;
  border-radius: 14px;
  background: var(--topic-soft);
}

.audience-note > span {
  width: 35px;
  height: 35px;
  display: grid;
  place-items: center;
  border-radius: 11px;
  color: #fff;
  background: var(--topic-primary);
}

.topic-drawer footer {
  margin-top: auto;
  padding: 15px 28px max(20px, env(safe-area-inset-bottom));
  position: sticky;
  z-index: 3;
  bottom: 0;
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 12px;
  align-items: center;
  border-top: 1px solid var(--topic-line);
  background: var(--topic-footer);
  -webkit-backdrop-filter: blur(12px);
  backdrop-filter: blur(12px);
}

.topic-drawer footer.without-persistence {
  grid-template-columns: 1fr;
}

.topic-drawer footer p {
  color: var(--topic-muted);
  font-size: 8px;
}

.topic-drawer footer p span {
  color: #4b9870;
}

.topic-drawer footer a {
  min-height: 46px;
  padding: 10px 13px 10px 17px;
  display: flex;
  align-items: center;
  gap: 18px;
  justify-self: end;
  border-radius: 14px;
  color: #fff;
  background: linear-gradient(
    135deg,
    var(--topic-primary),
    var(--topic-primary-dark)
  );
  box-shadow: 0 10px 24px rgb(77 56 150 / 24%);
  font-size: 11px;
  font-weight: 900;
  text-decoration: none;
}

.topic-drawer footer a:focus-visible {
  outline: 2px solid var(--topic-primary);
  outline-offset: 3px;
}

.topic-drawer footer a span {
  font-size: 17px;
}

.drawer-enter-active,
.drawer-leave-active {
  transition: opacity 0.22s ease;
}

.drawer-enter-active .topic-drawer,
.drawer-leave-active .topic-drawer {
  transition: transform 0.25s ease;
}

.drawer-enter-from,
.drawer-leave-to {
  opacity: 0;
}

.drawer-enter-from .topic-drawer,
.drawer-leave-to .topic-drawer {
  transform: translateX(100%);
}

@media (max-width: 700px) {
  .topic-drawer {
    width: 100%;
  }

  .drawer-content {
    padding-inline: 18px;
  }

  .layout-grid .section-items {
    grid-template-columns: 1fr;
  }

  .topic-drawer footer {
    padding-inline: 18px;
    grid-template-columns: 1fr;
  }

  .topic-drawer footer p {
    text-align: center;
  }

  .topic-drawer footer a {
    justify-content: center;
    justify-self: stretch;
  }

  .drawer-hero {
    padding-inline: 24px;
  }
}

@media (max-height: 650px) {
  .drawer-hero {
    min-height: 190px;
    padding-block: 30px 24px;
  }

  .hero-mark {
    margin-bottom: 10px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .drawer-enter-active,
  .drawer-leave-active,
  .drawer-enter-active .topic-drawer,
  .drawer-leave-active .topic-drawer {
    transition: none;
  }
}
</style>
