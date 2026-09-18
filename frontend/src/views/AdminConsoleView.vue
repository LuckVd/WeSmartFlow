<template>
  <div class="admin-console">
    <!-- 顶栏 -->
    <header class="topbar">
      <div class="topbar-left">
        <div class="logo">⚙ WeSmartFlow Admin</div>
        <div class="subtitle">积分卡管理</div>
      </div>
      <div class="topbar-right">
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
        <button
          class="btn-text btn-card active"
          @click="showCreditCardPanel = !showCreditCardPanel"
        >
          🎫 积分卡
        </button>
        <button class="btn-text" @click="loadCreditCards">刷新</button>
        <button class="btn-text" @click="logout">退出登录</button>
      </div>
    </header>

    <section v-if="showCreditCardPanel" class="credit-card-panel">
      <div class="credit-card-copy">
        <strong>生成积分卡</strong>
        <span>生成后把兑换码发给用户；用户可在设置页兑换。</span>
      </div>
      <div class="credit-card-grid">
        <label>
          <span>类型</span>
          <select v-model="creditCardForm.mode">
            <option value="add">增加积分</option>
            <option value="reset">重置为指定积分</option>
          </select>
        </label>
        <label>
          <span>金额（元）</span>
          <input
            v-model.number="creditCardForm.amountYuan"
            min="0.01"
            step="0.01"
            type="number"
          />
        </label>
        <label>
          <span>可兑换人数</span>
          <input
            v-model.number="creditCardForm.maxRedemptions"
            min="0"
            step="1"
            type="number"
          />
        </label>
        <label>
          <span>备注</span>
          <input
            v-model="creditCardForm.note"
            placeholder="例如：内测用户补偿"
          />
        </label>
      </div>
      <div class="credit-card-actions">
        <button
          class="btn btn-card-create"
          :disabled="creatingCreditCard"
          @click="createCreditCard"
        >
          {{ creatingCreditCard ? "生成中…" : "生成积分卡" }}
        </button>
        <code v-if="generatedCreditCard" class="credit-card-code">{{
          generatedCreditCard
        }}</code>
        <button
          v-if="generatedCreditCard"
          class="btn-text"
          type="button"
          @click="copyCreditCardCode"
        >
          复制
        </button>
        <span class="credit-card-hint"
          >可兑换人数填 0 表示不限人数；1 元 = 1,000,000 积分。</span
        >
      </div>
      <div
        v-if="creditCardMessage"
        class="credit-card-message"
        :class="creditCardStatus"
      >
        {{ creditCardMessage }}
      </div>

      <div class="credit-card-history">
        <div class="credit-card-history-head">
          <div>
            <strong>积分卡记录</strong>
            <span
              >共 {{ creditCardTotal }} 张，展示最近
              {{ creditCards.length }} 张</span
            >
          </div>
          <button
            class="btn-text"
            type="button"
            :disabled="creditCardsLoading"
            @click="loadCreditCards"
          >
            {{ creditCardsLoading ? "刷新中…" : "刷新记录" }}
          </button>
        </div>
        <div class="credit-card-filters">
          <label class="filter-wide">
            <span>搜索卡号/备注/创建者</span>
            <input
              v-model.trim="creditCardFilters.q"
              placeholder="输入完整卡号、尾号、备注关键词"
              @keyup.enter="loadCreditCards"
            />
          </label>
          <label>
            <span>类型</span>
            <select v-model="creditCardFilters.mode" @change="loadCreditCards">
              <option value="">全部类型</option>
              <option value="add">增加积分</option>
              <option value="reset">重置积分</option>
            </select>
          </label>
          <label>
            <span>状态</span>
            <select
              v-model="creditCardFilters.status"
              @change="loadCreditCards"
            >
              <option value="">全部状态</option>
              <option value="active">可用</option>
              <option value="disabled">已停用</option>
              <option value="unused">未消费</option>
              <option value="redeemed">已消费</option>
              <option value="exhausted">已兑完</option>
            </select>
          </label>
          <label>
            <span>最低额度（元）</span>
            <input
              v-model.number="creditCardFilters.minYuan"
              min="0"
              step="0.01"
              type="number"
              @keyup.enter="loadCreditCards"
            />
          </label>
          <label>
            <span>最高额度（元）</span>
            <input
              v-model.number="creditCardFilters.maxYuan"
              min="0"
              step="0.01"
              type="number"
              @keyup.enter="loadCreditCards"
            />
          </label>
          <label>
            <span>排序字段</span>
            <select
              v-model="creditCardFilters.sortBy"
              @change="loadCreditCards"
            >
              <option value="created_at">生成时间</option>
              <option value="amount">额度</option>
              <option value="code">卡号</option>
              <option value="redeemed_count">消费人数</option>
              <option value="max_redemptions">可兑换人数</option>
              <option value="mode">类型</option>
              <option value="status">状态</option>
            </select>
          </label>
          <label>
            <span>排序方向</span>
            <select
              v-model="creditCardFilters.sortOrder"
              @change="loadCreditCards"
            >
              <option value="desc">倒序</option>
              <option value="asc">正序</option>
            </select>
          </label>
          <div class="credit-card-filter-actions">
            <button
              class="btn btn-card-create"
              type="button"
              @click="loadCreditCards"
            >
              应用筛选
            </button>
            <button
              class="btn-text"
              type="button"
              @click="resetCreditCardFilters"
            >
              重置
            </button>
          </div>
        </div>
        <div v-if="creditCardsLoading" class="credit-card-empty">加载中…</div>
        <div v-else-if="!creditCards.length" class="credit-card-empty">
          暂无积分卡生成记录
        </div>
        <div v-else class="credit-card-list">
          <article
            v-for="card in creditCards"
            :key="card.card_id || card.code_hash_tail"
            class="credit-card-item"
            :class="{ disabled: card.disabled }"
          >
            <div class="credit-card-item-main">
              <div class="credit-card-item-title">
                <span class="credit-card-mode" :class="`mode-${card.mode}`">
                  {{ creditCardModeLabel(card.mode) }}
                </span>
                <span
                  class="credit-card-state"
                  :class="card.disabled ? 'state-disabled' : 'state-active'"
                >
                  {{ card.disabled ? "已停用" : "可用" }}
                </span>
                <b>{{ formatCredits(card.amount) }} 积分</b>
                <code class="credit-card-code-inline">
                  {{
                    card.code_plain || `历史卡，仅存尾号 ${card.code_preview}`
                  }}
                </code>
                <button
                  v-if="card.code_plain"
                  class="btn-mini"
                  type="button"
                  @click="copyText(card.code_plain, '兑换码已复制。')"
                >
                  复制
                </button>
                <button
                  class="btn-mini danger"
                  type="button"
                  :disabled="updatingCreditCardId === card.card_id"
                  @click="toggleCreditCardDisabled(card)"
                >
                  {{ card.disabled ? "恢复" : "停用" }}
                </button>
              </div>
              <div class="credit-card-item-meta">
                <span>生成：{{ formatTime(card.created_at) }}</span>
                <span>创建者：{{ card.created_by || "—" }}</span>
                <span
                  >兑换：{{ card.redeemed_count }}/{{
                    card.max_redemptions || "不限"
                  }}</span
                >
                <span v-if="card.expires_at"
                  >过期：{{ formatTime(card.expires_at) }}</span
                >
                <span v-if="card.disabled">已停用</span>
              </div>
              <div v-if="card.note" class="credit-card-note">
                备注：{{ card.note }}
              </div>
            </div>
            <details class="credit-card-redemptions">
              <summary>
                兑换记录（{{ (card.redemptions || []).length }}）
              </summary>
              <div
                v-if="!(card.redemptions || []).length"
                class="credit-card-empty small"
              >
                暂无用户兑换
              </div>
              <div v-else class="redemption-list">
                <div
                  v-for="r in card.redemptions"
                  :key="r.id"
                  class="redemption-row"
                >
                  <div>
                    <strong>{{ redemptionUserLabel(r) }}</strong>
                    <span class="mono dim">{{ r.user_id }}</span>
                  </div>
                  <div class="redemption-meta">
                    <span>变化 {{ signedCredits(r.amount) }}</span>
                    <span>兑换后 {{ formatCredits(r.balance_after) }}</span>
                    <span>{{ formatTime(r.created_at) }}</span>
                  </div>
                </div>
              </div>
            </details>
          </article>
        </div>
      </div>
    </section>

    <div v-if="false" class="admin-review-area">
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
                    <span
                      class="apply-badge"
                      :class="`a-${detail.apply_status}`"
                    >
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
                    <span class="dim small"
                      >score {{ formatNum(h.score) }}</span
                    >
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
const showCreditCardPanel = ref(true);
const creatingCreditCard = ref(false);
const generatedCreditCard = ref("");
const creditCardStatus = ref("idle");
const creditCardMessage = ref("");
const creditCards = ref([]);
const creditCardTotal = ref(0);
const creditCardsLoading = ref(false);
const creditCardForm = reactive({
  mode: "add",
  amountYuan: 5,
  maxRedemptions: 1,
  note: "",
});
const creditCardFilters = reactive({
  q: "",
  mode: "",
  status: "",
  minYuan: "",
  maxYuan: "",
  sortBy: "created_at",
  sortOrder: "desc",
});
const updatingCreditCardId = ref("");

function formatCredits(credits) {
  return Number(credits || 0).toLocaleString("zh-CN");
}

function signedCredits(credits) {
  const n = Number(credits || 0);
  return `${n >= 0 ? "+" : ""}${formatCredits(n)}`;
}

function creditCardModeLabel(mode) {
  return mode === "reset" ? "重置" : "增加";
}

function amountYuanToCredits(value) {
  if (value === "" || value === null || value === undefined) return "";
  const n = Number(value);
  if (!Number.isFinite(n)) return "";
  return Math.round(n * 1000000);
}

function redemptionUserLabel(record) {
  return (
    record.user_name ||
    record.user_email ||
    record.github_username ||
    "未知用户"
  );
}

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

async function loadCreditCards() {
  creditCardsLoading.value = true;
  try {
    const minAmount = amountYuanToCredits(creditCardFilters.minYuan);
    const maxAmount = amountYuanToCredits(creditCardFilters.maxYuan);
    const resp = await adminApi.creditCards({
      limit: 100,
      q: creditCardFilters.q,
      mode: creditCardFilters.mode,
      status: creditCardFilters.status,
      min_amount: minAmount,
      max_amount: maxAmount,
      sort_by: creditCardFilters.sortBy,
      sort_order: creditCardFilters.sortOrder,
    });
    creditCards.value = resp.items || [];
    creditCardTotal.value = resp.total || 0;
  } catch (e) {
    console.error("loadCreditCards", e);
    creditCards.value = [];
    creditCardTotal.value = 0;
    creditCardStatus.value = "error";
    creditCardMessage.value = e.message || "加载积分卡失败";
  } finally {
    creditCardsLoading.value = false;
  }
}

function resetCreditCardFilters() {
  Object.assign(creditCardFilters, {
    q: "",
    mode: "",
    status: "",
    minYuan: "",
    maxYuan: "",
    sortBy: "created_at",
    sortOrder: "desc",
  });
  loadCreditCards();
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

async function createCreditCard() {
  creatingCreditCard.value = true;
  generatedCreditCard.value = "";
  creditCardStatus.value = "idle";
  creditCardMessage.value = "";
  try {
    const amount = Math.round(Number(creditCardForm.amountYuan || 0) * 1000000);
    if (!Number.isFinite(amount) || amount <= 0) {
      throw new Error("金额必须大于 0");
    }
    const data = await adminApi.createCreditCard({
      mode: creditCardForm.mode,
      amount,
      max_redemptions: Math.max(0, Number(creditCardForm.maxRedemptions || 0)),
      note: creditCardForm.note || "",
    });
    generatedCreditCard.value = data.code;
    creditCardStatus.value = "success";
    creditCardMessage.value = `已生成 ${formatCredits(data.amount)} 积分卡。`;
    loadCreditCards();
  } catch (error) {
    creditCardStatus.value = "error";
    creditCardMessage.value = error.message || "生成失败";
  } finally {
    creatingCreditCard.value = false;
  }
}

async function toggleCreditCardDisabled(card) {
  if (!card?.card_id || updatingCreditCardId.value) return;
  const nextDisabled = !card.disabled;
  const action = nextDisabled ? "停用" : "恢复";
  if (!window.confirm(`确定要${action}这张积分卡吗？`)) return;
  updatingCreditCardId.value = card.card_id;
  creditCardStatus.value = "idle";
  creditCardMessage.value = "";
  try {
    await adminApi.updateCreditCardStatus(card.card_id, nextDisabled);
    card.disabled = nextDisabled ? 1 : 0;
    creditCardStatus.value = "success";
    creditCardMessage.value = `积分卡已${action}。`;
  } catch (error) {
    creditCardStatus.value = "error";
    creditCardMessage.value = error.message || `${action}失败`;
  } finally {
    updatingCreditCardId.value = "";
  }
}

async function copyCreditCardCode() {
  if (!generatedCreditCard.value) return;
  await copyText(generatedCreditCard.value, "兑换码已复制。");
}

async function copyText(text, successMessage) {
  if (!text) return;
  try {
    await navigator.clipboard.writeText(text);
    creditCardStatus.value = "success";
    creditCardMessage.value = successMessage;
  } catch {
    creditCardStatus.value = "error";
    creditCardMessage.value = "复制失败，请手动选中兑换码复制。";
  }
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
  await loadCreditCards();
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
.btn-text.btn-card {
  border-color: rgba(245, 158, 11, 0.45);
  color: #fbbf24;
}
.btn-text.btn-card:hover,
.btn-text.btn-card.active {
  background: rgba(245, 158, 11, 0.14);
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

.credit-card-panel {
  flex-shrink: 0;
  margin: 12px 20px 0;
  padding: 14px 16px;
  border: 1px dashed rgba(245, 158, 11, 0.45);
  border-radius: 10px;
  background: var(--bg-panel);
}
.credit-card-copy {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-bottom: 12px;
}
.credit-card-copy strong {
  color: var(--text-primary);
  font-size: 13px;
}
.credit-card-copy span,
.credit-card-hint {
  color: var(--text-dim);
  font-size: 11px;
}
.credit-card-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
}
.credit-card-grid label {
  display: flex;
  flex-direction: column;
  gap: 5px;
  color: var(--text-dim);
  font-size: 11px;
}
.credit-card-grid input,
.credit-card-grid select {
  width: 100%;
  background: var(--bg-base);
  color: var(--text-primary);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 7px 10px;
  font-size: 12px;
  outline: none;
}
.credit-card-grid input:focus,
.credit-card-grid select:focus {
  border-color: var(--brand, #6366f1);
}
.credit-card-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin-top: 12px;
}
.btn-card-create {
  background: #f59e0b;
  color: white;
}
.credit-card-code {
  padding: 7px 10px;
  border-radius: 6px;
  background: var(--bg-base);
  color: #fbbf24;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 12px;
  user-select: all;
}
.credit-card-code-inline {
  padding: 4px 7px;
  border-radius: 5px;
  background: var(--bg-panel);
  color: #fbbf24;
  border: 1px solid var(--border);
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 11px;
  user-select: all;
}
.btn-mini {
  padding: 2px 7px;
  border-radius: 5px;
  border: 1px solid var(--border);
  background: transparent;
  color: var(--text-secondary);
  font-size: 10px;
  cursor: pointer;
}
.btn-mini:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}
.btn-mini.danger {
  border-color: rgba(239, 68, 68, 0.35);
  color: #f87171;
}
.btn-mini.danger:hover {
  background: rgba(239, 68, 68, 0.12);
  color: #fecaca;
}
.credit-card-message {
  margin-top: 10px;
  padding: 7px 9px;
  border-radius: 6px;
  font-size: 12px;
}
.credit-card-message.success {
  color: #34d399;
  background: rgba(16, 185, 129, 0.12);
}
.credit-card-message.error {
  color: #f87171;
  background: rgba(239, 68, 68, 0.12);
}
.credit-card-history {
  margin-top: 16px;
  padding-top: 14px;
  border-top: 1px solid var(--border);
}
.credit-card-history-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
}
.credit-card-history-head > div {
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.credit-card-history-head strong {
  font-size: 13px;
  color: var(--text-primary);
}
.credit-card-history-head span {
  font-size: 11px;
  color: var(--text-dim);
}
.credit-card-filters {
  display: grid;
  grid-template-columns: minmax(220px, 1.6fr) repeat(6, minmax(110px, 1fr)) auto;
  gap: 10px;
  align-items: end;
  margin-bottom: 12px;
  padding: 12px;
  border-radius: 10px;
  border: 1px solid var(--border);
  background: var(--bg-base);
}
.credit-card-filters label {
  display: flex;
  flex-direction: column;
  gap: 5px;
  min-width: 0;
}
.credit-card-filters label span {
  font-size: 10px;
  color: var(--text-dim);
}
.credit-card-filters input,
.credit-card-filters select {
  width: 100%;
  min-width: 0;
  border: 1px solid var(--border);
  border-radius: 7px;
  padding: 7px 9px;
  background: var(--bg-panel);
  color: var(--text-primary);
  font-size: 12px;
}
.credit-card-filter-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  white-space: nowrap;
}
.credit-card-empty {
  padding: 12px;
  border-radius: 8px;
  background: var(--bg-base);
  color: var(--text-dim);
  font-size: 12px;
  text-align: center;
}
.credit-card-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 360px;
  overflow-y: auto;
  padding-right: 4px;
}
.credit-card-item {
  padding: 11px 12px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg-base);
}
.credit-card-item.disabled {
  opacity: 0.78;
  border-color: rgba(239, 68, 68, 0.35);
}
.credit-card-item-main {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.credit-card-item-title,
.credit-card-item-meta,
.redemption-meta {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}
.credit-card-item-title {
  color: var(--text-primary);
  font-size: 13px;
}
.credit-card-item-meta,
.redemption-meta,
.credit-card-note {
  color: var(--text-dim);
  font-size: 11px;
}
.credit-card-mode {
  padding: 1px 7px;
  border-radius: 999px;
  font-size: 10px;
  font-weight: 700;
}
.credit-card-mode.mode-add {
  background: rgba(16, 185, 129, 0.16);
  color: #34d399;
}
.credit-card-mode.mode-reset {
  background: rgba(59, 130, 246, 0.16);
  color: #60a5fa;
}
.credit-card-state {
  padding: 1px 7px;
  border-radius: 999px;
  font-size: 10px;
  font-weight: 700;
}
.credit-card-state.state-active {
  color: #34d399;
  background: rgba(16, 185, 129, 0.14);
}
.credit-card-state.state-disabled {
  color: #f87171;
  background: rgba(239, 68, 68, 0.14);
}
.credit-card-redemptions {
  margin-top: 9px;
  color: var(--text-secondary);
  font-size: 12px;
}
.credit-card-redemptions summary {
  cursor: pointer;
  user-select: none;
}
.redemption-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-top: 8px;
}
.redemption-row {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding: 8px 9px;
  border-radius: 6px;
  background: var(--bg-panel);
  border: 1px solid var(--border);
}
.redemption-row > div:first-child {
  display: flex;
  flex-direction: column;
  gap: 3px;
  min-width: 180px;
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

@media (max-width: 900px) {
  .credit-card-grid {
    grid-template-columns: 1fr 1fr;
  }
}

@media (max-width: 640px) {
  .credit-card-grid {
    grid-template-columns: 1fr;
  }
}
</style>
