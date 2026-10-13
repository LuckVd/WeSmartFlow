/**
 * 认证 API — 邮箱验证码登录 + GitHub OAuth 登录
 */

import { BASE_URL, createRequestId } from "./base.js";

export const authApi = {
  // ── 邮箱验证码登录 ──

  /**
   * 发送邮箱验证码
   * @param {string} email - 邮箱地址
   * @returns {Promise<{message: string, cooldown: number}>}
   */
  async sendCode(email) {
    const res = await fetch(`${BASE_URL}/api/auth/send-code`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Request-ID": createRequestId(),
      },
      body: JSON.stringify({ email }),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || "发送验证码失败");
    }

    return res.json();
  },

  /**
   * 邮箱验证码登录/注册
   * @param {string} email - 邮箱地址
   * @param {string} code - 验证码
   * @param {string} name - 用户昵称（可选，新用户注册时使用）
   * @returns {Promise<{access_token: string, token_type: string, user_id: string, user_name: string}>}
   */
  async verifyCode(email, code, name = "") {
    const res = await fetch(`${BASE_URL}/api/auth/verify-code`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Request-ID": createRequestId(),
      },
      body: JSON.stringify({ email, code, name }),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || "验证失败");
    }

    return res.json();
  },

  // ── GitHub OAuth 登录 ──

  /**
   * 获取 GitHub 授权 URL
   * @returns {Promise<{authorize_url: string}>}
   */
  async getGitHubAuthorizeUrl(reward = false) {
    const path = reward ? "github/reward/authorize" : "github/authorize";
    const token = localStorage.getItem("wesmartflow-token");
    const res = await fetch(`${BASE_URL}/api/auth/${path}`, {
      headers: {
        ...(reward && token ? { Authorization: `Bearer ${token}` } : {}),
        "X-Request-ID": createRequestId(),
      },
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || "获取 GitHub 授权地址失败");
    }

    const data = await res.json();
    sessionStorage.setItem("github-oauth-state", data.state);
    sessionStorage.setItem("github-oauth-purpose", reward ? "reward" : "login");
    return data;
  },

  /**
   * GitHub OAuth 回调登录
   * @param {string} code - GitHub 回调的 code
   * @returns {Promise<{access_token: string, token_type: string, user_id: string, user_name: string}>}
   */
  async githubCallback(code, state) {
    if (!state || state !== sessionStorage.getItem("github-oauth-state")) {
      throw new Error("GitHub 授权校验失败，请重新发起登录或奖励验证");
    }
    sessionStorage.removeItem("github-oauth-state");
    const res = await fetch(`${BASE_URL}/api/auth/github/callback`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Request-ID": createRequestId(),
      },
      body: JSON.stringify({ code, state }),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || "GitHub 登录失败");
    }

    return res.json();
  },
};
