import { AGENT_MESSAGE_MAX_CHARS } from "./agent-limits.js";
import { escapeHtml } from "./browser.js";

export function renderLessonInputDock({
  formId,
  inputId,
  statusId,
  inputName = "",
  inputValue = "",
  lastHeard = "",
  example = "",
  placeholder = "Say it your way…",
  optionalContent = "",
  agentBusy = false,
  voiceSubmitting = false,
  speechSupported = false,
  statusText = "",
}) {
  const micBusy = voiceSubmitting || agentBusy;
  const safeFormId = escapeHtml(formId);
  const safeInputId = escapeHtml(inputId);
  const safeStatusId = escapeHtml(statusId);
  const nameAttribute = inputName ? ` name="${escapeHtml(inputName)}"` : "";

  return `<div class="voice-example ${lastHeard ? "heard" : ""}"><small>${lastHeard ? "You said" : "Try saying"}</small><span>“${escapeHtml(lastHeard || example)}”</span>${optionalContent}</div>
    <form id="${safeFormId}" class="voice-composer">
      <label class="lesson-input-label" for="${safeInputId}"><strong>Your turn</strong><span>Type your English or use your voice</span></label>
      <div class="lesson-input-row">
        <div class="lesson-text-field">
          <input id="${safeInputId}"${nameAttribute} value="${escapeHtml(inputValue)}" maxlength="${AGENT_MESSAGE_MAX_CHARS}" autocomplete="off" enterkeyhint="send" placeholder="${escapeHtml(placeholder)}" aria-label="Speak or type to the world" aria-describedby="${safeStatusId}" ${agentBusy ? "disabled" : ""}>
          <span class="enter-hint" aria-hidden="true">↵ Enter</span>
        </div>
        <button type="button" class="mic-button ${micBusy ? "submitting" : speechSupported ? "" : "unsupported"}" data-action="voice" aria-label="${micBusy ? "Waiting for the Agent reply" : speechSupported ? "Start voice input; the command runs when you finish speaking" : "Voice input is unavailable"}" ${micBusy ? "disabled" : ""}><span aria-hidden="true">${micBusy ? "…" : "🎙"}</span><b>${micBusy ? "Waiting" : "Speak"}</b></button>
        <button type="submit" hidden>Send</button>
      </div>
      <small id="${safeStatusId}" class="voice-status" aria-live="polite">${escapeHtml(statusText)}</small>
    </form>`;
}
