/* Front-end request limits. The server clamps everything again; these values
   only keep the browser from sending payloads it knows will be rejected. */

/* Must stay above the server's worst case, or the browser gives up on a round
   the backend is still paying for. The server allows `CHEM_LAB_LLM_TIMEOUT`
   (60s by default) per attempt and retries once, so ~120s plus overhead. With
   reasoning enabled a single attempt genuinely takes longer, and abandoning it
   early is the one outcome with no upside: the learner waits and gets nothing. */
export const AGENT_REQUEST_TIMEOUT_MS = 150_000;
export const HEALTH_TIMEOUT_MS = 8_000;
export const HEALTH_RETRIES = 3;
export const CHAT_MESSAGE_MAX_CHARS = 500;
export const CHAT_TURN_MAX_CHARS = 800;
export const CHAT_HISTORY_MAX_TURNS = 12;
