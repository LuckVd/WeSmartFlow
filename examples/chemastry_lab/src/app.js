/* Chemistry Lab · free combination bench
   Shell (material library, vessel, conditions, goals, records) is local and
   instant. The Agent is the reaction referee: the space of combinations is
   explosive, so no rule table can cover it. Products can be banked back into
   the library for chain synthesis. */

import {
  LIBRARY,
  MAX_HELD,
  displayOf,
  findMaterial,
  normalizeFormula,
  normalizeName,
  strictKey,
  variantFromName,
  variantNote,
  variantOf,
  VARIANT_NOTES,
} from "./core/substances.js";
import {
  ADDITIVES,
  CATALYSTS,
  ENVIRONMENTS,
  MAX_ADDITIVES,
  PRESSURES,
  RATIOS,
  TEMP_MAX,
  TEMP_MIN,
  TEMP_PRESETS,
  clampTemp,
  conditionConflict,
  conditionList,
  conditionSentence,
  defaultConditions,
  selectivityHint,
  tempPreset,
} from "./core/conditions.js";
import { LabAgentError, askChat, askReaction, labelFor, probeEngine } from "./core/agent-client.js";
import { CHAT_MESSAGE_MAX_CHARS } from "./core/agent-limits.js";
import { clearProgress, loadProgress, loadThinking, saveProgress, saveThinking } from "./core/lab-memory.js";
import { QUESTS, QUEST_TOTAL, evaluateQuests, materialsKey, questsDone, starsFor } from "./core/quests.js";
import { escapeHtml, prefersReducedMotion } from "./core/browser.js";

const VERDICT_MARKS = {
  need: ["✔", "需要", "ok"],
  extra: ["·", "多余", "ex"],
  bad: ["!", "有问题", "bd"],
};

export function createLab({ root, platformHref = "" }) {
  const progress = loadProgress();

  const state = {
    held: [],
    conditions: defaultConditions(),
    busy: false,
    reaction: null,
    failure: null,
    engineOnline: null,
    calls: 0,
    query: "",
    selected: null,
    tried: 0,
    waited: 0,
    draft: "",
    chatBusy: false,
    chatError: "",
    unlockedNow: [],
    showGoals: true,
    showChat: true,
    // null until either the learner picks or /health reports the server default.
    thinking: loadThinking(),
  };

  let ticker = null;
  let inFlight = null;

  const query = (selector) => root.querySelector(selector);
  const queryAll = (selector) => root.querySelectorAll(selector);

  function toast(kind, message) {
    const node = document.createElement("div");
    node.className = `toast ${kind}`;
    node.setAttribute("role", "status");
    node.textContent = message;
    document.body.appendChild(node);
    setTimeout(() => node.remove(), 2_400);
  }

  /* ---------- engine health: slow is not offline ---------- */

  async function refreshEngine() {
    const health = await probeEngine();
    state.engineOnline = health.ok;
    // Adopt the server's default once, so the toggle opens in the real state.
    // A choice the learner already made outranks it. If the probe failed we still
    // have to settle on something, or the toggle stays stuck on "检测中" and
    // becomes unclickable — fall back to the same default the server ships with.
    if (state.thinking === null) {
      state.thinking = typeof health.thinking === "boolean" ? health.thinking : true;
    }
    paint();
  }

  /* ---------- bench mutations ---------- */

  function addMaterial(formula, name, variant) {
    if (state.held.length >= MAX_HELD) {
      toast("bad", `烧杯里最多放 ${MAX_HELD} 种`);
      return;
    }
    const resolved = variant || variantFromName(name);
    const duplicate = state.held.find((item) => strictKey(item.formula, item.variant) === strictKey(formula, resolved));
    if (duplicate) {
      toast("bad", `${displayOf(duplicate)} 已经在里面了`);
      return;
    }
    const sameFormula = state.held.find((item) => normalizeFormula(item.formula) === normalizeFormula(formula));
    if (sameFormula) {
      toast("bad", `注意：${displayOf(sameFormula)} 和 ${displayOf({ formula, variant: resolved })} 是同一种试剂的不同浓度`);
    }
    state.held.push({ formula, name, variant: resolved });
    resetVerdict();
    paint();
  }

  function resetVerdict() {
    state.reaction = null;
    state.failure = null;
    state.unlockedNow = [];
  }

  function bankProducts() {
    if (!state.reaction) return;
    let added = 0;
    const duplicates = [];
    for (const product of state.reaction.products) {
      const formula = product.formula || product.name;
      if (!formula) continue;
      const name = product.name || product.formula;
      const variant = product.variant || variantFromName(name);
      // Loose matching when banking: a produced acid is dilute by default, so
      // an existing 浓硫酸 entry must not spawn a second near-identical row.
      const hit = findMaterial({ formula, name, variant, loose: true, extra: progress.extra });
      if (hit) {
        if (!duplicates.includes(hit[0])) duplicates.push(hit[0]);
        continue;
      }
      progress.extra.push(variant ? [formula, name, variant] : [formula, name]);
      added += 1;
    }
    if (added) {
      saveProgress(progress);
      toast("pur", `＋ ${added} 种新物质进了材料库`);
      paint();
      return;
    }
    toast("bad", `这些库里已经有了：${duplicates.join("、")}`);
  }

  /* ---------- goals are decided locally, never by the model ---------- */

  /** Evaluate goals against the bench. `reaction` may be null: some goals (like
      talking things through) are not tied to a round having been run. */
  function applyQuests(reaction = null) {
    const unlocked = evaluateQuests({
      reaction,
      held: state.held,
      conditions: state.conditions,
      progress,
    });
    if (!unlocked.length) return;
    for (const quest of unlocked) progress.quests[quest.id] = true;
    state.unlockedNow = unlocked.map((quest) => quest.title);
    saveProgress(progress);
  }

  /* ---------- run a round ---------- */

  /* Reasoning takes real time, so silence for 30s reads as a hang. Say what the
     engine is doing instead of just counting up. In fast mode a long wait is not
     expected, so point at the toggle rather than asking for more patience. */
  function waitedText(seconds) {
    if (seconds < 3) return "";
    if (!state.thinking) {
      return seconds < 20
        ? `已等 ${seconds} 秒`
        : `已等 ${seconds} 秒，快速模式下这算慢了 —— 复杂组合可以开深度推理`;
    }
    if (seconds < 12) return `已等 ${seconds} 秒，正在数原子核对配平…`;
    if (seconds < 30) return `已等 ${seconds} 秒，这一步比较慢，别关页面`;
    return `已等 ${seconds} 秒，还在算。深度推理对复杂组合要想久一点。`;
  }

  function startTicker() {
    stopTicker();
    ticker = setInterval(() => {
      state.waited += 1;
      const node = root.querySelector("#waited");
      if (node) node.textContent = waitedText(state.waited);
    }, 1_000);
  }

  function stopTicker() {
    if (ticker) {
      clearInterval(ticker);
      ticker = null;
    }
  }

  async function run() {
    if (!state.held.length || state.busy) return;
    state.busy = true;
    resetVerdict();
    state.tried += 1;
    state.waited = 0;
    paint();
    startTicker();

    inFlight = new AbortController();
    const label = labelFor(state.held, state.conditions);
    try {
      const reaction = await askReaction({
        held: state.held,
        conditions: state.conditions,
        vessel: "烧杯",
        tried: state.tried,
        thinking: state.thinking,
      });
      state.engineOnline = true;
      state.calls += 1;
      state.reaction = reaction;
      // A verdict refused for failing the balance check is not a finding, so it
      // does not belong in the notebook — the learner just retries.
      if (!reaction.unresolved) {
        progress.discoveries.push({
          reacts: reaction.reacts,
          equation: reaction.equation,
          label,
          type: reaction.type,
          materialsKey: materialsKey(state.held),
          conditions: conditionSentence(state.conditions),
        });
        applyQuests(reaction);
        saveProgress(progress);
      }
      if (reaction.reacts) toast("ok", "✓ 反应发生了");
      else if (reaction.unresolved) toast("bad", "这一轮没算出来，再试一次");
    } catch (error) {
      const failure = error instanceof LabAgentError ? error : new LabAgentError("offline", "连不上 AI 化学引擎。");
      // Only a failed connection means offline. A slow round keeps the lamp lit.
      if (failure.kind === "offline") state.engineOnline = false;
      state.failure = {
        kind: failure.kind,
        why: failure.message,
        hint:
          failure.kind === "slow"
            ? "引擎还在，只是这一轮太慢了。直接再点一次「开始反应」。"
            : failure.kind === "http"
              ? "换个组合再试，或看一下后端日志里那一行报错。"
              : "确认 WeSmartFlow 后端在跑，然后点右上角那个状态灯重连。",
      };
      if (failure.kind === "slow") toast("bad", "⏱ 这一轮太慢，再点一次");
    } finally {
      stopTicker();
      inFlight = null;
      state.busy = false;
      paint();
    }
  }

  /* ---------- talking to the lab assistant ---------- */

  async function sendMessage(text) {
    const message = (text ?? state.draft).trim();
    if (!message || state.chatBusy) return;
    state.draft = "";
    state.chatError = "";
    state.chatBusy = true;
    // Show the learner's own line immediately; the reply streams in after.
    progress.chat.push({ role: "user", content: message });
    saveProgress(progress);
    paint();

    try {
      const answer = await askChat({
        message,
        held: state.held,
        conditions: state.conditions,
        // Exclude the turn just pushed — the server takes it as `message`.
        history: progress.chat.slice(0, -1),
        lastReaction: state.reaction,
        thinking: state.thinking,
      });
      progress.chat.push({
        role: "assistant",
        content: answer.reply,
        suggestion: answer.suggestion,
      });
      saveProgress(progress);
      // Conversation is a learning act in its own right, so it can complete a
      // goal even before any round has been run.
      applyQuests(state.reaction);
      saveProgress(progress);
    } catch (error) {
      const failure = error instanceof LabAgentError ? error : new LabAgentError("offline", "连不上助手。");
      if (failure.kind === "offline") state.engineOnline = false;
      state.chatError =
        failure.kind === "slow"
          ? "这句话等太久了，再说一次。"
          : failure.kind === "offline"
            ? "连不上助手，确认后端在跑后点右上角状态灯重连。"
            : failure.message;
    } finally {
      state.chatBusy = false;
      paint();
      focusChat();
      scrollChatToEnd();
    }
  }

  function scrollChatToEnd() {
    const log = query("#chatlog");
    if (log) log.scrollTop = log.scrollHeight;
  }

  function focusChat() {
    const field = query("#chatinput");
    if (!field) return;
    field.focus();
    // Not every engine implements selection on a textarea; the caret position is
    // a nicety, so never let it break sending a message.
    if (typeof field.setSelectionRange === "function") {
      const end = field.value.length;
      field.setSelectionRange(end, end);
    }
  }

  /* ---------- rendering ---------- */

  function visibleCategories() {
    const raw = state.query.trim();
    const wantedFormula = normalizeFormula(raw);
    const wantedName = normalizeName(raw);
    const groups = LIBRARY.concat(
      progress.extra.length ? [{ cat: "你合成出来的", items: progress.extra, isNew: true }] : [],
    );
    return groups
      .map((group) => {
        const items = group.items.filter(
          (item) =>
            !raw ||
            (wantedFormula && normalizeFormula(item[0]).includes(wantedFormula)) ||
            (wantedName && normalizeName(item[1]).includes(wantedName)),
        );
        return items.length ? { ...group, items } : null;
      })
      .filter(Boolean);
  }

  function materialHtml(group) {
    return group.items
      .map((item) => {
        const variant = variantOf(item);
        const note = VARIANT_NOTES[`${item[0]}|${variant}`] || "";
        const isSelected =
          state.selected && state.selected[0] === item[0] && (state.selected[2] || "") === variant;
        const classes = [
          "mat",
          group.isNew ? "new" : "",
          variant ? `v${variant === "浓" ? "n" : "x"}` : "",
          isSelected ? "sel" : "",
        ]
          .filter(Boolean)
          .join(" ");
        return `<button type="button" class="${classes}" draggable="true"
          data-formula="${escapeHtml(item[0])}" data-name="${escapeHtml(item[1])}" data-variant="${escapeHtml(variant)}"
          ${note ? `title="${escapeHtml(`${item[1]}：${note}`)}"` : ""}
          aria-pressed="${isSelected ? "true" : "false"}">
          <span class="f">${escapeHtml(item[0])}${variant ? `<span class="vb">${escapeHtml(variant)}</span>` : ""}</span>
          <span class="nm">${escapeHtml(item[1])}</span>
        </button>`;
      })
      .join("");
  }

  function heldHtml() {
    if (!state.held.length) {
      return `<div class="empty"><div><div class="ic" aria-hidden="true">⚗️</div>
        把左边的材料拖进来<br><span class="sm">（也可以点材料，再点烧杯）</span></div></div>`;
    }
    return state.held
      .map((item, index) => {
        const note = variantNote(item);
        return `<div class="hold">
          <button type="button" class="x" data-remove="${index}" aria-label="拿出 ${escapeHtml(displayOf(item))}">×</button>
          <div class="f">${escapeHtml(item.formula)}${item.variant ? `<span class="vb">${escapeHtml(item.variant)}</span>` : ""}</div>
          <div class="nm">${escapeHtml(item.name)}</div>
          ${note ? `<div class="vn">${escapeHtml(note)}</div>` : ""}
        </div>`;
      })
      .join("");
  }

  function chipRow(label, options, activeId, groupKey, hintFor = null) {
    const chips = options
      .map((option) => {
        const on = activeId === option.id;
        const title = hintFor?.(option);
        return `<button type="button" class="cd ${on ? "on" : ""}"
          data-axis="${groupKey}" data-value="${option.id}"
          ${title ? `title="${escapeHtml(title)}"` : ""}
          aria-pressed="${on ? "true" : "false"}">
          ${option.icon ? `<span class="i" aria-hidden="true">${option.icon}</span>` : ""}${escapeHtml(option.label)}</button>`;
      })
      .join("");
    return `<div class="cgrp"><div class="gl">${escapeHtml(label)}</div><div class="gi">${chips}</div></div>`;
  }

  function conditionsHtml() {
    const conflict = conditionConflict(state.conditions, state.held);
    const selectivity = selectivityHint(state.held);
    const preset = tempPreset(state.conditions);

    const temperature = chipRow(
      "温度",
      TEMP_PRESETS,
      state.conditions.tempPreset,
      "tempPreset",
      (option) => option.hint,
    );

    // The exact-temperature field is the whole point of this panel: reactions
    // like ethanol dehydration select their product on a 30℃ difference.
    const exact =
      preset.id === "custom"
        ? `<div class="cgrp"><div class="gl">℃</div><div class="gi tempexact">
            <input type="number" id="temp-exact" class="tempinput"
              min="${TEMP_MIN}" max="${TEMP_MAX}" step="5"
              value="${clampTemp(state.conditions.customTemp)}"
              aria-label="精确温度，摄氏度">
            <input type="range" id="temp-slider" class="tempslider"
              min="${TEMP_MIN}" max="${TEMP_MAX}" step="5"
              value="${clampTemp(state.conditions.customTemp)}"
              aria-label="拖动调整温度">
          </div></div>`
        : "";

    const additives = ADDITIVES.map((option) => {
      const on = state.conditions.add.includes(option.id);
      return `<button type="button" class="cd multi ${on ? "on" : ""}"
        data-additive="${option.id}" aria-pressed="${on ? "true" : "false"}">
        <span class="i" aria-hidden="true">${option.icon}</span>${escapeHtml(option.label)}</button>`;
    }).join("");

    return `<div class="conds">
      ${temperature}
      ${exact}
      ${chipRow("环境", ENVIRONMENTS, state.conditions.env, "env")}
      ${chipRow("催化剂", CATALYSTS, state.conditions.catalyst, "catalyst", (option) => option.formula)}
      ${chipRow("压强", PRESSURES, state.conditions.pressure, "pressure")}
      ${chipRow("配比", RATIOS, state.conditions.ratio, "ratio")}
      <div class="cgrp"><div class="gl">附加</div><div class="gi">${additives}</div></div>
      ${selectivity ? `<div class="selhint">💡 ${escapeHtml(selectivity)}</div>` : ""}
      <div class="condline ${conflict ? "warn" : ""}">
        <span class="vs">当前条件</span>&nbsp;${escapeHtml(conditionSentence(state.conditions))}
        ${conflict ? `<div class="cwarn">⚠ ${escapeHtml(conflict)}——想清楚了也可以照样试</div>` : ""}
        ${
          conditionList(state.conditions).length > 1
            ? `<button type="button" class="clr2" id="reset-conditions">重置条件</button>`
            : ""
        }
      </div>
    </div>`;
  }

  const CHAT_STARTERS = [
    "这样会发生什么？",
    "为什么不反应？",
    "该用什么条件？",
    "讲讲原理",
  ];

  function chatHtml() {
    const turns = progress.chat;
    const log = turns.length
      ? turns
          .map((turn) => {
            if (turn.role === "user") {
              return `<div class="msg me"><div class="bub2">${escapeHtml(turn.content)}</div></div>`;
            }
            return `<div class="msg ai"><div class="bub2">${escapeHtml(turn.content)}
              ${turn.suggestion ? `<span class="sug">↳ ${escapeHtml(turn.suggestion)}</span>` : ""}</div></div>`;
          })
          .join("")
      : `<div class="chatempty">放好材料、选好条件，然后问我任何问题 ——
          问什么我就答什么，不会跟你打太极。</div>`;

    // These stay visible for the whole session. Hiding them after the first
    // message left typing as the only way to ask anything, which is the slowest
    // possible path to a question the learner asks over and over.
    const starters = `<div class="starters">${CHAT_STARTERS.map(
      (text) => `<button type="button" class="starter" data-say="${escapeHtml(text)}">${escapeHtml(text)}</button>`,
    ).join("")}</div>`;

    return `<div class="box chat">
      <div class="bh"><div class="t">实验助手</div><div class="g"></div>
        <button type="button" class="fold inline" id="fold-chat" aria-expanded="${state.showChat ? "true" : "false"}">
          ${state.showChat ? "收起" : "展开"}</button></div>
      ${
        state.showChat
          ? `<div class="chatlog" id="chatlog" role="log" aria-live="polite" aria-label="与实验助手的对话">
              ${log}
              ${state.chatBusy ? `<div class="msg ai"><div class="bub2 typing"><span></span><span></span><span></span></div></div>` : ""}
            </div>
            ${starters}
            ${state.chatError ? `<div class="chaterr">${escapeHtml(state.chatError)}</div>` : ""}
            <div class="chatbar">
              <textarea id="chatinput" class="chatinput" rows="1" maxlength="${CHAT_MESSAGE_MAX_CHARS}"
                placeholder="问点什么，或说说你的猜测…"
                aria-label="给实验助手发消息">${escapeHtml(state.draft)}</textarea>
              <button type="button" id="chatsend" class="chatsend"
                ${!state.draft.trim() || state.chatBusy ? "disabled" : ""}>发送</button>
            </div>
            ${turns.length ? `<button type="button" class="fold" id="clear-chat">清空对话</button>` : ""}`
          : ""
      }
    </div>`;
  }

  function conditionCheckHtml(reaction) {
    if (!reaction.condChecks.length) return "";
    const rows = reaction.condChecks
      .map((check) => {
        const mark = VERDICT_MARKS[check.verdict] || ["?", "", ""];
        return `<div class="ck ${mark[2]}"><span class="mk" aria-hidden="true">${mark[0]}</span>
          <span class="c">${escapeHtml(check.label)}</span>
          <span class="nt">${escapeHtml(check.note || mark[1])}</span></div>`;
      })
      .join("");
    return `<div class="sec"><div class="sh">条件核对</div><div class="ckl">${rows}</div></div>`;
  }

  function resultHtml() {
    if (state.busy) {
      return `<div class="thinking" aria-live="polite">
        <span class="d"></span><span class="d"></span><span class="d"></span>
        <p>AI 正在判定这个组合…</p>
        <p id="waited" class="sm">${escapeHtml(waitedText(state.waited))}</p>
      </div>`;
    }
    if (state.failure) {
      return `<div class="verd pending">… 这一轮没判定出来</div>
        <div class="sec"><div class="sh">发生了什么</div><div class="sb">${escapeHtml(state.failure.why)}</div></div>
        <div class="hintbox"><div class="h">怎么办</div>${escapeHtml(state.failure.hint)}</div>
        <button type="button" class="addbtn" id="retry">↻ 再试一次这个组合</button>`;
    }
    const reaction = state.reaction;
    if (!reaction) {
      return `<div class="wait"><div class="ic" aria-hidden="true">🧪</div>
        放入物质、选好条件<br>点「开始反应」</div>`;
    }
    // Refused for being chemically wrong — not a chemical "no". Say so plainly
    // and offer a retry, instead of teaching that these materials do not react.
    if (reaction.unresolved) {
      // Dropped verdicts are the exact cost of fast mode, so say so here rather
      // than leaving the learner to retry the same losing round.
      const suggest = state.thinking
        ? ""
        : `<div class="misbox"><div class="h">试试这个</div>
            现在是<b>快速模式</b>，模型不做逐步推理，复杂反应容易配错。
            点右上角切到「深度推理」再试一次，通常一次就成。</div>`;
      return `<div class="verd pending">… 这一轮没算出来</div>
        <div class="sec"><div class="sh">发生了什么</div><div class="sb">${escapeHtml(reaction.why)}</div></div>
        <div class="hintbox"><div class="h">说明</div>这不代表它们不反应，只是这次给出的方程式没通过配平核对。</div>
        ${suggest}
        <button type="button" class="addbtn" id="retry">↻ 再试一次这个组合</button>`;
    }
    if (!reaction.reacts) {
      return `<div class="verd n">✕ 不发生反应${reaction.type ? `<span class="tp">${escapeHtml(reaction.type)}</span>` : ""}</div>
        <div class="sec"><div class="sh">为什么</div><div class="sb">${escapeHtml(reaction.why)}</div></div>
        ${conditionCheckHtml(reaction)}
        ${reaction.missing ? `<div class="misbox"><div class="h">还差一类条件</div>${escapeHtml(reaction.missing)}</div>` : ""}
        ${reaction.hint ? `<div class="hintbox"><div class="h">试试这个</div>${escapeHtml(reaction.hint)}</div>` : ""}
        ${reaction.danger ? `<div class="warnbox"><div class="h">安全提示</div>${escapeHtml(reaction.danger)}</div>` : ""}`;
    }
    const products = reaction.products
      .map(
        (product) => `<div class="pd"><div class="f">${escapeHtml(product.formula)}</div>
          <div class="nm">${escapeHtml(product.name)}</div>
          ${product.state ? `<div class="st">${escapeHtml(product.state)}</div>` : ""}</div>`,
      )
      .join("");
    return `<div class="verd y">✓ 发生反应${reaction.type ? `<span class="tp">${escapeHtml(reaction.type)}</span>` : ""}</div>
      ${reaction.scope === "超纲" ? `<div class="scopebox"><b>超出中学范围</b>反应是真的，方程式也是对的，只是课本上不要求你掌握。</div>` : ""}
      ${reaction.equation ? `<div class="eqbox"><div class="eq">${escapeHtml(reaction.equation)}</div></div>` : ""}
      ${conditionCheckHtml(reaction)}
      ${products ? `<div class="sec"><div class="sh">产物</div><div class="prods">${products}</div></div>` : ""}
      ${reaction.phenomenon ? `<div class="sec"><div class="sh">观察到</div><div class="sb">${escapeHtml(reaction.phenomenon)}</div></div>` : ""}
      ${reaction.why ? `<div class="sec"><div class="sh">原理</div><div class="sb">${escapeHtml(reaction.why)}</div></div>` : ""}
      ${reaction.danger ? `<div class="warnbox"><div class="h">安全提示</div>${escapeHtml(reaction.danger)}</div>` : ""}
      ${reaction.products.length ? `<button type="button" class="addbtn" id="bank">＋ 把产物加进材料库，继续合成</button>` : ""}`;
  }

  function goalsHtml() {
    const done = questsDone(progress);
    const stars = starsFor(progress);
    const rows = QUESTS.map((quest) => {
      const complete = Boolean(progress.quests[quest.id]);
      const fresh = state.unlockedNow.includes(quest.title);
      return `<div class="q ${complete ? "done" : ""} ${fresh ? "fresh" : ""}">
        <span class="qn">${complete ? "✓" : quest.label}</span>
        <span class="qt">${escapeHtml(quest.title)}<em>${escapeHtml(quest.detail)}</em></span>
      </div>`;
    }).join("");
    return `<div class="box">
      <div class="bh"><div class="t">探索目标</div><div class="g"></div>
        <div class="n">${done} / ${QUEST_TOTAL}</div></div>
      <div class="stars" aria-label="已获得 ${stars} 颗星，共 3 颗">
        ${[1, 2, 3].map((index) => `<span class="star ${index <= stars ? "on" : ""}" aria-hidden="true">★</span>`).join("")}
        <span class="starnote">${stars ? `已获得 ${stars} 颗星` : "完成 3 个目标点亮第一颗星"}</span>
      </div>
      <div class="qs ${state.showGoals ? "" : "folded"}">${rows}</div>
      <button type="button" class="fold" id="fold-goals" aria-expanded="${state.showGoals ? "true" : "false"}">
        ${state.showGoals ? "收起目标" : "展开目标"}</button>
    </div>`;
  }

  function recordsHtml() {
    if (!progress.discoveries.length) return `<div class="emptyd">还没有记录</div>`;
    return progress.discoveries
      .slice()
      .reverse()
      .map((item, index) => {
        const line = item.reacts ? item.equation || item.label : `${item.label} —— 不反应`;
        return `<div class="dr ${item.reacts ? "" : "no"}">
          <div class="n2">${progress.discoveries.length - index}</div>
          <div class="e2">${escapeHtml(line)}</div></div>`;
      })
      .join("");
  }

  /* Three states, not two. `null` means nobody has decided yet — the learner has
     no stored preference and /health has not answered — so claiming "快速模式"
     would be a guess, and the wrong one whenever the server defaults to on. */
  function thinkPillHtml() {
    if (state.thinking === null) {
      return `<div class="pill think" title="正在读取引擎的默认设置">
        <span class="d" aria-hidden="true"></span>推理 · 检测中</div>`;
    }
    const on = state.thinking;
    const title = on
      ? "深度推理：配平更可靠，但每轮更慢。点一下切换到快速模式。"
      : "快速模式：回得快，但复杂反应更容易配错被丢弃。点一下切换到深度推理。";
    return `<button type="button" class="pill think ${on ? "on" : ""}" id="think"
      aria-pressed="${on ? "true" : "false"}" title="${title}"
      ><span class="d" aria-hidden="true"></span>${on ? "深度推理" : "快速模式"}</button>`;
  }

  function paint() {
    const lampLabel =
      state.engineOnline === null
        ? "检测中…"
        : state.engineOnline
          ? `AI 化学引擎${state.calls ? ` · ${state.calls}` : ""}`
          : "引擎离线 · 点此重连";
    const categories = visibleCategories();

    root.innerHTML = `
    <div class="top">
      <div class="brand">化学<em>实验室</em></div>
      ${platformHref ? `<a class="back" href="${platformHref}">← 返回探索</a>` : ""}
      <div class="sp"></div>
      <div class="pill">已发现 <b>${progress.discoveries.filter((item) => item.reacts).length}</b> 个反应</div>
      ${thinkPillHtml()}
      <button type="button" class="pill lamp ${state.engineOnline ? "on" : ""}" id="lamp"
        title="点一下重新连接引擎"><span class="d" aria-hidden="true"></span>${escapeHtml(lampLabel)}</button>
    </div>

    <div class="grid">
      <div class="box col1">
        <div class="bh"><div class="t">材料库</div><div class="g"></div><div class="n">拖到烧杯</div></div>
        <input class="search" id="search" type="search" placeholder="搜索：铁 / Fe / 硫酸…"
          aria-label="搜索材料" value="${escapeHtml(state.query)}">
        <div class="cats">
          ${
            categories.length
              ? categories
                  .map(
                    (group) => `<div class="cat"><div class="ct">${escapeHtml(group.cat)}</div>
                      <div class="mats">${materialHtml(group)}</div></div>`,
                  )
                  .join("")
              : `<div class="emptyd">没找到「${escapeHtml(state.query)}」</div>`
          }
        </div>
      </div>

      <div class="box bench col2">
        <div class="bh"><div class="t">实验台</div><div class="g"></div>
          <div class="n">${state.held.length} 种物质</div></div>
        <div class="vessel">
          <div class="beaker ${state.reaction?.reacts ? "react" : ""}" id="beaker">
            <div class="ticks" aria-hidden="true">${"<i></i>".repeat(5)}</div>
            <div class="glow" id="glow" aria-hidden="true"></div>
            <div class="inside" id="inside">${heldHtml()}</div>
            <div class="prec" id="prec" aria-hidden="true"></div>
            <div class="flame" id="flame" aria-hidden="true">🔥</div>
          </div>
        </div>
        ${conditionsHtml()}
        <div class="run">
          <button type="button" class="gh" id="clear">清空</button>
          <button type="button" id="go" ${!state.held.length || state.busy ? "disabled" : ""}>
            ${state.busy ? "反应中…" : "开始反应"}</button>
        </div>
        ${chatHtml()}
      </div>

      <div class="col3">
        <div class="box res">
          <div class="bh"><div class="t">反应结果</div><div class="g"></div></div>
          <div id="result">${resultHtml()}</div>
        </div>
        ${goalsHtml()}
        <div class="box">
          <div class="bh"><div class="t">实验记录</div><div class="g"></div>
            <div class="n">${progress.discoveries.length}</div></div>
          <div class="disc">${recordsHtml()}</div>
          ${progress.discoveries.length ? `<button type="button" class="fold" id="reset">清空全部记录与进度</button>` : ""}
        </div>
      </div>
    </div>`;

    wire();
    // Every paint rebuilds the log, so pin it to the newest message.
    scrollChatToEnd();
    if (state.reaction) applyEffects(state.reaction);
  }

  /* ---------- bench effects ---------- */

  function applyEffects(reaction) {
    const beaker = query("#beaker");
    if (!beaker) return;
    const precipitate = query("#prec");
    const flame = query("#flame");
    const glow = query("#glow");
    beaker.querySelectorAll(".bub").forEach((bubble) => bubble.remove());
    // A verdict refused by the balance check has no phenomenon to show, so clear
    // the glassware instead of leaving the previous round's precipitate behind.
    if (reaction.unresolved || !reaction.reacts) {
      precipitate.style.height = "0";
      flame.classList.remove("on");
      glow.classList.remove("on");
      return;
    }
    const signals = `${reaction.phenomenon}${reaction.equation}`;
    const gas = reaction.products.some((product) => product.state === "气体") || /气体|气泡|放出|↑|冒/.test(signals);
    const settles = reaction.products.some((product) => product.state === "沉淀") || /沉淀|↓|浑浊|析出/.test(signals);
    const burns = /燃|火焰|发光|光|爆|剧烈/.test(signals);
    const reduced = prefersReducedMotion();

    if (gas && !reduced) {
      for (let index = 0; index < 9; index += 1) {
        const bubble = document.createElement("div");
        bubble.className = "bub";
        const size = 4 + Math.random() * 7;
        bubble.style.width = `${size}px`;
        bubble.style.height = `${size}px`;
        bubble.style.left = `${16 + Math.random() * 68}%`;
        bubble.style.animationDelay = `${Math.random() * 1.8}s`;
        bubble.style.animationDuration = `${1.3 + Math.random() * 1.1}s`;
        beaker.appendChild(bubble);
      }
    }
    precipitate.style.height = settles ? "34px" : "0";
    if (burns) {
      flame.classList.add("on");
      glow.classList.add("on");
      if (/爆/.test(signals) && !reduced) {
        beaker.classList.add("boom");
        setTimeout(() => beaker.classList.remove("boom"), 450);
      }
    } else {
      flame.classList.remove("on");
      glow.classList.remove("on");
    }
  }

  /* ---------- events ---------- */

  function wire() {
    const search = query("#search");
    search.oninput = () => {
      state.query = search.value;
      const caret = search.selectionStart;
      paint();
      const next = query("#search");
      if (next) {
        next.focus();
        if (typeof next.setSelectionRange === "function") {
          next.setSelectionRange(caret, caret);
        }
      }
    };

    const chatInput = query("#chatinput");
    if (chatInput) {
      // Track the draft without repainting, so the caret never jumps mid-word.
      chatInput.oninput = () => {
        const wasEmpty = !state.draft.trim();
        state.draft = chatInput.value;
        const isEmpty = !state.draft.trim();
        const send = query("#chatsend");
        if (send && wasEmpty !== isEmpty) send.disabled = isEmpty || state.chatBusy;
        chatInput.style.height = "auto";
        chatInput.style.height = `${Math.min(chatInput.scrollHeight, 110)}px`;
      };
      // Enter sends, Shift+Enter makes a new line.
      chatInput.onkeydown = (event) => {
        if (event.key === "Enter" && !event.shiftKey) {
          event.preventDefault();
          void sendMessage();
        }
      };
    }

    const chatSend = query("#chatsend");
    if (chatSend) chatSend.onclick = () => void sendMessage();

    queryAll("[data-say]").forEach((button) => {
      button.onclick = () => void sendMessage(button.dataset.say);
    });

    const foldChat = query("#fold-chat");
    if (foldChat) {
      foldChat.onclick = () => {
        state.showChat = !state.showChat;
        paint();
      };
    }

    const clearChat = query("#clear-chat");
    if (clearChat) {
      clearChat.onclick = () => {
        progress.chat = [];
        state.chatError = "";
        saveProgress(progress);
        paint();
      };
    }

    let dragging = null;
    queryAll(".mat").forEach((element) => {
      const pick = () => [element.dataset.formula, element.dataset.name, element.dataset.variant || ""];
      element.ondragstart = (event) => {
        dragging = pick();
        element.classList.add("drag");
        event.dataTransfer.effectAllowed = "copy";
      };
      element.ondragend = () => element.classList.remove("drag");
      element.onclick = () => {
        // Click-to-select keeps the bench usable without drag or hover.
        const picked = pick();
        const already =
          state.selected && state.selected[0] === picked[0] && (state.selected[2] || "") === picked[2];
        state.selected = already ? null : picked;
        paint();
      };
    });

    const beaker = query("#beaker");
    beaker.ondragover = (event) => {
      event.preventDefault();
      beaker.classList.add("over");
    };
    beaker.ondragleave = () => beaker.classList.remove("over");
    beaker.ondrop = (event) => {
      event.preventDefault();
      beaker.classList.remove("over");
      if (dragging) addMaterial(dragging[0], dragging[1], dragging[2]);
      dragging = null;
    };
    beaker.onclick = (event) => {
      if (event.target.closest("[data-remove]")) return;
      if (state.selected) {
        const [formula, name, variant] = state.selected;
        state.selected = null;
        addMaterial(formula, name, variant);
      }
    };

    queryAll("[data-remove]").forEach((button) => {
      button.onclick = (event) => {
        event.stopPropagation();
        state.held.splice(Number(button.dataset.remove), 1);
        resetVerdict();
        paint();
      };
    });

    queryAll("[data-axis]").forEach((chip) => {
      chip.onclick = () => {
        const axis = chip.dataset.axis;
        const value = chip.dataset.value;
        state.conditions[axis] = value;
        resetVerdict();
        paint();
        // Jump straight into the number field so picking 精确温度 is one gesture.
        if (axis === "tempPreset" && value === "custom") query("#temp-exact")?.focus();
      };
    });

    queryAll("[data-additive]").forEach((chip) => {
      chip.onclick = () => {
        const id = chip.dataset.additive;
        const index = state.conditions.add.indexOf(id);
        if (index >= 0) state.conditions.add.splice(index, 1);
        else if (state.conditions.add.length >= MAX_ADDITIVES) {
          toast("bad", `附加条件最多选 ${MAX_ADDITIVES} 个`);
          return;
        } else state.conditions.add.push(id);
        resetVerdict();
        paint();
      };
    });

    // Typing a temperature must not re-render on every keystroke, or the caret
    // jumps. Commit the value and only repaint when the field loses focus.
    const tempExact = query("#temp-exact");
    const tempSlider = query("#temp-slider");
    if (tempExact) {
      tempExact.oninput = () => {
        state.conditions.customTemp = tempExact.value;
        if (tempSlider) tempSlider.value = clampTemp(tempExact.value);
        state.reaction = null;
        state.failure = null;
      };
      tempExact.onchange = () => {
        state.conditions.customTemp = clampTemp(tempExact.value);
        resetVerdict();
        paint();
        query("#temp-exact")?.focus();
      };
    }
    if (tempSlider) {
      tempSlider.oninput = () => {
        state.conditions.customTemp = clampTemp(tempSlider.value);
        if (tempExact) tempExact.value = state.conditions.customTemp;
        state.reaction = null;
        state.failure = null;
      };
      tempSlider.onchange = () => {
        resetVerdict();
        paint();
      };
    }

    const resetConditions = query("#reset-conditions");
    if (resetConditions) {
      resetConditions.onclick = () => {
        state.conditions = defaultConditions();
        resetVerdict();
        paint();
      };
    }

    query("#clear").onclick = () => {
      state.held = [];
      state.selected = null;
      resetVerdict();
      paint();
    };
    query("#go").onclick = () => void run();

    const bank = query("#bank");
    if (bank) bank.onclick = bankProducts;

    const retry = query("#retry");
    if (retry) {
      retry.onclick = () => {
        state.tried = Math.max(0, state.tried - 1);
        void run();
      };
    }

    query("#lamp").onclick = () => {
      if (state.busy) return;
      state.engineOnline = null;
      paint();
      toast("pur", "正在重连引擎…");
      void refreshEngine();
    };

    // Switching mid-round would mislabel the verdict in flight, so wait it out.
    // Absent while the default is still unknown; see thinkPillHtml.
    const think = query("#think");
    if (think) {
      think.onclick = () => {
        if (state.busy || state.chatBusy) {
          toast("bad", "这一轮还在算，等它结束再切换");
          return;
        }
        state.thinking = !state.thinking;
        saveThinking(state.thinking);
        paint();
        toast(
          state.thinking ? "pur" : "ok",
          state.thinking ? "深度推理：慢一些，配平更可靠" : "快速模式：快一些，复杂反应可能配不平",
        );
      };
    }

    const fold = query("#fold-goals");
    if (fold) {
      fold.onclick = () => {
        state.showGoals = !state.showGoals;
        paint();
      };
    }

    const reset = query("#reset");
    if (reset) {
      reset.onclick = () => {
        if (!window.confirm("清空全部实验记录、合成出来的材料、对话和探索进度？")) return;
        clearProgress();
        progress.discoveries = [];
        progress.extra = [];
        progress.quests = {};
        progress.chat = [];
        state.chatError = "";
        resetVerdict();
        paint();
        toast("pur", "进度已清空，可以从头再做一遍");
      };
    }
  }

  return {
    render() {
      paint();
      void refreshEngine();
      window.addEventListener("beforeunload", () => {
        inFlight?.abort();
        stopTicker();
      });
    },
  };
}
