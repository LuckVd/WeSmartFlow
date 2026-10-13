/** Versioned generic asynchronous job API. */
import { api } from "./base.js";
import { consumeSSE } from "./streaming.js";

export const jobApi = {
  get: (jobId) => api.get(`/api/v1/jobs/${encodeURIComponent(jobId)}`),
  cancel: (jobId) =>
    api.post(`/api/v1/jobs/${encodeURIComponent(jobId)}/cancel`),
  stream: async (jobId, { afterSequence = 0, onEvent } = {}) => {
    const response = await api.getRaw(
      `/api/v1/jobs/${encodeURIComponent(jobId)}/events?after_sequence=${afterSequence}`,
    );
    if (!response.ok) {
      const problem = await response.json().catch(() => ({}));
      throw new Error(problem.detail || `HTTP ${response.status}`);
    }
    await consumeSSE(response, onEvent || (() => {}));
  },
  immersive: {
    get: (sessionId) =>
      api.get(`/api/v1/jobs/immersive/${encodeURIComponent(sessionId)}`),
    cancel: (sessionId) =>
      api.post(
        `/api/v1/jobs/immersive/${encodeURIComponent(sessionId)}/cancel`,
      ),
    stream: async (sessionId, { afterSequence = 0, onEvent } = {}) => {
      const response = await api.getRaw(
        `/api/v1/jobs/immersive/${encodeURIComponent(sessionId)}/events?after_sequence=${afterSequence}`,
      );
      if (!response.ok) {
        const problem = await response.json().catch(() => ({}));
        throw new Error(problem.detail || `HTTP ${response.status}`);
      }
      await consumeSSE(response, onEvent || (() => {}));
    },
  },
};
