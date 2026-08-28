<template>
  <div class="admin-console">
    <!-- 顶栏 -->
    <header class="topbar">
      <div class="topbar-left">
        <div class="logo">⚙ WeSmartFlow Admin</div>
        <div class="subtitle">反馈审核台</div>
      </div>
      <div class="topbar-right">
        <span class="stat-pill stat-pending">
          待审核 <b>{{ stats.pending ?? 0 }}</b>
        </span>
        <span class="stat-pill stat-ok">
          已通过 <b>{{ stats.approved ?? 0 }}</b>
        </span>
        <span class="stat-pill stat-no">
          已驳回 <b>{{ stats.rejected ?? 0 }}</b>
        </span>
        <button
          class="btn-icon"
          :title="isDark ? '切换到浅色' : '切换到深色'"
          @click="toggleTheme"
        >
          <svg
            v-if="isDark"
            width="14"
            height="14"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
          >
            <circle cx="12" cy="12" r="5" />
            <line x1="12" y1="1" x2="12" y2="3" />
            <line x1="12" y1="21" x2="12" y2="23" />
            <line x1="4.22" y1="4.22" x2="5.64" y2="5.64" />
            <line x1="18.36" y1="18.36" x2="19.78" y2="19.78" />
            <line x1="1" y1="12" x2="3" y2="12" />
            <line x1="21" y1="12" x2="23" y2="12" />
            <line x1="4.22" y1="19.78" x2="5.64" y2="18.36" />
            <line x1="18.36" y1="5.64" x2="19.78" y2="4.22" />
          </svg>
          <svg
            v-else
            width="14"
            height="14"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
          >
            <path d="M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z" />
          </svg>
        </button>
        <button class="btn-text btn-kg" @click="goKgGraph">🌐 知识图谱</button>
        <button class="btn-text" @click="refreshAll">刷新</button>
        <button class="btn-text" @click="logout">退出登录</button>
      </div>
    </header>

    <!-- Tab + 筛选 -->
    <div class="filter-row">
      <div class="tabs">
        <button
          v-for="t in tabs"
          :key="t.value"
          class="tab"
          :class="{ active: status === t.value }"
          @click="changeStatus(t.value)"
        >
          {{ t.label }}
          <span class="tab-count">{{ stats[t.value] ?? 0 }}</span>
        </button>
      </div>
      <div class="ops">
        <label>类型:</label>
        <select v-model="opFilter" @change="loadList">
          <option value="">全部</option>
          <option value="suggest_facet_pattern">共性反馈</option>
          <option value="suggest_missing_concept">缺失概念</option>
        </select>
      </div>
    </div>

    <!-- 双栏 -->
    <div class="main">
      <!-- 左：列表 -->
      <aside class="list-pane">
        <div v-if="listLoading" class="placeholder">加载中…</div>
        <div v-else-if="!items.length" class="placeholder">
          🎉 这一档没有数据
        </div>
        <div v-else class="card-list">
          <div
            v-for="it in items"
            :key="it.id"
            class="card"
            :class="{
              active: selectedId === it.id,
              [opClass(it.op)]: true,
            }"
            @click="selectItem(it.id)"
          >
            <div class="card-head">
              <span class="op-badge" :class="opClass(it.op)">
                {{ opLabel(it.op) }}
              </span>
              <span
                v-if="
                  it.status === 'approved' &&
                  it.apply_status &&
                  it.apply_status !== 'idle'
                "
                class="apply-badge"
                :class="`a-${it.apply_status}`"
                :title="applyTitle(it)"
              >
                {{ applyLabel(it.apply_status) }}
              </span>
              <span class="card-time">{{ formatTime(it.created_at) }}</span>
            </div>
            <div class="card-title">
              {{ it.title || "(空标题)" }}
            </div>
            <div v-if="it.target_concept_name" class="card-meta">
              目标概念: {{ it.target_concept_name }}
            </div>
            <div v-if="it.proposer" class="card-meta dim">
              {{ it.proposer }}
            </div>
          </div>
        </div>
      </aside>

      <!-- 右：详情 -->
      <section class="detail-pane">
        <div v-if="!selectedId" class="placeholder">
          ← 从左侧选择一条进行审阅
        </div>
        <div v-else-if="detailLoading" class="placeholder">详情加载中…</div>
        <div v-else-if="detail" class="detail">
          <!-- 元信息 -->
          <div class="block">
            <div class="block-title">元信息</div>
            <div class="kv-grid">
              <div class="k">类型</div>
              <div class="v">
                <span class="op-badge" :class="opClass(detail.op)">
                  {{ opLabel(detail.op) }}
                </span>
              </div>
              <div class="k">状态</div>
              <div class="v">
                <span class="status-badge" :class="`s-${detail.status}`">
                  {{ statusLabel(detail.status) }}
                </span>
              </div>
              <div class="k">提议来源</div>
              <div class="v">{{ detail.proposer }}</div>
              <div class="k">创建时间</div>
              <div class="v">{{ formatTime(detail.created_at) }}</div>
              <div v-if="detail.session_id" class="k">会话</div>
              <div v-if="detail.session_id" class="v mono">
                {{ detail.session_id }}
              </div>
              <div v-if="detail.reviewed_at" class="k">审核时间</div>
              <div v-if="detail.reviewed_at" class="v">
                {{ formatTime(detail.reviewed_at) }}
              </div>
              <div v-if="detail.review_note" class="k">备注</div>
              <div v-if="detail.review_note" class="v">
                {{ detail.review_note }}
              </div>
              <template
                v-if="
                  detail.status === 'approved' &&
                  detail.apply_status &&
                  detail.apply_status !== 'idle'
                "
              >
                <div class="k">落盘状态</div>
                <div class="v">
                  <span class="apply-badge" :class="`a-${detail.apply_status}`">
                    {{ applyLabel(detail.apply_status) }}
                  </span>
                  <span
                    v-if="detail.apply_finished_at"
                    class="dim small"
                    style="margin-left: 8px"
                  >
                    {{ formatTime(detail.apply_finished_at) }}
                  </span>
                </div>
                <template v-if="detail.apply_error">
                  <div class="k">错误信息</div>
                  <div class="v apply-error">{{ detail.apply_error }}</div>
                </template>
              </template>
            </div>
          </div>

          <!-- ============ 共性反馈 ============ -->
          <template v-if="detail.op === 'suggest_facet_pattern'">
            <!-- 目标概念 -->
            <div class="block">
              <div class="block-title">目标概念</div>
              <div v-if="detail.concept" class="concept-card">
                <div class="concept-name">
                  {{ detail.concept.canonical_name }}
                  <span class="dim mono small">
                    ({{ detail.concept.id }})
                  </span>
                </div>
                <div v-if="detail.concept.subject" class="concept-tag">
                  学科: {{ detail.concept.subject }}
                </div>
                <div v-if="detail.concept.summary" class="concept-summary">
                  {{ detail.concept.summary }}
                </div>
              </div>
              <div v-else class="warn-box">⚠ 概念已不存在或被删除</div>
            </div>

            <!-- 提议内容 -->
            <div class="block">
              <div class="block-title">
                提议内容
                <span class="block-sub">
                  kind:
                  <code>{{ detail.payload.kind || "—" }}</code>
                  · 建议置信度:
                  {{ formatNum(detail.payload.suggested_confidence) }}
                </span>
              </div>
              <div class="content-quote">
                {{ detail.payload.content || "(空)" }}
              </div>
            </div>

            <!-- 证据 -->
            <div class="block">
              <div class="block-title">证据</div>
              <div class="evidence-row">
                <div class="ev-pill">
                  观察 <b>{{ detail.payload.observation_count || 0 }}</b> 条
                </div>
                <div class="ev-pill">
                  涉及用户 <b>{{ detail.payload.user_count || 0 }}</b> 人
                </div>
                <div class="ev-pill">
                  类型: {{ detail.payload.observation_type || "—" }}
                </div>
              </div>
              <div v-if="detail.payload.rationale" class="rationale">
                <div class="rationale-label">归纳依据</div>
                <div class="rationale-body">
                  {{ detail.payload.rationale }}
                </div>
              </div>
            </div>

            <!-- 同概念已有 facet（重复对比） -->
            <div class="block">
              <div class="block-title">
                该概念已有反馈
                <span class="block-sub">
                  ({{ (detail.concept_facets || []).length }} 条) ·
                  审阅时请对比是否重复
                </span>
              </div>
              <div
                v-if="(detail.concept_facets || []).length === 0"
                class="dim small"
              >
                暂无；这条 approve 后将作为该概念第一条同 kind 反馈。
              </div>
              <div v-else class="facet-list">
                <div
                  v-for="f in detail.concept_facets"
                  :key="f.id"
                  class="facet-row"
                >
                  <div class="facet-head">
                    <span class="kind-tag">{{ f.kind }}</span>
                    <span class="dim small">
                      conf {{ formatNum(f.confidence) }} · sup
                      {{ f.support_count }} · {{ f.origin }}
                    </span>
                  </div>
                  <div class="facet-content">{{ f.content }}</div>
                </div>
              </div>
            </div>

            <!-- 关联观察 -->
            <div class="block">
              <details>
                <summary class="block-title clickable">
                  关联观察原文
                  <span class="block-sub">
                    ({{ (detail.observations || []).length }} 条)
                  </span>
                </summary>
                <div
                  v-if="(detail.observations || []).length === 0"
                  class="dim small"
                  style="padding: 8px 0"
                >
                  无（observation 已被清理或 ids 为空）
                </div>
                <div v-else class="obs-list">
                  <div
                    v-for="o in detail.observations"
                    :key="o.id"
                    class="obs-row"
                  >
                    <div class="obs-head">
                      <span class="obs-type">{{ o.observation_type }}</span>
                      <span class="dim small mono">{{ o.id }}</span>
                      <span class="dim small">
                        conf {{ formatNum(o.agent_confidence) }}
                      </span>
                    </div>
                    <div class="obs-desc">{{ o.description }}</div>
                  </div>
                </div>
              </details>
            </div>
          </template>

          <!-- ============ 缺失概念 ============ -->
          <template v-if="detail.op === 'suggest_missing_concept'">
            <div class="block">
              <div class="block-title">建议建档的概念</div>
              <div class="concept-card">
                <div class="concept-name big">
                  {{ detail.payload.concept_name }}
                </div>
              </div>
            </div>

            <div class="block">
              <div class="block-title">提议理由</div>
              <div class="content-quote">
                {{ detail.payload.reason_brief || "(无)" }}
              </div>
            </div>

            <div class="block">
              <div class="block-title">
                KG 查重结果
                <span class="block-sub">
                  (避免重复建档，请先确认是否已有近义概念)
                </span>
              </div>
              <div
                v-if="(detail.resolve_hits || []).length === 0"
                class="ok-box"
              >
                ✅ KG 中未找到同名 / 别名 / 近义概念，可放心建档
              </div>
              <div v-else class="resolve-list">
                <div
                  v-for="h in detail.resolve_hits"
                  :key="h.concept_id"
                  class="resolve-row"
                  :class="`mt-${h.match_type}`"
                >
                  <span class="match-tag">{{ h.match_type }}</span>
                  <span class="resolve-name">{{ h.canonical_name }}</span>
                  <span class="dim small mono">{{ h.concept_id }}</span>
                  <span class="dim small">score {{ formatNum(h.score) }}</span>
                </div>
              </div>
            </div>
          </template>

          <!-- 操作区 -->
          <div v-if="detail.status === 'pending'" class="action-bar">
            <textarea
              v-model="reviewNote"
              class="note-input"
              placeholder="审阅备注（可选）"
              rows="2"
            ></textarea>
            <div class="action-buttons">
              <button
                class="btn btn-reject"
                :disabled="reviewing"
                @click="doReject"
              >
                ✗ 驳回
              </button>
              <button
                class="btn btn-approve"
                :disabled="reviewing"
                @click="doApprove"
              >
                ✓ 通过
              </button>
            </div>
          </div>
          <div v-else class="action-bar readonly">
            <div class="dim small">
              已于 {{ formatTime(detail.reviewed_at) }} 由
              <b>{{ detail.reviewer_id || "—" }}</b> 审核
            </div>
            <div
              v-if="
                detail.status === 'approved' &&
                (detail.apply_status === 'failed' ||
                  detail.apply_status === 'aborted')
              "
              class="action-buttons"
              style="margin-top: 10px"
            >
              <button
                class="btn btn-retry"
                :disabled="reviewing"
                @click="doRetry"
              >
                ↻ 重试落盘
              </button>
            </div>
            <div
              v-if="
                detail.status === 'approved' &&
                detail.apply_status === 'done' &&
                (detail.apply_error || '').startsWith('kg_sync_failed:')
              "
              class="action-buttons"
              style="margin-top: 10px"
            >
              <button
                class="btn btn-retry"
                :disabled="reviewing"
                title="md 文件已落盘，仅重新跑一次 KG 同步（不会重写 .md）"
                @click="doRetryKgSync"
              >
                ↻ 重新同步 KG
              </button>
            </div>
          </div>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from "vue";
import { useRouter } from "vue-router";
import { adminApi, clearAdminToken } from "../api/admin.js";
import { useTheme } from "../composables/useTheme.js";

const router = useRouter();
const { isDark, toggleTheme } = useTheme();

const tabs = [
  { value: "pending", label: "待审核" },
  { value: "approved", label: "已通过" },
  { value: "rejected", label: "已驳回" },
];

const status = ref("pending");
const opFilter = ref("");
const items = ref([]);
const stats = reactive({ pending: 0, approved: 0, rejected: 0 });
const selectedId = ref("");
const detail = ref(null);
const listLoading = ref(false);
const detailLoading = ref(false);
const reviewing = ref(false);
const reviewNote = ref("");

// ========================================================
// 数据加载
// ========================================================

async function loadStats() {
  try {
    const s = await adminApi.stats();
    Object.assign(stats, s);
  } catch (e) {
    console.error("loadStats", e);
  }
}

async function loadList() {
  listLoading.value = true;
  try {
    const resp = await adminApi.list({
      status: status.value,
      op: opFilter.value || "",
      limit: 200,
    });
    items.value = resp.items || [];
    // 列表变化后，若当前选中已不在列表里，自动选第一条
    if (
      selectedId.value &&
      !items.value.find((x) => x.id === selectedId.value)
    ) {
      selectedId.value = "";
      detail.value = null;
    }
    if (!selectedId.value && items.value.length > 0) {
      selectItem(items.value[0].id);
    }
  } catch (e) {
    console.error("loadList", e);
    items.value = [];
  } finally {
    listLoading.value = false;
  }
}

async function selectItem(id) {
  selectedId.value = id;
  detail.value = null;
  reviewNote.value = "";
  detailLoading.value = true;
  try {
    detail.value = await adminApi.detail(id);
  } catch (e) {
    console.error("detail", e);
    detail.value = null;
  } finally {
    detailLoading.value = false;
  }
}

function changeStatus(s) {
  if (status.value === s) return;
  status.value = s;
  selectedId.value = "";
  detail.value = null;
  loadList();
}

async function refreshAll() {
  await Promise.all([loadStats(), loadList()]);
}

// ========================================================
// 操作
// ========================================================

async function doApprove() {
  if (!detail.value || reviewing.value) return;
  reviewing.value = true;
  try {
    await adminApi.approve(detail.value.id, reviewNote.value);
    afterReview();
  } catch (e) {
    alert("操作失败: " + e.message);
  } finally {
    reviewing.value = false;
  }
}

async function doReject() {
  if (!detail.value || reviewing.value) return;
  reviewing.value = true;
  try {
    await adminApi.reject(detail.value.id, reviewNote.value);
    afterReview();
  } catch (e) {
    alert("操作失败: " + e.message);
  } finally {
    reviewing.value = false;
  }
}

async function doRetry() {
  if (!detail.value || reviewing.value) return;
  reviewing.value = true;
  try {
    await adminApi.retryApply(detail.value.id);
    detail.value = await adminApi.detail(detail.value.id);
    const idx = items.value.findIndex((x) => x.id === detail.value.id);
    if (idx >= 0) {
      items.value[idx] = {
        ...items.value[idx],
        apply_status: detail.value.apply_status,
        apply_error: detail.value.apply_error,
      };
    }
  } catch (e) {
    alert("重试失败: " + e.message);
  } finally {
    reviewing.value = false;
  }
}

async function doRetryKgSync() {
  if (!detail.value || reviewing.value) return;
  reviewing.value = true;
  try {
    await adminApi.retryKgSync(detail.value.id);
    detail.value = await adminApi.detail(detail.value.id);
    const idx = items.value.findIndex((x) => x.id === detail.value.id);
    if (idx >= 0) {
      items.value[idx] = {
        ...items.value[idx],
        apply_status: detail.value.apply_status,
        apply_error: detail.value.apply_error,
      };
    }
  } catch (e) {
    alert("重新同步 KG 失败: " + e.message);
  } finally {
    reviewing.value = false;
  }
}

async function afterReview() {
  const idx = items.value.findIndex((x) => x.id === selectedId.value);
  // 从列表移除该条
  if (idx >= 0) items.value.splice(idx, 1);
  // 自动跳下一条
  const next = items.value[idx] || items.value[idx - 1] || null;
  selectedId.value = "";
  detail.value = null;
  reviewNote.value = "";
  if (next) {
    selectItem(next.id);
  }
  loadStats();
}

function logout() {
  clearAdminToken();
  router.replace("/admin/login");
}

function goKgGraph() {
  router.push("/admin/kg");
}

// ========================================================
// 工具
// ========================================================

function opLabel(op) {
  if (op === "suggest_facet_pattern") return "共性反馈";
  if (op === "suggest_missing_concept") return "缺失概念";
  return op;
}
function opClass(op) {
  if (op === "suggest_facet_pattern") return "op-facet";
  if (op === "suggest_missing_concept") return "op-concept";
  return "op-other";
}
function statusLabel(s) {
  return { pending: "待审", approved: "已通过", rejected: "已驳回" }[s] || s;
}
function applyLabel(a) {
  return (
    {
      idle: "",
      queued: "⏳ 排队中",
      running: "🔄 运行中",
      done: "✅ 已落盘",
      aborted: "⚪ 已中止",
      failed: "🔴 失败",
    }[a] || a
  );
}
function applyTitle(it) {
  if (!it.apply_status || it.apply_status === "idle") return "";
  if (it.apply_error)
    return `${applyLabel(it.apply_status)}：${it.apply_error}`;
  return applyLabel(it.apply_status);
}
function formatTime(s) {
  if (!s) return "—";
  try {
    const d = new Date(s);
    if (isNaN(d.getTime())) return s;
    return d.toLocaleString("zh-CN", { hour12: false });
  } catch {
    return s;
  }
}
function formatNum(n) {
  if (n === undefined || n === null || n === "") return "—";
  const f = Number(n);
  if (Number.isNaN(f)) return String(n);
  return f.toFixed(2);
}

// ========================================================
// 初始化
// ========================================================

onMounted(async () => {
  // 守卫：没有 token 就跳登录
  try {
    await adminApi.me();
  } catch {
    return;
  }
  await refreshAll();
});
</script>

<style scoped>
.admin-console {
  height: 100vh;
  display: flex;
  flex-direction: column;
  background: var(--bg-base);
  color: var(--text-primary);
  font-size: 13px;
}

/* 顶栏 */
.topbar {
  height: 52px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 20px;
  background: var(--bg-panel);
  border-bottom: 1px solid var(--border);
}
.topbar-left {
  display: flex;
  align-items: baseline;
  gap: 12px;
}
.logo {
  font-weight: 700;
  font-size: 14px;
  letter-spacing: -0.2px;
}
.subtitle {
  font-size: 11px;
  color: var(--text-dim);
}
.topbar-right {
  display: flex;
  align-items: center;
  gap: 8px;
}
.stat-pill {
  font-size: 11px;
  padding: 3px 9px;
  border-radius: 999px;
  background: var(--bg-active, rgba(255, 255, 255, 0.06));
  color: var(--text-secondary);
}
.stat-pill b {
  margin-left: 4px;
  color: var(--text-primary);
  font-weight: 700;
}
.stat-pending b {
  color: #f59e0b;
}
.stat-ok b {
  color: #10b981;
}
.stat-no b {
  color: #ef4444;
}
.btn-text {
  background: transparent;
  border: 1px solid var(--border);
  color: var(--text-secondary);
  padding: 4px 10px;
  border-radius: 6px;
  font-size: 11px;
  cursor: pointer;
}
.btn-text:hover {
  background: var(--bg-hover);
}
.btn-text.btn-kg {
  background: linear-gradient(135deg, #5b8def 0%, #8b5fef 100%);
  color: #fff;
  border-color: transparent;
  font-weight: 600;
}
.btn-text.btn-kg:hover {
  filter: brightness(1.1);
  box-shadow: 0 2px 10px rgba(91, 141, 239, 0.4);
}
.btn-icon {
  width: 28px;
  height: 26px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  border: 1px solid var(--border);
  color: var(--text-secondary);
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.12s;
}
.btn-icon:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}

/* 筛选行 */
.filter-row {
  height: 40px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 20px;
  border-bottom: 1px solid var(--border);
  background: var(--bg-panel);
}
.tabs {
  display: flex;
  gap: 4px;
}
.tab {
  background: transparent;
  border: none;
  color: var(--text-secondary);
  padding: 5px 12px;
  border-radius: 6px;
  font-size: 12px;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.tab:hover {
  background: var(--bg-hover);
}
.tab.active {
  background: var(--brand-dim, rgba(99, 102, 241, 0.14));
  color: var(--brand-light, #a5b4fc);
}
.tab-count {
  font-size: 10px;
  padding: 0 6px;
  border-radius: 10px;
  background: var(--bg-active, rgba(255, 255, 255, 0.08));
  color: var(--text-dim);
}
.tab.active .tab-count {
  background: rgba(99, 102, 241, 0.25);
  color: var(--brand-light, #a5b4fc);
}
.ops {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  color: var(--text-dim);
}
.ops select {
  background: var(--bg-base);
  color: var(--text-primary);
  border: 1px solid var(--border);
  border-radius: 5px;
  padding: 3px 8px;
  font-size: 11px;
}

/* 主体双栏 */
.main {
  flex: 1;
  display: flex;
  overflow: hidden;
}
.list-pane {
  width: 360px;
  flex-shrink: 0;
  border-right: 1px solid var(--border);
  overflow-y: auto;
  padding: 10px;
  background: var(--bg-panel);
}
.detail-pane {
  flex: 1;
  overflow-y: auto;
  padding: 18px 24px 80px;
}

.placeholder {
  padding: 40px 16px;
  text-align: center;
  color: var(--text-dim);
  font-size: 12px;
}

/* 卡片 */
.card-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.card {
  padding: 9px 11px;
  border-radius: 8px;
  border: 1px solid var(--border);
  background: var(--bg-base);
  cursor: pointer;
  transition: all 0.12s;
  border-left-width: 3px;
}
.card:hover {
  border-color: var(--border-hover);
}
.card.active {
  background: var(--brand-dim, rgba(99, 102, 241, 0.1));
  border-color: var(--brand, #6366f1);
}
.card.op-facet {
  border-left-color: #3b82f6;
}
.card.op-concept {
  border-left-color: #f59e0b;
}
.card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 4px;
}
.card-time {
  font-size: 10px;
  color: var(--text-dim);
}
.card-title {
  font-size: 12px;
  color: var(--text-primary);
  line-height: 1.4;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.card-meta {
  font-size: 10px;
  color: var(--text-secondary);
  margin-top: 4px;
}
.card-meta.dim {
  color: var(--text-dim);
}

.op-badge {
  font-size: 10px;
  font-weight: 600;
  padding: 1px 7px;
  border-radius: 10px;
}
.op-badge.op-facet {
  background: rgba(59, 130, 246, 0.18);
  color: #60a5fa;
}
.op-badge.op-concept {
  background: rgba(245, 158, 11, 0.18);
  color: #fbbf24;
}

/* 详情 */
.detail {
  max-width: 900px;
}
.block {
  margin-bottom: 22px;
}
.block-title {
  font-size: 11px;
  font-weight: 700;
  color: var(--text-secondary);
  letter-spacing: 0.06em;
  text-transform: uppercase;
  margin-bottom: 8px;
}
.block-title.clickable {
  cursor: pointer;
  user-select: none;
}
.block-sub {
  font-size: 10px;
  font-weight: 500;
  color: var(--text-dim);
  text-transform: none;
  letter-spacing: 0;
  margin-left: 8px;
}

.kv-grid {
  display: grid;
  grid-template-columns: 90px 1fr;
  gap: 6px 14px;
  font-size: 12px;
}
.kv-grid .k {
  color: var(--text-dim);
}
.kv-grid .v {
  color: var(--text-primary);
}
.mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 11px;
}

.status-badge {
  font-size: 10px;
  padding: 1px 7px;
  border-radius: 10px;
  font-weight: 600;
}
.status-badge.s-pending {
  background: rgba(245, 158, 11, 0.18);
  color: #fbbf24;
}
.status-badge.s-approved {
  background: rgba(16, 185, 129, 0.18);
  color: #34d399;
}
.status-badge.s-rejected {
  background: rgba(239, 68, 68, 0.18);
  color: #f87171;
}

/* apply_status 徽章（异步落盘流水线） */
.apply-badge {
  font-size: 10px;
  font-weight: 600;
  padding: 1px 7px;
  border-radius: 10px;
  margin-left: 6px;
}
.apply-badge.a-queued {
  background: rgba(148, 163, 184, 0.2);
  color: #cbd5e1;
}
.apply-badge.a-running {
  background: rgba(59, 130, 246, 0.18);
  color: #60a5fa;
}
.apply-badge.a-done {
  background: rgba(16, 185, 129, 0.18);
  color: #34d399;
}
.apply-badge.a-aborted {
  background: rgba(148, 163, 184, 0.16);
  color: #94a3b8;
}
.apply-badge.a-failed {
  background: rgba(239, 68, 68, 0.18);
  color: #f87171;
}
.apply-error {
  white-space: pre-wrap;
  word-break: break-word;
  color: #f87171;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 11px;
  padding: 6px 8px;
  background: rgba(239, 68, 68, 0.08);
  border-radius: 4px;
}

.concept-card {
  padding: 12px 14px;
  border-radius: 8px;
  border: 1px solid var(--border);
  background: var(--bg-panel);
}
.concept-name {
  font-size: 14px;
  font-weight: 600;
}
.concept-name.big {
  font-size: 18px;
}
.concept-tag {
  margin-top: 4px;
  font-size: 11px;
  color: var(--text-dim);
}
.concept-summary {
  margin-top: 8px;
  font-size: 12px;
  line-height: 1.55;
  color: var(--text-secondary);
}

.content-quote {
  padding: 12px 14px;
  border-radius: 8px;
  background: var(--bg-panel);
  border-left: 3px solid var(--brand, #6366f1);
  font-size: 13px;
  line-height: 1.6;
  white-space: pre-wrap;
}

.evidence-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 10px;
}
.ev-pill {
  font-size: 11px;
  padding: 3px 9px;
  background: var(--bg-active, rgba(255, 255, 255, 0.05));
  border-radius: 999px;
  color: var(--text-secondary);
}
.ev-pill b {
  color: var(--text-primary);
  font-weight: 700;
}
.rationale {
  margin-top: 8px;
  padding: 10px 12px;
  background: var(--bg-panel);
  border: 1px dashed var(--border);
  border-radius: 6px;
}
.rationale-label {
  font-size: 10px;
  color: var(--text-dim);
  text-transform: uppercase;
  letter-spacing: 0.06em;
  margin-bottom: 4px;
}
.rationale-body {
  font-size: 12px;
  line-height: 1.55;
  color: var(--text-secondary);
}

.facet-list,
.obs-list,
.resolve-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.facet-row,
.obs-row {
  padding: 8px 11px;
  border-radius: 6px;
  background: var(--bg-panel);
  border: 1px solid var(--border);
}
.facet-head,
.obs-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}
.kind-tag {
  font-size: 10px;
  padding: 1px 7px;
  border-radius: 10px;
  background: var(--brand-dim, rgba(99, 102, 241, 0.18));
  color: var(--brand-light, #a5b4fc);
  font-weight: 600;
}
.facet-content,
.obs-desc {
  font-size: 12px;
  line-height: 1.55;
  color: var(--text-secondary);
  white-space: pre-wrap;
}
.obs-type {
  font-size: 10px;
  padding: 1px 7px;
  border-radius: 10px;
  background: rgba(59, 130, 246, 0.16);
  color: #60a5fa;
  font-weight: 600;
}

.resolve-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 7px 10px;
  border-radius: 6px;
  background: var(--bg-panel);
  border: 1px solid var(--border);
}
.resolve-row.mt-exact,
.resolve-row.mt-alias {
  border-color: rgba(239, 68, 68, 0.4);
  background: rgba(239, 68, 68, 0.08);
}
.match-tag {
  font-size: 10px;
  padding: 1px 7px;
  border-radius: 10px;
  background: var(--bg-active, rgba(255, 255, 255, 0.06));
  color: var(--text-secondary);
  font-weight: 600;
}
.resolve-row.mt-exact .match-tag,
.resolve-row.mt-alias .match-tag {
  background: rgba(239, 68, 68, 0.2);
  color: #f87171;
}
.resolve-name {
  font-size: 12px;
  font-weight: 600;
}

.warn-box {
  padding: 10px 12px;
  background: rgba(239, 68, 68, 0.1);
  color: #f87171;
  border-radius: 6px;
  font-size: 12px;
}
.ok-box {
  padding: 10px 12px;
  background: rgba(16, 185, 129, 0.1);
  color: #34d399;
  border-radius: 6px;
  font-size: 12px;
}

/* 操作区 */
.action-bar {
  position: sticky;
  bottom: 0;
  margin-top: 24px;
  padding: 12px;
  background: var(--bg-panel);
  border-top: 1px solid var(--border);
  border-radius: 8px;
  box-shadow: 0 -4px 14px rgba(0, 0, 0, 0.18);
}
.action-bar.readonly {
  text-align: center;
  padding: 12px;
}
.note-input {
  width: 100%;
  background: var(--bg-base);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 8px 10px;
  color: var(--text-primary);
  font-size: 12px;
  resize: vertical;
  font-family: inherit;
  outline: none;
}
.note-input:focus {
  border-color: var(--brand, #6366f1);
}
.action-buttons {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
  margin-top: 8px;
}
.btn {
  padding: 7px 18px;
  border-radius: 6px;
  border: none;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: opacity 0.12s;
}
.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.btn-approve {
  background: #10b981;
  color: white;
}
.btn-reject {
  background: rgba(239, 68, 68, 0.16);
  color: #f87171;
  border: 1px solid rgba(239, 68, 68, 0.3);
}
.btn-retry {
  background: rgba(99, 102, 241, 0.18);
  color: #a5b4fc;
  border: 1px solid rgba(99, 102, 241, 0.35);
}
.btn-retry:hover {
  background: rgba(99, 102, 241, 0.28);
}

.dim {
  color: var(--text-dim);
}
.small {
  font-size: 11px;
}
</style>
