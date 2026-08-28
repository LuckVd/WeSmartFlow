// Keep browser and adapter limits aligned. Character budgets are deliberately
// larger than a normal learner turn so pasted stories and longer dialogue
// context reach the model without silent 280-character truncation.
export const AGENT_MESSAGE_MAX_CHARS = 12_000;
export const AGENT_HISTORY_TURN_MAX_CHARS = 6_000;
export const AGENT_HISTORY_MAX_TURNS = 20;
export const AGENT_REQUEST_TIMEOUT_MS = 90_000;
