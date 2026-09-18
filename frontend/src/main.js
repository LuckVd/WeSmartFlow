import { createApp } from "vue";
import { createRouter, createWebHashHistory } from "vue-router";
import App from "./App.vue";
import "./style.css";

import Login from "./views/LoginView.vue";
const Landing = () => import("./views/LandingView.vue");
import GitHubCallback from "./views/GitHubCallback.vue";
import Weclaw from "./views/WeclawView.vue";
import AdminLogin from "./views/AdminLoginView.vue";
import AdminConsole from "./views/AdminConsoleView.vue";
const Dashboard = () => import("./views/DashboardView.vue");
const Graph = () => import("./views/GraphView.vue");
const Brain = () => import("./views/BrainView.vue");
const Chat = () => import("./views/ChatView.vue");
const Immersive = () => import("./views/ImmersiveView.vue");
const Quiz = () => import("./views/QuizView.vue");
const DailyBrief = () => import("./views/DailyBrief.vue");
const Documents = () => import("./views/DocumentsView.vue");
const Sessions = () => import("./views/SessionsView.vue");
const Profile = () => import("./views/ProfileView.vue");
const Settings = () => import("./views/SettingsView.vue");
const AdminKg = () => import("./views/AdminKgView.vue");
const Explore = () => import("./views/ExploreView.vue");

const routes = [
  { path: "/login", component: Login, meta: { public: true } },
  {
    path: "/auth/github/callback",
    component: GitHubCallback,
    meta: { public: true },
  },
  // Admin 审核台（独立账号体系，public 表示不走普通用户守卫）
  {
    path: "/admin/login",
    component: AdminLogin,
    meta: { public: true, admin: true },
  },
  {
    path: "/admin/console",
    component: AdminConsole,
    meta: { public: true, admin: true },
  },
  {
    path: "/admin/kg",
    component: AdminKg,
    meta: { public: true, admin: true },
  },
  { path: "/", component: Landing, meta: { public: true, standalone: true } },
  { path: "/dashboard", component: Dashboard },
  { path: "/graph", component: Brain },
  { path: "/graph-classic", component: Graph },
  // /knowledge 重定向到 /graph（列表视图），保持旧链接可用，保留 query 参数
  {
    path: "/knowledge",
    redirect: (to) => ({ path: "/graph", query: to.query }),
  },
  { path: "/chat", component: Chat },
  { path: "/explore", component: Explore },
  { path: "/immersive", component: Immersive },
  { path: "/quiz", component: Quiz },
  { path: "/sessions", component: Sessions },
  { path: "/brief", component: DailyBrief },
  { path: "/documents", component: Documents },
  { path: "/profile", component: Profile },
  { path: "/settings", component: Settings },
  { path: "/weclaw", component: Weclaw },
];

const router = createRouter({
  history: createWebHashHistory(),
  routes,
});

// GitHub OAuth 回调处理：
// GitHub 回调 URL 格式为 http://localhost:5173/?code=xxx
// 由于使用 hash 模式，需要在应用启动时检测 URL query 中的 code 参数
// 并重定向到 hash 路由 /#/auth/github/callback?code=xxx
(function handleGitHubOAuthRedirect() {
  const urlParams = new URLSearchParams(window.location.search);
  const code = urlParams.get("code");
  if (code && !window.location.hash.includes("/auth/github/callback")) {
    // 清除 URL 中的 query 参数，跳转到 hash 路由
    window.location.replace(
      `${window.location.pathname}#/auth/github/callback?code=${encodeURIComponent(code)}&state=${encodeURIComponent(urlParams.get("state") || "")}`,
    );
  }
})();

// 路由守卫：未登录跳转到登录页
router.beforeEach((to) => {
  // ── Admin 路由独立守卫（不依赖 wesmartflow-token）──
  if (to.meta.admin) {
    const adminToken = localStorage.getItem("wesmartflow-admin-token");
    if (to.path === "/admin/login") {
      if (adminToken) return "/admin/console";
      return; // 未登录可访问登录页
    }
    // 其它 admin 子页必须有 admin token
    if (!adminToken) return "/admin/login";
    return;
  }

  // ── 普通用户路由守卫 ──
  const token = localStorage.getItem("wesmartflow-token");
  if (!to.meta.public && !token) {
    return "/login";
  }
  // 已登录时访问登录页，跳转到首页
  if (to.path === "/login" && token) {
    return "/chat";
  }
});

createApp(App).use(router).mount("#app");
