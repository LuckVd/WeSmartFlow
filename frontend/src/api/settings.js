/**
 * 设置 API
 * GET  /api/settings            获取当前设置
 * POST /api/settings            保存设置
 * POST /api/settings/test       测试 LLM 连接
 * POST /api/settings/test-tavily  测试 Tavily 连接
 * POST /api/settings/test-image   测试图像生成连接
 */
import { api } from "./base.js";

export const settingsApi = {
  // 获取当前设置
  get: () => api.get("/api/settings"),

  // 保存设置
  save: (data) => api.post("/api/settings", data),

  // 查询当期 credits 额度用量
  getQuota: () => api.get("/api/usage/credits/quota"),

  // 功能可用性（issue #62/#103：llm/search/image 是否已配置）
  getFeatures: () => api.get("/api/settings/features"),

  // 测试 LLM 连接
  testLLM: () => api.post("/api/settings/test"),

  // 测试 Tavily 连接
  testTavily: () => api.post("/api/settings/test-tavily"),

  // 测试图像生成连接
  testImage: () => api.post("/api/settings/test-image"),

  // 导出记忆与知识库备份（返回原始 Response，前端负责下载文件）
  exportBackup: () => api.getRaw("/api/backup/export"),

  // 导入记忆与知识库备份 JSON
  importBackup: (data) => api.post("/api/backup/import", data),
};
