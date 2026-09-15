<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from "vue";

const heroVideo = ref(null);
const filmDialog = ref(null);
const filmVideo = ref(null);
const mobileMenuButton = ref(null);
const mobileMenuOpen = ref(false);
const isPlaying = ref(false);
const filmOpened = ref(false);
const activeMode = ref(0);
const modes = [
  {
    id: "tutor",
    label: "自由辅导",
    english: "PERSONAL TUTOR",
    title: "从一个问题开始，直到真正理解。",
    description:
      "把不懂的地方交给 AI。用讲解、知识卡片、交互演示和即时练习，让抽象的概念变得清晰。",
    image: "/landing/tutor.webp",
    alt: "WeSmartFlow 自由辅导：积分知识卡片与 AI 对话示例",
    tags: ["随时追问", "交互式演示", "即时练习"],
  },
  {
    id: "course",
    label: "沉浸课程",
    english: "IMMERSIVE LEARNING",
    title: "一个好奇的主题，一段完整的旅程。",
    description:
      "从章节大纲到课件、插图、语音和练习，AI 为你组织学习内容。按自己的节奏深入，也可以随时停下来追问。",
    image: "/landing/course.webp",
    alt: "WeSmartFlow 沉浸课程：量子力学 PDF 课件与问答示例",
    tags: ["定制大纲", "课件与语音", "章节练习"],
  },
  {
    id: "knowledge",
    label: "知识图谱",
    english: "YOUR KNOWLEDGE, CONNECTED",
    title: "学过的每一步，都有迹可循。",
    description:
      "让零散的知识彼此连接。记录概念关系与掌握变化，在一次次学习和复习中，形成属于你的知识网络。",
    image: "/landing/knowledge.webp",
    alt: "WeSmartFlow 个人知识图谱与概念掌握详情示例",
    tags: ["概念连接", "掌握度追踪", "持续积累"],
  },
];
const currentMode = computed(() => modes[activeMode.value]);
const worlds = [
  {
    id: "science",
    number: "01",
    label: "SCIENCE",
    title: "回到发现的那一刻。",
    description: "与科学家对话，重做经典实验，在追问中理解世界。",
    image: "/landing/world-science.webp",
    alt: "宣传片中的旋涡星系",
    topics: "知识之境 · 化学实验室",
  },
  {
    id: "history",
    number: "02",
    label: "HISTORY",
    title: "让历史，与你对话。",
    description: "进入一段历史，面对角色、线索与选择，推演故事的另一种可能。",
    image: "/landing/world-history.webp",
    alt: "宣传片中的古代建筑与历史场景",
    topics: "生成世界 · 历史",
  },
  {
    id: "explore",
    number: "03",
    label: "LANGUAGE & PLAY",
    title: "在参与中，自然学会。",
    description: "在小镇开口说英语，在游戏中理解数学，让每次尝试推动故事向前。",
    image: "/landing/world-explore.webp",
    alt: "宣传片中融合自然、宇宙与建筑的探索世界",
    topics: "魔法英语小镇 · 走进数学花园",
  },
];
const questions = [
  {
    title: "我可以在 WeSmartFlow 学些什么？",
    answer:
      "你可以从一个具体问题开始自由辅导，也可以围绕一个主题生成沉浸课程。探索模式提供英语、数学、科学和历史等互动学习体验。",
  },
  {
    title: "需要先准备课程或资料吗？",
    answer:
      "不需要。带着一个想弄懂的问题，就可以开始。你也可以上传自己的学习资料，让 AI 围绕资料帮助你理解和练习。",
  },
  {
    title: "如何开始使用？",
    answer:
      "点击“开始学习”进入登录页，使用页面提供的登录方式登录，然后选择自由辅导、沉浸课程或探索模式。",
  },
  {
    title: "我可以参与开发或创作课程吗？",
    answer:
      "可以。WeSmartFlow 是开源项目，欢迎通过 GitHub 提交问题、贡献代码，或者制作自己的探索课程。仓库的探索主题开发指南提供了接入说明。",
  },
];
const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
let heroObserver;
let heroVisible = true;
let userPausedHero = false;
let userStartedHero = false;
let isFilmOpen = false;
let returnToMenuButton = false;
let isUnmounted = false;
let previousOverflow = "";
let previousPaddingRight = "";

function closeMobileMenu(restoreFocus = false) {
  mobileMenuOpen.value = false;
  if (restoreFocus) mobileMenuButton.value?.focus();
}

function jumpTo(id) {
  closeMobileMenu();
  const target = document.getElementById(id);
  target?.scrollIntoView({
    behavior: reducedMotion.matches ? "instant" : "smooth",
    block: "start",
  });
  target?.focus({ preventScroll: true });
}

function handleTabKey(event, index) {
  let next;
  if (event.key === "ArrowRight") next = (index + 1) % modes.length;
  else if (event.key === "ArrowLeft")
    next = (index + modes.length - 1) % modes.length;
  else if (event.key === "Home") next = 0;
  else if (event.key === "End") next = modes.length - 1;
  else return;
  event.preventDefault();
  activeMode.value = next;
  document.getElementById(`mode-${modes[next].id}`)?.focus();
}

function shouldPlayHero() {
  return (
    !isUnmounted &&
    heroVisible &&
    !document.hidden &&
    !isFilmOpen &&
    !userPausedHero &&
    (userStartedHero ||
      (!reducedMotion.matches && !navigator.connection?.saveData))
  );
}

function syncHeroPlayback() {
  const video = heroVideo.value;
  if (!video) return;
  if (!shouldPlayHero()) {
    video.pause();
  } else if (video.paused) {
    video
      .play()
      .then(() => {
        if (!shouldPlayHero()) video.pause();
      })
      .catch(() => {});
  }
}

function toggleHero() {
  if (!heroVideo.value) return;
  userPausedHero = !heroVideo.value.paused;
  if (!userPausedHero) userStartedHero = true;
  syncHeroPlayback();
}

async function openFilm() {
  if (isFilmOpen) return;
  returnToMenuButton = mobileMenuOpen.value;
  closeMobileMenu();
  isFilmOpen = true;
  syncHeroPlayback();
  filmOpened.value = true;
  await nextTick();
  if (isUnmounted) return;
  previousOverflow = document.body.style.overflow;
  previousPaddingRight = document.body.style.paddingRight;
  const scrollbarWidth =
    window.innerWidth - document.documentElement.clientWidth;
  if (scrollbarWidth > 0) {
    const bodyPadding =
      parseFloat(window.getComputedStyle(document.body).paddingRight) || 0;
    document.body.style.paddingRight = `${bodyPadding + scrollbarWidth}px`;
  }
  document.body.style.overflow = "hidden";
  filmDialog.value.showModal();
  filmVideo.value?.play().catch(() => {});
}

function closeFilm() {
  filmVideo.value?.pause();
  isFilmOpen = false;
  document.body.style.overflow = previousOverflow;
  document.body.style.paddingRight = previousPaddingRight;
  syncHeroPlayback();
  if (returnToMenuButton && !isUnmounted) mobileMenuButton.value?.focus();
  returnToMenuButton = false;
}

function handleMotionChange() {
  if (reducedMotion.matches) userStartedHero = false;
  syncHeroPlayback();
}

onMounted(() => {
  document.title = "WeSmartFlow — 让好奇，走得更远";
  reducedMotion.addEventListener("change", handleMotionChange);
  document.addEventListener("visibilitychange", syncHeroPlayback);
  heroObserver = new IntersectionObserver(([entry]) => {
    heroVisible = entry.isIntersecting;
    syncHeroPlayback();
  });
  if (heroVideo.value) heroObserver.observe(heroVideo.value);
  syncHeroPlayback();
});

onBeforeUnmount(() => {
  isUnmounted = true;
  heroObserver?.disconnect();
  reducedMotion.removeEventListener("change", handleMotionChange);
  document.removeEventListener("visibilitychange", syncHeroPlayback);
  if (filmDialog.value?.open) closeFilm();
  document.title = "WeSmartFlow";
});
</script>

<template>
  <div class="landing-page">
    <a
      class="skip-link"
      href="#landing-content"
      @click.prevent="jumpTo('landing-content')"
      >跳至正文</a
    >
    <header class="landing-header" @keydown.esc="closeMobileMenu(true)">
      <router-link to="/" class="wordmark" aria-label="WeSmartFlow 首页">
        <img src="/logo.png" alt="" width="32" height="32" />
        WeSmartFlow
      </router-link>
      <nav class="landing-nav" aria-label="首页导航">
        <a href="#learning" @click.prevent="jumpTo('learning')">学习方式</a>
        <a href="#worlds" @click.prevent="jumpTo('worlds')">探索世界</a>
        <button type="button" @click="openFilm">品牌短片</button>
        <a
          href="https://github.com/Tencent/WeSmartFlow"
          target="_blank"
          rel="noopener noreferrer"
          >开源社区 <span aria-hidden="true">↗</span></a
        >
      </nav>
      <div class="header-actions">
        <router-link to="/login" class="header-login"
          >开始学习 <span aria-hidden="true">↗</span></router-link
        >
        <button
          ref="mobileMenuButton"
          class="mobile-menu-button"
          type="button"
          :aria-expanded="mobileMenuOpen"
          aria-controls="mobile-navigation"
          :aria-label="mobileMenuOpen ? '关闭导航' : '展开导航'"
          @click="mobileMenuOpen = !mobileMenuOpen"
        >
          <span></span><span></span>
        </button>
      </div>
      <nav
        v-show="mobileMenuOpen"
        id="mobile-navigation"
        class="mobile-navigation"
        aria-label="移动端首页导航"
      >
        <a href="#learning" @click.prevent="jumpTo('learning')"
          >学习方式 <span aria-hidden="true">↗</span></a
        >
        <a href="#worlds" @click.prevent="jumpTo('worlds')"
          >探索世界 <span aria-hidden="true">↗</span></a
        >
        <button type="button" @click="openFilm">
          品牌短片 <span aria-hidden="true">▶</span>
        </button>
        <a
          href="https://github.com/Tencent/WeSmartFlow"
          target="_blank"
          rel="noopener noreferrer"
          @click="closeMobileMenu()"
          >开源社区 <span aria-hidden="true">↗</span></a
        >
      </nav>
    </header>

    <main id="landing-content" tabindex="-1">
      <section class="landing-hero" aria-labelledby="hero-title">
        <video
          ref="heroVideo"
          class="hero-video"
          src="/landing/hero.mp4"
          poster="/landing/hero-poster.webp"
          muted
          loop
          playsinline
          preload="none"
          aria-label="WeSmartFlow 学习世界背景短片"
          @play="isPlaying = true"
          @pause="isPlaying = false"
        ></video>
        <div class="hero-shade"></div>
        <div class="hero-caption">
          <span class="live-dot"></span> A WORLD OF CURIOSITY
        </div>
        <div class="hero-copy">
          <p class="eyebrow">YOUR CURIOSITY. IN MOTION.</p>
          <h1 id="hero-title">让好奇，<span>走得更远。</span></h1>
          <p class="hero-description">
            与 AI 一起理解、尝试、探索。<br
              class="mobile-break"
            />让每一次好奇，汇入你的知识世界。
          </p>
          <div class="hero-actions">
            <router-link to="/login" class="landing-button primary-button"
              >开始你的探索 <span aria-hidden="true">↗</span></router-link
            >
            <button
              type="button"
              class="landing-button film-button"
              @click="openFilm"
            >
              <span class="play-symbol" aria-hidden="true">▶</span> 观看短片
              <span class="film-duration">00:49</span>
            </button>
          </div>
        </div>
        <button
          class="hero-playback"
          type="button"
          :aria-label="isPlaying ? '暂停背景视频' : '播放背景视频'"
          @click="toggleHero"
        >
          <span aria-hidden="true">{{ isPlaying ? "Ⅱ" : "▶" }}</span>
        </button>
        <button class="hero-index" type="button" @click="jumpTo('learning')">
          向下探索 <span aria-hidden="true">↓</span>
        </button>
      </section>

      <div class="learning-strip" aria-label="学习理念">
        <p>每一种好奇，都有自己的打开方式。</p>
        <div><span>LEARN.</span><span>CONNECT.</span><span>EXPLORE.</span></div>
      </div>

      <section
        id="learning"
        tabindex="-1"
        class="landing-section learning-section"
        aria-labelledby="learning-title"
      >
        <div class="section-heading">
          <p class="eyebrow">01 / MADE FOR YOUR MIND</p>
          <div class="heading-row">
            <h2 id="learning-title">
              一种好奇。<br /><span>不止一种学法。</span>
            </h2>
            <p>
              问一个问题，深入一门课程，连接一片知识。<br />找到适合你的方式，让理解真正发生。
            </p>
          </div>
        </div>
        <div class="mode-tabs" role="tablist" aria-label="选择学习方式">
          <button
            v-for="(mode, index) in modes"
            :id="`mode-${mode.id}`"
            :key="mode.id"
            type="button"
            role="tab"
            :aria-selected="activeMode === index"
            aria-controls="learning-panel"
            :tabindex="activeMode === index ? 0 : -1"
            @click="activeMode = index"
            @keydown="handleTabKey($event, index)"
          >
            <span class="tab-number">0{{ index + 1 }}</span
            >{{ mode.label }}<span class="tab-arrow" aria-hidden="true">↗</span>
          </button>
        </div>
        <div
          id="learning-panel"
          class="mode-panel"
          role="tabpanel"
          :aria-labelledby="`mode-${currentMode.id}`"
          tabindex="0"
        >
          <div class="mode-info">
            <div>
              <span class="eyebrow">{{ currentMode.english }}</span>
              <h3>{{ currentMode.title }}</h3>
            </div>
            <p>{{ currentMode.description }}</p>
          </div>
          <div class="product-frame">
            <div class="product-frame-top" aria-hidden="true">
              <span class="frame-dots"><i></i><i></i><i></i></span
              ><span
                >WeSmartFlow <span class="frame-divider">/</span>
                {{ currentMode.label }}</span
              ><span class="frame-count"
                >0{{ activeMode + 1 }} <span>/ 03</span></span
              >
            </div>
            <div class="product-screen">
              <img
                v-for="(mode, index) in modes"
                :key="mode.id"
                :src="mode.image"
                :alt="mode.alt"
                :aria-hidden="activeMode !== index"
                :class="{ 'is-active': activeMode === index }"
                loading="lazy"
                width="1440"
                height="827"
              />
            </div>
          </div>
          <div class="mode-footer">
            <div class="mode-tags">
              <span v-for="tag in currentMode.tags" :key="tag">{{ tag }}</span>
            </div>
            <router-link to="/login"
              >亲自试一试 <span aria-hidden="true">↗</span></router-link
            >
          </div>
        </div>
      </section>

      <section
        id="worlds"
        tabindex="-1"
        class="worlds-section"
        aria-labelledby="worlds-title"
      >
        <div class="landing-section worlds-heading">
          <p class="eyebrow">02 / BEYOND THE CONVERSATION</p>
          <div class="heading-row">
            <h2 id="worlds-title">走进知识<br /><span>发生的现场。</span></h2>
            <p>
              故事、角色、实验与游戏。<br />学习，也可以是一场身临其境的探索。
            </p>
          </div>
        </div>
        <div class="world-grid">
          <router-link
            v-for="world in worlds"
            :key="world.id"
            to="/login"
            class="world-card"
            :aria-label="`${world.title} 登录后进入探索模式`"
          >
            <div class="world-media">
              <img
                :src="world.image"
                :alt="world.alt"
                width="1600"
                height="900"
                loading="lazy"
              /><span class="world-number"
                >{{ world.number }} / {{ world.label }}</span
              ><span class="world-arrow" aria-hidden="true">↗</span>
            </div>
            <div class="world-copy">
              <p class="world-topics">{{ world.topics }}</p>
              <h3>{{ world.title }}</h3>
              <p>{{ world.description }}</p>
            </div>
          </router-link>
        </div>
        <div class="worlds-bottom">
          <span>画面选自 WeSmartFlow 品牌短片</span
          ><router-link to="/login"
            >发现更多学习世界 <span aria-hidden="true">↗</span></router-link
          >
        </div>
      </section>

      <section
        class="landing-section manifesto"
        aria-labelledby="manifesto-title"
      >
        <p class="eyebrow">03 / LET KNOWLEDGE FLOW</p>
        <h2 id="manifesto-title">
          一次提问，是开始。<br /><span>每一次理解，</span
          ><br />都成为你的下一步。
        </h2>
        <div class="manifesto-bottom">
          <p>
            WeSmartFlow 把对话、课程、练习与知识图谱连接起来，<br
              class="desktop-break"
            />陪你把片刻的好奇，变成持续生长的理解。
          </p>
          <button type="button" class="text-button" @click="openFilm">
            观看我们的故事 <span aria-hidden="true">↗</span>
          </button>
        </div>
      </section>

      <section
        id="questions"
        class="landing-section faq-section"
        aria-labelledby="faq-title"
      >
        <div>
          <p class="eyebrow">A FEW THINGS TO KNOW</p>
          <h2 id="faq-title">开始之前。</h2>
        </div>
        <div class="faq-list">
          <details
            v-for="question in questions"
            :key="question.title"
            name="landing-faq"
          >
            <summary>
              {{ question.title }}<span aria-hidden="true">+</span>
            </summary>
            <p>{{ question.answer }}</p>
          </details>
        </div>
      </section>

      <section class="closing-section" aria-labelledby="closing-title">
        <p class="eyebrow">THE NEXT QUESTION IS YOURS.</p>
        <h2 id="closing-title">世界很大。<br />从你的下一个问题开始。</h2>
        <router-link to="/login" class="landing-button primary-button"
          >开始学习 <span aria-hidden="true">↗</span></router-link
        >
      </section>
    </main>

    <footer class="landing-footer">
      <div class="footer-top">
        <router-link to="/" class="footer-wordmark">WeSmartFlow</router-link>
        <p>让知识流动，让理解发生。</p>
      </div>
      <div class="footer-bottom">
        <span>© {{ new Date().getFullYear() }} WeSmartFlow</span>
        <nav aria-label="页脚导航">
          <button type="button" @click="jumpTo('learning')">学习方式</button
          ><a
            href="https://github.com/Tencent/WeSmartFlow"
            target="_blank"
            rel="noopener noreferrer"
            >GitHub ↗</a
          ><router-link to="/login">登录 ↗</router-link>
        </nav>
        <span>Built for curious minds.</span>
      </div>
    </footer>

    <dialog
      ref="filmDialog"
      class="film-dialog"
      aria-label="WeSmartFlow 品牌短片"
      @close="closeFilm"
      @click="(event) => event.target === filmDialog && filmDialog.close()"
    >
      <div class="film-dialog-header">
        <span>WeSmartFlow / 品牌短片</span
        ><button
          type="button"
          aria-label="关闭视频"
          @click="filmDialog.close()"
        >
          关闭 <span aria-hidden="true">×</span>
        </button>
      </div>
      <video
        v-if="filmOpened"
        ref="filmVideo"
        src="/landing/film.mp4"
        controls
        playsinline
        preload="metadata"
        aria-label="WeSmartFlow 完整品牌短片"
      ></video>
    </dialog>
  </div>
</template>

<style scoped>
.landing-page {
  --landing-bg: #080809;
  --landing-fg: #f4f2ef;
  --landing-muted: #a4a1ad;
  --landing-accent: #e0ddff;
  --landing-line: rgb(255 255 255 / 12%);
  --content-width: 1280px;
  --page-gutter: clamp(22px, 4.5vw, 72px);
  --page-inset: max(
    var(--page-gutter),
    calc((100% - var(--content-width)) / 2)
  );
  --section-space: clamp(76px, 8vw, 116px);
  --ease-out: cubic-bezier(0.22, 1, 0.36, 1);
  background: var(--landing-bg);
  color: var(--landing-fg);
  font-family: Inter, "PingFang SC", "Microsoft YaHei", sans-serif;
  font-size: 15px;
  min-height: 100svh;
  overflow: clip;
  -webkit-font-smoothing: antialiased;
}
.landing-page a {
  color: inherit;
  text-decoration: none;
}
.landing-page :where(button) {
  font: inherit;
  color: inherit;
  cursor: pointer;
}
.landing-page :focus-visible {
  outline: 2px solid var(--landing-accent);
  outline-offset: 6px;
}
.landing-page ::selection {
  background: var(--landing-accent);
  color: #101014;
}
.landing-page h1,
.landing-page h2,
.landing-page h3,
.landing-page p {
  overflow-wrap: break-word;
}
.landing-page :is(.heading-row, .mode-info) > * {
  min-width: 0;
}
.landing-page button {
  -webkit-tap-highlight-color: transparent;
}
.skip-link {
  position: fixed;
  top: -70px;
  left: 20px;
  z-index: 10;
  padding: 12px 20px;
  background: #19191e;
}
.skip-link:focus {
  top: 12px;
}
.landing-header {
  position: absolute;
  inset: 0 0 auto;
  z-index: 5;
  height: 88px;
  padding: 0 var(--page-inset);
  display: grid;
  grid-template-columns: 1fr auto 1fr;
  align-items: center;
  gap: 28px;
  border-bottom: 1px solid rgb(255 255 255 / 10%);
  background: linear-gradient(180deg, rgb(0 0 0 / 18%), transparent);
}
.wordmark {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  width: max-content;
  font-size: 21px;
  font-weight: 600;
  letter-spacing: -0.7px;
  white-space: nowrap;
}
.wordmark img {
  object-fit: contain;
  border-radius: 7px;
}
.landing-nav {
  display: flex;
  gap: clamp(22px, 2.4vw, 36px);
  align-items: center;
  white-space: nowrap;
}
.landing-nav button {
  background: none;
  border: 0;
}
.landing-nav a,
.landing-nav button {
  font-size: 13px;
  opacity: 0.82;
  transition: opacity 0.2s;
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-height: 44px;
  padding: 0;
}
.landing-nav :is(a, button)::after {
  position: absolute;
  right: 0;
  bottom: 5px;
  left: 0;
  height: 1px;
  background: var(--landing-accent);
  content: "";
  transform: scaleX(0);
  transform-origin: left;
  transition: transform 0.25s var(--ease-out);
}
.landing-nav :is(a, button):is(:hover, :focus-visible)::after {
  transform: scaleX(1);
}
.header-actions {
  justify-self: end;
  display: flex;
  align-items: center;
  gap: 8px;
}
.mobile-menu-button,
.mobile-navigation {
  display: none;
}
.landing-nav a:hover,
.landing-nav button:hover {
  opacity: 1;
}
.header-login {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 23px;
  min-height: 44px;
  font-size: 12px;
  font-weight: 500;
  border: 1px solid rgb(255 255 255 / 35%);
  padding: 10px 17px;
  border-radius: 6px;
  white-space: nowrap;
  transition:
    background 0.2s,
    border-color 0.2s;
}
.header-login:hover {
  background: rgb(255 255 255 / 12%);
}
.landing-hero {
  position: relative;
  min-height: 680px;
  height: 100svh;
  max-height: 1080px;
  display: flex;
  align-items: flex-end;
  justify-content: center;
  background: #06080f;
  isolation: isolate;
}
.hero-video {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 84%;
  object-fit: cover;
  object-position: center 45%;
}
.hero-shade {
  position: absolute;
  inset: 0;
  background: linear-gradient(
    180deg,
    rgb(0 0 0 / 35%) 0%,
    transparent 25%,
    rgb(8 8 9 / 10%) 45%,
    rgb(8 8 9 / 85%) 74%,
    #080809 94%
  );
  pointer-events: none;
}
.hero-caption {
  position: absolute;
  top: 120px;
  left: var(--page-inset);
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 10px;
  letter-spacing: 0.14em;
  color: #d6d8e5;
}
.live-dot {
  width: 5px;
  height: 5px;
  background: #e0ddff;
  border-radius: 50%;
}
.hero-copy {
  position: relative;
  z-index: 1;
  width: min(100%, 1040px);
  text-align: center;
  padding: 0 24px clamp(76px, 9svh, 100px);
  animation: hero-arrive 0.7s var(--ease-out) both;
}
.hero-copy h1 > span {
  white-space: nowrap;
}
@keyframes hero-arrive {
  from {
    opacity: 0;
    transform: translateY(14px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}
.eyebrow {
  font-size: 10px;
  letter-spacing: 0.2em;
  font-weight: 500;
  color: #b4b1be;
}
.hero-copy .eyebrow {
  margin-bottom: 18px;
}
.hero-copy h1 {
  font-size: clamp(46px, 5.3vw, 82px);
  line-height: 1.26;
  font-weight: 450;
  letter-spacing: -0.035em;
  margin-bottom: 22px;
  text-wrap: balance;
  text-shadow: 0 3px 30px rgb(0 0 0 / 20%);
}
.hero-description {
  color: #c0bdc8;
  font-size: 15px;
  line-height: 1.95;
  letter-spacing: 0.035em;
  text-wrap: pretty;
}
.mobile-break {
  display: none;
}
.hero-actions {
  display: flex;
  justify-content: center;
  gap: 12px;
  margin-top: 32px;
}
.hero-actions .landing-button {
  min-width: 186px;
}
.hero-actions .film-button {
  min-width: 180px;
}
.landing-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 24px;
  min-height: 50px;
  border-radius: 6px;
  padding: 14px 25px;
  font-size: 14px;
  font-weight: 500;
  border: 1px solid transparent;
  transition:
    background 0.25s,
    border-color 0.25s,
    box-shadow 0.25s,
    transform 0.3s var(--ease-out);
}
.landing-button:hover {
  transform: translateY(-2px);
}
.landing-page .primary-button {
  background: var(--landing-accent);
  color: #16151c;
}
.primary-button:hover {
  background: #eeecff;
}
.landing-page .primary-button:is(:hover, :focus-visible) {
  background: #eeecff;
  box-shadow: 0 4px 24px rgb(186 169 255 / 16%);
}
.landing-button:active {
  transform: translateY(0);
}
.header-login > span,
.primary-button > span,
.mode-footer a > span,
.worlds-bottom a > span,
.text-button > span {
  display: inline-block;
  transition: transform 0.3s var(--ease-out);
}
:is(
    .header-login,
    .primary-button,
    .mode-footer a,
    .worlds-bottom a,
    .text-button
  ):is(:hover, :focus-visible)
  > span {
  transform: translate(2px, -2px);
}
.hero-playback:is(:hover, :focus-visible) {
  background: rgb(224 221 255 / 12%);
  border-color: rgb(224 221 255 / 60%);
}
.hero-index > span {
  transition: transform 0.25s var(--ease-out);
}
.hero-index:is(:hover, :focus-visible) > span {
  transform: translateY(3px);
}
.film-button {
  background: rgb(25 24 31 / 48%);
  border-color: rgb(255 255 255 / 24%);
  gap: 12px;
  backdrop-filter: blur(12px);
}
.film-button:hover {
  background: #202024;
}
.play-symbol {
  font-size: 10px;
}
.film-duration {
  font-size: 10px;
  color: #9995a2;
  font-variant-numeric: tabular-nums;
}
.hero-playback {
  position: absolute;
  bottom: 30px;
  right: var(--page-inset);
  z-index: 2;
  display: grid;
  place-items: center;
  width: 44px;
  height: 44px;
  border: 1px solid rgb(255 255 255 / 22%);
  background: rgb(20 18 28 / 32%);
  border-radius: 50%;
  font-size: 12px;
  transition:
    border-color 0.2s,
    background 0.2s;
}
.hero-index {
  position: absolute;
  left: var(--page-inset);
  bottom: 30px;
  min-height: 44px;
  display: flex;
  align-items: center;
  font-size: 11px;
  letter-spacing: 0.1em;
  color: #b7b1c3;
  border: 0;
  background: none;
  padding: 0;
}
.hero-index span {
  margin-left: 20px;
}
.learning-strip {
  width: calc(100% - var(--page-gutter) * 2);
  max-width: var(--content-width);
  margin: 0 auto;
  padding: 34px 0 48px;
  text-align: center;
  border-bottom: 1px solid var(--landing-line);
}
.learning-strip p {
  color: #929096;
  font-size: 12px;
  margin-bottom: 22px;
  letter-spacing: 0.1em;
}
.learning-strip > div {
  display: flex;
  justify-content: center;
  gap: clamp(32px, 7vw, 104px);
  font-size: clamp(17px, 2.3vw, 30px);
  font-weight: 500;
  letter-spacing: -0.055em;
  color: #b4b2b9;
}
.landing-section {
  width: calc(100% - var(--page-gutter) * 2);
  max-width: var(--content-width);
  margin: 0 auto;
  padding: var(--section-space) 0;
  scroll-margin-top: 28px;
}
.section-heading .eyebrow,
.worlds-heading > .eyebrow {
  margin-bottom: 32px;
}
.heading-row {
  display: grid;
  grid-template-columns: 1.15fr 1fr;
  align-items: end;
  gap: clamp(32px, 6vw, 96px);
}
.heading-row h2 {
  font-size: clamp(38px, 4.1vw, 62px);
  line-height: 1.3;
  font-weight: 400;
  letter-spacing: -0.035em;
  text-wrap: balance;
}
.heading-row h2 span {
  color: #9d9aa5;
}
.heading-row > p {
  justify-self: end;
  width: min(100%, 370px);
  color: var(--landing-muted);
  font-size: 14px;
  line-height: 2;
  padding-bottom: 7px;
  text-wrap: pretty;
}
.section-heading > .eyebrow,
.worlds-heading > .eyebrow,
.manifesto > .eyebrow {
  display: flex;
  align-items: center;
  gap: 14px;
}
.section-heading > .eyebrow::before,
.worlds-heading > .eyebrow::before,
.manifesto > .eyebrow::before {
  content: "";
  width: 22px;
  height: 1px;
  background: #7f778e;
}
.mode-tabs {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 4px;
  margin-top: 48px;
  padding: 5px;
  border: 1px solid var(--landing-line);
  border-radius: 9px;
  background: #101013;
}
.mode-tabs button {
  min-width: 0;
  text-align: left;
  display: flex;
  align-items: center;
  gap: 15px;
  padding: 18px 22px;
  border: 1px solid transparent;
  border-radius: 5px;
  background: transparent;
  color: #a7a2b2;
  transition:
    background 0.25s,
    color 0.25s,
    border-color 0.25s;
}
.mode-tabs button:hover {
  background: #17161c;
}
.mode-tabs button[aria-selected="true"] {
  color: #eeebff;
  background: #24212f;
  border-color: #474153;
  box-shadow: 0 2px 8px rgb(0 0 0 / 14%);
}
.tab-number {
  font-size: 10px;
  font-variant-numeric: tabular-nums;
  opacity: 0.6;
}
.tab-arrow {
  margin-left: auto;
}
.mode-info {
  display: grid;
  grid-template-columns: 1.15fr 1fr;
  gap: clamp(32px, 5vw, 76px);
  min-height: 148px;
  padding: 32px 0;
  align-items: center;
}
.mode-info .eyebrow {
  font-size: 9px;
  color: #8f899e;
}
.mode-info h3 {
  font-weight: 400;
  font-size: clamp(21px, 1.9vw, 27px);
  line-height: 1.55;
  letter-spacing: -0.025em;
  margin-top: 10px;
  text-wrap: pretty;
}
.mode-info > p {
  justify-self: end;
  width: min(100%, 390px);
  color: var(--landing-muted);
  font-size: 13px;
  line-height: 1.95;
  text-wrap: pretty;
}
.product-frame {
  overflow: hidden;
  border-radius: 10px;
  border: 1px solid #393440;
  background: #15131b;
  padding: 0 12px 12px;
  box-shadow:
    0 18px 60px rgb(0 0 0 / 22%),
    0 1px 0 rgb(255 255 255 / 4%) inset;
}
.product-frame img {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: contain;
  display: block;
  opacity: 0;
  transition: opacity 0.24s ease;
}
.product-frame-top {
  display: grid;
  grid-template-columns: 1fr auto 1fr;
  align-items: center;
  gap: 12px;
  height: 42px;
  padding: 0 6px;
  color: #a29aaa;
  font-size: 10px;
  letter-spacing: 0.025em;
}
.frame-dots {
  display: flex;
  gap: 5px;
}
.frame-dots i {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: #5e566a;
}
.frame-dots i:first-child {
  background: #a697b8;
}
.frame-dots i:nth-child(2) {
  background: #81748e;
}
.frame-divider {
  padding: 0 7px;
  color: #6f647d;
}
.frame-count {
  justify-self: end;
  font-variant-numeric: tabular-nums;
}
.frame-count > span {
  color: #6f647d;
}
.product-screen {
  position: relative;
  overflow: hidden;
  aspect-ratio: 1440 / 827;
  border: 1px solid rgb(255 255 255 / 9%);
  border-radius: 5px;
  background: #f5f5f8;
}
.product-screen img.is-active {
  opacity: 1;
}
.mode-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding-top: 20px;
  gap: 16px;
}
.mode-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 22px;
  color: #a7a0b4;
  font-size: 11px;
}
.mode-tags span::before {
  content: "·";
  color: var(--landing-accent);
  margin-right: 7px;
}
.mode-footer > a,
.worlds-bottom > a {
  color: #e0ddff;
  font-size: 12px;
}
.mode-footer > a span,
.worlds-bottom > a span {
  margin-left: 20px;
}
.worlds-section {
  padding-bottom: var(--section-space);
  background: #101012;
  border-top: 1px solid rgb(255 255 255 / 6%);
  border-bottom: 1px solid rgb(255 255 255 / 6%);
  scroll-margin-top: 20px;
}
.worlds-heading {
  padding-bottom: 50px;
}
.world-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: clamp(20px, 2.3vw, 32px);
  width: calc(100% - var(--page-gutter) * 2);
  max-width: var(--content-width);
  margin: auto;
}
.world-media {
  position: relative;
  overflow: hidden;
  aspect-ratio: 16 / 11;
  border-radius: 8px;
  background: #17151d;
  border: 1px solid rgb(255 255 255 / 12%);
  isolation: isolate;
}
.world-media::after {
  content: "";
  position: absolute;
  inset: 0;
  background: linear-gradient(180deg, rgb(0 0 0 / 45%), transparent 45%);
  pointer-events: none;
}
.world-media img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  transition: transform 0.5s;
}
.world-card:hover img {
  transform: scale(1.04);
}
.world-number {
  position: absolute;
  top: 23px;
  left: 24px;
  z-index: 1;
  font-size: 9px;
  letter-spacing: 0.11em;
  color: #e7e3ed;
}
.world-arrow {
  position: absolute;
  bottom: 18px;
  right: 18px;
  z-index: 1;
  width: 44px;
  height: 44px;
  display: grid;
  place-items: center;
  border: 1px solid rgb(255 255 255 / 40%);
  border-radius: 50%;
  background: rgb(0 0 0 / 24%);
  backdrop-filter: blur(8px);
  font-size: 20px;
  transition:
    background 0.25s,
    color 0.25s,
    transform 0.3s var(--ease-out);
}
.world-copy {
  padding: 25px 0 24px;
  border-bottom: 1px solid var(--landing-line);
}
.world-card {
  display: flex;
  flex-direction: column;
  min-width: 0;
  border-radius: 8px;
}
.world-copy {
  flex: 1;
}
.world-card:is(:hover, :focus-visible) .world-arrow {
  color: #17141e;
  background: var(--landing-accent);
  border-color: var(--landing-accent);
  transform: translate(2px, -2px);
}
.world-card:focus-visible img {
  transform: scale(1.04);
}
.world-copy .world-topics {
  font-size: 10px;
  color: #9c95ae;
  margin-bottom: 11px;
}
.world-copy h3 {
  font-size: clamp(22px, 2vw, 28px);
  line-height: 1.5;
  font-weight: 400;
  letter-spacing: -0.03em;
  margin-bottom: 10px;
  text-wrap: balance;
}
.world-copy > p:last-child {
  font-size: 13px;
  line-height: 1.95;
  min-height: 3.9em;
  color: #a6a1af;
  text-wrap: pretty;
}
.worlds-bottom {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
  width: calc(100% - var(--page-gutter) * 2);
  max-width: var(--content-width);
  margin: 32px auto 0;
}
.worlds-bottom > span {
  color: #827d8a;
  font-size: 10px;
}
.manifesto {
  padding-top: var(--section-space);
  padding-bottom: var(--section-space);
}
.manifesto > .eyebrow {
  margin-bottom: 46px;
}
.manifesto h2 {
  font-weight: 400;
  font-size: clamp(38px, 4.6vw, 66px);
  line-height: 1.45;
  letter-spacing: -0.035em;
  text-wrap: balance;
}
.manifesto h2 > span {
  color: #e0ddff;
}
.manifesto-bottom {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 40px;
  margin-top: 44px;
}
.manifesto-bottom p {
  font-size: 14px;
  color: var(--landing-muted);
  line-height: 1.95;
}
.text-button {
  border: 0;
  border-bottom: 1px solid #6e687a;
  padding: 12px 0;
  background: none;
  font-size: 13px;
  white-space: nowrap;
}
.text-button span {
  margin-left: 36px;
}
.faq-section {
  border-top: 1px solid var(--landing-line);
  display: grid;
  grid-template-columns: 1fr 1.3fr;
  gap: 8%;
  padding-top: 76px;
  padding-bottom: 88px;
}
.faq-section h2 {
  font-size: 42px;
  font-weight: 400;
  letter-spacing: -0.05em;
  margin-top: 22px;
}
.faq-list details {
  border-bottom: 1px solid var(--landing-line);
}
.faq-list details:first-child {
  border-top: 1px solid var(--landing-line);
}
.faq-list summary {
  cursor: pointer;
  list-style: none;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
  min-height: 78px;
  padding: 23px 4px;
  font-size: 14px;
  transition: color 0.2s;
}
.faq-list summary::-webkit-details-marker {
  display: none;
}
.faq-list summary span {
  flex-shrink: 0;
  width: 28px;
  height: 28px;
  display: grid;
  place-items: center;
  border: 1px solid #48424f;
  border-radius: 50%;
  font-size: 19px;
  font-weight: 300;
  line-height: 1;
  color: #bcb5cc;
  transition:
    transform 0.25s,
    background 0.25s;
}
.faq-list details[open] summary span {
  transform: rotate(45deg);
  background: #282331;
}
.faq-list summary:is(:hover, :focus-visible),
.faq-list details[open] summary {
  color: var(--landing-accent);
}
.faq-list details > p {
  font-size: 13px;
  color: var(--landing-muted);
  line-height: 1.95;
  padding: 0 35px 24px 0;
}
.closing-section {
  position: relative;
  width: calc(100% - var(--page-gutter) * 2);
  max-width: var(--content-width);
  margin: 0 auto 76px;
  padding: 78px 24px;
  text-align: center;
  background:
    radial-gradient(ellipse at 50% 0%, rgb(131 113 179 / 13%), transparent 65%),
    #19171f;
  border: 1px solid #37323f;
  border-radius: 10px;
  box-shadow: 0 1px 0 rgb(255 255 255 / 5%) inset;
}
.closing-section > .eyebrow {
  color: #a7a0b7;
}
.closing-section h2 {
  font-size: clamp(31px, 3.8vw, 57px);
  line-height: 1.4;
  font-weight: 400;
  letter-spacing: -0.04em;
  margin: 25px 0 32px;
}
.landing-footer {
  width: calc(100% - var(--page-gutter) * 2);
  max-width: var(--content-width);
  margin: 0 auto;
  padding: 0 0 28px;
}
.footer-top {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  padding-bottom: 34px;
  border-bottom: 1px solid var(--landing-line);
  gap: 28px;
}
.footer-wordmark {
  font-size: clamp(38px, 7.1vw, 102px);
  line-height: 1.1;
  letter-spacing: -0.055em;
  font-weight: 500;
}
.footer-top > p {
  font-size: 13px;
  color: #a29cae;
  padding-bottom: 6px;
}
.footer-bottom {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  padding-top: 28px;
  font-size: 10px;
  color: #928d9c;
}
.footer-bottom nav {
  display: flex;
  align-items: center;
  gap: 28px;
}
.footer-bottom button {
  padding: 0;
  border: 0;
  background: none;
}
.footer-bottom > span:last-child {
  letter-spacing: 0.05em;
}
.film-dialog {
  position: fixed;
  inset: 0;
  width: min(1100px, calc(100vw - 48px));
  max-width: none;
  max-height: calc(100svh - 48px);
  margin: auto;
  border: 1px solid #49414f;
  border-radius: 12px;
  background: #121015;
  color: #fff;
  padding: 12px;
  box-shadow: 0 32px 120px rgb(0 0 0 / 60%);
}
.film-dialog::backdrop {
  background: rgb(0 0 0 / 88%);
  backdrop-filter: blur(12px);
}
.film-dialog-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  margin-bottom: 10px;
  padding-left: 6px;
  font-size: 12px;
  color: #b4b1be;
}
.film-dialog-header button {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  min-height: 44px;
  background: none;
  border: 1px solid transparent;
  border-radius: 5px;
  padding: 6px 12px;
  transition: background 0.2s;
}
.film-dialog-header button span {
  font-size: 22px;
  margin-left: 10px;
}
.film-dialog-header button:is(:hover, :focus-visible) {
  background: #282331;
}
.film-dialog video {
  display: block;
  width: 100%;
  max-height: 76svh;
  border-radius: 5px;
  background: #000;
}
@media (761px <= width <= 1100px) {
  .landing-header {
    grid-template-columns: auto 1fr auto;
    gap: 22px;
  }
  .landing-nav {
    justify-content: center;
    gap: 20px;
  }
  .landing-nav a,
  .landing-nav button {
    font-size: 12px;
  }
  .landing-nav > a:last-child {
    display: none;
  }
  .wordmark {
    font-size: 19px;
  }
  .header-login {
    gap: 12px;
  }
  .heading-row {
    gap: 32px;
  }
  .heading-row h2 {
    font-size: 42px;
  }
  .mode-info {
    grid-template-columns: 1fr;
    gap: 14px;
    min-height: 182px;
  }
  .mode-info > p {
    justify-self: start;
    width: 100%;
    min-height: 3.9em;
  }
  .world-grid {
    gap: 22px;
  }
  .world-media {
    aspect-ratio: 4 / 3;
  }
  .world-number {
    left: 14px;
    top: 18px;
    font-size: 8px;
  }
  .world-copy h3 {
    font-size: 21px;
  }
  .world-copy > p:last-child {
    font-size: 12px;
  }
  .footer-bottom > span:last-child {
    display: none;
  }
}
@media (width <= 760px) {
  .landing-header {
    height: 74px;
    padding: 0 var(--page-gutter);
    grid-template-columns: 1fr auto;
    gap: 12px;
  }
  .wordmark {
    font-size: 18px;
    gap: 7px;
  }
  .wordmark img {
    width: 26px;
    height: 26px;
  }
  .landing-nav {
    display: none;
  }
  .mobile-menu-button {
    width: 44px;
    height: 44px;
    flex-shrink: 0;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 6px;
    padding: 0;
    border: 1px solid rgb(255 255 255 / 25%);
    border-radius: 6px;
    background: rgb(14 12 20 / 30%);
  }
  .mobile-menu-button span {
    display: block;
    width: 16px;
    height: 1px;
    background: currentColor;
    transition: transform 0.2s;
  }
  .mobile-menu-button[aria-expanded="true"] span:first-child {
    transform: translateY(3.5px) rotate(45deg);
  }
  .mobile-menu-button[aria-expanded="true"] span:last-child {
    transform: translateY(-3.5px) rotate(-45deg);
  }
  .mobile-navigation {
    position: absolute;
    inset: calc(100% + 8px) var(--page-gutter) auto;
    display: grid;
    padding: 8px 18px;
    border: 1px solid #49424f;
    border-radius: 8px;
    background: rgb(16 14 21 / 96%);
    backdrop-filter: blur(20px);
    box-shadow: 0 16px 48px rgb(0 0 0 / 38%);
  }
  .mobile-navigation :is(a, button) {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 24px;
    min-height: 52px;
    padding: 12px 0;
    background: none;
    border: 0;
    border-bottom: 1px solid var(--landing-line);
    font-size: 13px;
  }
  .mobile-navigation :last-child {
    border-bottom: 0;
  }
  .mobile-navigation :is(a, button) > span {
    color: #a79cb9;
    font-size: 12px;
  }
  .header-login {
    padding: 8px 12px;
    gap: 12px;
    font-size: 12px;
  }
  .landing-hero {
    min-height: 640px;
    max-height: 1000px;
  }
  .hero-caption {
    top: 98px;
    left: var(--page-gutter);
    font-size: 8px;
  }
  .hero-video {
    height: 72%;
    object-position: 50% 35%;
  }
  .hero-shade {
    background: linear-gradient(
      180deg,
      rgb(0 0 0 / 30%),
      transparent 30%,
      rgb(8 8 9 / 60%) 50%,
      #080809 74%
    );
  }
  .hero-copy {
    padding: 0 var(--page-gutter) 86px;
    width: 100%;
  }
  .hero-copy h1 {
    font-size: clamp(43px, 8vw, 60px);
    letter-spacing: -0.035em;
  }
  .hero-copy h1 span {
    display: block;
  }
  .hero-description {
    font-size: 13px;
  }
  .mobile-break {
    display: inline;
  }
  .hero-actions {
    gap: 8px;
    margin-top: 26px;
  }
  .hero-actions .landing-button {
    min-width: 0;
  }
  .landing-button {
    padding: 13px 17px;
    font-size: 13px;
    gap: 12px;
  }
  .film-duration {
    display: none;
  }
  .hero-index {
    left: var(--page-gutter);
    bottom: max(24px, env(safe-area-inset-bottom));
  }
  .hero-playback {
    right: var(--page-gutter);
    bottom: max(24px, env(safe-area-inset-bottom));
  }
  .learning-strip {
    padding: 28px 0 38px;
  }
  .learning-strip p {
    font-size: 11px;
    letter-spacing: 0.02em;
  }
  .landing-section {
    padding: 70px 0;
  }
  .heading-row {
    grid-template-columns: 1fr;
    align-items: start;
    gap: 24px;
  }
  .heading-row h2 {
    font-size: 38px;
  }
  .heading-row > p {
    justify-self: start;
    font-size: 13px;
  }
  .mode-tabs {
    margin-top: 32px;
  }
  .mode-tabs button {
    padding: 14px 9px;
    gap: 7px;
    font-size: 12px;
  }
  .tab-arrow {
    display: none;
  }
  .mode-info {
    grid-template-columns: 1fr;
    align-items: start;
    min-height: 196px;
    padding: 26px 0;
    gap: 14px;
  }
  .mode-info h3 {
    font-size: 21px;
    min-height: 3.1em;
  }
  .mode-info > p {
    justify-self: start;
    width: 100%;
    font-size: 13px;
    min-height: 5.85em;
  }
  .product-frame-top {
    height: 34px;
    font-size: 9px;
    gap: 8px;
  }
  .frame-dots {
    gap: 4px;
  }
  .frame-dots i {
    width: 4px;
    height: 4px;
  }
  .product-frame {
    padding: 0 6px 6px;
    border-radius: 7px;
  }
  .mode-footer {
    align-items: flex-start;
    flex-direction: column;
  }
  .mode-tags {
    font-size: 10px;
    gap: 12px;
  }
  .worlds-section {
    padding-bottom: 60px;
  }
  .worlds-heading {
    padding-bottom: 36px;
  }
  .world-grid {
    grid-template-columns: 1fr;
    gap: 34px;
  }
  .world-media {
    aspect-ratio: 16 / 10;
  }
  .world-copy {
    padding: 18px 0 22px;
  }
  .world-copy h3 {
    font-size: 25px;
  }
  .worlds-bottom {
    flex-wrap: wrap;
    gap: 20px;
    margin-top: 36px;
  }
  .manifesto h2 {
    font-size: clamp(31px, 7.5vw, 42px);
  }
  .manifesto-bottom {
    flex-direction: column;
    align-items: flex-start;
    gap: 24px;
    margin-top: 26px;
  }
  .manifesto-bottom p {
    font-size: 13px;
  }
  .desktop-break {
    display: none;
  }
  .faq-section {
    grid-template-columns: 1fr;
    gap: 32px;
  }
  .faq-section h2 {
    font-size: 34px;
    margin-top: 16px;
  }
  .faq-list summary {
    font-size: 13px;
    min-height: 74px;
    gap: 16px;
  }
  .closing-section {
    margin: 0 auto 52px;
    padding: 55px 18px;
  }
  .closing-section h2 {
    font-size: 29px;
  }
  .closing-section .eyebrow {
    font-size: 8px;
  }
  .landing-footer {
    padding: 0 0 26px;
  }
  .footer-top {
    flex-direction: column;
    align-items: flex-start;
    gap: 16px;
    padding-bottom: 26px;
  }
  .footer-wordmark {
    font-size: clamp(36px, 9vw, 58px);
  }
  .footer-top > p {
    font-size: 11px;
  }
  .footer-bottom {
    flex-wrap: wrap;
    font-size: 9px;
  }
  .footer-bottom nav {
    gap: 20px;
  }
  .footer-bottom > span:last-child {
    display: none;
  }
  .film-dialog {
    width: calc(100vw - 24px);
    max-height: calc(100svh - 24px);
    padding: 8px;
  }
  .film-dialog-header {
    font-size: 11px;
  }
  .film-dialog-header button {
    padding: 4px 8px;
  }
  .film-dialog-header button span {
    margin-left: 0;
  }
}
@media (width <= 380px) {
  .wordmark {
    font-size: 16px;
  }
  .wordmark img {
    width: 25px;
    height: 25px;
  }
  .header-login {
    padding: 8px 10px;
  }
  .header-login > span {
    display: none;
  }
  .hero-copy h1 {
    font-size: 41px;
  }
  .hero-actions .landing-button {
    padding: 13px 14px;
    font-size: 12px;
  }
  .mode-tabs {
    gap: 2px;
    padding: 4px;
  }
  .mode-tabs button {
    gap: 6px;
    padding-inline: 7px;
  }
  .tab-number {
    font-size: 8px;
  }
  .closing-section h2 {
    font-size: 26px;
  }
}
@media (height <= 720px) and (width >= 761px) {
  .landing-hero {
    min-height: 600px;
  }
  .hero-copy {
    padding-bottom: 68px;
  }
  .hero-copy h1 {
    font-size: clamp(44px, 5vw, 68px);
    margin-bottom: 16px;
  }
  .hero-copy .eyebrow {
    margin-bottom: 14px;
  }
  .hero-actions {
    margin-top: 24px;
  }
  .hero-caption {
    top: 112px;
  }
  .hero-index,
  .hero-playback {
    bottom: 18px;
  }
}
@media (height <= 700px) and (width <= 760px) {
  .landing-hero {
    min-height: 580px;
  }
  .hero-copy {
    padding-bottom: 78px;
  }
  .hero-copy h1 {
    font-size: 40px;
    margin-bottom: 16px;
  }
  .hero-copy .eyebrow {
    margin-bottom: 12px;
  }
  .hero-actions {
    margin-top: 20px;
  }
}
@media (prefers-reduced-motion: reduce) {
  .landing-page *,
  .landing-page *::before,
  .landing-page *::after {
    transition: none !important;
    animation: none !important;
    scroll-behavior: auto !important;
  }
}
</style>
