/**
 * Shared SSE decoder for current legacy streams and the v1 event envelope.
 * It intentionally preserves the top-level event fields consumed by existing
 * views while exposing `event_id`, `sequence` and `job_id` to new job-aware UI.
 */

export function parseSSEFrame(frame) {
  const lines = String(frame || "").split("\n");
  let eventId = "";
  let eventName = "";
  const dataLines = [];
  for (const line of lines) {
    if (line.startsWith("id:")) eventId = line.slice(3).trim();
    else if (line.startsWith("event:")) eventName = line.slice(6).trim();
    else if (line.startsWith("data:"))
      dataLines.push(line.slice(5).trimStart());
  }
  if (!dataLines.length) return null;
  try {
    const data = JSON.parse(dataLines.join("\n"));
    if (!data || typeof data !== "object") return null;
    if (eventId && !data.event_id) data.event_id = eventId;
    if (eventName && !data.sse_event) data.sse_event = eventName;
    return data;
  } catch {
    return null;
  }
}

export async function consumeSSE(response, onEvent) {
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const frames = buffer.split("\n\n");
    buffer = frames.pop() || "";
    for (const frame of frames) {
      const event = parseSSEFrame(frame);
      if (event) onEvent(event);
    }
  }
  if (buffer.trim()) {
    const event = parseSSEFrame(buffer);
    if (event) onEvent(event);
  }
}
