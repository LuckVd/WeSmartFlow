import { api } from "./base.js";

/** weclaw 微信通道：扫码绑定 / 状态 / 解绑 */
export const weclawApi = {
  status: () => api.get("/api/weclaw/status"),
  startLogin: () => api.post("/api/weclaw/login/start", {}),
  pollLogin: (verifyCode) =>
    api.post("/api/weclaw/login/poll", { verify_code: verifyCode || null }),
  unbind: () => api.post("/api/weclaw/unbind", {}),
};
