/* ============================================================================
 * BingeMate · 追剧搭子 —— 交互逻辑
 *
 * 设计原则：这是一个「播放器 + 一个安静的搭子」，不是一节课。
 *   · Round 1 全程不打断，AI 保持沉默
 *   · Round 2 AI 才开始举手，而且举手可以被无视
 *   · 四个阶段可以随时自由跳转，不强制顺序
 *   · 所有内容预置在 data.js，零网络请求
 * ==========================================================================*/

(function () {
  'use strict';

  const D = window.BINGEMATE_DATA;
  const $ = (id) => document.getElementById(id);

  const RATES = [0.5, 0.75, 1, 1.25];

  const ROUNDS = [
    { n: 1, name: '裸听', sub: '先当剧看完' },
    { n: 2, name: '跟读', sub: '字幕 + 举手' },
    { n: 3, name: '精讲', sub: '金句回放' },
    { n: 4, name: '验收', sub: '做题 + 收获' },
  ];

  /* ------------------------------------------------------------------ 状态 */
  const S = {
    clip: null,
    round: 1,
    fired: new Set(),      // 已触发过举手的学习点
    skipped: [],           // 被无视的举手点 → 稍后再看
    opened: new Set(),     // 已看过的学习点
    blind: {},             // Round 1 作答
    final: {},             // Round 4 作答
    loop: null,            // { start, end } 循环区间
    once: null,            // { end } 单次播到此处即停
    curPoint: null,
    queue: [],             // 讲解卡翻页队列
    tab: 'usage',
    raiseTimer: null,
    pending: null,
    curLineId: null,
    rateIdx: 2,
    forceZh: false,
    r1done: false,
    harvested: false,
    saidSkipTip: false,
    optOrder: {},          // 每题选项的显示顺序（打乱后缓存，保证重渲染时不变）
  };

  /* localStorage 命名空间（WeSmartFlow examples 规范）：<demo-id>:<key>:<version>
     同域下 localStorage 不按路径隔离，必须带命名空间和版本，禁止使用 progress 这类通用键。 */
  const LS_NS = 'bingemate';
  const LS_VER = 'v1';
  const LS_LEGACY_PREFIX = 'bingemate_';

  const LS = {
    key(k) { return LS_NS + ':' + k + ':' + LS_VER; },
    get(k, d) {
      try {
        const cur = localStorage.getItem(LS.key(k));
        if (cur !== null) return JSON.parse(cur) ?? d;
        // 迁移：早期无版本号的键（bingemate_<k>），读到就顺手写成新格式
        const legacy = localStorage.getItem(LS_LEGACY_PREFIX + k);
        if (legacy !== null) {
          localStorage.setItem(LS.key(k), legacy);
          return JSON.parse(legacy) ?? d;
        }
        return d;
      } catch (e) { return d; }
    },
    set(k, v) { try { localStorage.setItem(LS.key(k), JSON.stringify(v)); } catch (e) {} },
  };

  /* --------------------------------------------------------------- 小工具 */
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"]/g, (c) =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

  const fmt = (s) => {
    if (!isFinite(s)) return '0:00';
    const m = Math.floor(s / 60), x = Math.floor(s % 60);
    return m + ':' + String(x).padStart(2, '0');
  };

  const norm = (w) => w.toLowerCase().replace(/[^a-z']/g, '');
  const v = () => $('video');
  const pointById = (id) => S.clip.points.find((p) => p.id === id);
  const lineById = (id) => S.clip.lines.find((l) => l.id === id);

  /** 有效时长：片源后面可能还接着别的戏，用 clipEnd 把播放范围掐掉 */
  const clipDur = () => {
    if (!S.clip) return 0;
    if (S.clip.clipEnd) return S.clip.clipEnd;
    const d = v().duration;
    return isFinite(d) && d ? d : S.clip.duration;
  };

  function toast(msg, icon) {
    const el = document.createElement('div');
    el.className = 'toast';
    el.innerHTML = (icon ? '<span>' + icon + '</span>' : '') + '<span>' + msg + '</span>';
    $('toastWrap').appendChild(el);
    setTimeout(() => { el.classList.add('out'); setTimeout(() => el.remove(), 260); }, 2300);
  }

  /* ==========================================================================
   * 首页
   * ========================================================================*/
  function renderHome() {
    const live = D.clips.filter((c) => c.available).length;
    $('homeCount').textContent = live + ' 段可学 · ' + (D.clips.length - live) + ' 段占位演示';

    $('clipGrid').innerHTML = D.clips.map((c) => {
      const thumb = c.cover
        ? '<img src="' + c.cover + '" alt="" />'
        : '<div class="ph">' + (c.isImport ? '＋' : '🎬') + '</div>';

      return '' +
        '<div class="clip-card ' + (c.available ? '' : 'locked') + '" data-id="' + c.id + '">' +
          '<div class="clip-thumb">' + thumb +
            (c.duration ? '<div class="clip-dur">' + fmt(c.duration) + '</div>' : '') +
            '<div class="clip-badge ' + (c.available ? 'live' : '') + '">' +
              (c.available ? '可以开始' : c.isImport ? '演示占位' : '即将开放') +
            '</div>' +
            (c.available ? '<div class="clip-play">▶</div>' : '') +
          '</div>' +
          '<div class="clip-body">' +
            '<div class="clip-show">' + esc(c.show) + (c.episode ? ' · ' + esc(c.episode) : '') + '</div>' +
            '<div class="clip-title">' + esc(c.title) + '</div>' +
            '<div class="clip-meta">' +
              '<span>' + esc(c.showZh) + '</span><i>·</i>' +
              '<span>' + esc(c.genre) + '</span><i>·</i>' +
              '<span>' + esc(c.level) + '</span>' +
            '</div>' +
            (c.available
              ? '<div class="clip-focus">🎯 <span>' + esc(c.focus) + '</span></div>'
              : '<div class="clip-soon">' + esc(c.soonNote || '') + '</div>') +
          '</div>' +
        '</div>';
    }).join('');

    $('clipGrid').querySelectorAll('.clip-card').forEach((el) => {
      el.addEventListener('click', () => {
        const c = D.clips.find((x) => x.id === el.dataset.id);
        if (c.available) openClip(c);
        else toast(c.isImport ? 'Demo 只开放了老友记这一段 😌' : '这段还没备课，先看老友记吧 😌', '🔒');
      });
    });

    renderStreak();
  }

  function renderStreak() {
    const st = LS.get('stats', { clips: [], days: 0, last: '' });
    $('stClips').textContent = st.clips.length;
    $('stWords').textContent = LS.get('vault', []).length;
    $('stDays').textContent = st.days || 1;
  }

  function bumpStreak(clipId) {
    const st = LS.get('stats', { clips: [], days: 0, last: '' });
    const today = new Date().toISOString().slice(0, 10);
    if (!st.last) { st.days = 1; st.last = today; }
    else if (st.last !== today) { st.days = (st.days || 1) + 1; st.last = today; }
    if (clipId && !st.clips.includes(clipId)) st.clips.push(clipId);
    LS.set('stats', st);
    renderStreak();
  }

  /* ==========================================================================
   * 进出学习页
   * ========================================================================*/
  function openClip(clip) {
    S.clip = clip;
    S.fired.clear(); S.opened.clear();
    S.skipped = []; S.blind = {}; S.final = {};
    S.loop = null; S.once = null;
    S.r1done = false; S.harvested = false; S.saidSkipTip = false;
    S.r2done = false;
    S.rateIdx = 2; S.forceZh = false;
    S.optOrder = {};

    $('chipZh').classList.remove('on');
    $('subZh').classList.remove('forced');

    $('pageHome').classList.add('hidden');
    $('pageStudy').classList.remove('hidden');
    window.scrollTo(0, 0);

    const el = v();
    el.src = clip.video;
    el.playbackRate = 1;
    el.load();

    applyMask(clip);

    renderVault();
    gotoRound(1);
    bumpStreak(null);
  }

  /** 硬字幕遮罩：每个片段两个独立参数（都按视频高度的百分比算）
   *    hardsubMask —— 遮罩总高度，含上沿那段渐变
   *    maskOpaque  —— 其中"完全不透明"的高度，必须盖过实测的字幕上沿
   *  只给 hardsubMask 时按 88% 折算不透明段（够保守，不会漏字）。
   *  顶部台标同理：topMask / topMaskOpaque。 */
  function applyMask(clip) {
    const solid = clip.maskStyle === 'solid';
    const set = (id, h, opaque) => {
      const box = $(id);
      box.style.height = h + '%';
      // 渐变里的位置是相对遮罩自身高度的，所以要把"占画面的百分比"换算过去
      box.style.setProperty('--solid-stop', h ? (Math.min(opaque, h) / h * 100).toFixed(1) + '%' : '100%');
      box.classList.toggle('solid', solid);
    };
    const bh = clip.hardsubMask || 22;
    set('hardsubMask', bh, clip.maskOpaque != null ? clip.maskOpaque : bh * 0.88);
    const th = clip.topMask || 0;
    set('hardsubMaskTop', th, clip.topMaskOpaque != null ? clip.topMaskOpaque : th * 0.88);
  }

  function goHome() {
    const el = v();
    el.pause();
    el.removeAttribute('src');
    el.load();
    clearRaise();
    closeSheet();
    $('pageStudy').classList.add('hidden');
    $('pageHome').classList.remove('hidden');
    renderHome();
    window.scrollTo(0, 0);
  }

  /* ==========================================================================
   * 四轮
   * ========================================================================*/
  function renderStepper() {
    // 四个阶段全部可点，不强制按顺序
    $('stepper').innerHTML = ROUNDS.map((r, i) => {
      const done = S.round !== r.n && isRoundDone(r.n);
      const cls = r.n === S.round ? 'active' : (done ? 'done' : 'free');
      return (i ? '<span class="step-arrow">›</span>' : '') +
        '<div class="step ' + cls + '" data-r="' + r.n + '" title="点击直接进入">' +
          '<span class="step-n">' + (done ? '✓' : r.n) + '</span>' +
          '<span>' + r.name + '<span class="step-sub"> · ' + r.sub + '</span></span>' +
        '</div>';
    }).join('');

    $('stepper').querySelectorAll('.step').forEach((el) => {
      el.addEventListener('click', () => gotoRound(+el.dataset.r));
    });
  }

  function isRoundDone(n) {
    if (n === 1) return Object.keys(S.blind).length >= S.clip.blindQuiz.length;
    if (n === 2) return S.fired.size >= S.clip.moments.length;
    if (n === 3) return S.opened.size >= 3;
    if (n === 4) return Object.keys(S.final).length >= S.clip.finalQuiz.length;
    return false;
  }

  function gotoRound(n) {
    if (S.round === n && S.clip && $('roundZone').innerHTML) return;
    S.round = n;
    S.loop = null; S.once = null;
    $('barLoop').classList.add('hidden');
    clearRaise();

    const el = v();
    el.pause();
    if (n !== 3) el.currentTime = 0;
    setPlayIcon(false);

    const blind = n === 1;
    $('subLayer').classList.toggle('hidden', blind);
    $('blindBadge').classList.toggle('hidden', !blind);
    $('chipNoHear').style.display = blind ? 'none' : '';
    $('chipZh').style.display = blind ? 'none' : '';
    $('playerCard').style.display = n === 4 ? 'none' : '';

    const jump = $('chipJump');
    if (n === 1) { jump.style.display = ''; jump.textContent = '⏭ 直接跳到问答'; }
    else if (n === 2) { jump.style.display = ''; jump.textContent = '⏭ 下一个举手点'; }
    else { jump.style.display = 'none'; }

    renderStepper();
    renderMarks();
    renderHint();
    renderMateForRound();
    renderRound();
  }

  function renderHint() {
    const map = {
      1: '<b>第 1 轮 · 裸听。</b>' + esc(S.clip.synopsis) +
         '<br />不给字幕，也不会有人打断你 —— 就当在追剧。看完我问你几个很轻的问题，答不上来完全没关系。',
      2: '<b>第 2 轮 · 跟读。</b>字幕出来了。播到有意思的地方我会在右下角举手 ✋ —— 想听就点，不想听<b>直接无视</b>，它会自己走开，我记在右下角「稍后再看」里。',
      3: '<b>第 3 轮 · 精讲。</b>下面每条都能<b>单独回放</b>，点开会自动把这句放一遍，边听边看讲解。想再听按「重听一次」。',
      4: '<b>第 4 轮 · 验收。</b>四道能直接拿去用的场景题。',
    };
    $('hintBar').innerHTML = map[S.round];
  }

  function renderRound() {
    const z = $('roundZone');
    if (S.round === 1) { if (S.r1done) renderBlindQuiz(); else z.innerHTML = ''; return; }
    if (S.round === 2) { z.innerHTML = ''; return; }
    if (S.round === 3) { renderDecode(); return; }
    if (S.round === 4) { renderCheck(); return; }
  }

  /* ==========================================================================
   * 伴学栏
   * ========================================================================*/
  function mateSay(html, me) {
    const el = document.createElement('div');
    el.className = 'msg' + (me ? ' me' : '');
    el.innerHTML = '<div class="msg-ava">' + (me ? '🙂' : '🍿') + '</div>' +
                   '<div class="msg-bubble">' + html + '</div>';
    const body = $('mateBody');
    const quiet = body.querySelector('.mate-quiet');
    if (quiet) quiet.remove();
    body.appendChild(el);
    body.scrollTop = body.scrollHeight;
  }

  /** 消息里提到的表达做成可点链接，点了直接开卡片 */
  function link(pointId) {
    const p = pointById(pointId);
    if (!p) return '';
    return '<a class="mlink" data-open="' + pointId + '">' + esc(p.phrase) + '</a>';
  }

  function renderMateForRound() {
    const body = $('mateBody');
    body.innerHTML = '';

    if (S.round === 1) {
      $('mateState').textContent = '在旁边看着（不打扰）';
      $('mateAva').classList.add('thinking');
      body.innerHTML =
        '<div class="mate-quiet">' +
          '<div class="quiet-ring">🍿</div>' +
          '<p>我先不说话。<br />这一轮你就正常看，<br />有需要随时叫我 👀</p>' +
        '</div>';
      return;
    }

    $('mateAva').classList.remove('thinking');

    if (S.round === 2) {
      $('mateState').textContent = '边看边等，遇到好东西就举手';
      mateSay('字幕开了。这一轮我只会在 <b>' + S.clip.moments.length + ' 个</b>地方举手 ✋<br />' +
        '正看得起劲的话<b>直接无视我</b>就行。');
      mateSay('字幕里<b>任何词都能点</b>，虚线标出来的是我有话说的；鼠标停在字幕上会出中文。');
    }
    if (S.round === 3) {
      $('mateState').textContent = '陪你抠细节';
      mateSay('这一轮挑了 <b>' + S.clip.points.length + '</b> 句值得反复听的。' +
        '点开会自动放一遍，想再听按「重听一次」。');
    }
    if (S.round === 4) {
      $('mateState').textContent = '看看这一趟收了多少';
      mateSay('最后四道题，都是能直接拿去用的场景。');
    }
  }

  /* ==========================================================================
   * 播放控制
   * ========================================================================*/
  function setPlayIcon(playing) { $('btnPlay').textContent = playing ? '❚❚' : '▶'; }

  function togglePlay() {
    const el = v();
    if (!el.src) return;
    if (el.paused) el.play().catch(() => {}); else el.pause();
  }

  function back3() { const el = v(); el.currentTime = Math.max(0, el.currentTime - 3); }

  function cycleRate() {
    S.rateIdx = (S.rateIdx + 1) % RATES.length;
    const r = RATES[S.rateIdx];
    v().playbackRate = r;
    const btn = $('chipRate');
    btn.textContent = r + 'x';
    btn.classList.toggle('on', r !== 1);
  }

  function setRate(r) {
    S.rateIdx = Math.max(0, RATES.indexOf(r));
    v().playbackRate = r;
    const btn = $('chipRate');
    btn.textContent = r + 'x';
    btn.classList.toggle('on', r !== 1);
  }

  function toggleZh() {
    S.forceZh = !S.forceZh;
    $('subZh').classList.toggle('forced', S.forceZh);
    $('chipZh').classList.toggle('on', S.forceZh);
  }

  function notHeard() {
    const el = v();
    const line = lineAt(el.currentTime) || lineAt(el.currentTime + 1) || lastLineBefore(el.currentTime);
    if (!line) { back3(); return; }
    playOnce(line);
    setRate(0.75);
    S.forceZh = true;
    $('subZh').classList.add('forced');
    $('chipZh').classList.add('on');
    toast('回到这句开头，0.75x 慢放 + 中文已打开', '🐢');
  }

  function lineAt(t) { return S.clip.lines.find((l) => t >= l.start && t < l.end) || null; }

  function lastLineBefore(t) {
    let r = null;
    for (const l of S.clip.lines) { if (l.start <= t) r = l; }
    return r;
  }

  /** 单次播放一句：播到句尾自动停 —— 比循环播放友好得多 */
  function playOnce(line) {
    const el = v();
    S.loop = null;
    $('barLoop').classList.add('hidden');
    S.once = { end: line.end + 0.12 };
    el.currentTime = Math.max(0, line.start - 0.08);
    el.play().catch(() => {});
    markLoopBar(line);
  }

  function playLoop(line) {
    const el = v();
    S.once = null;
    S.loop = { start: Math.max(0, line.start - 0.08), end: line.end + 0.12 };
    el.currentTime = S.loop.start;
    el.play().catch(() => {});
    markLoopBar(line);
  }

  function markLoopBar(line) {
    const d = clipDur();
    const lp = $('barLoop');
    lp.classList.remove('hidden');
    lp.style.left = (line.start / d * 100) + '%';
    lp.style.width = ((line.end - line.start) / d * 100) + '%';
  }

  /* ------------------------------------------------------------ 字幕渲染 */
  function paintSub(t) {
    const line = lineAt(t);

    if (!line) {
      if (S.curLineId !== null) $('subLayer').classList.add('gap');
      return;
    }
    $('subLayer').classList.remove('gap');

    if (line.id !== S.curLineId) {
      S.curLineId = line.id;
      $('subSpeaker').textContent = line.sp;
      $('subSpeaker').classList.add('on');
      $('subZh').textContent = line.zh;

      const g = S.clip.glossary || {};
      $('subEn').innerHTML = line.en.split(/(\s+)/).map((tk) => {
        if (/^\s+$/.test(tk)) return tk;
        const key = norm(tk);
        const known = key && g[key];
        return '<span class="w' + (known ? ' known' : '') + '" data-w="' + esc(key) + '">' + esc(tk) + '</span>';
      }).join('');
    }

    const ws = $('subEn').querySelectorAll('.w');
    if (ws.length) {
      const p = Math.max(0, Math.min(1, (t - line.start) / Math.max(0.1, line.end - line.start)));
      const n = Math.ceil(p * ws.length);
      ws.forEach((w, i) => w.classList.toggle('spoken', i < n));
    }
  }

  /* ------------------------------------------------------------ AI 举手 */
  /** AI 举手的调度：一次只举一只手，且过点不丢。
   *  台词密集处两个点可能只差 1 秒，而一个气泡要占 3.5 秒 ——
   *  所以不能用「到点那一瞬间的窗口」判断，否则后一个点会被整个吞掉。
   *  做法：取所有「已经到点、还没举过」的点里最早的那个，
   *  前一个气泡收掉后它自然接上；只有用户手动跳到更后面时才算作错过。 */
  function checkRaise(t) {
    if (S.round !== 2) return;
    if (S.pending) return;
    let due = null;
    for (const m of S.clip.moments) {
      if (S.fired.has(m.pointId)) continue;
      if (t >= m.at) { if (!due || m.at < due.at) due = m; }
    }
    if (!due) return;
    // 排队等出来的点也别太晚：距到点已过 12 秒说明是拖进度条跳过去的，直接记作跳过
    if (t - due.at > 12) {
      S.fired.add(due.pointId);
      if (!S.opened.has(due.pointId) && !S.skipped.some((x) => x.pointId === due.pointId)) {
        S.skipped.push(due);
        renderLater();
        renderMarks();
      }
      return;
    }
    S.fired.add(due.pointId);
    showRaise(due);
  }

  function showRaise(m) {
    S.pending = m;
    $('raiseTxt').textContent = m.hook;
    $('raise').classList.add('on');
    $('mateState').textContent = '举手中…';

    clearTimeout(S.raiseTimer);
    // 灵魂设计：不理它，3.5 秒后自己走开
    S.raiseTimer = setTimeout(() => {
      $('raise').classList.remove('on');
      $('mateState').textContent = '边看边等，遇到好东西就举手';
      const m2 = S.pending;
      S.pending = null;
      if (m2 && !S.opened.has(m2.pointId) && !S.skipped.some((x) => x.pointId === m2.pointId)) {
        S.skipped.push(m2);
        renderLater();
        // 只在第一次跳过时说一句，之后安静累加，不再刷屏
        if (!S.saidSkipTip) {
          S.saidSkipTip = true;
          mateSay('好，不打扰你。跳过的我都记在右下角<b>「稍后再看」</b>里，一条不丢 😌');
        }
      }
      renderMarks();
    }, 3500);
  }

  function clearRaise() {
    clearTimeout(S.raiseTimer);
    $('raise').classList.remove('on');
    S.pending = null;
  }

  function acceptRaise() {
    const m = S.pending;
    clearRaise();
    if (!m) return;
    v().pause();
    S.skipped = S.skipped.filter((x) => x.pointId !== m.pointId);
    renderLater();
    openPoint(m.pointId, { queue: S.clip.moments.map((x) => x.pointId) });
  }

  function renderLater() {
    $('laterN').textContent = S.skipped.length;
    $('laterStrip').classList.toggle('has', S.skipped.length > 0);
  }

  function openLater() {
    if (!S.skipped.length) { toast('目前一条都没跳过 👍', '✨'); return; }
    const ids = S.skipped.map((x) => x.pointId);
    openPoint(ids[0], { queue: ids });
  }

  /* ------------------------------------------------------------ 时间轴 */
  function onTime() {
    const el = v();
    const t = el.currentTime, d = clipDur();

    $('barFill').style.width = Math.min(100, t / d * 100) + '%';
    $('tCur').textContent = fmt(t);
    $('tDur').textContent = fmt(d);

    if (S.round !== 1) paintSub(t);
    checkRaise(t);

    if (S.once && t >= S.once.end) { S.once = null; el.pause(); return; }
    if (S.loop && t >= S.loop.end) { el.currentTime = S.loop.start; return; }

    // 片源尾部还接着别的戏，到 clipEnd 就当整段播完
    if (S.clip.clipEnd && t >= S.clip.clipEnd) {
      el.pause();
      if (S.round === 1) finishRound1();
      else if (S.round === 2) finishRound2();
    }
  }

  function renderMarks() {
    const bar = $('bar');
    bar.querySelectorAll('.bar-dot').forEach((e) => e.remove());
    if (S.round !== 2) return;
    const d = clipDur();
    S.clip.moments.forEach((m) => {
      const dot = document.createElement('div');
      dot.className = 'bar-dot' + (S.opened.has(m.pointId) ? ' used' : '');
      dot.style.left = (m.at / d * 100) + '%';
      dot.title = m.hook;
      bar.appendChild(dot);
    });
  }

  /* ==========================================================================
   * 讲解卡（Tab + 翻页）
   * ========================================================================*/
  function openPoint(id, opts) {
    opts = opts || {};
    const p = pointById(id);
    if (!p) return;

    S.curPoint = id;
    S.queue = opts.queue && opts.queue.length ? opts.queue : S.clip.points.map((x) => x.id);
    if (S.queue.indexOf(id) < 0) S.queue = S.clip.points.map((x) => x.id);

    const first = !S.opened.has(id);
    S.opened.add(id);
    renderMarks();

    // Tab 默认落在这个点最该看的那一面
    S.tab = p.kind === 'pron' ? 'pron' : 'usage';

    paintSheet(p);

    $('sheetMask').classList.add('on');
    $('sheet').classList.add('on');

    // 点开就把这句放一遍（单次，不循环）
    const line = lineById(p.lineId);
    if (line && S.round !== 4) playOnce(line);

    if (first && S.round !== 1) {
      mateSay('讲了 ' + link(id) + '。' +
        (p.kind === 'pron' ? '这条是发音，建议按「重听一次」跟两遍 🔊' : '觉得有用就收进表达库 📌'));
    }
  }

  function paintSheet(p) {
    const kindTag = { idiom: 'tag-idiom', pron: 'tag-pron', culture: 'tag-culture', grammar: 'tag-green' }[p.kind] || 'tag-idiom';
    $('sheetTag').className = 'tag ' + kindTag;
    $('sheetTag').textContent = p.tag;
    $('sheetPhrase').textContent = p.phrase;
    $('sheetZh').textContent = p.zh;

    /* --- Tab：只显示这个点真的有内容的面 --- */
    const tabs = [{ id: 'usage', label: '💬 用法', has: true }];
    if (p.pron) tabs.push({ id: 'pron', label: '🔊 发音', has: true });
    if (p.culture) tabs.push({ id: 'culture', label: '🎭 背景 / 梗', has: true });
    if (!tabs.some((t) => t.id === S.tab)) S.tab = 'usage';

    $('sheetTabs').innerHTML = tabs.length > 1
      ? tabs.map((t) => '<button class="stab ' + (t.id === S.tab ? 'on' : '') + '" data-tab="' + t.id + '">' +
          t.label + '</button>').join('')
      : '';
    $('sheetTabs').style.display = tabs.length > 1 ? '' : 'none';

    let body = '<div class="headline">💡 ' + p.headline + '</div>';

    if (S.tab === 'usage') {
      body += '<div class="blk"><div class="blk-title">为什么老外这么说</div>' +
              '<div class="why">' + p.why + '</div></div>';
      if (p.contrast) {
        body += '<div class="blk"><div class="blk-title">对照着看</div><div class="contrast">' +
          p.contrast.map((c) =>
            '<div class="contrast-row"><div class="contrast-label">' + esc(c.label) + '</div>' +
            '<div class="contrast-text">' + esc(c.text) + '</div></div>').join('') +
          '</div></div>';
      }
      if (p.examples) {
        body += '<div class="blk"><div class="blk-title">换几个句子感受一下</div>' +
          p.examples.map((e) =>
            '<div class="ex"><div class="ex-en">' + e.en + '</div><div class="ex-zh">' + esc(e.zh) + '</div></div>'
          ).join('') + '</div>';
      }
      if (p.swap) {
        body += '<div class="blk"><div class="blk-title">搬到你自己的场景</div>' +
          '<div class="swap"><div class="swap-scene">📍 ' + esc(p.swap.scene) + '</div>' +
          '<div class="swap-say">“' + esc(p.swap.say) + '”</div></div></div>';
      }
    } else if (S.tab === 'pron') {
      body += '<div class="blk"><div class="blk-title">吞音 / 连读 / 重音</div>' + renderPron(p.pron) + '</div>';
      if (p.examples) {
        body += '<div class="blk"><div class="blk-title">同类现象</div>' +
          p.examples.map((e) =>
            '<div class="ex"><div class="ex-en">' + e.en + '</div><div class="ex-zh">' + esc(e.zh) + '</div></div>'
          ).join('') + '</div>';
      }
    } else {
      body += '<div class="blk"><div class="blk-title">背景与梗</div>' +
              '<div class="why">' + p.culture + '</div></div>';
    }

    $('sheetBody').innerHTML = body;
    $('sheetBody').scrollTop = 0;

    // 翻页
    const i = S.queue.indexOf(p.id);
    $('sheetNav').innerHTML =
      '<button class="navbtn" data-nav="-1" ' + (i <= 0 ? 'disabled' : '') + '>‹</button>' +
      '<span class="navpos">' + (i + 1) + ' / ' + S.queue.length + '</span>' +
      '<button class="navbtn" data-nav="1" ' + (i >= S.queue.length - 1 ? 'disabled' : '') + '>›</button>';

    const saved = LS.get('vault', []).some((x) => x.phrase === p.phrase);
    $('sheetSave').textContent = saved ? '✓ 已在表达库' : '＋ 收进表达库';
    $('sheetSave').disabled = saved;
  }

  function renderPron(pr) {
    // 连读用国际音标的 undertie「‿」直接插在两词之间：位置精确，也是语音学标准记法
    const toks = pr.tokens.map((t) => {
      const cls = ['tok'];
      if (t.stress) cls.push('stress');
      if (t.weak) cls.push('weak');
      if (t.swallow) cls.push('swallow');
      return '<span class="' + cls.join(' ') + '">' + esc(t.w) + '</span>' +
             (t.link ? '<span class="tok-arc" title="和下一个词连读">‿</span>' : '');
    }).join('');

    return '<div class="pron-box">' +
      '<div class="pron-tokens">' + toks + '</div>' +
      '<div class="pron-legend">' +
        '<span class="lg"><span class="lg-dot"></span>重音落这里</span>' +
        '<span class="lg"><span class="tok-arc" style="font-size:16px;margin:0">‿</span>和下一词连读</span>' +
        '<span class="lg"><span class="lg-cut">t</span>这个音被吞掉</span>' +
        '<span class="lg"><span style="color:var(--text-muted)">小灰字</span>弱读带过</span>' +
      '</div>' +
      '<div class="shadow-line">' +
        '<span class="shadow-tag">实际听到的是</span>' +
        '<span class="shadow-txt">' + esc(pr.shadow) + '</span>' +
      '</div>' +
      '<div class="pron-tip">🎧 ' + pr.tip + '</div>' +
    '</div>';
  }

  function closeSheet() {
    $('sheetMask').classList.remove('on');
    $('sheet').classList.remove('on');
    S.curPoint = null;
    S.loop = null; S.once = null;
    $('barLoop').classList.add('hidden');
    if (S.round === 3) renderDecode();
  }

  function navSheet(d) {
    const i = S.queue.indexOf(S.curPoint) + d;
    if (i < 0 || i >= S.queue.length) return;
    openPoint(S.queue[i], { queue: S.queue });
  }

  function replayOnce() {
    const p = pointById(S.curPoint);
    if (!p) return;
    const line = lineById(p.lineId);
    if (line) playOnce(line);
  }

  function replayLoop() {
    const p = pointById(S.curPoint);
    if (!p) return;
    const line = lineById(p.lineId);
    if (line) { playLoop(line); toast('单句循环中 · 点暂停或关掉卡片即停', '🔁'); }
  }

  function savePoint() {
    const p = pointById(S.curPoint);
    if (!p) return;
    addVault(p.phrase, p.zh);
    $('sheetSave').textContent = '✓ 已在表达库';
    $('sheetSave').disabled = true;
  }

  /* ==========================================================================
   * 表达库
   * ========================================================================*/
  function addVault(phrase, zh) {
    const list = LS.get('vault', []);
    if (list.some((x) => x.phrase === phrase)) return false;
    list.push({ phrase, zh, clip: S.clip ? S.clip.id : '', ts: Date.now() });
    LS.set('vault', list);
    renderVault();
    renderStreak();
    toast('已收进表达库：' + phrase, '📌');
    return true;
  }

  function renderVault() {
    const list = LS.get('vault', []);
    $('vaultN').textContent = list.length;
    if (!list.length) {
      $('vaultList').innerHTML = '<span class="vault-empty">还是空的 —— 点字幕里的词，或收下讲解卡里的表达</span>';
      return;
    }
    $('vaultList').innerHTML = list.slice().reverse().map((x) =>
      '<span class="vault-item" title="' + esc(x.zh || '') + '">' + esc(x.phrase) + '</span>').join('');
  }

  /* ==========================================================================
   * 点词小卡
   * ========================================================================*/
  function showWordPop(word, el) {
    const info = (S.clip.glossary || {})[word];
    const pop = $('wordpop');

    if (!info) {
      pop.innerHTML = '<div class="wordpop-w"><span class="wordpop-word">' + esc(word) + '</span></div>' +
        '<div class="wordpop-note" style="border:0;padding-top:0">这个词没什么特别的，按字面理解就行 🙂</div>';
    } else {
      pop.innerHTML =
        '<div class="wordpop-w"><span class="wordpop-word">' + esc(word) + '</span>' +
        '<span class="wordpop-pos">' + esc(info.pos) + '</span></div>' +
        '<div class="wordpop-zh">' + esc(info.zh) + '</div>' +
        (info.note ? '<div class="wordpop-note">💬 ' + esc(info.note) + '</div>' : '') +
        '<div class="wordpop-foot"><button class="btn btn-sm" data-add="1">＋ 收进表达库</button></div>';
    }

    const r = el.getBoundingClientRect();
    pop.classList.add('on');
    const w = pop.offsetWidth, h = pop.offsetHeight;
    pop.style.left = Math.max(10, Math.min(window.innerWidth - w - 10, r.left + r.width / 2 - w / 2)) + 'px';
    pop.style.top = Math.max(10, r.top - h - 12) + 'px';

    const btn = pop.querySelector('[data-add]');
    if (btn) btn.onclick = () => {
      if (!addVault(word, info.zh)) toast('这个已经在表达库里了 🙂');
      el.classList.add('saved');
      hideWordPop();
    };
  }

  function hideWordPop() { $('wordpop').classList.remove('on'); }

  /* ==========================================================================
   * Round 3 · 金句精讲
   * ========================================================================*/
  function renderDecode() {
    const total = S.clip.points.length;
    const html = '<div class="section-head tight">' +
        '<h2>金句 ' + total + ' 句</h2>' +
        '<span>已看 ' + S.opened.size + '/' + total + ' · 点开会自动放一遍这句</span>' +
      '</div>' +
      '<div class="decode-grid">' +
      S.clip.points.map((p, i) => {
        const line = lineById(p.lineId);
        const skipped = S.skipped.some((x) => x.pointId === p.id);
        const done = S.opened.has(p.id);
        return '<div class="decode-item ' + (done ? 'opened' : '') + '" data-p="' + p.id + '">' +
            '<div class="decode-n">' + (done ? '✓' : i + 1) + '</div>' +
            '<div class="decode-main">' +
              '<div class="decode-phrase">' + esc(p.phrase) +
                ' <span class="tag ' + ({ idiom: 'tag-idiom', pron: 'tag-pron', culture: 'tag-culture', grammar: 'tag-green' }[p.kind] || 'tag-idiom') + '">' + p.tag + '</span>' +
                (skipped ? ' <span class="tag tag-yellow">刚才跳过</span>' : '') +
              '</div>' +
              '<div class="decode-desc">' + esc(p.headline) + '</div>' +
            '</div>' +
            '<div class="decode-loop">' + (line ? fmt(line.start) : '') + ' 🔊</div>' +
          '</div>';
      }).join('') + '</div>' +
      '<div class="row-btns">' +
        '<button class="btn btn-primary" id="toCheck">去验收 →</button>' +
        '<span class="muted-tip">看几句有感觉了就可以去验收</span>' +
      '</div>';

    $('roundZone').innerHTML = html;

    $('roundZone').querySelectorAll('.decode-item').forEach((el) => {
      el.addEventListener('click', () => openPoint(el.dataset.p));
    });
    $('toCheck').onclick = () => gotoRound(4);
  }

  /* ==========================================================================
   * Round 1 · 裸听题
   * ========================================================================*/
  function renderBlindQuiz() {
    const qs = S.clip.blindQuiz;
    $('roundZone').innerHTML = '<div class="section-head tight">' +
        '<h2>先别急，几个很轻的问题</h2><span>答不上来完全正常 —— 这是第一遍</span>' +
      '</div>' +
      qs.map((q, i) => renderQ(q, i, 'blind')).join('') +
      '<div class="row-btns">' +
        '<button class="btn btn-primary" id="toR2">开字幕，再看一遍 →</button>' +
        '<span class="muted-tip" id="r1tip"></span>' +
      '</div>';

    bindQ('blind');
    updateR1Tip();
    $('toR2').onclick = () => gotoRound(2);
  }

  function updateR1Tip() {
    const left = S.clip.blindQuiz.length - Object.keys(S.blind).length;
    const el = $('r1tip');
    if (el) el.textContent = left > 0 ? '还有 ' + left +' 题没填（不填也能往下走）' : '都填了 👍';
  }

  /* ==========================================================================
   * Round 1 第 4 题的回声：匹配学习点 / 找最接近的原句
   * ========================================================================*/
  function echoImpression(text) {
    const t = (text || '').toLowerCase().trim();
    if (!t) return { type: 'none' };

    // 1) 命中某个学习点
    for (const p of S.clip.points) {
      if ((p.matchKeys || []).some((k) => t.includes(k.toLowerCase()))) return { type: 'hit', p };
    }

    // 2) 和某句台词高度重合 → 顺手把措辞对一下（相当于纠正）
    const ws = t.split(/[^a-z']+/).filter((w) => w.length > 2);
    if (ws.length >= 2) {
      let best = null, score = 0;
      for (const l of S.clip.lines) {
        const lw = l.en.toLowerCase().split(/[^a-z']+/);
        const s = ws.filter((w) => lw.includes(w)).length / ws.length;
        if (s > score) { score = s; best = l; }
      }
      if (score >= 0.4 && best) return { type: 'near', line: best, score };
    }
    return { type: 'none' };
  }

  function echoHtml() {
    const rows = [];

    // 听辨那题（关联的学习点写在 blindQuiz 里，不能硬编码 id —— 每个片段的点 id 不同）
    const q3 = S.clip.blindQuiz.find((q) => q.answer === null && q.reveal !== undefined);
    if (q3 && S.blind[q3.id] !== undefined) {
      const heard = q3.options[S.blind[q3.id]];
      const right = q3.options[q3.reveal];
      const ok = S.blind[q3.id] === q3.reveal;
      const l = q3.pointId ? link(q3.pointId) : '';
      rows.push('<div class="echo-row"><span class="echo-k">' + esc(q3.echoKey || '那个关键词') + '</span>' +
        '<span class="echo-v">你第一遍听成 <b>' + esc(heard) + '</b>，' +
        (ok ? '<b class="ok">听对了 👏</b>' : '其实是 <b class="ok">' + esc(right) + '</b>') +
        (l ? ' —— ' + l : '') + '</span></div>');
    }

    // 印象最深的表达
    const q4 = S.clip.blindQuiz.find((q) => q.echo);
    const wrote = q4 && S.blind[q4.id];
    if (wrote) {
      const r = echoImpression(wrote);
      let val = '你写的是「<b>' + esc(wrote) + '</b>」。';
      if (r.type === 'hit') {
        val += '正好命中 ' + link(r.p.id) + ' —— 这也是我最想让你带走的那句 ✅';
      } else if (r.type === 'near') {
        val += '你记的应该是这句：<b class="ok">' + esc(r.line.en) + '</b>' +
               '<span class="echo-sub">（' + esc(r.line.zh) + '）措辞对一下就更准了</span>';
      } else {
        const recs = (S.clip.recommendPoints || S.clip.points.slice(0, 2).map((p) => p.id))
          .map(link).filter(Boolean);
        val += '这段里最值得带走的其实是 ' + recs.join(' 和 ') + '，都是能直接用的。';
      }
      rows.push('<div class="echo-row"><span class="echo-k">你印象最深的</span><span class="echo-v">' + val + '</span></div>');
    }

    if (!rows.length) return '';
    return '<div class="echo-bar">' + rows.join('') + '</div>';
  }

  /* ==========================================================================
   * Round 4 · 验收
   * ========================================================================*/
  function renderCheck() {
    $('roundZone').innerHTML = echoHtml() +
      '<div class="section-head tight"><h2>四道题，验收一下</h2>' +
      '<span>都是能直接拿去用的场景</span></div>' +
      S.clip.finalQuiz.map((q, i) => renderQ(q, i, 'final')).join('') +
      '<div id="harvestZone"></div>';

    bindQ('final');
    checkHarvest();
  }

  function checkHarvest() {
    const qs = S.clip.finalQuiz;
    if (Object.keys(S.final).length < qs.length) return;

    const correct = qs.filter((q) => S.final[q.id] && S.final[q.id].ok).length;
    const total = qs.length;
    const vault = LS.get('vault', []);
    const learned = S.clip.points.filter((p) => S.opened.has(p.id));

    const comp = Math.round(S.opened.size / S.clip.points.length * 100);
    const rete = Math.round(correct / total * 100);
    const conn = learned.length
      ? Math.round(learned.filter((p) => vault.some((x) => x.phrase === p.phrase)).length / learned.length * 100)
      : 0;

    const days = rete >= 80 ? 4 : rete >= 50 ? 2 : 1;
    const next = new Date(Date.now() + days * 864e5).toLocaleDateString('zh-CN', { month: 'long', day: 'numeric' });

    $('harvestZone').innerHTML =
      '<div class="harvest">' +
        '<div class="harvest-top">' +
          '<div class="harvest-score">' + correct + ' / ' + total + '</div>' +
          '<div class="harvest-sub">这一段你留下了 ' + learned.length + ' 个表达 · ' +
            (correct === total ? '全对，可以去看下一段了 🎉' : '错的那条已经记下，下次复习会再问你') + '</div>' +
        '</div>' +
        '<div class="harvest-body">' +
          '<div class="blk-title">这一趟收下的</div>' +
          '<div class="harvest-list">' +
            (learned.length ? learned.map((p) =>
              '<div class="harvest-item"><span class="harvest-check">✓</span>' +
              '<span class="harvest-phrase">' + esc(p.phrase) + '</span>' +
              '<span class="harvest-tag">' + p.tag + '</span></div>').join('')
              : '<div class="vault-empty">这一轮没打开讲解卡 —— 回第 3 轮看看？</div>') +
          '</div>' +
          '<div class="blk-title">掌握度（理解 × 记忆 × 连接）</div>' +
          '<div class="mastery">' +
            masteryRow('理解', comp, 'var(--brand)') +
            masteryRow('记忆', rete, 'var(--green)') +
            masteryRow('连接', conn, 'var(--purple)') +
          '</div>' +
          '<div class="quiz-note mt">' +
            '📅 按间隔重复的节奏，<b>' + next + '</b> 再过一遍这几个表达最划算。' +
            '真实产品里这一步会自动排进复习队列。' +
          '</div>' +
          '<div class="row-btns">' +
            '<button class="btn btn-primary" data-go="home">← 回片单，换一段</button>' +
            '<button class="btn" data-go="r3">再看看金句</button>' +
          '</div>' +
        '</div>' +
      '</div>';

    $('harvestZone').querySelector('[data-go="home"]').onclick = goHome;
    $('harvestZone').querySelector('[data-go="r3"]').onclick = () => gotoRound(3);

    renderStepper();
    bumpStreak(S.clip.id);

    if (!S.harvested) {
      S.harvested = true;
      mateSay('这一段过完了 🎉<br />你再去看一遍原片，那几句应该会自己跳出来 —— 这就是我想要的效果。');
    }
  }

  function masteryRow(k, val, color) {
    return '<div class="mastery-row"><div class="mastery-k">' + k + '</div>' +
      '<div class="mastery-track"><div class="mastery-fill" style="width:' + val + '%;background:' + color + '"></div></div>' +
      '<div class="mastery-v">' + val + '%</div></div>';
  }

  /* ==========================================================================
   * 题目
   * ========================================================================*/
  /** 选项显示顺序：进入题目时洗牌一次并缓存，避免正确答案永远在 A。
   *  按钮上的 data-k 始终是数据里的原始下标，所以判分逻辑完全不受影响。
   *  keepLast:n 表示末尾 n 个选项固定不动（"完全没听清"这类兜底项）。 */
  function optOrder(q) {
    if (!S.optOrder[q.id]) {
      const n = q.options.length;
      const tail = q.keepLast || 0;
      const head = [];
      for (let k = 0; k < n - tail; k++) head.push(k);
      for (let i = head.length - 1; i > 0; i--) {
        const j = Math.floor(Math.random() * (i + 1));
        [head[i], head[j]] = [head[j], head[i]];
      }
      for (let k = n - tail; k < n; k++) head.push(k);
      S.optOrder[q.id] = head;
    }
    return S.optOrder[q.id];
  }

  function renderQ(q, i, ns) {
    let body = '';
    if (q.type === 'choice') {
      body = '<div class="opts">' + optOrder(q).map((k, pos) =>
        '<button class="opt" data-q="' + q.id + '" data-k="' + k + '">' +
        '<span class="opt-k">' + 'ABCD'[pos] + '</span><span>' + esc(q.options[k]) + '</span></button>').join('') + '</div>';
    } else if (q.type === 'fill') {
      body = '<div class="fill-row"><span>' + esc(q.prefix) + '</span>' +
        '<input class="inp" data-q="' + q.id + '" placeholder="填这里" />' +
        '<span>' + esc(q.suffix || '') + '</span>' +
        '<button class="btn btn-sm" data-submit="' + q.id + '">对答案</button></div>';
    } else {
      body = '<textarea class="inp" data-q="' + q.id + '" placeholder="' + esc(q.placeholder || '随便写') + '"></textarea>' +
        '<div class="mt8"><button class="btn btn-sm" data-submit="' + q.id + '">记下来</button></div>';
    }

    return '<div class="quiz-card" data-card="' + q.id + '">' +
        '<div class="quiz-top"><div class="quiz-idx">' + (i + 1) + '</div>' +
        '<div class="quiz-q">' + esc(q.q) + '</div></div>' + body +
        (q.hint ? '<div class="quiz-note">💡 ' + esc(q.hint) + '</div>' : '') +
        '<div class="fb-slot"></div></div>';
  }

  function applyChoice(q, card, k) {
    // 选项顺序被打乱过，只能按 data-k 找按钮，不能按 DOM 下标
    const btns = card.querySelectorAll('.opt');
    const at = (idx) => card.querySelector('.opt[data-k="' + idx + '"]');
    btns.forEach((b) => b.classList.add('locked'));
    if (q.answer === null) {
      at(k).classList.add('picked');
      card.querySelector('.fb-slot').innerHTML =
        '<div class="feedback info"><span>🤫</span><span>' + esc(q.note) + '</span></div>';
      return null;
    }
    const ok = k === q.answer;
    at(k).classList.add(ok ? 'right' : 'wrong');
    if (!ok) at(q.answer).classList.add('right');
    card.querySelector('.fb-slot').innerHTML =
      '<div class="feedback ' + (ok ? 'ok' : 'no') + '"><span>' + (ok ? '✓' : '✕') + '</span><span>' +
      (ok ? '对了。' : '这题错了。') + esc(q.because || '') + '</span></div>';
    return ok;
  }

  function applyInput(q, card, val, ok) {
    const inp = card.querySelector('.inp');
    const btn = card.querySelector('[data-submit]');
    inp.value = val;
    inp.disabled = true;
    if (btn) btn.disabled = true;

    if (q.type === 'fill') {
      inp.classList.add(ok ? 'right' : 'wrong');
      card.querySelector('.fb-slot').innerHTML =
        '<div class="feedback ' + (ok ? 'ok' : 'no') + '"><span>' + (ok ? '✓' : '✕') + '</span><span>' +
        (ok ? '正是这个。' : '正确答案是 <b>' + esc(q.answer[0]) + '</b>。') + esc(q.because || '') + '</span></div>';
    } else {
      // 当场给一句轻反馈，真正的回声放在第 4 轮
      const r = echoImpression(val);
      let msg = '记下了。';
      if (r.type === 'hit') msg += '你挑的这个正好是重点之一，最后一轮我们再说它。';
      else if (r.type === 'near') msg += '我大概知道你说的是哪句了，最后一轮把原句放一起对一下。';
      else msg += '最后一轮我会把它和这段的重点放一起看。';
      card.querySelector('.fb-slot').innerHTML =
        '<div class="feedback info"><span>📌</span><span>' + msg + '</span></div>';
    }
  }

  function bindQ(ns) {
    const zone = $('roundZone');
    const qs = ns === 'blind' ? S.clip.blindQuiz : S.clip.finalQuiz;
    const store = ns === 'blind' ? S.blind : S.final;

    zone.querySelectorAll('.opt').forEach((btn) => {
      btn.addEventListener('click', () => {
        if (btn.classList.contains('locked')) return;
        const q = qs.find((x) => x.id === btn.dataset.q);
        const card = zone.querySelector('[data-card="' + q.id + '"]');
        const ok = applyChoice(q, card, +btn.dataset.k);
        store[q.id] = ns === 'final' ? { pick: +btn.dataset.k, ok } : +btn.dataset.k;
        afterAnswer(ns);
      });
    });

    zone.querySelectorAll('[data-submit]').forEach((btn) => {
      btn.addEventListener('click', () => {
        const q = qs.find((x) => x.id === btn.dataset.submit);
        const card = zone.querySelector('[data-card="' + q.id + '"]');
        const val = (card.querySelector('.inp').value || '').trim();
        if (!val) { toast('写点什么再提交 🙂'); return; }
        if (q.type === 'fill') {
          const ok = q.answer.some((a) => val.toLowerCase().replace(/\s+/g, ' ') === a.toLowerCase());
          applyInput(q, card, val, ok);
          store[q.id] = { val, ok };
        } else {
          applyInput(q, card, val);
          store[q.id] = val;
        }
        afterAnswer(ns);
      });
    });

    // 回到已作答过的轮次时恢复状态
    qs.forEach((q) => {
      if (store[q.id] === undefined) return;
      const card = zone.querySelector('[data-card="' + q.id + '"]');
      if (!card) return;
      const s = store[q.id];
      if (q.type === 'choice') applyChoice(q, card, typeof s === 'object' ? s.pick : s);
      else if (q.type === 'fill') applyInput(q, card, s.val, s.ok);
      else applyInput(q, card, s);
    });
  }

  function afterAnswer(ns) {
    renderStepper();
    if (ns === 'final') checkHarvest();
    else updateR1Tip();
  }

  /* ==========================================================================
   * 每轮收尾 / 快进
   * ========================================================================*/
  function finishRound1() {
    v().pause();
    if (S.r1done) { $('roundZone').scrollIntoView({ behavior: 'smooth', block: 'start' }); return; }
    S.r1done = true;
    S.loop = null; S.once = null;
    mateSay('看完了。<br />我一句话都没插 —— 这一轮本来就该这样 😌');
    renderBlindQuiz();
    $('roundZone').scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  function finishRound2() {
    v().pause();
    clearRaise();
    if (S.r2done) { $('roundZone').scrollIntoView({ behavior: 'smooth', block: 'start' }); return; }
    S.r2done = true;
    const miss = S.skipped.length;
    mateSay('第二遍过完了。' + (miss ? '跳过的 <b>' + miss + '</b> 处都在。' : '') +
      '接下来把金句挑出来一句一句抠。');
    $('roundZone').innerHTML =
      '<div class="quiz-card center">' +
        '<div class="big">这一遍看完了</div>' +
        '<div class="muted-tip block">举手点你打开了 ' + S.opened.size + '/' + S.clip.moments.length + ' 个' +
          (miss ? '，跳过的 ' + miss + ' 个都还在' : '') + '</div>' +
        '<button class="btn btn-primary" id="toR3">进入精讲 →</button>' +
      '</div>';
    $('toR3').onclick = () => gotoRound(3);
    renderStepper();
    $('roundZone').scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  function jump() {
    const el = v();
    if (!el.src) return;
    if (S.round === 1) { el.pause(); finishRound1(); return; }
    if (S.round === 2) {
      const next = S.clip.moments.find((m) => !S.fired.has(m.pointId));
      if (next) {
        S.once = null; S.loop = null;
        el.currentTime = Math.max(0, next.at - 2.2);
        el.play().catch(() => {});
        toast('跳到下一个举手点 —— 等 2 秒它就抬手', '✋');
      } else finishRound2();
    }
  }

  /* ==========================================================================
   * 事件
   * ========================================================================*/
  function bindGlobal() {
    const el = v();

    el.addEventListener('timeupdate', onTime);
    el.addEventListener('loadedmetadata', () => { $('tDur').textContent = fmt(clipDur()); renderMarks(); });
    el.addEventListener('play', () => setPlayIcon(true));
    el.addEventListener('pause', () => setPlayIcon(false));
    el.addEventListener('ended', () => {
      setPlayIcon(false);
      if (S.round === 1) finishRound1();
      else if (S.round === 2) finishRound2();
    });

    $('bar').addEventListener('click', (e) => {
      const d = clipDur();
      if (!d) return;
      const r = $('bar').getBoundingClientRect();
      S.once = null; S.loop = null;
      $('barLoop').classList.add('hidden');
      el.currentTime = Math.max(0, Math.min(d - 0.05, (e.clientX - r.left) / r.width * d));
    });

    $('subEn').addEventListener('click', (e) => {
      const w = e.target.closest('.w');
      if (!w || !w.dataset.w) return;
      el.pause();
      showWordPop(w.dataset.w, w);
    });

    // 讲解卡：Tab / 翻页
    $('sheet').addEventListener('click', (e) => {
      const tab = e.target.closest('[data-tab]');
      if (tab) { S.tab = tab.dataset.tab; paintSheet(pointById(S.curPoint)); return; }
      const nav = e.target.closest('[data-nav]');
      if (nav && !nav.disabled) navSheet(+nav.dataset.nav);
    });

    // 伴学栏消息里的表达链接
    $('mateBody').addEventListener('click', (e) => {
      const a = e.target.closest('[data-open]');
      if (a) openPoint(a.dataset.open);
    });
    $('roundZone').addEventListener('click', (e) => {
      const a = e.target.closest('[data-open]');
      if (a) openPoint(a.dataset.open);
    });

    document.addEventListener('click', (e) => {
      if (!e.target.closest('#wordpop') && !e.target.closest('.w')) hideWordPop();
    });

    document.addEventListener('keydown', (e) => {
      if (/input|textarea/i.test(e.target.tagName || '')) return;
      if (e.code === 'Space' && !$('pageStudy').classList.contains('hidden')) { e.preventDefault(); togglePlay(); }
      if (e.code === 'Escape') { closeSheet(); hideWordPop(); }
      if (e.code === 'ArrowLeft' && S.curPoint) navSheet(-1);
      if (e.code === 'ArrowRight' && S.curPoint) navSheet(1);
    });

    window.addEventListener('scroll', hideWordPop, { passive: true });
  }

  /* ==========================================================================
   * 导出
   * ========================================================================*/
  window.App = {
    goHome, gotoRound, togglePlay, back3, cycleRate, toggleZh, notHeard,
    acceptRaise, openLater, closeSheet, replayOnce, replayLoop, savePoint,
    openPoint, jump,
  };

  /* 入口来源适配（WeSmartFlow examples 规范）：
     带 ?source=wesmartflow 时说明是从探索页进来的，顶栏换成「返回探索」并指回 /#/explore；
     独立部署 / 直接打开时保持原有外链，两种入口互不干扰。 */
  function setupPortalLink() {
    let fromPortal = false;
    try {
      fromPortal = new URLSearchParams(window.location.search).get('source') === 'wesmartflow';
    } catch (e) { return; }
    if (!fromPortal) return;
    const a = $('wsfLink');
    if (!a) return;
    a.textContent = '← 返回探索';
    a.href = '/#/explore';
    a.removeAttribute('target');
    a.removeAttribute('rel');
  }

  document.addEventListener('DOMContentLoaded', () => { setupPortalLink(); renderHome(); bindGlobal(); });
})();
