<template>
  <div class="admin-login-page">
    <button
      class="theme-fab"
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
    <div class="login-card">
      <div class="brand">
        <div class="brand-mark">W</div>
        <div>
          <div class="brand-title">WeSmartFlow Admin</div>
          <div class="brand-sub">用户 · 积分 · 知识图谱</div>
        </div>
      </div>

      <form class="login-form" @submit.prevent="handleLogin">
        <div class="field">
          <label>账号</label>
          <input
            v-model="username"
            type="text"
            autocomplete="username"
            :disabled="loading"
            autofocus
          />
        </div>
        <div class="field">
          <label>密码</label>
          <input
            v-model="password"
            type="password"
            autocomplete="current-password"
            :disabled="loading"
            @keyup.enter="handleLogin"
          />
        </div>

        <div v-if="errorMsg" class="error-msg">{{ errorMsg }}</div>

        <button
          class="login-btn"
          type="submit"
          :disabled="loading || !canSubmit"
        >
          {{ loading ? "正在验证…" : "进入管理后台" }}
        </button>
      </form>

      <div class="hint">使用管理员账号登录工作空间。</div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from "vue";
import { useRouter } from "vue-router";
import { adminApi, setAdminToken } from "../api/admin.js";
import { useTheme } from "../composables/useTheme.js";

const router = useRouter();
const { isDark, toggleTheme } = useTheme();
isDark.value = localStorage.getItem("wesmartflow-admin-theme") === "dark";
watch(isDark, (value) =>
  localStorage.setItem("wesmartflow-admin-theme", value ? "dark" : "light"),
);

const username = ref("");
const password = ref("");
const loading = ref(false);
const errorMsg = ref("");

const canSubmit = computed(
  () => username.value.trim() && password.value.length > 0,
);

async function handleLogin() {
  if (!canSubmit.value || loading.value) return;
  loading.value = true;
  errorMsg.value = "";
  try {
    const resp = await adminApi.login(username.value.trim(), password.value);
    setAdminToken(resp.access_token);
    router.replace("/admin/users");
  } catch (e) {
    errorMsg.value = e.message || "登录失败";
  } finally {
    loading.value = false;
  }
}
</script>

<style scoped>
.admin-login-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-base);
  padding: 32px;
  position: relative;
}
.theme-fab {
  position: absolute;
  top: 18px;
  right: 22px;
  width: 32px;
  height: 32px;
  border-radius: 8px;
  background: var(--bg-panel);
  border: 1px solid var(--border);
  color: var(--text-secondary);
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  transition: all 0.12s;
}
.theme-fab:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}
.login-card {
  width: 100%;
  max-width: 380px;
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 28px 26px 22px;
  box-shadow: 0 8px 28px rgba(0, 0, 0, 0.18);
}
.brand {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 22px;
}
.brand-mark {
  width: 38px;
  height: 38px;
  border-radius: 9px;
  background: var(--gradient-brand, linear-gradient(135deg, #6366f1, #8b5cf6));
  color: white;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
}
.brand-title {
  font-size: 15px;
  font-weight: 700;
  color: var(--text-primary);
  letter-spacing: -0.2px;
}
.brand-sub {
  font-size: 11px;
  color: var(--text-dim);
  margin-top: 2px;
}

.login-form {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.field {
  display: flex;
  flex-direction: column;
  gap: 5px;
}
.field label {
  font-size: 11px;
  color: var(--text-dim);
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}
.field input {
  padding: 9px 12px;
  border-radius: 7px;
  border: 1px solid var(--border);
  background: var(--bg-base);
  color: var(--text-primary);
  font-size: 13px;
  outline: none;
  transition: border-color 0.15s;
}
.field input:focus {
  border-color: var(--brand, #6366f1);
}

.error-msg {
  background: var(--red-dim, rgba(239, 68, 68, 0.12));
  color: var(--red, #ef4444);
  padding: 8px 10px;
  border-radius: 6px;
  font-size: 12px;
}

.login-btn {
  margin-top: 6px;
  padding: 10px 14px;
  border: none;
  border-radius: 8px;
  background: var(--gradient-brand, linear-gradient(135deg, #6366f1, #8b5cf6));
  color: white;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: opacity 0.15s;
}
.login-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.hint {
  margin-top: 18px;
  font-size: 11px;
  color: var(--text-dim);
  text-align: center;
  line-height: 1.5;
}
.hint code {
  background: var(--bg-active, rgba(255, 255, 255, 0.06));
  padding: 1px 5px;
  border-radius: 4px;
}
</style>
