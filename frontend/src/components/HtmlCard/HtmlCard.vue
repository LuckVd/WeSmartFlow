<template>
  <div ref="rootRef" class="html-card-root" :class="{ 'is-compact': compact }">
    <!-- 加载中 -->
    <div v-if="loading" class="html-card-loading">
      <div class="html-card-spinner"></div>
      <span>正在加载卡片...</span>
    </div>

    <!-- 错误 -->
    <div v-if="error" class="html-card-error">
      <svg
        width="14"
        height="14"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="2"
      >
        <circle cx="12" cy="12" r="10" />
        <line x1="12" y1="8" x2="12" y2="12" />
        <line x1="12" y1="16" x2="12.01" y2="16" />
      </svg>
      <span>{{ error }}</span>
      <button class="html-card-btn" @click="load">重试</button>
    </div>

    <!-- 可滚动缩放视口：自动适配 + 用户手动放大查看局部 -->
    <div ref="viewportRef" class="html-card-viewport">
      <div
        class="html-card-stage"
        :style="{
          width: naturalW * effectiveScale + 'px',
          height: naturalH * effectiveScale + 'px',
          visibility: loading || !sizeReady ? 'hidden' : 'visible',
        }"
      >
        <div
          class="html-card-scaler"
          :style="{
            width: naturalW + 'px',
            height: naturalH + 'px',
            transform: `scale(${effectiveScale})`,
          }"
        >
          <iframe
            ref="iframeRef"
            class="html-card-iframe"
            scrolling="no"
            sandbox="allow-scripts allow-same-origin allow-popups allow-popups-to-escape-sandbox"
            @load="onIframeLoad"
          ></iframe>
        </div>
      </div>
    </div>

    <div
      v-if="showZoomControls && !loading && !error && sizeReady"
      class="html-card-zoom-controls"
    >
      <span class="zoom-label">缩放</span>
      <input
        v-model.number="userZoomPct"
        class="zoom-slider"
        type="range"
        min="80"
        max="220"
        step="5"
        aria-label="卡片缩放"
      />
      <span class="zoom-value">{{ userZoomPct }}%</span>
      <button class="zoom-reset" type="button" @click="resetZoom">适配</button>
    </div>

    <!-- 选中文本气泡 -->
    <Transition name="bubble">
      <div
        v-if="selectionBubble.visible"
        class="ask-ai-bubble"
        :style="{
          left: selectionBubble.x + 'px',
          top: selectionBubble.y + 'px',
        }"
        @mousedown.prevent
        @click="openAskPanel"
      >
        <svg
          width="12"
          height="12"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2.5"
        >
          <path
            d="M12 2a10 10 0 0 1 10 10c0 5.52-4.48 10-10 10S2 17.52 2 12 6.48 2 12 2z"
          />
          <path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3" />
          <line x1="12" y1="17" x2="12.01" y2="17" />
        </svg>
        问AI
      </div>
    </Transition>

    <!-- AI 解释浮窗 -->
    <Transition name="panel">
      <div v-if="askPanel.visible" class="ask-ai-panel" @mousedown.stop>
        <!-- 浮窗头部 -->
        <div class="aap-header">
          <div class="aap-title">
            <svg
              width="13"
              height="13"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
            >
              <circle cx="12" cy="12" r="10" />
              <path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3" />
              <line x1="12" y1="17" x2="12.01" y2="17" />
            </svg>
            AI 解释
          </div>
          <button class="aap-close" @click="closeAskPanel">
            <svg
              width="13"
              height="13"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
            >
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>

        <!-- 选中内容预览 -->
        <div class="aap-selected-text">
          <span class="aap-selected-label">选中内容</span>
          <span class="aap-selected-content">{{ askPanel.selectedText }}</span>
        </div>

        <!-- 回复区域 -->
        <div ref="askBodyRef" class="aap-body">
          <!-- 加载中 -->
          <div v-if="askPanel.loading && !askPanel.reply" class="aap-thinking">
            <div class="aap-dots"><span /><span /><span /></div>
            <span>正在思考...</span>
          </div>
          <!-- 流式回复 -->
          <div
            v-else-if="askPanel.reply"
            class="aap-reply"
            v-html="renderMd(askPanel.reply)"
          ></div>
          <!-- 错误 -->
          <div v-else-if="askPanel.error" class="aap-error">
            {{ askPanel.error }}
          </div>
        </div>

        <!-- 底部操作 -->
        <div class="aap-footer">
          <button v-if="!askPanel.loading" class="aap-btn-retry" @click="doAsk">
            <svg
              width="11"
              height="11"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2.5"
            >
              <polyline points="1 4 1 10 7 10" />
              <path d="M3.51 15a9 9 0 1 0 .49-3.5" />
            </svg>
            重新解释
          </button>
          <span v-else class="aap-loading-hint">生成中...</span>
        </div>
      </div>
    </Transition>
  </div>
</template>

<script setup>
import {
  computed,
  ref,
  watch,
  onMounted,
  onBeforeUnmount,
  nextTick,
} from "vue";
import { api } from "../../api/base.js";
import { renderMd } from "../../composables/useMarkdown.js";
import { llmApi } from "../../api/llm.js";

const props = defineProps({
  fileId: { type: String, required: true },
  title: { type: String, default: "" },
  script: { type: String, default: "" },
  showHeader: { type: Boolean, default: true },
  /** 缩略图/只读预览模式：隐藏缩放控件、禁用交互，只展示主体内容 */
  compact: { type: Boolean, default: false },
  /** 传入当前会话 ID，用于「问AI」功能；不传则不显示气泡 */
  sessionId: { type: String, default: "" },
});

const emit = defineEmits(["loaded", "error"]);

const rootRef = ref(null);
const viewportRef = ref(null);
const iframeRef = ref(null);
const loading = ref(true);
const error = ref("");
const sizeReady = ref(false);

const DEFAULT_NATURAL_WIDTH = 900;
const DEFAULT_NATURAL_HEIGHT = 600;

const naturalW = ref(DEFAULT_NATURAL_WIDTH);
const naturalH = ref(DEFAULT_NATURAL_HEIGHT);
const scale = ref(1);
const userZoomPct = ref(100);
const compact = computed(() => props.compact || props.showHeader === false);
const showZoomControls = computed(() => !compact.value);
const effectiveScale = computed(() => scale.value * (userZoomPct.value / 100));

// ── 选中文本气泡 ──────────────────────────────────────────────────
const selectionBubble = ref({ visible: false, x: 0, y: 0, text: "" });

// ── AI 解释浮窗 ───────────────────────────────────────────────────
const askPanel = ref({
  visible: false,
  selectedText: "",
  reply: "",
  loading: false,
  error: "",
});
const askBodyRef = ref(null);
let askAbortController = null;

function openAskPanel() {
  selectionBubble.value.visible = false;
  askPanel.value = {
    visible: true,
    selectedText: selectionBubble.value.text,
    reply: "",
    loading: false,
    error: "",
  };
  nextTick(() => doAsk());
}

function closeAskPanel() {
  askPanel.value.visible = false;
  askAbortController?.abort();
  askAbortController = null;
}

async function doAsk() {
  if (!askPanel.value.selectedText) return;
  askAbortController?.abort();
  askPanel.value.reply = "";
  askPanel.value.error = "";
  askPanel.value.loading = true;

  askAbortController = llmApi.quickAsk(
    {
      question: `请解释以下内容：\n\n"${askPanel.value.selectedText}"`,
      context: "",
    },
    {
      onTextChunk: (delta) => {
        askPanel.value.reply += delta;
        nextTick(() => {
          if (askBodyRef.value)
            askBodyRef.value.scrollTop = askBodyRef.value.scrollHeight;
        });
      },
      onDone: () => {
        askPanel.value.loading = false;
      },
      onError: (err) => {
        askPanel.value.loading = false;
        askPanel.value.error = err.message || "请求失败，请重试";
      },
    },
  );
}

// ── 缩放计算 ──────────────────────────────────────────────────────
function updateScale() {
  const viewport = viewportRef.value || rootRef.value;
  if (!viewport) return;
  const { clientWidth: cw } = viewport;
  if (!cw) return;
  // 默认只按宽度贴合 frame：高度超出时交给外层视口滚动，避免为了塞进高度而把卡片缩得很窄。
  scale.value = Math.max(0.05, (cw - 1) / naturalW.value);
}

function resetZoom() {
  userZoomPct.value = 100;
  nextTick(() => {
    if (viewportRef.value) {
      viewportRef.value.scrollLeft = 0;
      viewportRef.value.scrollTop = 0;
    }
    updateScale();
  });
}

function isRootMeasurable() {
  const root = rootRef.value;
  return Boolean(
    root &&
    root.offsetWidth > 0 &&
    root.offsetHeight > 0 &&
    root.getClientRects().length > 0,
  );
}

let resizeRequestTimer = null;

function requestIframeResize(delay = 0) {
  clearTimeout(resizeRequestTimer);
  resizeRequestTimer = setTimeout(() => {
    if (!isRootMeasurable() || !iframeRef.value?.contentWindow) return;
    iframeRef.value.contentWindow.postMessage({ type: "requestResize" }, "*");
    updateScale();
  }, delay);
}

let resizeObserver = null;
let wasRootMeasurable = false;

function initResizeObserver() {
  resizeObserver?.disconnect();
  resizeObserver = new ResizeObserver(() => {
    const measurable = isRootMeasurable();
    updateScale();
    // Safari 会把 display:none 下的 iframe 排版成极窄、极高的页面。
    // 卡片从 v-show 的隐藏状态恢复后，必须基于可见布局重新测量。
    if (measurable && !wasRootMeasurable) requestIframeResize(50);
    wasRootMeasurable = measurable;
  });
  if (rootRef.value) resizeObserver.observe(rootRef.value);
}

let resizeTimer = null;

function handleMessage(event) {
  if (!iframeRef.value || event.source !== iframeRef.value.contentWindow)
    return;
  const msg = event.data;

  // 尺寸上报
  if (
    msg?.type === "resize" &&
    Number.isFinite(msg.height) &&
    Number.isFinite(msg.width) &&
    msg.height > 0 &&
    msg.width > 0
  ) {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => {
      // v-show 会让未选中的主卡片在 display:none 下继续加载。
      // WebKit 此时上报的 scrollWidth/scrollHeight 不可信，不能写回 iframe 尺寸。
      if (!isRootMeasurable()) return;
      naturalW.value = msg.width;
      naturalH.value = msg.height;
      updateScale();
      sizeReady.value = true;
      loading.value = false;
    }, 100);
    return;
  }

  // iframe 内禁用自带滚动条，滚轮统一转给外层视口，避免出现内外两个纵向滚动条。
  if (msg?.type === "html_card_wheel") {
    const viewport = viewportRef.value;
    if (!viewport || compact.value) return;
    viewport.scrollBy({ left: msg.deltaX || 0, top: msg.deltaY || 0 });
    return;
  }

  // 选中文本上报
  if (msg?.type === "text_selected") {
    const text = (msg.text || "").trim();
    if (text.length < 2) {
      selectionBubble.value.visible = false;
      return;
    }
    // 将 iframe 内坐标转换为卡片容器坐标；放大并滚动后要扣掉视口滚动量
    const root = rootRef.value;
    const viewport = viewportRef.value;
    if (!root || !viewport) return;
    const cw = root.offsetWidth;
    const bx = msg.x * effectiveScale.value - viewport.scrollLeft;
    const by = msg.y * effectiveScale.value - viewport.scrollTop - 32;

    selectionBubble.value = {
      visible: true,
      x: Math.max(4, Math.min(bx, cw - 80)),
      y: Math.max(4, by),
      text,
    };
    return;
  }

  // 点击空白处，隐藏气泡
  if (msg?.type === "selection_cleared") {
    selectionBubble.value.visible = false;
  }
}

// ── 注入脚本：尺寸上报 + 选中文本上报 ───────────────────────────
function injectResizeScript(html) {
  const style = `
<style id="html-card-adaptive-image-style">
  html,
  body {
    overflow: hidden !important;
    scrollbar-width: none !important;
  }
  html::-webkit-scrollbar,
  body::-webkit-scrollbar {
    display: none !important;
  }
  img,
  .card-image {
    max-width: 100% !important;
    height: auto !important;
    max-height: none !important;
    object-fit: contain !important;
    object-position: center center !important;
  }
  .card-image { width: 100% !important; }
</style>`;
  const scriptOpen = "<" + "script>";
  const scriptClose = "<" + "/script>";
  const script = `
${scriptOpen}
(function() {
  // 尺寸上报
  function report() {
    var w = document.documentElement.scrollWidth || document.body.scrollWidth;
    var h = document.documentElement.scrollHeight || document.body.scrollHeight;
    window.parent.postMessage({ type: 'resize', width: w, height: h }, '*');
  }
  function normalizeImages() {
    Array.prototype.forEach.call(document.images || [], function(img) {
      img.style.maxWidth = '100%';
      img.style.height = 'auto';
      img.style.maxHeight = 'none';
      img.style.objectFit = 'contain';
      img.style.objectPosition = 'center center';
      img.addEventListener('load', function() { setTimeout(report, 50); }, { once: true });
    });
  }
  function normalizeExternalLinks() {
    var pageOrigin = '';
    try {
      pageOrigin = window.parent.location.origin;
    } catch (_) {
      try { pageOrigin = new URL(document.baseURI).origin; } catch (_) {}
    }
    Array.prototype.forEach.call(document.querySelectorAll('a[href]'), function(link) {
      try {
        var url = new URL(link.getAttribute('href'), document.baseURI);
        if ((url.protocol !== 'http:' && url.protocol !== 'https:') || url.origin === pageOrigin) return;
        if (link.getAttribute('target') !== '_blank') link.setAttribute('target', '_blank');
        var rel = (link.getAttribute('rel') || '').split(/\\s+/).filter(Boolean);
        if (rel.indexOf('noopener') < 0) rel.push('noopener');
        if (rel.indexOf('noreferrer') < 0) rel.push('noreferrer');
        var nextRel = rel.join(' ');
        if (link.getAttribute('rel') !== nextRel) link.setAttribute('rel', nextRel);
      } catch (_) {}
    });
  }
  normalizeImages();
  normalizeExternalLinks();
  window.addEventListener('load', function() { normalizeImages(); normalizeExternalLinks(); setTimeout(report, 300); });
  window.addEventListener('message', function(e) { if (e.data?.type === 'requestResize') report(); });
  document.addEventListener('wheel', function(e) {
    window.parent.postMessage({ type: 'html_card_wheel', deltaX: e.deltaX, deltaY: e.deltaY }, '*');
    e.preventDefault();
  }, { passive: false });
  var t;
  new MutationObserver(function() { normalizeImages(); normalizeExternalLinks(); clearTimeout(t); t = setTimeout(report, 200); })
    .observe(document.body, { childList: true, subtree: true, attributes: true });

  // 选中文本上报
  document.addEventListener('mouseup', function(e) {
    var sel = window.getSelection();
    var text = sel ? sel.toString().trim() : '';
    if (text.length >= 2) {
      var range = sel.getRangeAt(0);
      var rect = range.getBoundingClientRect();
      window.parent.postMessage({
        type: 'text_selected',
        text: text,
        x: rect.left + rect.width / 2,
        y: rect.top + window.scrollY,
      }, '*');
    } else {
      window.parent.postMessage({ type: 'selection_cleared' }, '*');
    }
  });

  // 点击空白处清除
  document.addEventListener('mousedown', function(e) {
    var sel = window.getSelection();
    if (sel && sel.toString().trim().length === 0) {
      window.parent.postMessage({ type: 'selection_cleared' }, '*');
    }
  });
})();
${scriptClose}`;
  if (html.includes("</head>")) {
    html = html.replace("</head>", style + "</head>");
  } else {
    html = style + html;
  }
  if (html.includes("</body>"))
    return html.replace("</body>", script + "</body>");
  return html + script;
}

// ── 加载卡片 ──────────────────────────────────────────────────────
async function load() {
  if (!props.fileId) return;
  clearTimeout(resizeTimer);
  loading.value = true;
  error.value = "";
  sizeReady.value = false;
  naturalW.value = DEFAULT_NATURAL_WIDTH;
  naturalH.value = DEFAULT_NATURAL_HEIGHT;
  scale.value = 1;
  userZoomPct.value = 100;
  if (viewportRef.value) {
    viewportRef.value.scrollLeft = 0;
    viewportRef.value.scrollTop = 0;
  }

  try {
    const res = await api.getRaw(`/api/documents/${props.fileId}/raw`);
    if (!res.ok) throw new Error(`加载失败 (${res.status})`);
    let html = await res.text();

    // 内嵌图片序列化为 dataURL，避免 iframe 子资源丢鉴权。
    // 后端生成的文件中图片 src 的格式为 /api/documents/{docId}/asset/images/xxx.{png|jpg|jpeg|webp}。
    const imgPaths = [
      ...new Set(
        [
          ...html.matchAll(
            /src="(\/api\/documents\/[^"]+\/asset\/[^"]+\.(png|jpg|jpeg|webp))"/gi,
          ),
        ].map((m) => m[1]),
      ),
    ];
    await Promise.all(
      imgPaths.map(async (imgPath) => {
        try {
          const r = await api.getRaw(imgPath);
          if (!r.ok) return;
          const blob = await r.blob();
          const dataUrl = await new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = () => resolve(reader.result);
            reader.onerror = reject;
            reader.readAsDataURL(blob);
          });
          html = html.replaceAll(`src="${imgPath}"`, `src="${dataUrl}"`);
        } catch {
          /* 图片失败不影响整体 */
        }
      }),
    );

    if (iframeRef.value) {
      iframeRef.value.srcdoc = injectResizeScript(html);
    }
  } catch (e) {
    loading.value = false;
    error.value = e.message || "加载失败";
    emit("error", error.value);
  }
}

function onIframeLoad() {
  error.value = "";
  emit("loaded");
}

watch(
  () => props.fileId,
  () => {
    load();
  },
);

let visibilityObserver = null;

onMounted(() => {
  window.addEventListener("message", handleMessage);
  initResizeObserver();
  load();

  visibilityObserver = new IntersectionObserver(
    (entries) => {
      for (const entry of entries) {
        if (entry.isIntersecting && iframeRef.value?.contentWindow) {
          requestIframeResize(50);
        }
      }
    },
    { threshold: 0.01 },
  );

  setTimeout(() => {
    if (iframeRef.value) visibilityObserver.observe(iframeRef.value);
  }, 0);
});

onBeforeUnmount(() => {
  window.removeEventListener("message", handleMessage);
  clearTimeout(resizeTimer);
  clearTimeout(resizeRequestTimer);
  resizeObserver?.disconnect();
  visibilityObserver?.disconnect();
  askAbortController?.abort();
});

defineExpose({ reload: load });
</script>

<style scoped>
/* 根容器：撑满父级，作为缩放基准 */
.html-card-root {
  position: relative;
  width: 100%;
  height: 100%;
  overflow: hidden;
}

.html-card-viewport {
  position: absolute;
  inset: 0 0 40px;
  overflow: auto;
  overscroll-behavior: contain;
  scrollbar-gutter: stable;
}

.html-card-viewport::-webkit-scrollbar {
  width: 7px;
  height: 7px;
}

.html-card-viewport::-webkit-scrollbar-thumb {
  background: rgba(100, 116, 139, 0.42);
  border-radius: 999px;
}

.html-card-viewport::-webkit-scrollbar-track {
  background: transparent;
}

.html-card-root.is-compact .html-card-viewport {
  inset: 0;
  overflow: hidden;
  scrollbar-gutter: auto;
}

.html-card-stage {
  position: relative;
  min-width: 100%;
  min-height: 100%;
}

/* 固定原始尺寸的缩放层：左上角缩放，放大后可滚动查看局部 */
.html-card-scaler {
  flex-shrink: 0;
  position: absolute;
  top: 0;
  left: 0;
  transform-origin: top left;
}

/* iframe 撑满缩放层 */
.html-card-iframe {
  width: 100%;
  height: 100%;
  border: none;
  display: block;
}

/* 加载 */
.html-card-loading {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  font-size: 12px;
  color: var(--text-muted, #9ca3af);
  z-index: 1;
}

.html-card-spinner {
  width: 16px;
  height: 16px;
  border: 2px solid var(--border, #e5e7eb);
  border-top-color: var(--brand, #4f46e5);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

/* 错误 */
.html-card-error {
  position: absolute;
  top: 8px;
  left: 8px;
  right: 8px;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  background: var(--red-dim, #fef2f2);
  border: 1px solid rgba(239, 68, 68, 0.25);
  border-radius: var(--radius-sm, 6px);
  font-size: 12px;
  color: var(--red, #ef4444);
  z-index: 1;
}

.html-card-error .html-card-btn {
  margin-left: auto;
  color: var(--red, #ef4444);
  border-color: rgba(239, 68, 68, 0.3);
}

.html-card-btn {
  padding: 2px 8px;
  border-radius: var(--radius-sm, 6px);
  border: 1px solid var(--border, #e5e7eb);
  background: transparent;
  cursor: pointer;
  font-size: 12px;
}

.html-card-zoom-controls {
  position: absolute;
  left: 12px;
  right: 12px;
  bottom: 8px;
  z-index: 18;
  display: flex;
  align-items: center;
  gap: 8px;
  height: 30px;
  padding: 0 10px;
  border: 1px solid var(--border, #e5e7eb);
  border-radius: 999px;
  background: color-mix(in srgb, var(--bg-card, #fff) 92%, transparent);
  box-shadow: 0 8px 24px rgba(15, 23, 42, 0.1);
  backdrop-filter: blur(10px);
}

.zoom-label,
.zoom-value {
  flex: 0 0 auto;
  font-size: 11px;
  color: var(--text-muted, #6b7280);
  font-weight: 600;
}

.zoom-value {
  min-width: 38px;
  text-align: right;
}

.zoom-slider {
  flex: 1 1 auto;
  min-width: 80px;
  accent-color: var(--brand, #4f46e5);
}

.zoom-reset {
  flex: 0 0 auto;
  height: 22px;
  padding: 0 9px;
  border: 1px solid var(--border, #e5e7eb);
  border-radius: 999px;
  background: var(--bg-elevated, #fff);
  color: var(--text-secondary, #4b5563);
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
}

.zoom-reset:hover {
  color: var(--brand, #4f46e5);
  border-color: color-mix(
    in srgb,
    var(--brand, #4f46e5) 35%,
    var(--border, #e5e7eb)
  );
}

.html-card-root.is-compact .html-card-zoom-controls,
.html-card-root.is-compact .ask-ai-bubble,
.html-card-root.is-compact .ask-ai-panel {
  display: none;
}

/* ── 选中文本气泡 ─────────────────────────────────────────────── */
.ask-ai-bubble {
  position: absolute;
  z-index: 20;
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 5px 10px;
  background: var(--brand, #4f46e5);
  color: #fff;
  font-size: 12px;
  font-weight: 600;
  border-radius: 20px;
  cursor: pointer;
  box-shadow: 0 4px 12px rgba(79, 70, 229, 0.35);
  white-space: nowrap;
  user-select: none;
  transform: translateX(-50%);
  transition:
    opacity 0.15s,
    transform 0.15s;
}

.ask-ai-bubble:hover {
  opacity: 0.9;
  transform: translateX(-50%) scale(1.04);
}

/* 气泡小箭头 */
.ask-ai-bubble::after {
  content: "";
  position: absolute;
  top: 100%;
  left: 50%;
  transform: translateX(-50%);
  border: 5px solid transparent;
  border-top-color: var(--brand, #4f46e5);
}

.bubble-enter-active,
.bubble-leave-active {
  transition:
    opacity 0.15s,
    transform 0.15s;
}
.bubble-enter-from,
.bubble-leave-to {
  opacity: 0;
  transform: translateX(-50%) translateY(4px);
}

/* ── AI 解释浮窗 ──────────────────────────────────────────────── */
.ask-ai-panel {
  position: absolute;
  bottom: 12px;
  right: 12px;
  z-index: 30;
  width: 320px;
  max-width: calc(100% - 24px);
  background: var(--bg-card, #fff);
  border: 1px solid var(--border, #e5e7eb);
  border-radius: var(--radius-lg, 10px);
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.12);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.panel-enter-active,
.panel-leave-active {
  transition:
    opacity 0.2s,
    transform 0.2s;
}
.panel-enter-from,
.panel-leave-to {
  opacity: 0;
  transform: translateY(8px) scale(0.97);
}

.aap-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 12px 8px;
  border-bottom: 1px solid var(--border, #e5e7eb);
}

.aap-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  font-weight: 600;
  color: var(--brand, #4f46e5);
}

.aap-close {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border: none;
  background: transparent;
  cursor: pointer;
  color: var(--text-muted, #9ca3af);
  border-radius: 4px;
  transition:
    background 0.15s,
    color 0.15s;
}

.aap-close:hover {
  background: var(--bg-subtle, #f3f4f6);
  color: var(--text-primary, #111);
}

.aap-selected-text {
  padding: 8px 12px;
  background: var(--bg-subtle, #f8fafc);
  border-bottom: 1px solid var(--border, #e5e7eb);
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.aap-selected-label {
  font-size: 10px;
  font-weight: 600;
  color: var(--text-muted, #9ca3af);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.aap-selected-content {
  font-size: 12px;
  color: var(--text-secondary, #6b7280);
  line-height: 1.5;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.aap-body {
  padding: 12px;
  max-height: 260px;
  overflow-y: auto;
  flex: 1;
}

.aap-thinking {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--text-muted, #9ca3af);
  font-size: 12px;
}

.aap-dots {
  display: flex;
  gap: 3px;
}

.aap-dots span {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: var(--brand, #4f46e5);
  animation: dot-bounce 1.2s infinite ease-in-out;
}

.aap-dots span:nth-child(2) {
  animation-delay: 0.2s;
}
.aap-dots span:nth-child(3) {
  animation-delay: 0.4s;
}

@keyframes dot-bounce {
  0%,
  80%,
  100% {
    transform: scale(0.6);
    opacity: 0.4;
  }
  40% {
    transform: scale(1);
    opacity: 1;
  }
}

.aap-reply {
  font-size: 13px;
  line-height: 1.7;
  color: var(--text-primary, #111);
}

.aap-reply :deep(p) {
  margin: 0 0 8px;
}
.aap-reply :deep(p:last-child) {
  margin-bottom: 0;
}
.aap-reply :deep(code) {
  background: var(--bg-subtle, #f3f4f6);
  padding: 1px 5px;
  border-radius: 3px;
  font-size: 12px;
}
.aap-reply :deep(pre) {
  background: var(--bg-subtle, #f3f4f6);
  padding: 8px 10px;
  border-radius: 6px;
  overflow-x: auto;
  font-size: 12px;
}
.aap-reply :deep(.katex-display) {
  margin: 6px 0;
}

.aap-error {
  font-size: 12px;
  color: var(--red, #ef4444);
}

.aap-footer {
  padding: 8px 12px;
  border-top: 1px solid var(--border, #e5e7eb);
  display: flex;
  align-items: center;
}

.aap-btn-retry {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 4px 10px;
  border-radius: var(--radius-sm, 6px);
  border: 1px solid var(--border, #e5e7eb);
  background: transparent;
  cursor: pointer;
  font-size: 11px;
  color: var(--text-secondary, #6b7280);
  transition:
    border-color 0.15s,
    color 0.15s;
}

.aap-btn-retry:hover {
  border-color: var(--brand, #4f46e5);
  color: var(--brand, #4f46e5);
}

.aap-loading-hint {
  font-size: 11px;
  color: var(--text-muted, #9ca3af);
}
</style>
