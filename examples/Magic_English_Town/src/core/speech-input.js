import { stopSpeaking } from "./browser.js";

export function createSpeechInput({
  onStart,
  onPartial,
  onSubmitStart,
  onFinal,
  onEnd,
  onError,
  autoSubmitDelay = 1200,
  maxListeningDuration = 15000,
  errorResetDelay = 600,
} = {}) {
  const Recognition = typeof window !== "undefined" && (window.SpeechRecognition || window.webkitSpeechRecognition);
  let recognition = null;
  let listening = false;
  let starting = false;
  let stopping = false;
  let suppressFinal = false;
  let sessionId = 0;
  let finalizedSessionId = 0;
  let finalTranscript = "";
  let latestTranscript = "";
  let latestAlternatives = [];
  let sessionError = "";
  let silenceTimer = null;
  let durationTimer = null;
  let errorTimer = null;
  let language = "en-US";

  const active = () => starting || listening;

  function clearTimer(timer) {
    if (timer) clearTimeout(timer);
  }

  function clearSessionTimers() {
    clearTimer(silenceTimer);
    clearTimer(durationTimer);
    clearTimer(errorTimer);
    silenceTimer = null;
    durationTimer = null;
    errorTimer = null;
  }

  function requestStop(instance, session, { cancel = false } = {}) {
    if (session !== sessionId || finalizedSessionId === session) return false;
    if (stopping) return false;
    stopping = true;
    suppressFinal ||= cancel;
    if (!cancel) onSubmitStart?.(finalTranscript.trim() || latestTranscript.trim());
    clearTimer(silenceTimer);
    silenceTimer = null;
    errorTimer = setTimeout(
      () => finalizeSession(instance, session, { submit: !cancel }),
      400,
    );
    try {
      if (cancel && typeof instance?.abort === "function") instance.abort();
      else instance?.stop();
      return true;
    } catch {
      return false;
    }
  }

  function finalizeSession(instance, session, { submit = true } = {}) {
    if (session !== sessionId || finalizedSessionId === session) return;
    finalizedSessionId = session;
    clearSessionTimers();
    starting = false;
    listening = false;
    stopping = false;
    const heard = finalTranscript.trim() || latestTranscript.trim();
    const alternatives = [heard, ...latestAlternatives]
      .filter((candidate, index, all) => candidate && all.indexOf(candidate) === index);
    const shouldSubmit = submit && !suppressFinal && !sessionError && Boolean(heard);
    if (shouldSubmit) {
      adaptLanguageToText(heard);
      onFinal?.(heard, alternatives);
    }
    onEnd?.(shouldSubmit ? heard : "");
    if (sessionError && recognition === instance) recognition = null;
    finalTranscript = "";
    latestTranscript = "";
    latestAlternatives = [];
    sessionError = "";
    suppressFinal = false;
  }

  function scheduleAutoSubmit(instance, session) {
    clearTimer(silenceTimer);
    silenceTimer = null;
    if (!Number.isFinite(autoSubmitDelay) || autoSubmitDelay < 0) return;
    silenceTimer = setTimeout(() => {
      silenceTimer = null;
      if (session !== sessionId || !listening) return;
      requestStop(instance, session);
    }, autoSubmitDelay);
  }

  function resultAlternatives(results) {
    const alternatives = [];
    const list = Array.from(results ?? []);
    const maxAlternatives = list.reduce((max, result) => Math.max(max, result.length ?? 0), 0);
    for (let rank = 0; rank < maxAlternatives; rank += 1) {
      const candidate = list
        .map((result) => result[rank]?.transcript ?? result[0]?.transcript ?? "")
        .join(" ")
        .replace(/\s+/g, " ")
        .trim();
      if (candidate && !alternatives.includes(candidate)) alternatives.push(candidate);
    }
    return alternatives;
  }

  function adaptLanguageToText(text) {
    const value = String(text ?? "").trim();
    if (!value || active()) return language;
    language = /[\u3400-\u9fff]/.test(value) ? "zh-CN" : "en-US";
    if (recognition) recognition.lang = language;
    return language;
  }

  function ensureRecognition() {
    if (!Recognition) return null;
    if (recognition) return recognition;
    const instance = new Recognition();
    instance.lang = language;
    instance.continuous = false;
    instance.interimResults = true;
    instance.maxAlternatives = 3;
    instance.onstart = () => {
      const session = instance.__magicTownSession;
      if (session !== sessionId || finalizedSessionId === session) return;
      starting = false;
      listening = true;
      if (stopping) {
        try {
          instance.abort?.();
        } catch {
          // The end fallback scheduled by requestStop will settle the session.
        }
        return;
      }
      durationTimer = setTimeout(() => requestStop(instance, session), maxListeningDuration);
      onStart?.();
    };
    instance.onresult = (event) => {
      const session = instance.__magicTownSession;
      if (session !== sessionId || finalizedSessionId === session || !listening) return;
      let interim = "";
      for (let index = event.resultIndex; index < event.results.length; index += 1) {
        const transcript = event.results[index][0]?.transcript ?? "";
        if (event.results[index].isFinal) finalTranscript += `${transcript} `;
        else interim += transcript;
      }
      const visibleText = `${finalTranscript}${interim}`.replace(/\s+/g, " ").trim();
      const transcriptChanged = visibleText !== latestTranscript;
      latestTranscript = visibleText;
      latestAlternatives = resultAlternatives(event.results);
      if (transcriptChanged) {
        onPartial?.(visibleText);
        if (visibleText) scheduleAutoSubmit(instance, session);
      }
    };
    instance.onerror = (event) => {
      const session = instance.__magicTownSession;
      if (session !== sessionId || finalizedSessionId === session) return;
      sessionError = event.error || "unknown";
      clearTimer(silenceTimer);
      clearTimer(durationTimer);
      clearTimer(errorTimer);
      const messages = {
        "not-allowed": "Microphone permission is off. You can still type and press Enter.",
        "service-not-allowed": "Voice recognition is blocked here. You can still type your words.",
        "audio-capture": "I can't find a microphone. You can still type your words.",
        "no-speech": "I didn't hear any words. Tap the microphone and try again.",
        network: "Voice recognition is unavailable right now. Try typing instead.",
      };
      if (sessionError !== "aborted") {
        onError?.(messages[sessionError] ?? "I couldn't hear that clearly. Try once more, or type it.");
      }
      errorTimer = setTimeout(() => finalizeSession(instance, session, { submit: false }), errorResetDelay);
    };
    instance.onend = () => {
      const session = instance.__magicTownSession;
      finalizeSession(instance, session, { submit: !sessionError });
    };
    recognition = instance;
    return instance;
  }

  return {
    supported: Boolean(Recognition),
    get listening() { return active(); },
    get submitting() { return stopping && !suppressFinal; },
    get language() { return language; },
    setLanguage(nextLanguage) {
      if (!["en-US", "zh-CN"].includes(nextLanguage) || active()) return false;
      language = nextLanguage;
      if (recognition) recognition.lang = language;
      return true;
    },
    adaptToText(text) {
      return adaptLanguageToText(text);
    },
    start() {
      if (active()) return false;
      const instance = ensureRecognition();
      if (!instance) return false;
      stopSpeaking();
      sessionId += 1;
      starting = true;
      stopping = false;
      suppressFinal = false;
      sessionError = "";
      finalTranscript = "";
      latestTranscript = "";
      latestAlternatives = [];
      clearSessionTimers();
      instance.__magicTownSession = sessionId;
      try {
        instance.lang = language;
        instance.start();
        return true;
      } catch {
        starting = false;
        recognition = null;
        return false;
      }
    },
    stop() {
      if (!active() || !recognition) return false;
      return requestStop(recognition, sessionId);
    },
    cancel() {
      if (!active() || !recognition) return false;
      return requestStop(recognition, sessionId, { cancel: true });
    },
  };
}
