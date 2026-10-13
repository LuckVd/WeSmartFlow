<template>
  <div class="admin-shell" :class="{ collapsed, 'menu-open': mobileOpen }">
    <button
      v-if="mobileOpen"
      class="admin-scrim"
      aria-label="关闭导航"
      @click="mobileOpen = false"
    />
    <aside class="admin-sidebar" @keydown.esc="mobileOpen = false">
      <router-link to="/admin/users" class="admin-brand"
        ><span class="admin-mark">W</span
        ><span class="nav-label"
          >WeSmartFlow<small>管理后台</small></span
        ></router-link
      >
      <div class="admin-nav-label nav-label">工作空间</div>
      <nav aria-label="后台导航">
        <router-link
          v-for="item in items"
          :key="item.path"
          :to="item.path"
          :title="item.label"
          class="admin-nav-link"
          :class="{ 'is-current': route.path.startsWith(item.path) }"
          @click="mobileOpen = false"
        >
          <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="1.6"
            aria-hidden="true"
          >
            <path :d="item.icon" /></svg
          ><span class="nav-label">{{ item.label }}</span>
        </router-link>
      </nav>
      <div class="admin-sidebar-bottom">
        <router-link to="/" title="返回主站"
          ><span>↗</span><span class="nav-label">返回主站</span></router-link
        >
        <button :title="isDark ? '切换浅色' : '切换深色'" @click="toggleTheme">
          <span>◐</span
          ><span class="nav-label">{{ isDark ? "浅色外观" : "深色外观" }}</span>
        </button>
        <button title="退出登录" @click="logout">
          <span>↪</span><span class="nav-label">退出登录</span>
        </button>
      </div>
    </aside>
    <div class="admin-workspace">
      <header class="admin-shell-header">
        <button
          class="a-button nav-desktop-toggle"
          :aria-expanded="!collapsed"
          aria-label="切换侧栏"
          @click="collapsed = !collapsed"
        >
          ☰
        </button>
        <button
          class="a-button nav-mobile-toggle"
          :aria-expanded="mobileOpen"
          aria-label="打开导航"
          @click="mobileOpen = !mobileOpen"
        >
          ☰
        </button>
        <span>工作空间 <span class="admin-divider">/</span> {{ section }}</span
        ><span class="admin-role">管理员</span>
      </header>
      <main class="admin-main"><router-view /></main>
    </div>
  </div>
</template>
<script setup>
import { computed, ref, watch, onMounted } from "vue";
import { useRoute, useRouter } from "vue-router";
import { adminApi, clearAdminToken } from "../../api/admin.js";
import { useTheme } from "../../composables/useTheme.js";
import "./admin.css";
const route = useRoute(),
  router = useRouter();
const { isDark, toggleTheme } = useTheme();
isDark.value = localStorage.getItem("wesmartflow-admin-theme") === "dark";
watch(isDark, (value) =>
  localStorage.setItem("wesmartflow-admin-theme", value ? "dark" : "light"),
);
const collapsed = ref(
    localStorage.getItem("wesmartflow-admin-collapsed") === "true",
  ),
  mobileOpen = ref(false);
watch(collapsed, (value) =>
  localStorage.setItem("wesmartflow-admin-collapsed", String(value)),
);
watch(
  () => route.fullPath,
  () => {
    mobileOpen.value = false;
  },
);
const items = [
  {
    path: "/admin/users",
    label: "用户管理",
    icon: "M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2 M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8 M22 21v-2a4 4 0 0 0-3-3.87 M16 3.13a4 4 0 0 1 0 7.75",
  },
  {
    path: "/admin/credit-cards",
    label: "积分卡",
    icon: "M3 5h18v14H3z M3 9h18 M7 15h4",
  },
  {
    path: "/admin/kg",
    label: "知识图谱",
    icon: "M12 3a3 3 0 1 0 0 6 3 3 0 0 0 0-6 M5 15a3 3 0 1 0 0 6 3 3 0 0 0 0-6 M19 15a3 3 0 1 0 0 6 3 3 0 0 0 0-6 M10 9l-4 6 M14 9l4 6 M8 18h8",
  },
];
const section = computed(
  () => items.find((i) => route.path.startsWith(i.path))?.label || "用户管理",
);
function logout() {
  clearAdminToken();
  router.replace("/admin/login");
}
onMounted(async () => {
  try {
    await adminApi.me();
  } catch {
    /* API handles expired tokens. */
  }
});
</script>
