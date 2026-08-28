<template>
  <div class="weclaw-page">
    <div class="wc-card">
      <div class="wc-header">
        <div class="wc-title">微信助手（WeClaw）</div>
        <div class="wc-subtitle">
          扫码绑定 WeClaw，绑定对话由你的 WeSmartFlow 学习助手回复。
        </div>
      </div>

      <!-- 已绑定 -->
      <div v-if="bound && !binding" class="wc-bound">
        <div class="wc-bound-badge" :class="{ off: !enabled }">
          {{ enabled ? "● 已绑定并在线" : "○ 已绑定（已停用）" }}
        </div>
        <div class="wc-bound-info">
          <div>
            bot 账号：<code>{{ accountId || "—" }}</code>
          </div>
          <div v-if="loginUserId">
            绑定微信：<code>{{ loginUserId }}</code>
          </div>
        </div>
        <div class="wc-actions">
          <button class="wc-btn ghost" @click="startBinding">重新绑定</button>
          <button class="wc-btn danger" @click="doUnbind">解绑</button>
        </div>
      </div>

      <!-- 未绑定 / 绑定中 -->
      <div v-else class="wc-bind">
        <button v-if="!binding" class="wc-btn primary" @click="startBinding">
          开始绑定
        </button>

        <div v-else class="wc-qr-wrap">
          <div v-if="qrImgSrc" class="wc-qr">
            <img :src="qrImgSrc" alt="微信扫码二维码" />
          </div>
          <div v-else class="wc-qr placeholder">二维码加载中…</div>

          <div class="wc-status" :class="statusClass">{{ statusMessage }}</div>

          <!-- 需要验证码 -->
          <div v-if="status === 'need_verifycode'" class="wc-verify">
            <input
              v-model="verifyCode"
              class="wc-input"
              placeholder="输入手机微信显示的数字"
              maxlength="12"
            />
            <button class="wc-btn primary" @click="submitVerify">提交</button>
          </div>

          <div class="wc-actions">
            <button class="wc-btn ghost" @click="cancelBinding">取消</button>
            <button
              v-if="canRefresh"
              class="wc-btn ghost"
              @click="startBinding"
            >
              刷新二维码
            </button>
          </div>
        </div>
      </div>

      <div class="wc-tip">
        提示：绑定的是你自己的 WeClaw，目前支持对话式学习功能，html / viz / quiz
        卡片 都将会转换成图片发送。
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from "vue";
import QRCode from "qrcode";
import { weclawApi } from "../api/weclaw.js";

const bound = ref(false);
const enabled = ref(false);
const accountId = ref("");
const loginUserId = ref("");

const binding = ref(false);
const status = ref("");
const statusMessage = ref("");
const qrcodeUrl = ref("");
const qrImgSrc = ref("");
const verifyCode = ref("");

let pollTimer = null;

// 服务端返回的 qrcode_url 是“待编码进二维码的字符串内容”（如微信登录 URL），
// 不是图片地址——需用 qrcode 库把它渲染成二维码图供用户扫描。
// 仅当它本身已是 data: 图片时才直接使用。
async function renderQr(content) {
  const v = (content || "").trim();
  if (!v) {
    qrImgSrc.value = "";
    return;
  }
  if (v.startsWith("data:")) {
    qrImgSrc.value = v;
    return;
  }
  try {
    qrImgSrc.value = await QRCode.toDataURL(v, { width: 220, margin: 1 });
  } catch (e) {
    console.warn("二维码渲染失败", e);
    qrImgSrc.value = "";
  }
}

const statusClass = computed(() => {
  if (["confirmed"].includes(status.value)) return "ok";
  if (["failed", "expired", "verify_code_blocked"].includes(status.value))
    return "err";
  return "";
});

const canRefresh = computed(() => ["expired", "failed"].includes(status.value));

async function loadStatus() {
  try {
    const res = await weclawApi.status();
    bound.value = !!res.bound;
    enabled.value = !!res.enabled;
    accountId.value = res.account_id || "";
    loginUserId.value = res.login_user_id || "";
  } catch (e) {
    console.warn("加载 weclaw 状态失败", e);
  }
}

function stopPoll() {
  if (pollTimer) {
    clearTimeout(pollTimer);
    pollTimer = null;
  }
}

async function startBinding() {
  stopPoll();
  binding.value = true;
  status.value = "waiting";
  statusMessage.value = "正在获取二维码…";
  qrcodeUrl.value = "";
  qrImgSrc.value = "";
  verifyCode.value = "";
  try {
    const res = await weclawApi.startLogin();
    status.value = res.status || "waiting";
    statusMessage.value = res.message || "";
    qrcodeUrl.value = res.qrcode_url || "";
    await renderQr(qrcodeUrl.value);
    schedulePoll();
  } catch (e) {
    status.value = "failed";
    statusMessage.value = e.message || "获取二维码失败";
  }
}

function schedulePoll(delay = 2500) {
  stopPoll();
  pollTimer = setTimeout(pollOnce, delay);
}

async function pollOnce() {
  if (!binding.value) return;
  try {
    const res = await weclawApi.pollLogin();
    applyPoll(res);
  } catch (e) {
    status.value = "failed";
    statusMessage.value = e.message || "轮询失败";
  }
}

function applyPoll(res) {
  status.value = res.status || "waiting";
  statusMessage.value = res.message || "";
  if (res.qrcode_url) {
    qrcodeUrl.value = res.qrcode_url;
    renderQr(qrcodeUrl.value);
  }

  if (res.status === "confirmed" || res.status === "already_connected") {
    binding.value = false;
    stopPoll();
    loadStatus();
    return;
  }
  if (["failed", "expired"].includes(res.status)) {
    stopPoll();
    return; // 让用户手动刷新
  }
  if (res.status === "need_verifycode") {
    stopPoll(); // 等用户输入
    return;
  }
  schedulePoll();
}

async function submitVerify() {
  const code = verifyCode.value.trim();
  if (!code) return;
  statusMessage.value = "正在校验…";
  try {
    const res = await weclawApi.pollLogin(code);
    applyPoll(res);
  } catch (e) {
    status.value = "failed";
    statusMessage.value = e.message || "校验失败";
  }
}

function cancelBinding() {
  binding.value = false;
  stopPoll();
  loadStatus();
}

async function doUnbind() {
  try {
    await weclawApi.unbind();
    await loadStatus();
  } catch (e) {
    console.warn("解绑失败", e);
  }
}

onMounted(loadStatus);
onUnmounted(stopPoll);
</script>

<style scoped>
.weclaw-page {
  display: flex;
  justify-content: center;
  padding: 32px 16px;
  overflow-y: auto;
}
.wc-card {
  width: 100%;
  max-width: 520px;
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: 24px;
  color: var(--text-primary);
  box-shadow: var(--shadow-md);
}
.wc-title {
  font-size: 20px;
  font-weight: 700;
}
.wc-subtitle {
  margin-top: 6px;
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.5;
}
.wc-bound,
.wc-bind {
  margin-top: 20px;
}
.wc-bound-badge {
  display: inline-block;
  padding: 4px 12px;
  border-radius: var(--radius-full);
  font-size: 13px;
  background: var(--green-dim);
  color: var(--green);
}
.wc-bound-badge.off {
  background: var(--bg-active);
  color: var(--text-muted);
}
.wc-bound-info {
  margin-top: 14px;
  font-size: 13px;
  line-height: 1.9;
  color: var(--text-secondary);
}
.wc-bound-info code,
.wc-tip code {
  background: var(--bg-active);
  color: var(--text-primary);
  padding: 1px 6px;
  border-radius: var(--radius-sm);
}
.wc-qr-wrap {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 14px;
}
.wc-qr {
  width: 220px;
  height: 220px;
  background: #fff;
  border-radius: var(--radius-md);
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
}
.wc-qr img {
  width: 100%;
  height: 100%;
  object-fit: contain;
}
.wc-qr.placeholder {
  color: #888;
  font-size: 13px;
}
.wc-status {
  font-size: 14px;
  color: var(--text-secondary);
}
.wc-status.ok {
  color: var(--green);
}
.wc-status.err {
  color: var(--red);
}
.wc-verify {
  display: flex;
  gap: 8px;
}
.wc-input {
  padding: 8px 12px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border);
  background: var(--bg-card);
  color: var(--text-primary);
  outline: none;
}
.wc-input:focus {
  border-color: var(--border-active);
}
.wc-actions {
  display: flex;
  gap: 10px;
  margin-top: 16px;
}
.wc-btn {
  padding: 8px 18px;
  border-radius: var(--radius-sm);
  border: none;
  cursor: pointer;
  font-size: 14px;
  transition: var(--transition);
}
.wc-btn.primary {
  background: var(--gradient-brand);
  color: #fff;
}
.wc-btn.ghost {
  background: var(--bg-hover);
  color: var(--text-primary);
  border: 1px solid var(--border);
}
.wc-btn.danger {
  background: var(--red-dim);
  color: var(--red);
}
.wc-btn:hover {
  opacity: 0.9;
}
.wc-tip {
  margin-top: 22px;
  font-size: 12px;
  color: var(--text-muted);
  line-height: 1.6;
}
</style>
