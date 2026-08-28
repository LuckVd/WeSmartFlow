/**
 * Admin 审核台 API（独立于普通用户登录）
 *
 * - token 存于 localStorage["wesmartflow-admin-token"]，跟普通 token 互不影响
 * - 401 时不跳普通登录页，而是跳 /#/admin/login
 */

const BASE_URL = import.meta.env.VITE_API_BASE || "";
const ADMIN_TOKEN_KEY = "wesmartflow-admin-token";

export function getAdminToken() {
  return localStorage.getItem(ADMIN_TOKEN_KEY) || "";
}

export function setAdminToken(token) {
  if (token) {
    localStorage.setItem(ADMIN_TOKEN_KEY, token);
  } else {
    localStorage.removeItem(ADMIN_TOKEN_KEY);
  }
}

export function clearAdminToken() {
  localStorage.removeItem(ADMIN_TOKEN_KEY);
}

function handleAdminUnauthorized() {
  clearAdminToken();
  window.location.href = window.location.pathname + "#/admin/login";
}

async function adminRequest(method, path, body = null) {
  const headers = { "Content-Type": "application/json" };
  const token = getAdminToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(`${BASE_URL}${path}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : null,
  });

  if (res.status === 401) {
    handleAdminUnauthorized();
    throw new Error("未登录或已过期");
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || err.message || res.statusText);
  }
  if (res.status === 204) return null;
  return res.json();
}

export const adminApi = {
  login: (username, password) =>
    adminRequest("POST", "/api/admin/login", { username, password }),

  me: () => adminRequest("GET", "/api/admin/me"),

  stats: () => adminRequest("GET", "/api/admin/proposals/stats"),

  list: ({ status = "pending", op = "", limit = 100, offset = 0 } = {}) => {
    const q = new URLSearchParams({
      status,
      limit: String(limit),
      offset: String(offset),
    });
    if (op) q.set("op", op);
    return adminRequest("GET", `/api/admin/proposals?${q.toString()}`);
  },

  detail: (id) =>
    adminRequest(
      "GET",
      `/api/admin/proposals/${encodeURIComponent(id)}/detail`,
    ),

  approve: (id, note = "") =>
    adminRequest(
      "POST",
      `/api/admin/proposals/${encodeURIComponent(id)}/approve`,
      { note },
    ),

  reject: (id, note = "") =>
    adminRequest(
      "POST",
      `/api/admin/proposals/${encodeURIComponent(id)}/reject`,
      { note },
    ),

  retryApply: (id) =>
    adminRequest(
      "POST",
      `/api/admin/proposals/${encodeURIComponent(id)}/retry_apply`,
    ),

  retryKgSync: (id) =>
    adminRequest(
      "POST",
      `/api/admin/proposals/${encodeURIComponent(id)}/retry_kg_sync`,
    ),

  // ── KG 图谱可视化 ──
  kgGraph: ({ subject = "", includePending = false } = {}) => {
    const q = new URLSearchParams();
    if (subject) q.set("subject", subject);
    if (includePending) q.set("include_pending", "true");
    const qs = q.toString();
    return adminRequest("GET", `/api/admin/kg/graph${qs ? "?" + qs : ""}`);
  },

  kgConceptDetail: (id) => {
    // concept_id 形如 "math/limit"，后端用 {concept_id:path} 转换器，
    // 必须保留 "/" 作为路径分隔符；其他字符仍需 URL 编码（中文/空格/百分号等）。
    const safeId = String(id)
      .split("/")
      .map((seg) => encodeURIComponent(seg))
      .join("/");
    return adminRequest("GET", `/api/admin/kg/concept/${safeId}/detail`);
  },
};
