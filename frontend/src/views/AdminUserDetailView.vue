<template>
  <div class="admin-page">
    <router-link class="a-link" :to="backLink">← 返回用户列表</router-link>
    <div v-if="loading" class="a-empty">正在加载用户资料…</div>
    <div v-if="error" class="a-error" role="alert">
      {{ error }} <button class="a-button" @click="load">重试</button>
    </div>
    <template v-if="detail && !loading">
      <div class="admin-page-head" style="margin-top: 22px">
        <div>
          <h1>{{ detail.user.name }}</h1>
          <p>
            {{ detail.user.email || "未提供邮箱" }} · {{ detail.user.id }}
            <button class="a-button" @click="copyId">
              {{ copyStatus || "复制 ID" }}
            </button>
          </p>
        </div>
        <span class="a-tag">注册于 {{ time(detail.user.created_at) }}</span>
      </div>
      <div class="a-metrics">
        <div class="a-metric">
          <small>已入账积分余额</small
          ><strong>{{ number(detail.user.balance) }}</strong>
        </div>
        <div v-for="metric in metrics" :key="metric.key" class="a-metric">
          <small>{{ metric.label }}</small
          ><strong>{{ number(detail.counts[metric.key]) }}</strong>
        </div>
      </div>
      <nav class="a-tabs" aria-label="用户详情页签">
        <router-link
          v-for="item in tabs"
          :key="item.key"
          class="a-tab-link"
          :class="{ active: tab === item.key }"
          :to="{
            query: { ...route.query, tab: item.key, record_page: undefined },
          }"
          >{{ item.label }}</router-link
        >
      </nav>
      <template v-if="tab === 'profile'">
        <section class="a-panel">
          <h2 class="a-section-title">账号资料</h2>
          <dl class="a-details">
            <dt>用户 ID</dt>
            <dd>{{ detail.user.id }}</dd>
            <dt>邮箱</dt>
            <dd>{{ detail.user.email || "未提供" }}</dd>
            <dt>绑定方式</dt>
            <dd>
              {{
                detail.user.bindings.map(bindingLabel).join(" / ") || "未绑定"
              }}
            </dd>
            <dt>GitHub 用户名</dt>
            <dd>{{ detail.user.github_username || "未绑定" }}</dd>
            <dt>GitHub ID</dt>
            <dd>{{ detail.user.github_id || "—" }}</dd>
            <dt>微信</dt>
            <dd>{{ detail.user.wechat_bound ? "已绑定" : "未绑定" }}</dd>
            <dt>钱包状态</dt>
            <dd>
              {{ detail.user.wallet_initialized ? "已初始化" : "未初始化"
              }}<span v-if="detail.user.wallet_month">
                · 最近处理月份 {{ detail.user.wallet_month }}</span
              >
            </dd>
          </dl>
        </section>
        <section class="a-panel" style="margin-top: 20px">
          <h2 class="a-section-title">学习画像</h2>
          <p class="a-muted" style="padding: 8px 24px">
            根据学习记录生成的摘要，仅作为了解学习情况的参考。
          </p>
          <dl v-if="detail.profile" class="a-details">
            <template v-for="(label, key) in profileLabels" :key="key"
              ><dt>{{ label }}</dt>
              <dd>{{ profileText(key) }}</dd></template
            >
          </dl>
          <div v-else class="a-empty">尚未形成学习画像</div>
        </section>
      </template>
      <template v-else-if="tab === 'wallet'">
        <div v-if="detail.rewards.length" class="a-metrics">
          <div
            v-for="reward in detail.rewards"
            :key="reward.kind"
            class="a-metric"
          >
            <small>{{ transactionLabel(reward.kind) }} · 累计变动</small>
            <strong>{{ number(reward.amount) }}</strong>
          </div>
        </div>
        <p class="a-muted" style="margin-bottom: 16px">
          查看不会补发积分；重置卡的流水金额表示实际增减，可能为负数。
        </p>
        <div class="a-actions" style="margin-bottom: 16px">
          <router-link
            v-for="kind in ['transactions', 'redemptions']"
            :key="kind"
            class="a-button"
            :class="{ primary: recordKind === kind }"
            :to="{ query: { ...route.query, kind, record_page: undefined } }"
            >{{
              kind === "transactions" ? "全部积分流水" : "积分卡兑换"
            }}</router-link
          >
        </div>
      </template>
      <template v-else-if="tab === 'usage'">
        <label class="a-field" style="max-width: 210px; margin-bottom: 18px"
          >统计月份（UTC）<input
            type="month"
            :value="period"
            @change="changePeriod"
        /></label>
        <p class="a-muted" style="margin-bottom: 16px">
          平台额度消耗：{{ number(usage?.used ?? 0) }} 积分。总折算积分包含自备
          Key 和系统任务，平台扣费列按计费标记统计。
        </p>
        <div v-if="usageLoading" class="a-empty">正在加载统计…</div>
        <div v-else-if="usageError" class="a-error">{{ usageError }}</div>
        <section v-else class="a-panel">
          <div class="a-table-wrap">
            <table class="a-table">
              <thead>
                <tr>
                  <th>类别</th>
                  <th>场景</th>
                  <th>调用次数</th>
                  <th>总折算积分</th>
                  <th>平台扣费积分</th>
                  <th>输入 / 输出 Token</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="row in usage?.items || []"
                  :key="row.category + row.scene"
                >
                  <td>{{ categoryLabel(row.category) }}</td>
                  <td>{{ row.scene }}</td>
                  <td>{{ number(row.calls) }}</td>
                  <td>{{ number(row.credits) }}</td>
                  <td>{{ number(row.charged) }}</td>
                  <td>
                    {{ number(row.prompt_tokens) }} /
                    {{ number(row.completion_tokens) }}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <div v-if="!usage?.items.length" class="a-empty">
            该月暂无用量记录
          </div>
        </section>
      </template>
      <div v-else class="a-actions" style="margin-bottom: 16px">
        <router-link
          v-for="metric in metrics"
          :key="metric.key"
          class="a-button"
          :class="{ primary: recordKind === metric.key }"
          :to="{
            query: { ...route.query, kind: metric.key, record_page: undefined },
          }"
          >{{ metric.label }}</router-link
        >
      </div>
      <section v-if="tab === 'wallet' || tab === 'learning'" class="a-panel">
        <div v-if="recordsLoading" class="a-empty">正在加载记录…</div>
        <div v-else-if="recordsError" class="a-error">{{ recordsError }}</div>
        <template v-else
          ><div v-if="!records.items.length" class="a-empty">暂无相关记录</div>
          <div v-else class="a-table-wrap">
            <table class="a-table">
              <thead>
                <tr>
                  <th v-for="column in columns" :key="column.key">
                    {{ column.label }}
                  </th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="row in records.items" :key="row.id">
                  <td v-for="column in columns" :key="column.key">
                    {{ cell(row, column.key) }}
                  </td>
                </tr>
              </tbody>
            </table>
          </div></template
        >
        <div class="a-pager">
          <span>共 {{ records.total }} 条 · 第 {{ recordPage }} 页</span>
          <div class="a-actions">
            <button
              class="a-button"
              :disabled="recordPage <= 1 || recordsLoading"
              @click="goRecords(-1)"
            >
              上一页</button
            ><button
              class="a-button"
              :disabled="recordPage * 20 >= records.total || recordsLoading"
              @click="goRecords(1)"
            >
              下一页
            </button>
          </div>
        </div>
      </section>
    </template>
  </div>
</template>
<script setup>
import { computed, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { adminApi } from "../api/admin.js";
import {
  number,
  time,
  bindingLabel,
  transactionLabel,
  pageNumber,
  copy,
} from "../components/Admin/format.js";
const route = useRoute(),
  router = useRouter();
const detail = ref(null),
  loading = ref(false),
  error = ref(""),
  copyStatus = ref("");
const metrics = [
  { key: "sessions", label: "会话" },
  { key: "courses", label: "课程" },
  { key: "documents", label: "文档" },
  { key: "nodes", label: "知识节点" },
  { key: "quizzes", label: "测验" },
];
const tabs = [
  { key: "profile", label: "基本资料" },
  { key: "wallet", label: "积分钱包" },
  { key: "usage", label: "使用统计" },
  { key: "learning", label: "学习概况" },
];
const tab = computed(() =>
  tabs.some((t) => t.key === route.query.tab) ? route.query.tab : "profile",
);
const backLink = computed(() => ({
  path: "/admin/users",
  query: Object.fromEntries(
    Object.entries(route.query).filter(
      ([key]) => !["tab", "kind", "record_page", "period"].includes(key),
    ),
  ),
}));
const profileLabels = {
  overall_judgement: "整体判断",
  interests: "兴趣",
  learning_level: "学习水平",
  knowledge_scope: "知识范围",
  dialogue_preference: "交流偏好",
  learning_behavior: "学习行为",
  weakness_summary: "薄弱环节",
  strategy_summary: "学习建议",
  updated_at: "更新时间",
};
function profileText(key) {
  const value = detail.value.profile[key];
  if (key === "updated_at") return time(value);
  if (key === "interests") {
    try {
      const list = JSON.parse(value);
      return Array.isArray(list) ? list.join("、") || "暂无" : value;
    } catch {
      return value || "暂无";
    }
  }
  return value || "暂无";
}
const recordKind = computed(() => {
  const allowed =
    tab.value === "wallet"
      ? ["transactions", "redemptions"]
      : metrics.map((m) => m.key);
  return allowed.includes(route.query.kind) ? route.query.kind : allowed[0];
});
const recordPage = computed(() => pageNumber(route.query.record_page)),
  records = ref({ items: [], total: 0 }),
  recordsLoading = ref(false),
  recordsError = ref("");
const columns = computed(() => {
  let fields =
    tab.value === "wallet"
      ? [
          ["created_at", "时间"],
          ...(recordKind.value === "transactions" ? [["kind", "类型"]] : []),
          ["amount", "积分变化"],
          ["balance_after", "变动后余额"],
        ]
      : recordKind.value === "quizzes"
        ? [
            ["id", "测验 ID"],
            ["score", "分数"],
            ["is_correct", "作答结果"],
            ["answered_at", "作答时间"],
          ]
        : [
            ["title", "标题"],
            ...(recordKind.value === "nodes"
              ? [["mastery_level", "掌握度"]]
              : [["status", "状态"]]),
            ["created_at", "创建时间"],
          ];
  return fields.map(([key, label]) => ({ key, label }));
});
function cell(row, key) {
  if (key.endsWith("_at")) return time(row[key]);
  if (key === "kind") return transactionLabel(row[key]);
  if (key === "amount") return `${row[key] > 0 ? "+" : ""}${number(row[key])}`;
  if (key === "balance_after") return number(row[key]);
  if (key === "is_correct")
    return row[key] == null ? "未判定" : row[key] ? "正确" : "错误";
  if (key === "mastery_level") return `${Math.round((row[key] || 0) * 100)}%`;
  return row[key] ?? "—";
}
const month = new Intl.DateTimeFormat("sv-SE", {
  timeZone: "UTC",
  year: "numeric",
  month: "2-digit",
}).format(new Date());
const period = computed(() =>
  /^\d{4}-(0[1-9]|1[0-2])$/.test(route.query.period || "")
    ? route.query.period
    : month,
);
const usage = ref(null),
  usageLoading = ref(false),
  usageError = ref("");
let detailRequest = 0,
  recordRequest = 0,
  usageRequest = 0;
async function load() {
  const n = ++detailRequest;
  loading.value = true;
  error.value = "";
  detail.value = null;
  try {
    const result = await adminApi.user(route.params.id);
    if (n === detailRequest) detail.value = result;
  } catch (e) {
    if (n === detailRequest) error.value = e.message;
  } finally {
    if (n === detailRequest) loading.value = false;
  }
}
async function loadRecords() {
  const n = ++recordRequest;
  recordsLoading.value = true;
  recordsError.value = "";
  records.value = { items: [], total: 0 };
  try {
    const result = await adminApi.userRecords(route.params.id, {
      kind: recordKind.value,
      limit: 20,
      offset: (recordPage.value - 1) * 20,
    });
    if (n === recordRequest) records.value = result;
  } catch (e) {
    if (n === recordRequest) recordsError.value = e.message;
  } finally {
    if (n === recordRequest) recordsLoading.value = false;
  }
}
async function loadUsage() {
  const n = ++usageRequest;
  usageLoading.value = true;
  usageError.value = "";
  usage.value = null;
  try {
    const result = await adminApi.userUsage(route.params.id, period.value);
    if (n === usageRequest) usage.value = result;
  } catch (e) {
    if (n === usageRequest) usageError.value = e.message;
  } finally {
    if (n === usageRequest) usageLoading.value = false;
  }
}
function categoryLabel(value) {
  return (
    { llm: "模型", search: "搜索", image: "图片", audio: "语音" }[value] ||
    value
  );
}
function changePeriod(event) {
  router.push({ query: { ...route.query, period: event.target.value } });
}
function goRecords(delta) {
  router.push({
    query: { ...route.query, record_page: String(recordPage.value + delta) },
  });
}
async function copyId() {
  try {
    await copy(detail.value.user.id);
    copyStatus.value = "已复制";
  } catch {
    copyStatus.value = "请手动复制";
  }
}
watch(
  () => route.params.id,
  () => {
    copyStatus.value = "";
    load();
  },
  { immediate: true },
);
watch(
  () => [
    route.params.id,
    tab.value,
    recordKind.value,
    recordPage.value,
    period.value,
  ],
  () => {
    if (["wallet", "learning"].includes(tab.value)) loadRecords();
    if (tab.value === "usage") loadUsage();
  },
  { immediate: true },
);
</script>
