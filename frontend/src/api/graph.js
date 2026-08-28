import { api } from "./base.js";

export const graphApi = {
  getSimplified: () => api.get("/api/graph/simplified"),
  simplify: () => api.post("/api/graph/simplify"),
};
