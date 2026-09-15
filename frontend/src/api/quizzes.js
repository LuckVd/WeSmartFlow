/**
 * 测验 API
 * GET  /api/quiz/effort-modes        出题模式列表（含预期耗时提示）
 * POST /api/quiz/generate/:node_id   为节点生成题目
 * POST /api/quiz/:quiz_id/submit     提交答案
 */
import { api } from "./base.js";

export const quizApi = {
  // 出题模式列表（快速/均衡/深度），由后端定义避免前后端取值漂移
  effortModes: () => api.get("/api/quiz/effort-modes"),

  // 为某节点生成一道题
  // effortMode 影响推理模型的思考强度，直接决定出题耗时
  generate: (
    nodeId,
    quizType = "multiple_choice",
    sessionId = null,
    effortMode = null,
  ) => {
    const params = new URLSearchParams({ quiz_type: quizType });
    if (sessionId) params.append("session_id", sessionId);
    if (effortMode) params.append("effort_mode", effortMode);
    return api.post(`/api/quiz/generate/${nodeId}?${params}`);
  },

  // 提交答案，返回评分 + 掌握度变化
  submit: (quizId, answer) =>
    api.post(`/api/quiz/${quizId}/submit`, { answer }),
};
