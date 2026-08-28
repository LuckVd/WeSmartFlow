const FEMALE_ENGLISH_VOICES = [
  "Samantha",
  "Ava",
  "Serena",
  "Karen",
  "Moira",
  "Tessa",
  "Victoria",
  "Allison",
  "Susan",
  "Zira",
  "Aria",
  "Jenny",
  "Sonia",
];

let speechRunId = 0;
let speechTimer = null;

export function selectSpeechVoice(voices = [], preference = "default") {
  const englishVoices = voices.filter((voice) => /^en(?:-|_)/i.test(voice.lang || ""));
  if (preference !== "female") return englishVoices[0] ?? voices[0] ?? null;
  return FEMALE_ENGLISH_VOICES
    .map((name) => englishVoices.find((voice) => voice.name.toLowerCase().includes(name.toLowerCase())))
    .find(Boolean) ?? englishVoices.find((voice) => /female|woman|girl/i.test(voice.name)) ?? englishVoices[0] ?? voices[0] ?? null;
}

function splitLongPart(part, maxLength) {
  const chunks = [];
  let remaining = part.trim();
  while (remaining.length > maxLength) {
    let splitAt = remaining.lastIndexOf(" ", maxLength);
    if (splitAt < Math.floor(maxLength * 0.55)) splitAt = maxLength;
    chunks.push(remaining.slice(0, splitAt).trim());
    remaining = remaining.slice(splitAt).trim();
  }
  if (remaining) chunks.push(remaining);
  return chunks;
}

export function chunkSpeechText(text, maxLength = 180) {
  const normalized = String(text ?? "").replace(/\s+/g, " ").trim();
  if (!normalized) return [];
  const sentences = normalized.match(/[^.!?。！？]+[.!?。！？]?/g) ?? [normalized];
  const chunks = [];
  let current = "";
  for (const sentence of sentences) {
    const part = sentence.trim();
    if (!part) continue;
    if (`${current} ${part}`.trim().length <= maxLength) {
      current = `${current} ${part}`.trim();
      continue;
    }
    if (current) chunks.push(current);
    const longParts = splitLongPart(part, maxLength);
    current = longParts.pop() ?? "";
    chunks.push(...longParts);
  }
  if (current) chunks.push(current);
  return chunks;
}

function clearSpeechTimer() {
  if (speechTimer) clearTimeout(speechTimer);
  speechTimer = null;
}

export function stopSpeaking() {
  speechRunId += 1;
  clearSpeechTimer();
  if (typeof window !== "undefined") window.speechSynthesis?.cancel?.();
}

export function speak(text, { voice = "default", rate = 0.86, pitch = 1.08 } = {}) {
  if (typeof window === "undefined") return false;
  const synthesis = window.speechSynthesis;
  const Utterance = window.SpeechSynthesisUtterance || globalThis.SpeechSynthesisUtterance;
  const chunks = chunkSpeechText(text);
  if (!synthesis || !Utterance || !chunks.length) return false;

  const runId = ++speechRunId;
  clearSpeechTimer();
  synthesis.cancel();
  let index = 0;

  const playNext = () => {
    if (runId !== speechRunId) return;
    clearSpeechTimer();
    if (index >= chunks.length) return;
    const chunk = chunks[index];
    index += 1;
    const utterance = new Utterance(chunk);
    utterance.lang = "en-US";
    utterance.rate = Math.max(0.5, Math.min(1.5, Number(rate) || 0.86));
    utterance.pitch = Math.max(0.5, Math.min(1.5, voice === "female" ? Math.max(pitch, 1.08) : pitch));
    const selectedVoice = selectSpeechVoice(synthesis.getVoices?.() ?? [], voice);
    if (selectedVoice) utterance.voice = selectedVoice;

    let advanced = false;
    const advance = () => {
      if (advanced || runId !== speechRunId) return;
      advanced = true;
      clearSpeechTimer();
      speechTimer = setTimeout(playNext, 20);
    };
    utterance.onend = advance;
    utterance.onerror = advance;

    const startedAt = Date.now();
    const hardTimeout = Math.max(12000, chunk.length * 260);
    const watchdog = () => {
      if (advanced || runId !== speechRunId) return;
      if (synthesis.paused) synthesis.resume?.();
      if (Date.now() - startedAt >= hardTimeout) {
        synthesis.cancel();
        advance();
        return;
      }
      speechTimer = setTimeout(watchdog, 4000);
    };

    speechTimer = setTimeout(() => {
      if (runId !== speechRunId) return;
      synthesis.resume?.();
      synthesis.speak(utterance);
      speechTimer = setTimeout(watchdog, 4000);
    }, 0);
  };

  playNext();
  return true;
}

export function escapeHtml(value) {
  return value.replace(
    /[&<>'"]/g,
    (character) =>
      ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        "'": "&#39;",
        '"': "&quot;",
      })[character],
  );
}
