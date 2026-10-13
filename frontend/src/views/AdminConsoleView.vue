<template>
  <div class="admin-page">
    <div class="admin-page-head">
      <div>
        <h1>积分卡</h1>
        <p>
          管理兑换码、发放额度和兑换记录，共 {{ number(total) }} 张匹配积分卡。
        </p>
      </div>
      <div class="a-actions">
        <button class="a-button" :disabled="loading" @click="load">刷新</button
        ><button class="a-button primary" @click="openCreate">
          ＋ 生成积分卡
        </button>
      </div>
    </div>
    <div v-if="error" class="a-error" role="alert">{{ error }}</div>
    <div v-if="message" class="a-success" role="status">{{ message }}</div>
    <section class="a-panel">
      <form class="a-filters" @submit.prevent="apply">
        <label class="a-field wide"
          >搜索积分卡<input
            v-model="filters.q"
            placeholder="兑换码、尾号、备注或创建者"
        /></label>
        <label class="a-field"
          >类型<select v-model="filters.mode">
            <option value="">全部</option>
            <option value="add">增加积分</option>
            <option value="reset">重置余额</option>
          </select></label
        >
        <label class="a-field"
          >状态<select v-model="filters.status">
            <option value="">全部</option>
            <option value="active">已启用</option>
            <option value="disabled">已停用</option>
            <option value="unused">未兑换</option>
            <option value="redeemed">有兑换记录</option>
            <option value="exhausted">已兑完</option>
          </select></label
        >
        <label class="a-field"
          >最低额度（元）<input
            v-model="filters.minYuan"
            type="number"
            min="0"
            step="0.01"
            placeholder="不限" /></label
        ><label class="a-field"
          >最高额度（元）<input
            v-model="filters.maxYuan"
            type="number"
            min="0"
            step="0.01"
            placeholder="不限"
        /></label>
        <label class="a-field"
          >排序<select v-model="filters.sort_by">
            <option value="created_at">生成时间</option>
            <option value="amount">额度</option>
            <option value="redeemed_count">兑换人数</option>
            <option value="max_redemptions">人数上限</option>
            <option value="code">卡号</option>
            <option value="mode">类型</option>
            <option value="status">停用状态</option>
          </select></label
        >
        <label class="a-field"
          >顺序<select v-model="filters.sort_order">
            <option value="desc">降序</option>
            <option value="asc">升序</option>
          </select></label
        >
        <button class="a-button primary">筛选</button
        ><button class="a-button" type="button" @click="reset">重置</button>
      </form>
      <div v-if="loading" class="a-empty">正在加载积分卡…</div>
      <div v-else-if="error" class="a-empty">
        <button class="a-button" @click="load">重试</button>
      </div>
      <div v-else-if="!cards.length" class="a-empty">
        暂无匹配记录，可以调整筛选或生成新的积分卡。
      </div>
      <div v-else class="a-table-wrap">
        <table class="a-table">
          <thead>
            <tr>
              <th>兑换码 / 备注</th>
              <th>类型</th>
              <th>额度</th>
              <th>兑换人数</th>
              <th>状态</th>
              <th>最近邮件发送</th>
              <th>生成时间</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="card in cards" :key="card.card_id">
              <td>
                <code>{{
                  card.code_plain || `历史卡 · 尾号 ${card.code_preview}`
                }}</code>
                <div class="a-muted">
                  {{ card.note || "无备注" }} · {{ card.created_by || "admin" }}
                </div>
              </td>
              <td>
                <span class="a-tag" :class="{ warn: card.mode === 'reset' }">{{
                  card.mode === "reset" ? "重置余额" : "增加积分"
                }}</span>
              </td>
              <td class="numeric">
                {{ number(card.amount) }}
                <div class="a-muted">
                  {{ number(card.amount / 1000000) }} 元
                </div>
              </td>
              <td>
                {{ card.redeemed_count }} / {{ card.max_redemptions || "不限" }}
              </td>
              <td>
                <span
                  class="a-tag"
                  :class="{ good: cardStatus(card) === '可兑换' }"
                  >{{ cardStatus(card) }}</span
                >
              </td>
              <td>
                <template v-if="card.delivery"
                  ><span
                    class="a-tag"
                    :class="{
                      good: card.delivery.status === 'sent',
                      warn: ['failed', 'unknown'].includes(
                        card.delivery.status,
                      ),
                    }"
                    >{{ deliveryLabel(card.delivery.status) }}</span
                  >
                  <div class="a-muted">{{ card.delivery.recipient_email }}</div>
                  <div v-if="card.delivery.last_error" class="a-muted">
                    {{ card.delivery.last_error }}
                  </div>
                  <button
                    v-if="
                      ['sent', 'failed', 'unknown'].includes(
                        card.delivery.status,
                      )
                    "
                    class="a-button"
                    :disabled="
                      retryingEmail === card.card_id || !!card.disabled
                    "
                    @click="retryEmail(card.card_id)"
                  >
                    重发邮件
                  </button></template
                ><span v-else class="a-muted">仅生成</span>
              </td>
              <td>
                {{ time(card.created_at) }}
                <div v-if="card.expires_at" class="a-muted">
                  到期 {{ time(card.expires_at) }}
                </div>
              </td>
              <td>
                <div class="a-actions">
                  <button
                    v-if="card.code_plain"
                    class="a-button"
                    :disabled="
                      creating ||
                      cardStatus(card) !== '可兑换' ||
                      ['queued', 'sending'].includes(card.delivery?.status)
                    "
                    @click="openGift(card)"
                  >
                    赠送
                  </button>
                  <button
                    v-if="card.code_plain"
                    class="a-button"
                    @click="copyCode(card.code_plain)"
                  >
                    复制</button
                  ><button class="a-button" @click="showRecords(card)">
                    明细</button
                  ><button
                    class="a-button"
                    :class="{ danger: !card.disabled }"
                    :disabled="updating === card.card_id"
                    @click="toggleCard(card)"
                  >
                    {{ card.disabled ? "恢复" : "停用" }}
                  </button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <div class="a-pager">
        <span>第 {{ page }} / {{ pages }} 页 · 每页 25 张</span>
        <div class="a-actions">
          <button
            class="a-button"
            :disabled="page <= 1 || loading"
            @click="go(-1)"
          >
            上一页</button
          ><button
            class="a-button"
            :disabled="page >= pages || loading"
            @click="go(1)"
          >
            下一页
          </button>
        </div>
      </div>
    </section>
    <dialog
      ref="createDialog"
      class="a-drawer"
      aria-labelledby="create-card-title"
    >
      <div class="a-drawer-head">
        <h2 id="create-card-title">
          {{ giftCard ? "赠送积分卡" : "生成积分卡" }}
        </h2>
        <button
          class="a-button"
          aria-label="关闭生成面板"
          @click="createDialog.close()"
        >
          关闭
        </button>
      </div>
      <section v-if="giftCard" class="gift-summary">
        <span class="a-tag">{{
          giftCard.mode === "reset" ? "重置余额" : "增加积分"
        }}</span>
        <h3>{{ number(giftCard.amount) }} 积分</h3>
        <code class="a-code">{{ giftCard.code_plain }}</code>
        <p class="a-muted">
          已兑换 {{ giftCard.redeemed_count }} /
          {{ giftCard.max_redemptions || "不限" }} 人
        </p>
        <p v-if="giftCard.delivery" class="a-muted">
          最近收件邮箱：{{ giftCard.delivery.recipient_email }} ·
          {{ deliveryLabel(giftCard.delivery.status) }}
        </p>
        <p class="a-muted">
          赠送会发送此兑换码，不会新增卡片或增加可兑换人数，也不会为收件人预留名额。
        </p>
        <p v-if="giftCard.mode === 'reset'" class="a-error">
          重置卡会覆盖收件人的原有积分余额，可能减少已有积分。
        </p>
      </section>
      <form @submit.prevent="create">
        <template v-if="!giftCard">
          <label class="a-field"
            >类型<select v-model="form.mode">
              <option value="add">增加积分</option>
              <option value="reset">重置为指定余额</option>
            </select></label
          >
          <div v-if="form.mode === 'reset'" class="a-error">
            重置卡会将用户整个余额改为指定额度，可能减少已有积分。
          </div>
          <label class="a-field"
            >金额（元）<input
              v-model.number="form.amountYuan"
              type="number"
              min="0.01"
              step="0.01"
              required
            /><span>1 元 = 1,000,000 积分</span></label
          >
          <label class="a-field"
            >可兑换人数<input
              v-model.number="form.maxRedemptions"
              type="number"
              min="0"
              step="1"
              required
            /><span>0 表示不限人数；每个用户只能兑换一次。</span></label
          >
          <label class="a-field"
            >备注<textarea
              v-model="form.note"
              maxlength="200"
              rows="3"
              placeholder="例如：课程活动奖励"
            />
          </label>
          <label class="email-toggle"
            ><input
              v-model="sendEmail"
              type="checkbox"
              :disabled="creating || !!generated"
            />
            生成后发送到用户邮箱</label
          >
        </template>
        <section v-if="sendEmail" class="email-recipient">
          <label class="a-field"
            >选择收件用户<input
              v-model="userQuery"
              type="search"
              placeholder="搜索昵称、邮箱、用户 ID 或 GitHub 用户名"
              :disabled="creating || !!generated"
          /></label>
          <p v-if="usersLoading" class="a-muted" role="status">正在搜索用户…</p>
          <p v-if="usersError" class="a-error">{{ usersError }}</p>
          <div
            v-if="!recipient && !usersLoading && !generated"
            class="recipient-options"
            aria-label="搜索结果"
          >
            <button
              v-for="user in matchingUsers"
              :key="user.id"
              type="button"
              class="recipient-option"
              :disabled="!user.email || creating"
              @click="selectRecipient(user)"
            >
              <span
                >{{ user.name }} <small>{{ user.id }}</small></span
              ><span>{{ user.email || "未提供邮箱，无法发送" }}</span>
            </button>
            <p v-if="!matchingUsers.length && !usersError" class="a-muted">
              没有匹配用户，请更换关键词。
            </p>
          </div>
          <div v-if="recipient" class="recipient-selected">
            <strong>{{ recipient.name }}</strong>
            <p>{{ recipient.email }}</p>
            <button
              v-if="!generated"
              type="button"
              class="a-button"
              :disabled="creating"
              @click="clearRecipient"
            >
              更换用户
            </button>
          </div>
          <p class="a-muted">
            邮件包含兑换码和兑换说明，发送不会自动增加积分。兑换码仍按卡片原有规则使用。
          </p>
        </section>
        <button
          class="a-button primary"
          :disabled="creating || (sendEmail && (!recipient || !!generated))"
        >
          {{
            creating
              ? "正在处理…"
              : giftCard
                ? "发送赠送邮件"
                : sendEmail
                  ? "生成并发送邮件"
                  : "生成兑换码"
          }}
        </button>
      </form>
      <div
        v-if="createError"
        class="a-error"
        style="margin-top: 18px"
        role="alert"
      >
        {{ createError }}
      </div>
      <section v-if="generatedDelivery" class="email-result" role="status">
        <strong>{{ deliveryLabel(generatedDelivery.status) }}</strong>
        <p class="a-muted">
          {{ generatedDelivery.recipient_email }} · 已尝试
          {{ generatedDelivery.attempts }} 次
        </p>
        <p v-if="generatedDelivery.last_error" class="a-error">
          {{ generatedDelivery.last_error }}
        </p>
        <p v-if="generatedDelivery.status === 'sent'" class="a-muted">
          邮件服务器已接受，请用户检查收件箱或垃圾邮件。
        </p>
        <button
          v-if="['failed', 'unknown'].includes(generatedDelivery.status)"
          class="a-button"
          :disabled="retryingEmail === generatedId"
          @click="retryEmail(generatedId)"
        >
          重发同一兑换码
        </button>
      </section>
      <template v-if="generated"
        ><p class="a-muted" style="margin-top: 24px">
          {{
            generatedDelivery
              ? giftCard
                ? "本次赠送使用以下兑换码。"
                : "积分卡已生成，邮件发送状态如上。"
              : "生成成功，可以将以下兑换码发给用户。"
          }}
        </p>
        <code class="a-code">{{ generated }}</code
        ><button class="a-button" @click="copyGenerated">
          {{ generatedCopy || "复制兑换码" }}
        </button></template
      >
    </dialog>
    <dialog
      ref="recordsDialog"
      class="a-drawer"
      aria-labelledby="redemptions-title"
    >
      <div class="a-drawer-head">
        <h2 id="redemptions-title">兑换明细</h2>
        <button class="a-button" @click="recordsDialog.close()">关闭</button>
      </div>
      <template v-if="selected"
        ><code class="a-code">{{
          selected.code_plain || selected.code_preview
        }}</code>
        <p class="a-muted">共兑换 {{ selected.redeemed_count }} 次</p>
        <div v-if="!selected.redemptions?.length" class="a-empty">尚未兑换</div>
        <article
          v-for="record in selected.redemptions || []"
          :key="record.id"
          class="card-redemption"
        >
          <router-link
            class="a-link"
            :to="`/admin/users/${encodeURIComponent(record.user_id)}`"
            >{{
              record.user_name || record.user_email || record.user_id
            }}
            →</router-link
          >
          <p class="a-muted">{{ record.user_email || record.user_id }}</p>
          <p>
            积分变化 {{ record.amount > 0 ? "+" : ""
            }}{{ number(record.amount) }} · 余额
            {{ number(record.balance_after) }}
          </p>
          <p class="a-muted">{{ time(record.created_at) }}</p>
        </article></template
      >
    </dialog>
  </div>
</template>
<script setup>
import { computed, reactive, ref, watch, onBeforeUnmount } from "vue";
import { useRoute, useRouter } from "vue-router";
import { adminApi } from "../api/admin.js";
import { number, time, pageNumber, copy } from "../components/Admin/format.js";
const route = useRoute(),
  router = useRouter();
const defaults = {
  q: "",
  mode: "",
  status: "",
  minYuan: "",
  maxYuan: "",
  sort_by: "created_at",
  sort_order: "desc",
};
const filters = reactive({ ...defaults }),
  cards = ref([]),
  total = ref(0),
  loading = ref(false),
  error = ref(""),
  message = ref(""),
  updating = ref("");
const page = computed(() => pageNumber(route.query.page)),
  pages = computed(() => Math.max(1, Math.ceil(total.value / 25)));
const createDialog = ref(null),
  recordsDialog = ref(null),
  selected = ref(null),
  creating = ref(false),
  createError = ref(""),
  generated = ref(""),
  generatedCopy = ref("");
const form = reactive({
  mode: "add",
  amountYuan: 5,
  maxRedemptions: 1,
  note: "",
});
const sendEmail = ref(false),
  userQuery = ref(""),
  matchingUsers = ref([]),
  usersLoading = ref(false),
  usersError = ref(""),
  recipient = ref(null);
const generatedId = ref(""),
  giftCard = ref(null),
  generatedDelivery = ref(null),
  retryingEmail = ref("");
let emailRequestId = "",
  userRequest = 0,
  searchTimer,
  pollTimer,
  disposed = false;
let request = 0;
function deliveryLabel(status) {
  return (
    {
      queued: "等待发送",
      sending: "发送中",
      sent: "已提交邮件服务器",
      failed: "发送失败",
      unknown: "发送状态不明",
    }[status] || status
  );
}
async function searchUsers() {
  const n = ++userRequest;
  usersLoading.value = true;
  usersError.value = "";
  try {
    const result = await adminApi.users({ q: userQuery.value, limit: 8 });
    if (n === userRequest) matchingUsers.value = result.items;
  } catch (e) {
    if (n === userRequest) usersError.value = e.message;
  } finally {
    if (n === userRequest) usersLoading.value = false;
  }
}
watch([sendEmail, userQuery], () => {
  clearTimeout(searchTimer);
  userRequest++;
  recipient.value = null;
  matchingUsers.value = [];
  usersError.value = "";
  usersLoading.value = false;
  if (sendEmail.value) searchTimer = setTimeout(searchUsers, 250);
});
function selectRecipient(user) {
  recipient.value = user;
}
function clearRecipient() {
  recipient.value = null;
  searchUsers();
}
function schedulePoll() {
  clearTimeout(pollTimer);
  if (disposed) return;
  const pending = (d) => d && ["queued", "sending"].includes(d.status);
  if (
    !pending(generatedDelivery.value) &&
    !cards.value.some((c) => pending(c.delivery))
  )
    return;
  pollTimer = setTimeout(async () => {
    try {
      if (generatedId.value && pending(generatedDelivery.value))
        generatedDelivery.value = await adminApi.cardEmail(generatedId.value);
    } catch (e) {
      createError.value = e.message;
    }
    if (!disposed) await load(true);
  }, 2000);
}
async function retryEmail(id) {
  if (retryingEmail.value) return;
  if (
    !window.confirm(
      "将向原收件邮箱重新发送同一兑换码。若发送状态不明，请先检查收件箱，确认重发？",
    )
  )
    return;
  retryingEmail.value = id;
  error.value = "";
  createError.value = "";
  try {
    const result = await adminApi.retryCardEmail(id);
    if (id === generatedId.value) generatedDelivery.value = result;
    await load(true);
  } catch (e) {
    if (id === generatedId.value) createError.value = e.message;
    else error.value = e.message;
  } finally {
    retryingEmail.value = "";
  }
}

function credits(value) {
  return value === "" || value == null
    ? ""
    : Math.round(Number(value) * 1000000);
}
async function load(silent = false) {
  silent = silent === true;
  const n = ++request;
  if (!silent) loading.value = true;
  error.value = "";
  try {
    const f = { ...defaults, ...route.query };
    const result = await adminApi.creditCards({
      ...f,
      min_amount: credits(f.minYuan),
      max_amount: credits(f.maxYuan),
      limit: 25,
      offset: (page.value - 1) * 25,
    });
    if (n !== request) return;
    cards.value = result.items;
    total.value = result.total;
  } catch (e) {
    if (n === request) error.value = e.message;
  } finally {
    if (n === request) {
      loading.value = false;
      schedulePoll();
    }
  }
}
function apply() {
  const query = Object.fromEntries(
    Object.entries(filters).filter(([, v]) => v !== ""),
  );
  if (JSON.stringify(query) === JSON.stringify(route.query)) load();
  else router.push({ query });
}
function reset() {
  Object.assign(filters, defaults);
  router.push("/admin/credit-cards");
}
function go(delta) {
  router.push({ query: { ...route.query, page: String(page.value + delta) } });
}
function cardStatus(card) {
  if (card.disabled) return "已停用";
  if (card.expires_at && Date.parse(card.expires_at) < Date.now())
    return "已过期";
  if (card.max_redemptions && card.redeemed_count >= card.max_redemptions)
    return "已兑完";
  return "可兑换";
}
function openCreate() {
  if (creating.value) return;
  giftCard.value = null;
  generatedId.value = "";
  generatedDelivery.value = null;
  sendEmail.value = false;
  userQuery.value = "";
  recipient.value = null;
  emailRequestId = Array.from(crypto.getRandomValues(new Uint8Array(16)), (v) =>
    v.toString(16).padStart(2, "0"),
  ).join("");
  createError.value = "";
  generated.value = "";
  generatedCopy.value = "";
  createDialog.value.showModal();
}
function openGift(card) {
  if (creating.value) return;
  openCreate();
  giftCard.value = card;
  sendEmail.value = true;
}
async function create() {
  if (
    creating.value ||
    (sendEmail.value && (!recipient.value || generated.value))
  )
    return;
  createError.value = "";
  if (
    (giftCard.value?.mode || form.mode) === "reset" &&
    !window.confirm("此卡会覆盖兑换者的全部积分余额，确认继续？")
  )
    return;
  creating.value = true;
  generated.value = "";
  generatedCopy.value = "";
  try {
    let result;
    if (giftCard.value) {
      const card = giftCard.value;
      const delivery = await adminApi.giftCreditCard(card.card_id, {
        recipient_user_id: recipient.value.id,
        email_request_id: emailRequestId,
      });
      result = { card_id: card.card_id, code: card.code_plain, delivery };
    } else {
      result = await adminApi.createCreditCard({
        mode: form.mode,
        amount: credits(form.amountYuan),
        max_redemptions: form.maxRedemptions,
        note: form.note,
        ...(sendEmail.value
          ? {
              recipient_user_id: recipient.value.id,
              email_request_id: emailRequestId,
            }
          : {}),
      });
    }
    generatedId.value = result.card_id;
    generatedDelivery.value = result.delivery || null;
    generated.value = result.code;
    await load();
  } catch (e) {
    createError.value = e.message;
  } finally {
    creating.value = false;
  }
}
async function copyGenerated() {
  try {
    await copy(generated.value);
    generatedCopy.value = "已复制";
  } catch {
    generatedCopy.value = "复制失败，请手动复制";
  }
}
async function copyCode(code) {
  try {
    await copy(code);
    message.value = "兑换码已复制";
  } catch {
    error.value = "复制失败，请手动选中兑换码复制";
  }
}
function showRecords(card) {
  selected.value = card;
  recordsDialog.value.showModal();
}
async function toggleCard(card) {
  const action = card.disabled ? "恢复" : "停用";
  if (!window.confirm(`确认${action}这张积分卡？`)) return;
  updating.value = card.card_id;
  error.value = "";
  message.value = "";
  try {
    await adminApi.updateCreditCardStatus(card.card_id, !card.disabled);
    message.value = `积分卡已${action}`;
    await load();
  } catch (e) {
    error.value = e.message;
  } finally {
    updating.value = "";
  }
}
watch(
  () => route.query,
  () => {
    Object.assign(
      filters,
      Object.fromEntries(
        Object.keys(defaults).map((key) => [
          key,
          route.query[key] ?? defaults[key],
        ]),
      ),
    );
    load();
  },
  { immediate: true },
);
onBeforeUnmount(() => {
  disposed = true;
  userRequest++;
  clearTimeout(searchTimer);
  clearTimeout(pollTimer);
  createDialog.value?.close();
  recordsDialog.value?.close();
});
</script>
<style scoped>
.card-redemption {
  padding: 20px 0;
  border-bottom: 1px solid var(--border);
  font-size: 13px;
}
.card-redemption p {
  margin-top: 7px;
}
.email-toggle {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 13px;
  cursor: pointer;
}
.gift-summary {
  display: grid;
  gap: 12px;
  margin-bottom: 24px;
}
.gift-summary h3,
.gift-summary p {
  margin: 0;
}
.gift-summary .a-code {
  margin: 0;
}
.gift-summary .a-tag {
  justify-self: start;
}
.email-recipient {
  display: grid;
  gap: 12px;
  padding: 16px;
  border: 1px solid var(--border);
  border-radius: 8px;
}
.recipient-options {
  max-height: 220px;
  overflow: auto;
  display: grid;
  gap: 6px;
}
.recipient-option {
  display: grid;
  gap: 4px;
  padding: 10px;
  text-align: left;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--bg-panel);
  color: var(--text-primary);
  cursor: pointer;
  font-size: 12px;
  overflow-wrap: anywhere;
}
.recipient-option:hover {
  background: var(--bg-hover);
}
.recipient-option:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}
.recipient-option small {
  color: var(--text-secondary);
  margin-left: 6px;
}
.recipient-selected {
  padding: 12px;
  border-radius: 6px;
  background: var(--brand-dim);
  font-size: 13px;
  overflow-wrap: anywhere;
}
.recipient-selected .a-button {
  margin-top: 8px;
}
.email-result {
  margin-top: 20px;
  padding: 14px;
  border: 1px solid var(--border);
  border-radius: 8px;
  overflow-wrap: anywhere;
}
</style>
