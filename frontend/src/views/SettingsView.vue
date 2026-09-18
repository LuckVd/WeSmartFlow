<template>
  <div class="settings-page page-std">
    <div class="page-header">
      <div>
        <h1 class="page-title">设置</h1>
        <p class="page-subtitle">配置 AI 模型和 API 参数</p>
      </div>
      <button class="btn btn-primary" :disabled="saving" @click="saveAll">
        <svg
          v-if="!saveSuccess"
          width="13"
          height="13"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
        >
          <path
            d="M19 21H5a2 2 0 01-2-2V5a2 2 0 012-2h11l5 5v11a2 2 0 01-2 2z"
          />
          <polyline points="17 21 17 13 7 13 7 21" />
          <polyline points="7 3 7 8 15 8" />
        </svg>
        {{ saveSuccess ? "✓ 已保存" : saving ? "保存中..." : "保存设置" }}
      </button>
    </div>

    <!-- 功能可用性（issue #62/#103） -->
    <div v-if="features" class="features-status card">
      <span class="fs-title">功能状态</span>
      <span
        v-for="(ok, name) in features"
        :key="name"
        class="fs-chip"
        :class="ok ? 'ok' : 'off'"
      >
        {{ featureLabels[name] || name }}{{ ok ? " ✓" : " 未配置" }}
      </span>
    </div>

    <!-- 用量概览 -->
    <div v-if="quotaLoaded" class="quota-overview card">
      <div class="quota-header">
        <span class="quota-title">我的积分</span>
        <span class="wallet-badge">跨月保留</span>
      </div>
      <div class="wallet-balance-row">
        <div>
          <strong class="wallet-number">{{
            formatCredits(wallet.remaining)
          }}</strong
          ><span class="wallet-unit">可用积分</span>
        </div>
        <span class="quota-hint"
          >本月已用 {{ formatCredits(wallet.used) }}</span
        >
      </div>
      <div
        class="wallet-progress"
        role="progressbar"
        aria-label="可用积分"
        :aria-valuenow="Math.max(0, wallet.remaining || 0)"
        :aria-valuemax="walletCapacity"
        :aria-valuemin="0"
        :aria-valuetext="`${formatCredits(wallet.remaining)} 积分可用`"
      >
        <div
          class="wallet-progress-fill"
          :class="{ 'is-low': walletPercent < 20 }"
          :style="{ width: walletPercent + '%' }"
        />
      </div>
      <div class="wallet-scale">
        <span>0</span><span>{{ formatCredits(walletCapacity) }} 积分</span>
      </div>
      <p v-if="wallet.balance < 0" class="wallet-note">
        待抵扣 {{ formatCredits(-wallet.balance) }} 积分，后续赠送将优先抵扣。
      </p>
      <p class="wallet-note">
        注册赠送
        {{ formatCredits(wallet.signup_credits) }} 积分；次月起每月补充最多
        {{ formatCredits(wallet.monthly_credits) }}，补至
        {{ formatCredits(wallet.monthly_cap) }}。
      </p>
      <div class="credit-card-box">
        <div class="credit-card-copy">
          <strong>兑换积分卡</strong>
          <span>输入管理员发放的兑换码，可增加积分或重置可用积分。</span>
        </div>
        <div class="credit-card-actions">
          <input
            v-model="creditCardCode"
            class="form-input credit-card-input"
            placeholder="输入积分卡兑换码"
            @keyup.enter="redeemCreditCard"
          />
          <button
            class="btn btn-primary btn-sm"
            :disabled="redeemingCard || !creditCardCode.trim()"
            @click="redeemCreditCard"
          >
            {{ redeemingCard ? "兑换中..." : "兑换" }}
          </button>
        </div>
        <div
          v-if="creditCardMessage"
          class="status-hint"
          :class="creditCardStatus"
        >
          {{ creditCardMessage }}
        </div>
      </div>
      <div class="wallet-reward">
        <div class="wallet-reward-copy">
          <a
            href="https://github.com/Tencent/WeSmartFlow"
            target="_blank"
            rel="noopener noreferrer"
            >Star WeSmartFlow</a
          >
          <span
            >额外获得
            {{ formatCredits(wallet.github_reward_credits) }} 积分</span
          >
        </div>
        <span v-if="wallet.github_reward_claimed" class="wallet-claimed"
          >✓ 已领取</span
        >
        <button
          v-else
          class="wallet-claim-button"
          :disabled="rewardLoading"
          @click="claimGithubReward"
        >
          {{
            rewardLoading
              ? "正在跳转…"
              : wallet.github_linked
                ? "验证并领取"
                : "绑定 GitHub 并领取"
          }}
        </button>
      </div>
      <p v-if="rewardMessage" class="wallet-note" role="status">
        {{ rewardMessage }}
      </p>
      <details class="wallet-history">
        <summary>积分明细</summary>
        <div
          v-for="(entry, index) in wallet.transactions"
          :key="index"
          class="wallet-entry"
        >
          <div>
            <span>{{ transactionLabel(entry.kind) }}</span
            ><time>{{ new Date(entry.created_at).toLocaleString() }}</time>
          </div>
          <span
            class="wallet-entry-amount"
            :class="{ 'is-gain': entry.amount > 0 }"
            >{{ entry.amount > 0 ? "+" : entry.amount < 0 ? "−" : ""
            }}{{ formatCredits(Math.abs(entry.amount)) }}</span
          >
        </div>
      </details>
    </div>

    <div class="settings-layout">
      <!-- Sidebar tabs -->
      <div class="settings-tabs">
        <button
          v-for="tab in tabs"
          :key="tab.key"
          class="st-btn"
          :class="{ active: activeTab === tab.key }"
          @click="activeTab = tab.key"
        >
          <span v-html="tab.icon" />
          {{ tab.label }}
        </button>
      </div>

      <!-- Content -->
      <div class="settings-content">
        <!-- AI 模型 -->
        <div v-if="activeTab === 'model'">
          <div class="settings-section card">
            <div class="ss-title">AI 模型配置</div>
            <p class="ss-desc">
              使用 OpenAI 兼容格式的 LLM 接口，需支持
              <strong>Function Calling</strong>（工具调用）能力。
            </p>

            <div class="config-block">
              <div class="cb-title">API 配置</div>
              <div class="form-item">
                <label>API Key</label>
                <div class="input-with-btn">
                  <input
                    v-model="form.llm_api_key"
                    class="form-input"
                    :type="showKey ? 'text' : 'password'"
                    placeholder="sk-..."
                  />
                  <button
                    class="btn btn-ghost btn-sm"
                    @click="showKey = !showKey"
                  >
                    {{ showKey ? "隐藏" : "显示" }}
                  </button>
                </div>
                <div v-if="maskedKeys.llm_api_key" class="field-hint">
                  当前已保存：{{ maskedKeys.llm_api_key }}
                </div>
              </div>
              <div class="form-item">
                <label>Base URL</label>
                <input
                  v-model="form.llm_base_url"
                  class="form-input"
                  placeholder="https://api.openai.com/v1"
                />
              </div>
              <div class="form-item">
                <label
                  >模型名称
                  <span class="optional"
                    >（需支持 Function Calling）</span
                  ></label
                >
                <input
                  v-model="form.llm_model"
                  class="form-input"
                  placeholder="gpt-4o / deepseek-chat / qwen-plus ..."
                />
              </div>
              <div class="form-item-row">
                <button
                  class="btn btn-ghost btn-sm"
                  :disabled="testing"
                  @click="testLLM"
                >
                  {{ testing ? "测试中..." : "测试连接" }}
                </button>
                <div
                  v-if="testStatus !== 'idle'"
                  class="status-hint"
                  :class="testStatus"
                >
                  <span v-if="testStatus === 'success'">✓ {{ testReply }}</span>
                  <span v-else>✗ {{ testError }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Tavily 搜索 -->
        <div v-if="activeTab === 'tavily'">
          <div class="settings-section card">
            <div class="ss-title">Tavily 搜索配置</div>
            <p class="ss-desc">
              Tavily 是专为 AI 设计的搜索 API，用于联网搜索增强回答。访问
              <a
                href="https://tavily.com"
                target="_blank"
                style="color: var(--brand-light)"
                >tavily.com</a
              >获取 <strong>免费</strong> API Key。
            </p>
            <div class="config-block">
              <div class="cb-title">API 配置</div>
              <div class="form-item">
                <label>Tavily API Key</label>
                <div class="input-with-btn">
                  <input
                    v-model="form.tavily_api_key"
                    class="form-input"
                    :type="showTavilyKey ? 'text' : 'password'"
                    placeholder="tvly-..."
                  />
                  <button
                    class="btn btn-ghost btn-sm"
                    @click="showTavilyKey = !showTavilyKey"
                  >
                    {{ showTavilyKey ? "隐藏" : "显示" }}
                  </button>
                </div>
                <div v-if="maskedKeys.tavily_api_key" class="field-hint">
                  当前已保存：{{ maskedKeys.tavily_api_key }}
                </div>
              </div>
              <div class="form-item-row">
                <button
                  class="btn btn-ghost btn-sm"
                  :disabled="testingTavily"
                  @click="testTavily"
                >
                  {{ testingTavily ? "测试中..." : "测试连接" }}
                </button>
                <div
                  v-if="tavilyStatus !== 'idle'"
                  class="status-hint"
                  :class="tavilyStatus"
                >
                  <span v-if="tavilyStatus === 'success'"
                    >✓ {{ tavilyReply }}</span
                  >
                  <span v-else>✗ {{ tavilyError }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- 图像生成 -->
        <div v-if="activeTab === 'image'">
          <div class="settings-section card">
            <div class="ss-title">图像生成 API 配置</div>
            <p class="ss-desc">
              配置兼容 OpenAI Images
              API（<code>/v1/images/generations</code>）的图像生成服务。
            </p>
            <div class="config-block">
              <div class="cb-title">API 配置</div>
              <div class="form-item">
                <label>API Key</label>
                <div class="input-with-btn">
                  <input
                    v-model="form.img_api_key"
                    class="form-input"
                    :type="showImgKey ? 'text' : 'password'"
                    placeholder="any"
                  />
                  <button
                    class="btn btn-ghost btn-sm"
                    @click="showImgKey = !showImgKey"
                  >
                    {{ showImgKey ? "隐藏" : "显示" }}
                  </button>
                </div>
                <div v-if="maskedKeys.img_api_key" class="field-hint">
                  当前已保存：{{ maskedKeys.img_api_key }}
                </div>
              </div>
              <div class="form-item">
                <label>Base URL</label>
                <input
                  v-model="form.img_base_url"
                  class="form-input"
                  placeholder="http://localhost:8080/v1"
                />
              </div>
              <div class="form-item">
                <label>模型名称</label>
                <input
                  v-model="form.img_model"
                  class="form-input"
                  placeholder="gpt-image-1 / dall-e-3 / qwen-image-2.0 ..."
                />
              </div>
              <div class="form-item-row">
                <button
                  class="btn btn-ghost btn-sm"
                  :disabled="testingImage"
                  @click="testImageGen"
                >
                  {{ testingImage ? "测试中..." : "测试连接" }}
                </button>
                <div
                  v-if="imageStatus !== 'idle'"
                  class="status-hint"
                  :class="imageStatus"
                >
                  <span v-if="imageStatus === 'success'"
                    >✓ {{ imageReply }}</span
                  >
                  <span v-else>✗ {{ imageError }}</span>
                </div>
                <div v-if="testImageUrl" class="test-image-preview">
                  <img :src="testImageUrl" alt="测试生成图片" />
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- 数据备份 -->
        <div v-if="activeTab === 'backup'">
          <div class="settings-section card">
            <div class="ss-title">数据备份</div>
            <p class="ss-desc">
              导出当前用户的会话记录、知识节点、复习进度、长期画像和知识库。不会导出密码、API
              Key、Token 或日志。
            </p>
            <div class="config-block">
              <div class="cb-title">导出</div>
              <div class="backup-actions">
                <button
                  class="btn btn-primary"
                  :disabled="exportingBackup"
                  @click="exportBackup"
                >
                  {{ exportingBackup ? "导出中..." : "导出记忆与知识库" }}
                </button>
                <span class="field-hint"
                  >保存为 JSON 文件，可用于换设备或重装后恢复。</span
                >
              </div>
            </div>
            <div class="config-block backup-import-block">
              <div class="cb-title">导入</div>
              <p class="field-hint">
                导入会合并到当前登录用户：同 ID 数据覆盖，新数据插入；不会恢复
                API Key 或密码。
              </p>
              <div class="backup-actions">
                <input
                  ref="backupFileInput"
                  type="file"
                  accept="application/json,.json"
                  class="hidden-file"
                  @change="onBackupFileChange"
                />
                <button
                  class="btn btn-ghost"
                  :disabled="importingBackup"
                  @click="backupFileInput?.click()"
                >
                  {{ importingBackup ? "导入中..." : "选择备份 JSON 导入" }}
                </button>
                <div
                  v-if="backupStatus"
                  class="status-hint"
                  :class="backupStatusType"
                >
                  {{ backupStatus }}
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- 关于 -->
        <div v-if="activeTab === 'about'">
          <div class="settings-section card about-card">
            <div class="about-logo">
              <div class="logo-mark-lg">
                <img src="/logo.png" alt="Logo" class="logo-img-lg" />
              </div>
              <div>
                <div class="about-name">WeSmartFlow</div>
                <div class="about-tagline">你的本地个人知识大脑</div>
              </div>
            </div>
            <div class="about-desc">
              WeSmartFlow 是一个开源的本地 AI 教育助手。你学过的所有东西，都被
              AI
              组织成一张属于你自己的知识图谱，完全离线，完全私有，越用越懂你。
            </div>
            <div class="about-meta">
              <div class="am-item">
                <span class="am-label">版本</span><span>v0.1.0-alpha</span>
              </div>
              <div class="am-item">
                <span class="am-label">许可证</span><span>MIT</span>
              </div>
              <div class="am-item">
                <span class="am-label">技术栈</span
                ><span>Vue 3 + Vite + Python</span>
              </div>
            </div>
            <div class="about-links">
              <a
                class="btn btn-ghost btn-sm"
                href="https://github.com/Tencent/WeSmartFlow"
                target="_blank"
              >
                <svg
                  width="12"
                  height="12"
                  viewBox="0 0 24 24"
                  fill="currentColor"
                >
                  <path
                    d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z"
                  />
                </svg>
                GitHub
              </a>
              <a class="btn btn-ghost btn-sm" href="#" target="_blank"
                >📖 文档</a
              >
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, computed } from "vue";
import { settingsApi, authApi } from "@/api";
import { useAuth } from "@/composables/useAuth.js";

const activeTab = ref("model");
const showKey = ref(false);
const saving = ref(false);
const saveSuccess = ref(false);
const testing = ref(false);
const testStatus = ref("idle"); // 'idle' | 'success' | 'error'
const testReply = ref("");
const testError = ref("");

// Tavily 测试状态
const showTavilyKey = ref(false);
const testingTavily = ref(false);
const tavilyStatus = ref("idle"); // 'idle' | 'success' | 'error'
const tavilyReply = ref("");
const tavilyError = ref("");

// 图像生成测试状态
const showImgKey = ref(false);
const testingImage = ref(false);
const imageStatus = ref("idle"); // 'idle' | 'success' | 'error'
const imageReply = ref("");
const imageError = ref("");
const testImageUrl = ref(""); // 测试生成的图片 base64 data URL

// 用量数据
const quotaLoaded = ref(false);
const features = ref(null);
const featureLabels = {
  llm: "AI 对话",
  search: "联网搜索",
  image: "图像生成",
};
async function loadFeatures() {
  try {
    const r = await settingsApi.getFeatures();
    features.value = r.data;
  } catch {
    /* 静默失败：状态条不显示 */
  }
}
loadFeatures();
const wallet = ref({ remaining: 0, used: 0, transactions: [] });
const rewardLoading = ref(false);
const { user } = useAuth();
const rewardMessage = ref("");
const creditCardCode = ref("");
const redeemingCard = ref(false);
const creditCardStatus = ref("idle");
const creditCardMessage = ref("");
const formatCredits = (credits) => Number(credits || 0).toLocaleString("zh-CN");
const walletCapacity = computed(() =>
  Math.max(
    Number(wallet.value.signup_credits || 5000000) +
      (wallet.value.github_reward_claimed
        ? Number(wallet.value.github_reward_credits || 0)
        : 0),
    Number(wallet.value.remaining || 0),
  ),
);
const walletPercent = computed(() =>
  Math.min(
    100,
    Math.max(
      0,
      (Number(wallet.value.remaining || 0) / walletCapacity.value) * 100,
    ),
  ),
);

const transactionLabel = (kind) =>
  ({
    signup: "注册/迁移赠送",
    monthly: "月度补充",
    github_star: "GitHub Star 奖励",
    credit_card_add: "积分卡充值",
    credit_card_reset: "积分卡重置",
    usage: "API 消费",
  })[kind] || kind;
async function claimGithubReward() {
  rewardLoading.value = true;
  rewardMessage.value = "";
  try {
    const { authorize_url } = await authApi.getGitHubAuthorizeUrl(true);
    sessionStorage.setItem("github-oauth-purpose", "reward");
    window.location.href = authorize_url;
  } catch (error) {
    rewardMessage.value = error.message;
    rewardLoading.value = false;
  }
}

async function redeemCreditCard() {
  const code = creditCardCode.value.trim();
  if (!code) return;
  redeemingCard.value = true;
  creditCardStatus.value = "idle";
  creditCardMessage.value = "";
  try {
    const data = await settingsApi.redeemCreditCard(code);
    const value =
      data.mode === "reset" ? data.card_amount : Math.abs(data.amount || 0);
    const verb = data.mode === "reset" ? "已重置为" : "已增加";
    creditCardStatus.value = "success";
    creditCardMessage.value = `${verb} ${formatCredits(value)} 积分，当前可用 ${formatCredits(data.remaining)} 积分。`;
    creditCardCode.value = "";
    await loadQuota();
  } catch (error) {
    creditCardStatus.value = "error";
    creditCardMessage.value = error.message || "兑换失败";
  } finally {
    redeemingCard.value = false;
  }
}

// 数据备份状态
const exportingBackup = ref(false);
const importingBackup = ref(false);
const backupStatus = ref("");
const backupStatusType = ref("success");
const backupFileInput = ref(null);

// 表单数据（用户输入，空字符串表示不修改）
const form = reactive({
  llm_api_key: "",
  llm_base_url: "",
  llm_model: "",
  tavily_api_key: "",
  img_api_key: "",
  img_base_url: "",
  img_model: "",
});

// 已保存的脱敏值（用于提示用户当前已配置）
const maskedKeys = reactive({
  llm_api_key: "",
  tavily_api_key: "",
  img_api_key: "",
});

const tabs = [
  {
    key: "model",
    label: "AI 模型",
    icon: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="3" width="20" height="14" rx="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/></svg>`,
  },
  {
    key: "tavily",
    label: "Tavily 搜索",
    icon: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>`,
  },
  {
    key: "image",
    label: "图像生成",
    icon: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg>`,
  },
  {
    key: "backup",
    label: "数据备份",
    icon: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>`,
  },
  {
    key: "about",
    label: "关于",
    icon: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>`,
  },
];

// 加载用量数据
async function loadQuota() {
  try {
    const data = await settingsApi.getQuota();
    wallet.value = data;
    const key = `github-reward:${user.value?.id || user.value?.user_id || ""}`;
    rewardMessage.value = (sessionStorage.getItem(key) || "").replace(
      "Star 奖励 5 元已到账。",
      "Star 奖励 5,000,000 积分已到账。",
    );
    sessionStorage.removeItem(key);
    quotaLoaded.value = true;
  } catch (e) {
    console.error("加载用量数据失败", e);
  }
}

// 加载当前配置
async function loadSettings() {
  try {
    const data = await settingsApi.get();
    // 非敏感字段直接填入表单
    form.llm_base_url = data.llm_base_url || "";
    form.llm_model = data.llm_model || "";
    form.img_base_url = data.img_base_url || "";
    form.img_model = data.img_model || "";
    // 敏感字段只存脱敏值用于提示
    maskedKeys.llm_api_key = data.llm_api_key || "";
    maskedKeys.tavily_api_key = data.tavily_api_key || "";
    maskedKeys.img_api_key = data.img_api_key || "";
  } catch (e) {
    console.error("加载设置失败", e);
  }
}

// 保存设置
async function saveAll() {
  saving.value = true;
  try {
    // 只发送非空字段（空字符串表示用户没有输入新值，不覆盖）
    const payload = {};
    for (const [k, v] of Object.entries(form)) {
      if (v !== "") payload[k] = v;
    }
    const data = await settingsApi.save(payload);
    if (data.ok) {
      // 保存成功后重新加载（刷新脱敏提示，清空密码输入框）
      form.llm_api_key = "";
      form.tavily_api_key = "";
      form.img_api_key = "";
      await loadSettings();
      // 显示保存成功状态，1.5s 后恢复
      saveSuccess.value = true;
      setTimeout(() => {
        saveSuccess.value = false;
      }, 1500);
    }
  } catch (e) {
    console.error("保存失败", e);
  } finally {
    saving.value = false;
  }
}

// 测试 LLM 连接
async function testLLM() {
  testing.value = true;
  testStatus.value = "idle";
  try {
    const data = await settingsApi.testLLM();
    if (data.ok) {
      testStatus.value = "success";
      testReply.value = data.reply || "连接成功";
    } else {
      testStatus.value = "error";
      testError.value = data.error || "连接失败";
    }
  } catch (e) {
    testStatus.value = "error";
    testError.value = String(e);
  } finally {
    testing.value = false;
    loadQuota();
  }
}

// 测试 Tavily 连接
async function testTavily() {
  testingTavily.value = true;
  tavilyStatus.value = "idle";
  try {
    const data = await settingsApi.testTavily();
    if (data.ok) {
      tavilyStatus.value = "success";
      tavilyReply.value = data.reply || "连接成功";
    } else {
      tavilyStatus.value = "error";
      tavilyError.value = data.error || "连接失败";
    }
  } catch (e) {
    tavilyStatus.value = "error";
    tavilyError.value = String(e);
  } finally {
    testingTavily.value = false;
    loadQuota();
  }
}

// 测试图像生成连接
async function testImageGen() {
  testingImage.value = true;
  imageStatus.value = "idle";
  testImageUrl.value = "";
  try {
    const data = await settingsApi.testImage();
    if (data.ok) {
      imageStatus.value = "success";
      imageReply.value = data.reply || "连接成功";
      if (data.image) {
        testImageUrl.value = data.image;
      }
    } else {
      imageStatus.value = "error";
      imageError.value = data.error || "连接失败";
    }
  } catch (e) {
    imageStatus.value = "error";
    imageError.value = String(e);
  } finally {
    testingImage.value = false;
    loadQuota();
  }
}

async function exportBackup() {
  exportingBackup.value = true;
  backupStatus.value = "";
  try {
    const res = await settingsApi.exportBackup();
    if (!res.ok) throw new Error(`导出失败：${res.status}`);
    const blob = await res.blob();
    const cd = res.headers.get("Content-Disposition") || "";
    const m = cd.match(/filename="?([^";]+)"?/);
    const filename = m?.[1] || `wesmartflow-backup-${Date.now()}.json`;
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
    backupStatusType.value = "success";
    backupStatus.value = "导出完成，备份文件已下载。";
  } catch (e) {
    backupStatusType.value = "error";
    backupStatus.value = String(e?.message || e);
  } finally {
    exportingBackup.value = false;
  }
}

async function onBackupFileChange(e) {
  const file = e.target.files?.[0];
  if (!file) return;
  importingBackup.value = true;
  backupStatus.value = "";
  try {
    const text = await file.text();
    const payload = JSON.parse(text);
    const data = await settingsApi.importBackup(payload);
    backupStatusType.value = "success";
    backupStatus.value = `导入完成：主库 ${data.stats?.main_rows || 0} 行，KG ${data.stats?.kg_rows || 0} 行，会话文件 ${data.stats?.session_message_files || 0} 个。`;
  } catch (err) {
    backupStatusType.value = "error";
    backupStatus.value = `导入失败：${err?.message || err}`;
  } finally {
    importingBackup.value = false;
    if (backupFileInput.value) backupFileInput.value.value = "";
  }
}

onMounted(() => {
  loadSettings();
  loadQuota();
});
</script>

<style scoped>
.settings-page {
}

.settings-layout {
  display: grid;
  grid-template-columns: 180px 1fr;
  gap: 16px;
}

/* Tabs */
.settings-tabs {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.st-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-radius: var(--radius-sm);
  background: transparent;
  border: none;
  color: var(--text-secondary);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: var(--transition);
  text-align: left;
}
.st-btn:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}
.st-btn.active {
  background: var(--brand-dim);
  color: var(--brand-light);
}

/* Section */
.settings-section {
  padding: 24px;
  margin-bottom: 14px;
}
.ss-title {
  font-size: 14px;
  font-weight: 700;
  color: var(--text-primary);
  margin-bottom: 6px;
}
.ss-desc {
  font-size: 12px;
  color: var(--text-muted);
  line-height: 1.6;
  margin-bottom: 18px;
}

/* Model selector */
.model-selector {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 20px;
}
.model-option {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 16px;
  border-radius: var(--radius-md);
  background: var(--bg-hover);
  border: 1.5px solid var(--border);
  cursor: pointer;
  transition: var(--transition);
}
.model-option:hover {
  border-color: var(--border-hover);
}
.model-option.active {
  border-color: var(--border-active);
  background: var(--brand-dim);
}
.mo-icon {
  font-size: 22px;
  flex-shrink: 0;
}
.mo-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 2px;
}
.mo-desc {
  font-size: 11px;
  color: var(--text-muted);
}
.mo-badge {
  margin-left: auto;
}

/* Config block */
.config-block {
  background: var(--bg-hover);
  border-radius: var(--radius-md);
  padding: 16px;
}
.cb-title {
  font-size: 12px;
  font-weight: 700;
  color: var(--text-secondary);
  margin-bottom: 12px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

/* Form */
.form-item {
  margin-bottom: 12px;
}
.form-item label {
  display: block;
  font-size: 12px;
  color: var(--text-muted);
  margin-bottom: 5px;
}
.form-input {
  width: 100%;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 7px 10px;
  color: var(--text-primary);
  font-size: 13px;
  outline: none;
  transition: var(--transition);
}
.form-input:focus {
  border-color: var(--border-active);
  box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.1);
}
.form-select {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 7px 10px;
  color: var(--text-secondary);
  font-size: 13px;
  outline: none;
  cursor: pointer;
}
.input-with-btn {
  display: flex;
  gap: 8px;
}
.input-with-btn .form-input {
  flex: 1;
}

/* 字段辅助提示 */
.field-hint {
  font-size: 11px;
  color: var(--text-muted);
  margin-top: 4px;
}
.optional {
  font-size: 11px;
  color: var(--text-dim);
  font-weight: 400;
}
.form-item-row {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 4px;
}
.form-item-row .status-hint {
  margin-top: 0;
}
.backup-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.backup-import-block {
  margin-top: 14px;
}
.hidden-file {
  display: none;
}

.status-hint {
  font-size: 12px;
  margin-top: 8px;
  padding: 5px 8px;
  border-radius: var(--radius-sm);
}
.status-hint.success {
  color: var(--green);
  background: var(--green-dim);
}
.status-hint.error {
  color: var(--red);
  background: var(--red-dim);
}
.status-hint.idle {
  color: var(--text-dim);
}

/* 测试图片预览 */
.test-image-preview {
  margin-top: 12px;
}
.test-image-preview img {
  max-width: 256px;
  max-height: 256px;
  border-radius: var(--radius-md);
  border: 1px solid var(--border);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

/* 用量概览 */
.features-status {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  padding: 12px 16px;
  margin-bottom: 16px;
}
.fs-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-dim);
}
.fs-chip {
  font-size: 12px;
  padding: 3px 10px;
  border-radius: 12px;
}
.fs-chip.ok {
  background: rgba(16, 185, 129, 0.12);
  color: #10b981;
}
.fs-chip.off {
  background: rgba(239, 68, 68, 0.1);
  color: #ef4444;
}

.wallet-badge {
  margin-left: auto;
  padding: 3px 9px;
  border-radius: 20px;
  font-size: 11px;
  color: var(--text-secondary);
  background: var(--bg-base);
}
.wallet-balance-row {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
  margin: 20px 0 16px;
  flex-wrap: wrap;
}
.wallet-number {
  font-size: 32px;
  font-weight: 650;
  letter-spacing: -1px;
  font-variant-numeric: tabular-nums;
}
.wallet-unit {
  margin-left: 10px;
  font-size: 12px;
  color: var(--text-muted);
}
.wallet-progress {
  height: 9px;
  border-radius: 20px;
  overflow: hidden;
  background: var(--border);
}
.wallet-progress-fill {
  height: 100%;
  border-radius: inherit;
  background: var(--accent, #6366f1);
  transition: width 0.3s ease;
}
.wallet-progress-fill.is-low {
  background: var(--orange, #d99b45);
}
.wallet-scale {
  display: flex;
  justify-content: space-between;
  margin-top: 7px;
  font-size: 11px;
  color: var(--text-muted);
}
.wallet-note {
  margin: 14px 0 0;
  font-size: 12px;
  line-height: 1.7;
  color: var(--text-muted);
}
.wallet-reward {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-top: 20px;
  padding: 16px;
  border: 1px solid var(--border);
  border-radius: 12px;
}
.wallet-reward-copy {
  display: flex;
  flex-direction: column;
  gap: 5px;
}
.wallet-reward-copy a {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  text-decoration: none;
}
.wallet-reward-copy a:hover {
  text-decoration: underline;
}
.wallet-reward-copy span {
  font-size: 12px;
  color: var(--text-muted);
}
.wallet-claim-button {
  flex-shrink: 0;
  padding: 8px 14px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg-base);
  color: var(--text-primary);
  font: inherit;
  font-size: 12px;
  cursor: pointer;
}
.wallet-claim-button:hover {
  border-color: var(--accent, #6366f1);
}
.wallet-claim-button:disabled {
  opacity: 0.55;
  cursor: wait;
}
.credit-card-box {
  margin-top: 18px;
  padding: 16px;
  border: 1px solid var(--border);
  border-radius: 12px;
  background: var(--bg-hover);
}
.credit-card-copy {
  display: flex;
  flex-direction: column;
  gap: 5px;
  margin-bottom: 12px;
}
.credit-card-copy strong {
  font-size: 13px;
  color: var(--text-primary);
}
.credit-card-copy span {
  font-size: 12px;
  color: var(--text-muted);
}
.credit-card-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.credit-card-input {
  flex: 1;
  min-width: 220px;
}
.wallet-claimed {
  font-size: 12px;
  color: var(--text-secondary);
  white-space: nowrap;
}
.wallet-history {
  margin-top: 18px;
  font-size: 12px;
  color: var(--text-secondary);
}
.wallet-history summary {
  cursor: pointer;
  padding: 4px 0;
}
.wallet-entry {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 0;
  border-bottom: 1px solid var(--border);
}
.wallet-entry > div {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.wallet-entry time {
  color: var(--text-muted);
  font-size: 11px;
}
.wallet-entry-amount {
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}
.wallet-entry-amount.is-gain {
  color: var(--accent, #6366f1);
}
@media (max-width: 480px) {
  .wallet-number {
    font-size: 27px;
  }
  .wallet-reward {
    align-items: flex-start;
    flex-direction: column;
    gap: 12px;
  }
}
@media (prefers-reduced-motion: reduce) {
  .wallet-progress-fill {
    transition: none;
  }
}

.quota-overview {
  padding: 18px 22px;
  margin-bottom: 16px;
}
.quota-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 14px;
  color: var(--text-secondary);
}
.quota-title {
  font-size: 13px;
  font-weight: 700;
  color: var(--text-primary);
}
.quota-hint {
  font-size: 11px;
  color: var(--text-dim);
  margin-left: auto;
}
.quota-bars {
  display: flex;
  gap: 16px;
}
.quota-item {
  flex: 1;
  min-width: 0;
}
.qi-label {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 6px;
  font-size: 12px;
}
.qi-icon {
  display: flex;
  align-items: center;
  color: var(--text-muted);
}
.qi-name {
  font-weight: 600;
  color: var(--text-secondary);
}
.qi-count {
  margin-left: auto;
  font-size: 11px;
  color: var(--text-muted);
  font-family: "Fira Code", monospace;
}
.qi-badge {
  margin-left: auto;
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 8px;
  font-weight: 600;
}
.qi-badge.unlimited {
  background: var(--green-dim);
  color: var(--green);
}
.qi-bar-track {
  height: 6px;
  background: var(--bg-hover);
  border-radius: 3px;
  overflow: hidden;
}
.qi-bar-fill {
  height: 100%;
  border-radius: 3px;
  transition: width 0.6s ease;
}
.qi-bar-fill.bar-ok {
  background: linear-gradient(90deg, #6366f1, #818cf8);
}
.qi-bar-fill.bar-warn {
  background: linear-gradient(90deg, #f59e0b, #fbbf24);
}
.qi-bar-fill.bar-danger {
  background: linear-gradient(90deg, #ef4444, #f87171);
}
.qi-bar-fill.unlimited-bar {
  background: linear-gradient(90deg, #10b981, #34d399);
  opacity: 0.5;
}

/* Data stats */
.data-stats {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 10px;
  margin-bottom: 18px;
}
.ds-item {
  background: var(--bg-hover);
  border-radius: var(--radius-md);
  padding: 12px;
  display: flex;
  align-items: center;
  gap: 10px;
}
.ds-icon {
  display: flex;
  align-items: center;
}
.ds-val {
  font-size: 16px;
  font-weight: 700;
  color: var(--text-primary);
}
.ds-label {
  font-size: 10px;
  color: var(--text-dim);
  margin-top: 1px;
}

.data-path {
  background: var(--bg-hover);
  border-radius: var(--radius-md);
  padding: 12px 14px;
}
.dp-label {
  font-size: 11px;
  color: var(--text-muted);
  margin-bottom: 6px;
}
.dp-path {
  display: flex;
  align-items: center;
  gap: 10px;
}
.dp-path code {
  flex: 1;
  font-size: 13px;
  color: var(--brand-light);
  font-family: "Fira Code", monospace;
}

/* Action list */
.action-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.action-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 14px;
  border-radius: var(--radius-sm);
  background: var(--bg-hover);
}
.ai-name {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary);
  margin-bottom: 2px;
}
.ai-desc {
  font-size: 11px;
  color: var(--text-muted);
}
.btn-danger {
  background: var(--red-dim);
  color: var(--red);
  border: 1px solid rgba(239, 68, 68, 0.2);
}
.btn-danger:hover {
  background: var(--red);
  color: white;
}

/* Prefs */
.pref-list {
  display: flex;
  flex-direction: column;
}
.pref-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 0;
  border-bottom: 1px solid var(--border);
}
.pref-item:last-child {
  border-bottom: none;
}
.pi-label {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary);
  margin-bottom: 2px;
}
.pi-desc {
  font-size: 11px;
  color: var(--text-muted);
}

/* Toggle */
.toggle {
  position: relative;
  display: inline-block;
  width: 36px;
  height: 20px;
  flex-shrink: 0;
}
.toggle input {
  opacity: 0;
  width: 0;
  height: 0;
}
.toggle-slider {
  position: absolute;
  cursor: pointer;
  inset: 0;
  background: var(--bg-active);
  border: 1px solid var(--border-hover);
  border-radius: 20px;
  transition: var(--transition);
}
.toggle-slider::before {
  content: "";
  position: absolute;
  height: 14px;
  width: 14px;
  left: 2px;
  bottom: 2px;
  background: var(--text-dim);
  border-radius: 50%;
  transition: var(--transition);
}
.toggle input:checked + .toggle-slider {
  background: var(--brand);
  border-color: var(--brand);
}
.toggle input:checked + .toggle-slider::before {
  transform: translateX(16px);
  background: white;
}

/* About */
.about-card {
  display: flex;
  flex-direction: column;
  gap: 18px;
}
.about-logo {
  display: flex;
  align-items: center;
  gap: 14px;
}
.logo-mark-lg {
  width: 52px;
  height: 52px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
}
.logo-img-lg {
  width: 100%;
  height: 100%;
  object-fit: cover;
  border-radius: 12px;
}
.about-name {
  font-size: 20px;
  font-weight: 800;
  color: var(--text-primary);
  letter-spacing: -0.4px;
}
.about-tagline {
  font-size: 12px;
  color: var(--text-muted);
  margin-top: 2px;
}
.about-desc {
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.8;
}
.about-meta {
  background: var(--bg-hover);
  border-radius: var(--radius-md);
  padding: 14px 16px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.am-item {
  display: flex;
  gap: 12px;
  font-size: 13px;
}
.am-label {
  color: var(--text-muted);
  min-width: 60px;
}
.about-links {
  display: flex;
  gap: 8px;
}
</style>
