/* ============================================================================
 * BingeMate · 追剧搭子 —— 课程数据
 *
 * 为什么用 .js 而不是 .json：
 *   浏览器在 file:// 协议下 fetch 本地 json 会被 CORS 拦截，
 *   而 <script src> 不受限制。这样双击 index.html 就能直接演示，无需起服务。
 *
 * 字幕轴的来源（三者取长，缺一不可）：
 *   1) 时间戳  —— faster-whisper (small.en) 转写本文件，毫秒级，误差 < 0.2s
 *   2) 台词文本 —— 官方剧本裁决（Whisper 会把 would/wouldn't、Chandler/Charlie 听错）
 *   3) 说话人  —— 同上剧本（剧本带 speaker 标注，Whisper 完全没有）
 *
 * 发音标记（pron.tokens）的来源 —— 不靠感觉，靠实测：
 *   · 重音 stress —— 用 Whisper 词级时间戳切出每个词，算音频 RMS 能量，
 *                    取相对峰值 > 0.72 的词。实测常和直觉相反：
 *                    "I just don't think it's going to fit" 全句只有 fit 一个重音，
 *                    think 反而是被压得最扁的词之一。
 *   · 弱读 weak   —— 相对能量 < 0.45，或词时长异常短
 *   · 连读 link   —— 与后一词的时间间隔 ≤ 0.02s（词界消失）
 *   · 吞音 swallow —— 音素级现象，词级数据测不到，
 *                    用公认的语音规则判定（/t/ 在 /θ/ 前脱落等），并与影子拼写对照
 *   验证脚本见 EXTENSIONS.md 第 1 节。
 *
 * 换一部剧只需在 clips 数组里加一项 —— 页面逻辑完全数据驱动。
 * ==========================================================================*/

window.BINGEMATE_DATA = {

  clips: [
    /* ======================================================================
     * CLIP 1 · Friends —— 沙发抬不上去（PIVOT!）
     * ==================================================================== */
    {
      id: 'friends_pivot',
      available: true,
      show: 'Friends',
      showZh: '老友记',
      episode: 'S5E16',
      title: '沙发抬不上去',
      subtitle: 'The One with the Cop',
      video: 'friends_pivot.mp4',
      cover: 'cover_friends.jpg',
      duration: 134,
      genre: '情景喜剧',
      level: '中级 · B1',
      focus: '生活口语 · 吐槽艺术',
      /* 第 1 轮末题「印象最深」没命中任何点时，兜底推荐这两个 */
      recommendPoints: ['p2', 'p6'],
      /* 片源自带中文硬字幕（中文一行 + 英文一到两行），用底部渐变遮住。
       * 参数是逐帧扫出来的，不是目测：把视频帧画到 canvas 上扫亮像素行，
       * 单行时字幕上沿在 y=411（底部 14.4%），但英文折成两行时会顶到
       * y=376（底部 21.7%，如 6.5s / 46s）—— 第一版只按单行量，
       * 结果这些时刻从渐变的半透明段漏出中文。
       * 所以 maskOpaque 按最坏情况 21.7% + 4px 余量给到 22.5，
       * 上面再留 2.5% 做淡出，总高 25%（仍比最初的 29% 小）。 */
      hardsubMask: 25,
      maskOpaque: 22.5,
      synopsis:
        'Ross 买了新沙发却不肯付送货费，决定自己扛上楼。Rachel 帮不上忙，只好去搬救兵——结果来的是 Chandler。三个人、一张沙发、一个直角楼梯转角，和一句被全世界玩了二十多年的台词。',

      /* --------------------------------------------------------------
       * 字幕轴：Whisper 时间戳 + 剧本文本/说话人
       * ------------------------------------------------------------ */
      lines: [
        { id: 1, start: 2.38, end: 3.70, sp: 'Rachel', en: 'Hey Ross! I brought reinforcements.', zh: '嘿 Ross！我把救兵带来了。' },
        { id: 2, start: 4.18, end: 5.50, sp: 'Ross', en: 'Oh great! What, you brought Joey?', zh: '太好了！怎么，你把 Joey 叫来了？' },
        { id: 3, start: 5.84, end: 7.20, sp: 'Rachel', en: 'Well, I brought the next best thing.', zh: '呃，我带了退而求其次的那个。' },
        { id: 4, start: 7.60, end: 8.30, sp: 'Chandler', en: 'Hey!', zh: '嘿！' },
        { id: 5, start: 10.05, end: 12.80, sp: 'Ross', en: 'Chandler?! You brought Chandler?! The next best thing would be Monica!', zh: 'Chandler？你带的是 Chandler？退而求其次也该是 Monica 啊！' },
        { id: 6, start: 14.80, end: 18.05, sp: 'Chandler', en: "Y'know, I would be offended, but Monica is freakishly strong, so...", zh: '你知道吗，我本来该不爽的，可 Monica 确实壮得离谱，所以……' },
        { id: 7, start: 19.25, end: 22.00, sp: 'Ross', en: "Look, I drew a sketch about how we're gonna do it, okay?", zh: '看，我画了张草图，我们就按这个搬，好吗？' },
        { id: 8, start: 22.20, end: 25.10, sp: 'Ross', en: "Okay Rach, that's you. That's the couch.", zh: '好，Rach，这个是你。这个是沙发。' },
        { id: 9, start: 26.00, end: 27.80, sp: 'Rachel', en: "Whoa-oh, what's that?", zh: '喔，那这个是什么？' },
        { id: 10, start: 27.82, end: 29.20, sp: 'Ross', en: "Oh, that's me.", zh: '哦，那是我。' },
        { id: 11, start: 31.10, end: 36.25, sp: 'Rachel', en: 'Wow! You certainly think a lot of yourself.', zh: '哇！你还挺看得起自己啊。' },
        { id: 12, start: 38.55, end: 40.20, sp: 'Ross', en: "No! That's my arm!", zh: '不是！那是我的手臂！' },
        { id: 13, start: 44.60, end: 47.75, sp: 'Chandler', en: 'Oh, I see. I thought you just really, really liked your new couch.', zh: '哦，我懂了。我还以为你是真的真的很爱你的新沙发。' },
        { id: 14, start: 51.30, end: 53.80, sp: 'Ross', en: "Y'know what? Just follow my lead.", zh: '这样吧，你们听我指挥就行。' },
        { id: 15, start: 53.86, end: 54.50, sp: 'Rachel', en: 'Okay!', zh: '好！' },
        { id: 16, start: 55.80, end: 57.05, sp: 'Ross', en: 'Come on, Chandler.', zh: '来吧，Chandler。' },
        { id: 17, start: 59.00, end: 60.40, sp: 'Ross', en: 'All right. Okay.', zh: '好。好的。' },
        { id: 18, start: 61.20, end: 62.40, sp: 'Ross', en: 'Here we go!', zh: '开始了！' },
        { id: 19, start: 63.55, end: 64.80, sp: 'Ross', en: 'All right, ready?', zh: '好了，准备好了吗？' },
        { id: 20, start: 65.60, end: 69.35, sp: 'Ross', en: 'Turn. Turn! Turn!', zh: '转。转！转！' },
        { id: 21, start: 70.05, end: 72.90, sp: 'Chandler', en: "Okay, I don't think we can turn anymore!", zh: '好吧，我觉得转不动了！' },
        { id: 22, start: 74.20, end: 75.60, sp: 'Rachel', en: "Ross, I just don't think it's going to fit.", zh: 'Ross，我觉得它真的挤不上去。' },
        { id: 23, start: 75.75, end: 77.30, sp: 'Ross', en: 'Oh yeah, it will! Come on, up! Up-up-up!', zh: '当然可以！来，抬起来！抬抬抬！' },
        { id: 24, start: 79.50, end: 82.20, sp: 'Ross', en: 'Yes! Here we go! Pivot!', zh: '对！就这样！转轴！' },
        { id: 25, start: 84.00, end: 94.70, sp: 'Ross', en: 'Pivot! Piv-ot! Piv-et! Piv-ett! Piv-et!', zh: '转轴！转——轴！转轴啊！' },
        { id: 26, start: 95.35, end: 97.70, sp: 'Chandler', en: 'Shut up! Shut up! Shut up!', zh: '闭嘴！闭嘴！闭嘴！' },
        { id: 27, start: 101.95, end: 104.65, sp: 'Ross', en: "Okay, I don't think it's going to pivot anymore.", zh: '好吧，我看它是转不动了。' },
        { id: 28, start: 104.95, end: 105.40, sp: 'Chandler & Rachel', en: 'You think?!', zh: '你才知道？！' },
        { id: 29, start: 108.20, end: 112.05, sp: 'Ross', en: "All right, let's uh, let's bring it back down and try again.", zh: '好吧，那我们……先搬下去，再来一次。' },
        { id: 30, start: 119.65, end: 122.35, sp: 'Chandler', en: "Okay, yeah, I think it's really stuck now.", zh: '好吧，我觉得它现在真的卡死了。' },
        { id: 31, start: 124.60, end: 126.40, sp: 'Ross', en: "I can't believe that didn't work!", zh: '真不敢相信居然没成功！' },
        { id: 32, start: 126.65, end: 129.55, sp: 'Rachel', en: 'I know, me neither! I mean, you had a sketch!', zh: '就是啊，我也没想到！毕竟你都画了草图了！' },
        { id: 33, start: 132.30, end: 133.90, sp: 'Chandler', en: "Oh, y'know, what did you mean when you said pivot?", zh: '哦对了，你说的那个「转轴」，到底什么意思？' },
      ],

      /* --------------------------------------------------------------
       * 可点词典
       * ------------------------------------------------------------ */
      glossary: {
        reinforcements: { pos: 'n.', zh: '增援部队；救兵', note: '军事词拿来说日常小事，制造夸张的幽默' },
        offended: { pos: 'adj.', zh: '被得罪的；不爽的', note: 'be / get offended 是"被冒犯"的标准说法' },
        freakishly: { pos: 'adv.', zh: '离谱地；反常地', note: '比 very 生动得多，专门形容"不正常的程度"' },
        sketch: { pos: 'n.', zh: '草图；速写', note: '也可指喜剧小品（a comedy sketch）' },
        certainly: { pos: 'adv.', zh: '确实；当然', note: '口语里 t 常被吞掉，听着像 "cer-nly"' },
        couch: { pos: 'n.', zh: '沙发', note: '美式常用 couch，英式多用 sofa' },
        pivot: { pos: 'v./n.', zh: '绕轴转动；（商业）转型', note: '科技新闻高频词：the company pivoted to AI' },
        stuck: { pos: 'adj.', zh: '卡住的；动不了的', note: 'be stuck 也可指"陷入困境、毫无进展"' },
        neither: { pos: 'adv.', zh: '也不', note: '附和否定句用 Me neither，不是 Me too' },
        lead: { pos: 'n.', zh: '带头；指引', note: 'follow my lead = 听我指挥、跟我走' },
        gonna: { pos: 'contr.', zh: 'going to 的口语缩合', note: '日常对话里几乎不会把 going to 读全' },
        fit: { pos: 'v.', zh: '塞得进；装得下；合身', note: "It doesn't fit 既能说家具塞不进，也能说衣服不合身" },
        anymore: { pos: 'adv.', zh: '（不）再', note: '美式写成一个词，且只用在否定/疑问句：I can’t turn anymore' },
        "y'know": { pos: 'contr.', zh: 'you know 的口语缩合', note: '开口的缓冲词，相当于中文"你知道吧、我说啊"，没有实义' },
      },

      /* --------------------------------------------------------------
       * AI 举手点：和第 3 轮精讲的学习点一一对应（每个点都有机会在观影中被提出），
       * 时间点都压在对应台词说完的瞬间 —— 先听完整句，再决定要不要听讲。
       * ------------------------------------------------------------ */
      moments: [
        { at: 3.50, pointId: 'p1', hook: '这个词用得有点"重"，故意的 ✋' },
        { at: 7.10, pointId: 'p2', hook: '这句是全场最实用的习语 ✋' },
        { at: 17.90, pointId: 'p3', hook: 'Chandler 的招牌吐槽句型 ✋' },
        { at: 36.15, pointId: 'p4', hook: '这句夸人和损人只差一个语气 ✋' },
        { at: 72.85, pointId: 'p9', hook: '这个句型这一场出现了四次 ✋' },
        { at: 75.50, pointId: 'p5', hook: '这句听着糊？有三处缩音 ✋' },
        { at: 82.10, pointId: 'p6', hook: '这词你在科技新闻里天天见 ✋' },
        { at: 105.30, pointId: 'p7', hook: '两个词的反问，杀伤力很大 ✋' },
        { at: 129.40, pointId: 'p8', hook: '这句中国人十有八九说错 ✋' },
      ],

      /* --------------------------------------------------------------
       * 学习点讲解卡
       *   kind: idiom | pron | culture   （决定讲解卡默认打开哪个 Tab）
       *   matchKeys: 用于第 1 轮"印象最深的表达"回声匹配
       *   pron.tokens 标记：stress 重音 / swallow 吞音 / link 连读 / weak 弱读
       * ------------------------------------------------------------ */
      points: [
        {
          id: 'p1',
          lineId: 1,
          kind: 'idiom',
          tag: '地道表达',
          phrase: 'I brought reinforcements.',
          zh: '我把救兵带来了。',
          matchKeys: ['reinforcement', '救兵', '增援'],
          headline: '用军事大词说生活小事，是英语幽默的常规操作',
          why:
            'reinforcements 本义是战场上的<b>增援部队</b>。Rachel 只是叫了个朋友来帮忙抬沙发，' +
            '却用了这么重的一个词——这种<b>故意把小事说得很大</b>的反差，' +
            '是英美日常幽默最常见的手法。词用"过头"一点，笑点就出来了。',
          contrast: [
            { label: '平淡说法', text: 'I brought someone to help.' },
            { label: '地道说法', text: 'I brought reinforcements.' },
          ],
          examples: [
            { en: "Pizza won't be enough — I brought reinforcements.", zh: '光靠披萨不够，我把救兵也带来了。' },
            { en: "We're losing. Time to call in reinforcements.", zh: '要输了，该叫援军了。' },
          ],
          culture:
            '这类"军事词进日常"的用法在英语里成套存在：' +
            '<b>call in reinforcements</b>（叫援军）、<b>damage control</b>（危机公关/擦屁股）、' +
            '<b>bite the bullet</b>（咬牙硬扛）、<b>in the trenches</b>（在一线苦干）。' +
            '知道它们出身军事，就能感觉到那股夸张的劲儿。',
          swap: {
            scene: '你们组在赶项目，你拉了两个同事来支援',
            say: 'Relax, I brought reinforcements.',
          },
        },

        {
          id: 'p2',
          lineId: 3,
          kind: 'idiom',
          tag: '地道表达',
          phrase: 'the next best thing',
          zh: '退而求其次的最佳选择',
          matchKeys: ['next best', '退而求其次', '次优'],
          headline: '不是「下一个最好的东西」，而是「拿不到最好的，那就这个」',
          why:
            '最理想的选项没了，能找到的<b>第二好</b>——这就是 the next best thing。' +
            'Rachel 想叫的是力气大的 Joey，叫不到，于是带了 Chandler。' +
            '<br><br>真正精彩的是 Ross 的反应：<b>“The next best thing would be Monica!”</b>' +
            '——意思是"就算退而求其次，也该是 Monica，你 Chandler 连第二都排不上"。' +
            '一句话贬了两层，这就是 Friends 台词的密度。',
          contrast: [
            { label: '字面误解', text: '下一个最好的东西' },
            { label: '真实含义', text: '拿不到最理想的，只能选的次优方案' },
          ],
          examples: [
            { en: "Can't fly to Paris this year? A French film is the next best thing.", zh: '今年去不了巴黎？看部法国片就是次优选择了。' },
            { en: "He wasn't my first choice, but he's the next best thing.", zh: '他不是我的首选，但已经是能找到最好的了。' },
          ],
          swap: {
            scene: '想买的球鞋断货，你买了同系列另一双',
            say: "It's not the one I wanted, but it's the next best thing.",
          },
        },

        {
          id: 'p3',
          lineId: 6,
          kind: 'idiom',
          tag: '地道表达',
          phrase: 'I would be offended, but... / freakishly strong',
          zh: '我本该生气，可是……／壮得离谱',
          matchKeys: ['offended', 'freakishly', '壮得', '离谱'],
          headline: '先假装要发火，再自己拆台 —— Chandler 的招牌句型',
          why:
            '<b>① I would be offended, but…</b><br>' +
            '一个「让步式吐槽」：先摆出"我本来该被得罪"的架势，下一秒自己承认对方说得对。' +
            '效果是既接了梗，又显得毫不在意，非常高级的自嘲。<br><br>' +
            '<b>② freakishly</b><br>' +
            'freak 是"怪胎"，freakishly = <b>离谱地、反常地</b>。' +
            '它专门形容"程度不正常"，比 very 生动一百倍。' +
            'freakishly strong / freakishly good / freakishly tall 都是地道搭配。',
          contrast: [
            { label: '平淡说法', text: 'Monica is very strong.' },
            { label: '地道说法', text: 'Monica is freakishly strong.' },
          ],
          examples: [
            { en: "She's freakishly good at math.", zh: '她数学好得不像话。' },
            { en: "I would be offended, but honestly, you're right.", zh: '我本来该不爽，但说实话你没说错。' },
          ],
          pron: {
            shadow: "Y'know, I'd be oh-FEN-did, but...",
            tip: '注意 <b>I would</b> 在口语里几乎一定缩成 <b>I\'d</b>，一个音节带过；offended 的重音在<b>中间</b>那个音节。',
            tokens: [
              { w: "Y'know", weak: true },
              { w: 'I', link: true }, { w: "'d", weak: true },
              { w: 'be', weak: true },
              { w: 'of', weak: true }, { w: 'FEN', stress: true }, { w: 'ded', weak: true },
              { w: 'but', weak: true },
            ],
          },
          swap: {
            scene: '同事吐槽你做 PPT 太慢，你想优雅接梗',
            say: "I would be offended, but you're not wrong.",
          },
        },

        {
          id: 'p4',
          lineId: 11,
          kind: 'idiom',
          tag: '地道表达',
          phrase: 'You certainly think a lot of yourself.',
          zh: '你还挺看得起自己啊。',
          matchKeys: ['think a lot of', '看得起自己', 'certainly'],
          headline: 'think a lot of yourself ≠ 想很多，是「自视甚高」',
          why:
            'think a lot of <i>someone</i> = <b>很看重某人、评价很高</b>。' +
            '所以 think a lot of <b>yourself</b> 就是「自我感觉良好、自视甚高」——一句轻飘飘的吐槽。<br><br>' +
            '<b>笑点在后面两句：</b>Rachel 以为草图上那个魁梧的人形是 Ross 在美化自己，' +
            '结果 Ross 一本正经地说 “No! That’s my arm!”（那不是人，那是我的手臂）—— ' +
            '画面瞬间更荒谬，于是 Chandler 补刀：' +
            '“I thought you just really, <i>really</i> liked your new couch.”',
          contrast: [
            { label: '字面误解', text: '你想得挺多的' },
            { label: '真实含义', text: '你还挺自恋 / 挺看得起自己' },
          ],
          examples: [
            { en: 'You think a lot of yourself, don’t you?', zh: '你还挺自信啊？' },
            { en: 'She thinks a lot of her own writing.', zh: '她对自己的文笔评价很高。' },
          ],
          pron: {
            shadow: "You cer'nly think-a-LOT-uh yourself",
            tip: '<b>实测数据：</b>全句唯一的重音是 <b>lot</b>（音频能量最高）。' +
                 'Certainly 虽然拖了 0.58 秒，但音量很低 —— <b>说得长 ≠ 重读</b>，这点最容易搞错。' +
                 'of 只有 0.12 秒、音量全句最低，弱化到几乎只剩一个 /ə/。' +
                 '开头那个 You 确实存在，只是弱到连 Whisper 有时都识别不出来。',
            tokens: [
              { w: 'You', weak: true, link: true },
              { w: 'Cer', link: true }, { w: 't', swallow: true }, { w: 'ain', weak: true }, { w: 'ly', weak: true },
              { w: 'think', weak: true, link: true },
              { w: 'a', weak: true, link: true },
              { w: 'LOT', stress: true },
              { w: 'of', weak: true },
              { w: 'yourself', weak: true },
            ],
          },
          swap: {
            scene: '朋友说自己是团队里最聪明的',
            say: 'Wow. You certainly think a lot of yourself.',
          },
        },

        {
          id: 'p9',
          lineId: 21,
          kind: 'grammar',
          tag: '语法 · 否定转移',
          phrase: "I don't think we can turn anymore.",
          zh: '我觉得转不动了。',
          matchKeys: ["don't think", '否定转移', 'anymore', '我觉得不'],
          headline: '中文说「我觉得不行」，英语要说「我不觉得行」—— 这一场戏里出现了四次',
          why:
            '注意这一场里反复出现的同一个句型：<br><br>' +
            '· Chandler：I <b>don’t</b> think we can turn anymore.<br>' +
            '· Rachel：I <b>don’t</b> think it’s going to fit.<br>' +
            '· Ross：I <b>don’t</b> think it’s going to pivot anymore.<br>' +
            '· Chandler：I think it’s <b>really stuck</b> now.（这句反过来了，因为后半句是肯定的）<br><br>' +
            '<b>否定转移（negative raising）：</b>英语习惯把 not 提到<b>主句</b>去，' +
            '说 I don’t think + 肯定；中文正好相反，把否定留在<b>后半句</b>：「我觉得<b>不</b>行」。<br>' +
            '所以 <b>I think it can’t work</b> 语法没错，但一听就很不英语；' +
            '地道说法是 <b>I don’t think it can work</b>。<br>' +
            '同样吃这条规则的还有 <b>believe / suppose / expect / imagine</b>：<br>' +
            '· I don’t believe he’s coming.（我觉得他不会来）<br>' +
            '· I don’t suppose you have a charger?（你应该没带充电器吧？）<br><br>' +
            '<b>顺带一个小词：anymore</b><br>' +
            '美式写成一个词，而且<b>只用在否定句和疑问句</b>里：' +
            'We can’t turn <b>anymore</b>. ✅ ／ We can turn anymore. ❌' +
            '（肯定句里要说 We can <b>still</b> turn.）<br>' +
            '它说的是<b>时间上的"不再"</b>，不是数量上的"不再多"——' +
            '数量要用 <b>any more</b>（分写）：I don’t want <b>any more</b> coffee.<br><br>' +
            '<b>为什么这个点值得专门记：</b>它不影响别人听懂你，' +
            '但它是中文母语者最稳定的一处"口音"。改过来之后，你说的英语会立刻自然一档。',
          contrast: [
            { label: '中式直译', text: 'I think it can’t fit.（能懂，但很别扭）' },
            { label: '地道说法', text: 'I don’t think it’s going to fit.' },
          ],
          examples: [
            { en: "I don't think that's a good idea.", zh: '我觉得那不是个好主意。（不说 I think that’s not…）' },
            { en: "I don't suppose you could help me?", zh: '你应该帮不上我吧？（很客气的问法）' },
            { en: "He doesn't live here anymore.", zh: '他不住这儿了。（anymore 只进否定句）' },
          ],
          swap: {
            scene: '评审会上你觉得某个方案行不通',
            say: "I don't think this approach is going to work.",
          },
        },

        {
          id: 'p5',
          lineId: 22,
          kind: 'pron',
          tag: '发音技巧',
          phrase: "I just don't think it's going to fit.",
          zh: '我觉得它真的挤不上去。',
          matchKeys: ['going to fit', 'gonna', "don't think", '挤不上'],
          headline: '听不懂快速英语，八成不是词汇问题，是没适应「压缩」',
          why:
            '这句话里没有一个生词，但正常语速下很难一次听清。' +
            '我把这句的音频切开逐词量过，数据很说明问题：<br><br>' +
            '<b>① 整句 8 个词只用了 1.32 秒。</b><br>' +
            '<b>② 全句只有一个重音：fit</b>（独占 0.36 秒，音量最高）。' +
            '其余 7 个词平均每个只有 0.14 秒 —— 注意 <b>think 并不是重音</b>，' +
            '它反而是被压得最扁的词之一，这跟大多数人的直觉相反。<br>' +
            '<b>③ going to 两个词合起来只有 0.18 秒</b>，物理上根本读不完整 —— ' +
            '所以你听到的一定是 <b>gonna</b>。<br>' +
            '<b>④ don’t 的 t 脱落</b>：后面紧跟 think 的 /θ/，舌位来不及切换，直接省略。<br><br>' +
            '真实入耳的是：<b>I jus’ don’ think it’s gonna FIT</b>。' +
            '知道"整句只有一个词是重的、其余全被压平"这个规律，再听一遍，你会突然"听清"了。',
          pron: {
            shadow: "I jus' don' think it's gonna FIT",
            tip: '<b>实测数据：</b>fit 0.36 秒 / 能量 1.00（全句唯一重音）；' +
                 'think 仅 0.14 秒 / 能量 0.36；going + to 合计 0.18 秒；' +
                 '所有相邻词的间隔都 ≤ 0.02 秒，等于整句连成了一串。' +
                 '先按标记慢读三遍，再按<b>重听一次</b>对比原声。',
            tokens: [
              { w: 'I', weak: true, link: true },
              { w: 'jus', link: true }, { w: 't', swallow: true },
              { w: 'don', link: true }, { w: "'t", swallow: true },
              { w: 'think', weak: true, link: true },
              { w: "it's", weak: true, link: true },
              { w: 'gon', link: true }, { w: 'na', weak: true },
              { w: 'FIT', stress: true },
            ],
          },
          examples: [
            { en: "I don't think so.", zh: '（同样吞 t）听着像 "I don’ think so."' },
            { en: "It's gonna be fine.", zh: '（going to→gonna）"s’gonna be fine."' },
            { en: 'What are you going to do?', zh: '→ "Whaddaya gonna do?" 整句都在缩。' },
          ],
          swap: {
            scene: '搬东西时你判断塞不进去',
            say: "I don't think it's gonna fit.",
          },
        },

        {
          id: 'p6',
          lineId: 24,
          kind: 'culture',
          tag: '文化梗',
          phrase: 'Pivot!',
          zh: '（绕着支点）转过去！',
          matchKeys: ['pivot', '转轴', '中心点'],
          headline: '一个搬沙发的指令，成了全球通用的梗，还是科技圈高频词',
          why:
            '<b>本义：</b>pivot = 绕着一个<b>支点／轴</b>转动。' +
            'Ross 想让他们以沙发的一个角为轴转过楼梯拐角，' +
            '所以他喊的不是"转"，而是一个很具体的物理动作。<br><br>' +
            '<b>今天最常见的用法：</b>在商业和科技语境里，a company <b>pivots</b> = <b>转型、换赛道</b>。' +
            '英文科技新闻里这个词出现频率极高。<br><br>' +
            '<b>剧本里的细节：</b>Ross 越喊越急，' +
            '词都被他喊变形了——剧本原文写的就是 “Pivot! Piv-ot! Piv-et!! Piv-ett!!! Piv-et!”，' +
            '连拼写都在跟着走音。<br>' +
            '而最后 Chandler 那句 “what did you mean when you said <i>pivot</i>?” 是全场最狠的一刀：' +
            '他喊了一路的指令，压根没人听懂。',
          contrast: [
            { label: '剧里的意思', text: '以某个角为轴，转过去' },
            { label: '职场里的意思', text: '（公司/项目）转型、换方向' },
          ],
          culture:
            '这段戏是二十多年不衰的 meme：只要有人搬东西卡在门口，' +
            '评论区一定会刷 <b>“PIVOT!”</b>。' +
            '所以学会这个词不只是记住一个单词，而是能听懂一个梗、接得上话。<br><br>' +
            '顺带一提，硅谷创业圈把"转型"叫 pivot 也正是这个意象：' +
            '<b>一只脚不动，另一只脚换方向</b>——不是掉头重来，而是以既有积累为轴心调整。',
          pron: {
            shadow: 'PI-vət',
            tip: '重音在<b>第一</b>音节，第二个音节弱化成 /ət/。中文母语者很容易读成 "pi-VOT"，那样听着就不对了。',
            tokens: [
              { w: 'PI', stress: true }, { w: 'vot', weak: true },
            ],
          },
          examples: [
            { en: 'Our startup pivoted from hardware to AI.', zh: '我们公司从做硬件转型做 AI 了。' },
            { en: 'Sales are flat. Time to pivot.', zh: '销量不动了，该换个方向了。' },
          ],
          swap: {
            scene: '团队讨论产品方向要不要改',
            say: 'Maybe we should pivot.',
          },
        },

        {
          id: 'p7',
          lineId: 28,
          kind: 'idiom',
          tag: '地道表达',
          phrase: 'You think?!',
          zh: '你才知道？！／这还用说？',
          matchKeys: ['you think', '你才知道'],
          headline: '两个词的反讽，杀伤力比一整句吐槽还大',
          why:
            'Ross 卡了半天才说 “I don’t think it’s going to pivot anymore.”（我看它是转不动了），' +
            'Chandler 和 Rachel <b>同时</b>回了一句 <b>“You think?!”</b><br><br>' +
            '它字面是"你觉得？"，实际是<b>明知故问的反讽</b>：' +
            '「这不是明摆着的吗，你现在才反应过来？」' +
            '中文最接近的是<b>"你才知道？"</b>或<b>"这还用说？"</b><br><br>' +
            '用法要点：<b>一定是升调 + 重读 think</b>，而且通常紧跟在对方说了句废话之后。' +
            '语气可以是好笑的，也可以相当刺人，看关系。',
          contrast: [
            { label: '字面理解', text: '你这么认为吗？' },
            { label: '真实语气', text: '这不明摆着吗，你才发现？' },
          ],
          examples: [
            { en: '"I think we\'re late." — "You think?!"', zh: '"我觉得我们迟到了。" — "你才知道？"' },
            { en: '"That was a bad idea." — "You think?"', zh: '"那主意挺糟的。" — "这还用说？"' },
          ],
          swap: {
            scene: '同事熬到凌晨才说"这个方案好像有问题"',
            say: 'You think?!',
          },
        },

        {
          id: 'p8',
          lineId: 32,
          kind: 'idiom',
          tag: '地道表达',
          phrase: 'Me neither.',
          zh: '我也不 / 我也没想到。',
          matchKeys: ['me neither', 'me too', '我也'],
          headline: '附和否定句要用 Me neither —— 中文母语者最高频的口语错误之一',
          why:
            'Ross 说 “I can’t believe that didn’t work!”（不敢相信居然没成）——这是<b>否定句</b>。' +
            'Rachel 附和时用的是 <b>Me neither</b>，不是 Me too。<br><br>' +
            '规则很简单：<br>' +
            '· 附和<b>肯定</b>句 → Me too. （"I love it." → "Me too."）<br>' +
            '· 附和<b>否定</b>句 → Me neither. （"I don’t like it." → "Me neither."）<br><br>' +
            '中文的"我也是"通吃两种情况，所以我们特别容易在否定句后错说 Me too。' +
            '对方能听懂，但一听就是外国人。<br><br>' +
            '想说得更正式一点，就把 <b>Neither + 助动词 + I</b> 拼出来。' +
            '注意<b>助动词要跟着对方那句走</b>：<br>' +
            '· “I don’t like it.” → <b>Neither do I.</b><br>' +
            '· “I can’t swim.” → <b>Neither can I.</b><br>' +
            '· “I haven’t seen it.” → <b>Neither have I.</b>',
          contrast: [
            { label: '常见错误', text: '"I don’t like durian." — "Me too." ❌' },
            { label: '正确说法', text: '"I don’t like durian." — "Me neither." ✅' },
          ],
          examples: [
            { en: '"I didn’t sleep at all." — "Me neither."', zh: '"我完全没睡。" — "我也没睡。"' },
            { en: '"I can’t swim." — "Neither can I."', zh: '"我不会游泳。" — "我也不会。"（更正式）' },
          ],
          swap: {
            scene: '同事说"我没看懂这个需求"',
            say: 'Me neither. Let’s ask again.',
          },
        },
      ],

      /* --------------------------------------------------------------
       * Round 1 · 裸听后的「整体印象」题
       *   门槛故意放很低：建立印象、留下悬念，不是考试
       *   answer === null 的题不当场判分，留到第 4 轮回声
       * ------------------------------------------------------------ */
      blindQuiz: [
        {
          id: 'b1', type: 'choice',
          q: '这段发生在什么地方？',
          options: ['公寓楼的楼梯间', '家具卖场', '咖啡馆', '办公室走廊'],
          answer: 0,
          hint: '听声音回响 + 脚步声就能判断',
        },
        {
          id: 'b2', type: 'choice',
          q: '他们三个人在干什么？',
          options: ['把一张沙发搬上楼', '组装一个衣柜', '打包搬家', '把车挪出车位'],
          answer: 0,
        },
        {
          id: 'b3', type: 'choice',
          q: '有个词被反复大喊了好几遍。你听到的是哪个？',
          options: ['Pivot', 'People', 'Pilot', '完全没听清'],
          keepLast: 1,
          answer: null,
          reveal: 0,
          pointId: 'p6',
          echoKey: '那个被反复大喊的词',
          note: '这题先不判分 —— 最后一轮我们回来看你第一遍听到的是什么 👀',
        },
        {
          id: 'b4', type: 'text',
          q: '这一遍里，哪句话或哪个说法让你印象最深？（凭印象随手写，中英文都行）',
          placeholder: "比如：pivot / 那句 next best thing / 听不懂但觉得很好笑的那句",
          echo: true,
        },
      ],

      /* --------------------------------------------------------------
       * Round 4 · 验收题
       * ------------------------------------------------------------ */
      finalQuiz: [
        {
          id: 'f1', type: 'choice',
          q: '朋友搬家，你带了两个同事去帮忙。想说"我把救兵带来了"，最地道的是？',
          options: [
            'I brought reinforcements.',
            'I brought some soldiers.',
            'I brought helping people.',
            'I brought my powers.',
          ],
          answer: 0,
          because: 'reinforcements 就是这个场景的固定说法，还自带一点夸张的幽默感。',
        },
        {
          id: 'f2', type: 'fill',
          q: '想去的餐厅满座了，你退而求其次去了隔壁那家。补全这句话：',
          prefix: "It's not my first choice, but it's the",
          suffix: '.',
          answer: ['next best thing'],
          because: 'the next best thing = 拿不到最理想的，能找到的第二好选择。',
        },
        {
          id: 'f3', type: 'choice',
          q: '科技新闻标题写着 "This startup is pivoting to AI"。这里的 pivot 是什么意思？',
          options: ['转型、换方向', '旋转展示商品', '完成融资', '准备上市'],
          answer: 0,
          because: '从"绕轴转动"引申而来：一只脚不动，另一只脚换方向。科技报道里的高频词。',
        },
        {
          id: 'f4', type: 'choice',
          q: '同事说 "I can\'t believe it\'s Friday already."（不敢相信已经周五了）你想附和"我也是"，说哪句？',
          options: ['Me neither.', 'Me too.', 'So do I.', 'Me also.'],
          answer: 0,
          because: '对方是否定句（can\'t），附和要用 Me neither。这是最容易说错的一句。',
        },
      ],
    },

    /* ======================================================================
     * CLIP 2 · Avengers: Age of Ultron —— 谁能举起雷神之锤
     *   刻意和老友记形成对比：这里的重点是「反讽语气 + 文化梗 + 语域反差」，
     *   而不是生活口语。同一套流程，换部剧就换套重点。
     * ==================================================================== */
    {
      id: 'avengers_hammer',
      available: true,
      show: 'Avengers: Age of Ultron',
      showZh: '复仇者联盟 2',
      episode: '2015',
      title: '谁能举起雷神之锤',
      subtitle: 'The Party Scene',
      video: 'raw_avengers.mp4',
      cover: 'cover_avengers.jpg',
      duration: 118,
      /* 片源后面接了「幻视拿锤」的另一场戏，这里只播举锤派对这一段 */
      clipEnd: 118,
      genre: '超级英雄 · 电影',
      level: '中高级 · B2',
      focus: '反讽语气 · 文化梗 · 古英语腔',
      recommendPoints: ['a1', 'a6'],
      /* 这一段是 letterbox 电影画幅，中文字幕和台标分别压在下、上边缘。
       * 用近似纯色的遮罩把两头盖掉 —— 视觉上就像黑边加宽，比渐变干净。 */
      maskStyle: 'solid',
      /* 实测（canvas 逐行扫描）：中文字幕落在 y=385~408（底部 19.8% 以内，
       * 这一段字幕从不折行，所以没有老友记那种两行顶高的问题），
       * 静态台标下沿在 y=73（顶部 15.2%）。两头各留几像素余量即可。 */
      hardsubMask: 23,
      maskOpaque: 22,
      topMask: 16,
      topMaskOpaque: 15.2,
      synopsis:
        '复仇者们在斯塔克大厦开派对。Clint 咬定雷神之锤是个「把戏」，Thor 索性让所有人轮流试一把。' +
        '于是一群超级英雄轮番出丑——而 Steve 让锤子微微动了一下，成了整个系列最漂亮的伏笔。',

      /* Whisper 时间戳 + 剧本校正台词与说话人。
       * 说话人这一栏踩过坑：第一版凭印象把好几句记在了 Thor 头上，
       * 后来拿 IMDb Quotes 和 Movie Quote DB 两个来源逐句对过才发现 ——
       * 损 Clint 的、说 "You bet your ass" 的都是别人。
       * 这直接决定讲解怎么写，所以宁可慢一点也要对。 */
      lines: [
        { id: 1, start: 0.0, end: 1.30, sp: 'Clint', en: "But it's a trick.", zh: '可这就是个把戏。' },
        { id: 2, start: 1.38, end: 2.95, sp: 'Thor', en: "No, no. It's much more than that.", zh: '不不。它可远不止是个把戏。' },
        { id: 3, start: 3.16, end: 6.35, sp: 'Clint', en: '"Whosoever be he worthy shall haveth the power."', zh: '「凡配得上者，皆可拥其神力。」' },
        { id: 4, start: 6.82, end: 8.45, sp: 'Clint', en: "Whatever, man! It's a trick.", zh: '随你怎么说，就是个把戏。' },
        { id: 5, start: 8.98, end: 10.30, sp: 'Thor', en: 'Please, be my guest.', zh: '那请吧，你随意。' },
        { id: 6, start: 11.88, end: 12.55, sp: 'Tony / Clint', en: 'Come on. — Really?', zh: '上啊。——真的？' },
        { id: 7, start: 12.88, end: 13.25, sp: 'Thor', en: 'Yeah.', zh: '来吧。' },
        { id: 8, start: 14.72, end: 15.72, sp: 'Rhodey', en: 'Oh, this is gonna be beautiful.', zh: '哦，这下有好戏看了。' },
        { id: 9, start: 15.80, end: 18.45, sp: 'Tony', en: "Clint, you've had a tough week. We won't hold it against you if you can't get it up.", zh: 'Clint，你这周挺不容易的。你要是举不起来，我们不会怪你的。' },
        { id: 10, start: 19.32, end: 20.75, sp: 'Clint', en: "You know I've seen this before, right?", zh: '你知道我以前见过这场面吧？' },
        { id: 11, start: 24.04, end: 26.35, sp: 'Clint', en: "I still don't know how you do it!", zh: '我还是搞不懂你是怎么做到的！' },
        { id: 12, start: 26.68, end: 27.62, sp: 'Tony', en: 'Smell the silent judgment?', zh: '闻到那股无声的鄙视了吗？' },
        { id: 13, start: 27.78, end: 29.50, sp: 'Clint', en: 'Please, Stark, by all means.', zh: '来吧 Stark，请随意。' },
        { id: 14, start: 32.84, end: 37.55, sp: 'Tony', en: 'Never one to shrink from an honest challenge. It\'s physics.', zh: '我从不回避正当的挑战。这是物理问题。' },
        { id: 15, start: 38.12, end: 41.05, sp: 'Tony', en: 'So, if I lift it, I then rule Asgard?', zh: '那么，我要是举起来了，就统治阿斯加德了？' },
        { id: 16, start: 41.18, end: 41.80, sp: 'Thor', en: 'Yes, of course.', zh: '当然。' },
        { id: 17, start: 42.88, end: 45.90, sp: 'Tony', en: 'I will be reinstituting prima nocta.', zh: '那我要恢复「初夜权」了。' },
        { id: 18, start: 49.56, end: 50.60, sp: 'Tony', en: 'Be right back.', zh: '我马上回来。' },
        { id: 19, start: 58.24, end: 60.60, sp: 'Rhodey / Tony', en: 'Are you even pulling? — Are you on my team?', zh: '你到底有没有在拉？——你到底是不是我这队的？' },
        { id: 20, start: 61.00, end: 62.15, sp: 'Rhodey', en: 'Just represent. Pull!', zh: '出点力就行了，拉啊！' },
        { id: 21, start: 62.22, end: 63.65, sp: 'Tony', en: "All right, let's go.", zh: '好了，来吧。' },
        { id: 22, start: 73.24, end: 74.60, sp: 'Tony', en: 'Go ahead, Steve. No pressure.', zh: '上吧 Steve，别有压力。' },
        { id: 23, start: 77.94, end: 78.80, sp: 'Rhodey', en: 'Come on, Cap.', zh: '加油啊，队长。' },
        { id: 24, start: 91.90, end: 94.80, sp: 'Natasha', en: "Oh, no, no. That's not a question I need answered.", zh: '哦不不。这个问题我并不需要答案。' },
        { id: 25, start: 95.14, end: 97.35, sp: 'Tony', en: "All deference to the Man Who Wouldn't Be King, but it's rigged.", zh: '无意冒犯这位「不愿称王的人」，但这里头有猫腻。' },
        { id: 26, start: 97.66, end: 98.40, sp: 'Clint', en: 'You bet your ass.', zh: '那还真让你说对了。' },
        { id: 27, start: 98.62, end: 100.35, sp: 'Maria Hill', en: 'Steve, he said a bad language word.', zh: 'Steve，他说脏话了。' },
        { id: 28, start: 100.66, end: 101.50, sp: 'Steve', en: 'Did you tell everyone about that?', zh: '你把那事跟所有人都说了？' },
        { id: 29, start: 101.60, end: 103.55, sp: 'Tony', en: "The handle's imprinted, right? Like a security code.", zh: '锤柄上有压印，对吧？就像一道安全码。' },
        { id: 30, start: 103.96, end: 106.95, sp: 'Tony', en: '"Whosoever is carrying Thor\'s fingerprints" is, I think, the literal translation.', zh: '「凡带有索尔指纹者」——我觉得直译过来是这个意思。' },
        { id: 31, start: 107.10, end: 112.10, sp: 'Thor', en: "Yes, well, that's, uh, that's a very, very interesting theory. I have a simpler one.", zh: '嗯，这个……这个理论非常非常有意思。我有个更简单的解释。' },
        { id: 32, start: 114.04, end: 115.10, sp: 'Thor', en: "You're all not worthy.", zh: '你们都不配。' },
      ],

      glossary: {
        trick: { pos: 'n.', zh: '把戏；花招', note: "It's a trick 常用来指\"这里面有机关/骗人的\"" },
        whosoever: { pos: 'pron.', zh: '无论何人（whoever 的古体强调形式）', note: '今天只活在法律条文、圣经、告示牌里；日常同族词只剩 no ... whatsoever' },
        haveth: { pos: '（伪古语）', zh: '并不存在的词形', note: 'have 的古体是 hath；且 shall 后面本该接原形 have —— Clint 故意乱装古腔' },
        worthy: { pos: 'adj.', zh: '配得上的；值得的', note: '锤子铭文里的关键词，后面被 Ultron 接梗，是全片核心意象' },
        guest: { pos: 'n.', zh: '客人', note: 'Be my guest = 请便（表面客气，语气一变就是挑衅）' },
        deference: { pos: 'n.', zh: '敬重；顺从', note: 'with all deference to X = 恕我对 X 不敬，非常正式的书面语' },
        rigged: { pos: 'adj.', zh: '被操纵的；作弊的', note: '选举、比赛、抽奖里的高频词：the game is rigged' },
        physics: { pos: 'n.', zh: '物理（学）', note: "Tony 说 it's physics 意思是\"这纯粹是力学问题，不玄乎\"" },
        represent: { pos: 'v.', zh: '出力；撑场面', note: '这里是俚语用法：至少做做样子、别掉队' },
        imprinted: { pos: 'adj.', zh: '压印的；刻上去的', note: 'imprint 也可指心理上的"深深印刻"' },
        literal: { pos: 'adj.', zh: '字面的', note: 'the literal translation = 直译' },
        shrink: { pos: 'v.', zh: '（+from）回避、往后躲；（本义）缩水', note: 'shrink from a challenge = 面对挑战往后躲，偏书面；口语说 shy away from' },
        honest: { pos: 'adj.', zh: '正当的；不掺假的', note: '这里不是"诚实"：an honest challenge / an honest mistake / an honest day\'s work' },
        reinstituting: { pos: 'v.-ing', zh: '恢复、重新设立（某制度）', note: 'reinstitute 是正式用词，多用于制度、规定、传统' },
        judgment: { pos: 'n.', zh: '评判；（此处）鄙视的眼神', note: 'silent judgment = 不说话但写在脸上的评判，很地道的吐槽用法' },
        even: { pos: 'adv.', zh: '（加强质问）到底、究竟', note: 'Are you even pulling? = 你到底有没有在拉？even 一放进疑问句就带质疑' },
        pressure: { pos: 'n.', zh: '压力', note: 'No pressure. 字面"别有压力"，实际几乎总是反话，等于"全看你了"' },
        tough: { pos: 'adj.', zh: '难熬的；硬气的', note: 'a tough week 是"这周不好过"的固定说法' },
      },

      /* 举手点与精讲点一一对应。台词密集处（94–100s 连着三个）靠前端
       * 「一次只举一只手」的规则自动排队，不会撞在一起。 */
      moments: [
        { at: 6.55, pointId: 'a8', hook: '这句是假古英语，还故意说错了 ✋' },
        { at: 10.20, pointId: 'a1', hook: '这句"请便"其实在挑衅 ✋' },
        { at: 18.35, pointId: 'a2', hook: '表面体贴，实际是双重嘲讽 ✋' },
        { at: 27.50, pointId: 'a10', hook: '"闻到"鄙视？这个动词用错位了 ✋' },
        { at: 37.75, pointId: 'a9', hook: 'shrink from 不是"缩小" ✋' },
        { at: 45.80, pointId: 'a3', hook: '这个拉丁语梗信息量很大 ✋' },
        { at: 94.70, pointId: 'a7', hook: '这句的节奏很典型，值得听两遍 ✋' },
        { at: 97.30, pointId: 'a4', hook: '前半句像开庭，后半句像吐槽 ✋' },
        { at: 98.30, pointId: 'a5', hook: '这句为什么被说成"脏话" ✋' },
        { at: 115.00, pointId: 'a6', hook: '这一个词撑起了整部电影 ✋' },
      ],

      points: [
        {
          id: 'a8',
          lineId: 3,
          kind: 'grammar',
          tag: '语法 · 古英语腔',
          phrase: '"Whosoever be he worthy shall haveth the power."',
          zh: '「凡配得上者，皆可拥其神力。」',
          matchKeys: ['whosoever', 'haveth', 'be he worthy', '古英语', '铭文'],
          headline: '这不是古英语，是"装古英语"——而且 Clint 还故意装错了',
          why:
            'Clint 在这里<b>背锤子上的铭文</b>，用的是一种一听就"很神话"的老派腔调。' +
            '逐个词拆开，你会发现三样东西：<br><br>' +
            '<b>① whosoever = whoever 的加强古体</b><br>' +
            '意思就是"无论是谁"，但语域高得多，今天只活在<b>法律条文、圣经、誓词</b>里' +
            '（Whosoever shall break this law…）。同一家族还有 whatsoever / whensoever / ' +
            'howsoever —— 其中只有 <b>whatsoever</b> 在日常里常见，且几乎只出现在否定句：' +
            '<b>no idea whatsoever</b>（一点头绪都没有）。<br><br>' +
            '<b>② be he worthy = if he be worthy（虚拟语气 + 倒装）</b><br>' +
            '古英语用 <b>be</b> 而不是 is 来表示"假设、未定"，' +
            '还可以把 be 提到主语前，用<b>倒装代替 if</b>。<br>' +
            '这种句式今天几乎只剩几个化石短语，但它们仍然常用，值得认得：<br>' +
            '· <b>be that as it may</b>（即便如此）<br>' +
            '· <b>come what may</b>（无论发生什么）<br>' +
            '· <b>if need be</b>（如果有必要）<br>' +
            '· <b>so be it</b>（那就这样吧）<br>' +
            '句中的 <b>he</b> 也是旧式用法：<b>泛指任何人</b>（法律英语里的通性 he），' +
            '现代英语会改成 they，或者干脆重写成 whoever holds it。<br><br>' +
            '<b>③ haveth 是个不存在的词 —— 这就是笑点</b><br>' +
            '<b>-eth</b> 是古英语<b>第三人称单数</b>的动词词尾（he giveth / he doth / he hath）。' +
            '但这里有两处硬伤：have 的古形是 <b>hath</b>，不是 haveth；' +
            '而且 <b>shall 后面必须接原形</b>，本来就该是 shall <b>have</b>。<br>' +
            '所以 Clint 是<b>一边嘲讽 Thor 那套神话腔，一边随口乱加 -eth</b>，' +
            '连装都没装对 —— 说完他立刻补一句 “Whatever, man! It’s a trick.”（随你怎么说，就是个把戏）。' +
            '这种<b>故意乱说的假古英语</b>英文里有个名字：<b>mock-archaic</b>。',
          contrast: [
            { label: '锤子上的原铭文', text: 'Whosoever holds this hammer, if he be worthy, shall possess the power of Thor.' },
            { label: 'Clint 的走音版', text: 'Whosoever be he worthy shall haveth the power.（语法一锅粥）' },
            { label: '换成现代英语', text: 'Anyone who is worthy can have this power.' },
          ],
          examples: [
            { en: 'Whosoever enters must remove their shoes.', zh: '（告示牌腔）凡入内者须脱鞋。' },
            { en: 'I have no idea whatsoever.', zh: '我一点头绪都没有。（whatsoever 唯一的日常高频用法）' },
            { en: 'Be that as it may, we still have to finish it.', zh: '即便如此，我们还是得把它做完。（同一个古体 be 的化石）' },
            { en: 'I can stay late if need be.', zh: '有必要的话我可以留晚点。' },
          ],
          culture:
            '这句台词埋了一个<b>会在 100 秒后回来的梗</b>。<br><br>' +
            'Tony 举不动锤子之后，给出他的"技术解释"：' +
            '<b>“The handle’s imprinted, right? Like a security code. ‘Whosoever is carrying Thor’s ' +
            'fingerprints’ is, I think, the literal translation.”</b>' +
            '（锤柄上有压印，像一道安全码。「凡带有索尔指纹者」，我觉得直译是这个意思。）<br><br>' +
            '他把 <b>whosoever</b> 这个圣经级别的古词，接上 <b>fingerprints / security code</b> ' +
            '这种最现代的科技词 —— <b>语域反差</b>就是笑点，也是 Tony Stark 全片的说话方式：' +
            '<b>用工程学解释神话</b>。<br><br>' +
            '顺带说一句：这种<b>装古腔</b>在英语娱乐里成套存在，认得出来就够，不必真会用 ——' +
            '古董店招牌上的 <b>Ye Olde Shoppe</b>、游戏台词里的 <b>thou shalt not…</b>、' +
            '<b>verily</b>（"实在地"），都是同一种"我在扮演古人"的信号。',
          swap: {
            scene: '朋友把简单的事说得特别玄，你想学一句这种腔调打趣他',
            say: 'Whosoever be he worthy shall haveth the last cookie.',
          },
        },

        {
          id: 'a1',
          lineId: 5,
          kind: 'idiom',
          tag: '地道表达',
          phrase: 'Be my guest. / By all means.',
          zh: '请便。／请随意。',
          matchKeys: ['be my guest', 'by all means', '请便', '随意'],
          headline: '英语幽默的核心机制：用最客气的话，说最不客气的意思',
          why:
            '这一段里同一个"请"出现了两次，说的人不同、句式不同，味道一模一样：<br><br>' +
            '<b>① Be my guest.</b>（Thor 对 Clint）字面是"当我的客人"，实际就是<b>「请便、你随意」</b>。' +
            'Clint 刚说锤子是个把戏，Thor 就把锤子推过去 ——' +
            '客气话，但意思是"你上啊"。<br>' +
            '<b>② Please, Stark, by all means.</b>（Clint 对 Tony）' +
            'by all means = <b>「当然可以、无论如何请」</b>，比 Be my guest 更正式一点。' +
            '有意思的是这次说的人是<b>刚刚出丑的 Clint</b> ——' +
            '他自己没举起来，转头就把这份"客气"传给了 Tony：<b>你也来试试啊</b>。<br><br>' +
            '两句都是标准的礼貌用语，但放在"你根本举不起来"这个前提下，' +
            '就成了<b>不动声色的挑衅</b>——这正是英语幽默最常用的一招：' +
            '<b>句子越客气，态度越欠</b>。中文里"您请"、"您随意"也能这么用，但英语用得更频繁、更放肆。',
          contrast: [
            { label: '字面理解', text: '请当我的客人 / 用尽一切办法' },
            { label: '真实语气', text: '请便啊（我看你怎么举）' },
          ],
          examples: [
            { en: '"Can I use your charger?" — "Be my guest."', zh: '"能用下你的充电器吗？" — "请便。"' },
            { en: '"May I ask a question?" — "By all means."', zh: '"我能问个问题吗？" — "当然请问。"' },
          ],
          swap: {
            scene: '同事说"这活我来试试"，你其实觉得他搞不定',
            say: 'Be my guest.',
          },
        },

        {
          id: 'a2',
          lineId: 9,
          kind: 'idiom',
          tag: '地道表达',
          phrase: "We won't hold it against you.",
          zh: '我们不会因此怪你的。',
          matchKeys: ['hold it against', 'get it up', '怪你'],
          headline: '一句「体贴」里塞了两层嘲讽',
          why:
            '<b>hold something against someone</b> = <b>因为某件事而怪某人、记恨某人</b>。' +
            '这是个很实用的固定搭配，日常和职场都常用。<br><br>' +
            'Tony 这句话表面上是在体贴 Clint：「你这周挺不容易的，举不起来我们不怪你。」' +
            '但放在语境里，它是<b>双重嘲讽</b>：<br>' +
            '① 提醒大家 Clint 这周刚受了伤、状态很差；<br>' +
            '② <b>can’t get it up</b> —— 字面是"举不起来"，但这个短语在英语里' +
            '几乎默认指男性生理上的"不行"。<br><br>' +
            '这就是漫威台词的典型密度：一句"关心"里埋两个梗。' +
            '而且注意<b>说的人是 Tony 不是 Thor</b> —— Thor 全程只是礼貌地邀请，' +
            '开黄腔的活儿都是 Tony 干的，这很符合两人的人设。',
          contrast: [
            { label: '字面', text: '我们不会拿这件事怪你' },
            { label: '实际', text: '你举不起来我们不怪你（但大家都懂那是什么意思）' },
          ],
          examples: [
            { en: "You were late once — nobody's holding it against you.", zh: '你就迟到过一次，没人跟你计较。' },
            { en: "I hope you don't hold it against me.", zh: '希望你不会因此记恨我。' },
          ],
          culture:
            '英语喜剧里有一整套「表面无辜、实际带荤」的双关，' +
            '典型如 <b>can’t get it up</b>、<b>that’s what she said</b>、<b>size matters</b>。' +
            '它们的笑点全靠<b>说的人一本正经</b>——Tony 用最关切的口气说出来，' +
            '全场笑倒，Clint 却只能硬着头皮上场。' +
            '知道这类梗存在，看剧时就不会一脸茫然地看着全场笑。',
          swap: {
            scene: '朋友把你交代的事忘了，你想说"没关系不怪你"',
            say: "Don't worry, I won't hold it against you.",
          },
        },

        {
          id: 'a10',
          lineId: 12,
          kind: 'idiom',
          tag: '地道表达',
          phrase: 'Smell the silent judgment? / No pressure.',
          zh: '闻到那股无声的鄙视了吗？／别有压力。',
          matchKeys: ['silent judgment', 'smell the', 'no pressure', '鄙视', '压力'],
          headline: '两句最"漫威"的吐槽：一句故意用错感官，一句纯粹是反话',
          why:
            '<b>① Smell the silent judgment?</b>（Tony 说的）<br>' +
            '拆开看每个词都简单，合起来却很难直译。关键在两处：<br>' +
            '<b>judgment</b> 在这里不是"判决"，而是<b>「评判、挑刺的眼光」</b>。' +
            '英语里说 <b>I feel judged</b>（我感觉被审视了）、' +
            '<b>Don’t judge me</b>（别对我有意见）都是这个义项，日常极常用。<br>' +
            '<b>silent judgment</b> = 没人说话，但每个人的表情都在打分 —— ' +
            '就是中文说的<b>"无声的鄙视"</b>。<br>' +
            '而 <b>smell</b> 是故意用错位的：情绪本来是"感觉到"的，' +
            'Tony 偏说"闻到"，把气氛写成了<b>一种能闻见的味道</b>。' +
            '这种<b>把抽象的东西接到感官动词上</b>是英语里成套的玩法：' +
            '<b>I can smell trouble</b>（我嗅到麻烦了）、' +
            '<b>You could taste the tension</b>（那股紧张感几乎能尝到）、' +
            '<b>The silence was deafening</b>（沉默响得刺耳）。<br><br>' +
            '<b>② No pressure.</b>（Tony 对 Steve 说的）<br>' +
            '字面"别有压力"，实际<b>几乎永远是反话</b> ——' +
            '真的没压力就不必提这三个字了。它专门用在' +
            '<b>全场都盯着你、你还非做不可</b>的时刻，是最典型的英式/美式打趣：' +
            '<b>用宽慰的话把压力再加一层</b>。<br>' +
            '同一家族还有 <b>Take your time.</b>（不着急啊 —— 通常正是在催你）、' +
            '<b>Don’t worry about it.</b>（看语气可以是真安慰，也可以是"你完了"）。<br><br>' +
            '这两句都印着漫威台词的共同点：<b>词都认识，意思全在语气里</b>。',
          contrast: [
            { label: '字面', text: '闻一下这个无声的判决 / 不要有压力' },
            { label: '真实语气', text: '看见大家那眼神了吧？／全场都看着你呢' },
          ],
          examples: [
            { en: 'I could smell trouble the moment he walked in.', zh: '他一进门我就嗅到麻烦了。' },
            { en: "Stop judging me — it's just instant noodles.", zh: '别用那种眼光看我，就是碗泡面。' },
            { en: "It's live on stage in front of 500 people. No pressure.", zh: '就在 500 人面前现场演，别紧张啊。（反话）' },
          ],
          swap: {
            scene: '同事要在全公司面前做汇报，你想打趣一句',
            say: "You're up next. No pressure.",
          },
        },

        {
          id: 'a9',
          lineId: 14,
          kind: 'idiom',
          tag: '地道表达',
          phrase: 'Never one to shrink from an honest challenge.',
          zh: '我从不回避正当的挑战。',
          matchKeys: ['shrink from', 'never one to', 'honest challenge', '回避', '退缩'],
          headline: '三个容易看错的地方：省略的主语、shrink 的另一个义项、honest 的另一个意思',
          why:
            'Tony 撸起袖子上场前说了这么一句，短短八个词里有三个考点：<br><br>' +
            '<b>① 开头省掉了 “I’m”</b><br>' +
            '完整是 <b>I’m never one to shrink from…</b>。' +
            '英语里这种<b>省略主语和 be 动词</b>的说法，语气像是在给自己配旁白（或者念自己的简历），' +
            '常见于自夸和自嘲：<b>Always happy to help.</b>（乐意效劳）／' +
            '<b>Never one to complain.</b>（我从不抱怨）。<br><br>' +
            '<b>② (not) one to do sth = 不是那种会做某事的人</b><br>' +
            '这是描述<b>性格</b>的固定句式，比 I don’t… 更有"人设"感：<br>' +
            '· He’s not one to give up.（他不是会放弃的人）<br>' +
            '· She’s one to speak her mind.（她是个有话直说的人）<br><br>' +
            '<b>③ shrink from ≠ 缩小</b><br>' +
            'shrink 最熟的义项是"缩水、变小"（My shirt shrank.），' +
            '但 <b>shrink from something</b> 是另一个义项：<b>因为害怕、不情愿而回避、往后躲</b>' +
            '（想象一下身体本能地往后一缩）。它偏<b>正式书面</b>，搭配也很固定：' +
            'shrink from <b>a challenge / responsibility / duty / the truth</b>，' +
            '后面接动词要用 -ing：<b>shrink from telling him</b>。<br>' +
            '换成口语就是 <b>shy away from</b>；反过来说是 <b>rise to the challenge</b>（迎难而上）。<br><br>' +
            '<b>④ honest 在这里不是"诚实"</b><br>' +
            '而是<b>"正当的、不掺假的"</b>：an honest challenge = 一场明明白白、不耍花招的较量。' +
            '同一个意思还有 <b>an honest mistake</b>（无心之失）、' +
            '<b>an honest day’s work</b>（实实在在干一天活）、<b>honest money</b>（干净钱）。<br><br>' +
            '连起来的味道是：<b>「正当的挑战，我从来不躲。」</b>' +
            '说得像颁奖致辞，紧接着一句 <b>“It’s physics.”</b>（这是物理问题）把神话拉回工程学 ——' +
            '然后他就没举起来。',
          contrast: [
            { label: '字面拆错', text: '从不因为一个诚实的挑战而缩小' },
            { label: '真实含义', text: '正当的较量我从不回避（说得很正式，其实在自夸）' },
          ],
          examples: [
            { en: "He never shrinks from a difficult conversation.", zh: '难谈的话他从不回避。' },
            { en: "Don't shrink from asking for help.", zh: '别不敢开口求助。（from 后面接 -ing）' },
            { en: "I'm not one to complain, but this is cold.", zh: '我不是爱抱怨的人，但这真的凉了。' },
            { en: 'It was an honest mistake.', zh: '那是无心之失。（honest = 不掺假的，不是"诚实的"）' },
          ],
          swap: {
            scene: '领导问谁来接这个难做的项目，你想接得体面一点',
            say: "I'm never one to shrink from a challenge — I'll take it.",
          },
        },

        {
          id: 'a3',
          lineId: 17,
          kind: 'culture',
          tag: '文化梗',
          phrase: 'reinstituting prima nocta',
          zh: '恢复「初夜权」',
          matchKeys: ['prima nocta', '初夜'],
          headline: '两个词的拉丁语，背后是一整套「统治者特权」的历史梗',
          why:
            'Tony 先确认规则：「如果我举起锤子，就统治阿斯加德了？」Thor 说「当然」。' +
            'Tony 立刻接：<b>“I will be reinstituting prima nocta.”</b><br><br>' +
            '<b>reinstitute</b> = 重新设立、恢复（某项制度），正式用词。<br>' +
            '<b>prima nocta</b>（字面"第一夜"）指传说中中世纪领主对领地内新婚女子的' +
            '「初夜权」。<br>' +
            '<b>一个语言细节：</b>严格的拉丁语说法是 <b>ius primae noctis</b>（"初夜之权"），' +
            'prima nocta 其实是《勇敢的心》带火的通俗版 —— Tony 用的正是大家耳熟的这个版本，' +
            '这也说明这个梗完全是靠电影传播的。<br><br>' +
            '所以这句话的意思是：「等我当了阿斯加德的王，我第一件事就是把初夜权恢复了。」' +
            '——用一个<b>荒谬的古代特权</b>来开黄腔，是 Tony Stark 式幽默的标准配方：' +
            '<b>越正式的词 + 越离谱的内容 = 越好笑</b>。',
          culture:
            '这个梗的流行几乎全靠一部电影：《勇敢的心》(Braveheart, 1995) 里，' +
            '英王爱德华一世宣布对苏格兰行使 prima nocta，成了全片最激起观众愤怒的情节。' +
            '（史学界普遍认为这项"权利"更多是传说而非普遍实行的制度。）<br><br>' +
            '对英语学习者的意义：漫威台词里塞满了这类<b>只用两三个词就调用一整个文化背景</b>的引用。' +
            '你不查根本听不出笑点在哪 —— 而查过一次，就再也不会忘。',
          contrast: [
            { label: '字面', text: '我将重新设立"第一夜"' },
            { label: '实际', text: '我当了王，第一件事就是恢复领主初夜权（开黄腔）' },
          ],
          examples: [
            { en: 'The school is reinstituting the dress code.', zh: '学校要恢复着装规定了。' },
          ],
          swap: {
            scene: '你被推举当了小组长，想开个玩笑立"威"',
            say: "First order of business: I'll be reinstituting the coffee run.",
          },
        },

        {
          id: 'a4',
          lineId: 25,
          kind: 'idiom',
          tag: '地道表达',
          phrase: "All deference to..., but it's rigged.",
          zh: '恕我不敬……但这里头有猫腻。',
          matchKeys: ['deference', 'rigged', '猫腻', '作弊'],
          headline: '把最正式的书面语和最口语的吐槽拼在一句里，笑点就出来了',
          why:
            '<b>with all deference to X</b>（这里省略成 all deference to X）= ' +
            '<b>「恕我对 X 不敬 / 无意冒犯 X」</b>，是极正式的书面表达，' +
            '常用在学术、法庭、议会里，后面必然接一句反驳。<br>' +
            '同类还有 <b>with all due respect</b>（恕我直言）—— 记住一个规律：' +
            '<b>凡是这么客气地开头，后半句一定是要打脸的</b>。<br><br>' +
            '<b>rigged</b> = <b>被操纵的、作弊的</b>，口语程度很高（a rigged election / the game is rigged）。<br><br>' +
            'Tony 把这两个极端拼在一起：前半句像在议会发言，后半句像在酒吧抱怨。' +
            '<b>语域反差</b>本身就是笑点 —— 这是 Tony Stark 说话方式的精髓。',
          contrast: [
            { label: '前半句语域', text: '极正式（法庭 / 议会腔）' },
            { label: '后半句语域', text: '极口语（酒吧抱怨腔）' },
          ],
          examples: [
            { en: "With all due respect, I think that's the wrong call.", zh: '恕我直言，我觉得这个决定不对。' },
            { en: 'The whole competition was rigged.', zh: '整个比赛都是做了局的。' },
          ],
          culture:
            '顺带一个小引用：Tony 管 Thor 叫 <b>“the Man Who Wouldn’t Be King”</b>，' +
            '这是在戏仿吉卜林的小说《The Man Who <i>Would</i> Be King》（《执迷不悟》）。' +
            '把 would 改成 wouldn’t，一个词就把 Thor 那种"我本可称王却不在意"的姿态挖苦了一遍。',
          swap: {
            scene: '会上你要反驳领导的方案',
            say: "With all due respect, I think there's a problem here.",
          },
        },

        {
          id: 'a5',
          lineId: 26,
          kind: 'idiom',
          tag: '地道表达',
          phrase: 'You bet your ass.',
          zh: '那你还真说对了。／那当然。',
          matchKeys: ['you bet', 'bad language', '脏话'],
          headline: '同样是「那当然」，语域差一级，后果就差一级',
          why:
            'Tony 说锤子有猫腻（it’s rigged），<b>Clint 立刻接了一句 “You bet your ass.”</b>' +
            '——「那还真让你说对了」。<br><br>' +
            '<b>You bet.</b> 本身就是很地道的「那当然、没问题」。' +
            '加上 <b>your ass</b> 之后强度拉满，但也从<b>随意</b>变成了<b>轻度粗口</b>。<br><br>' +
            '一个语域阶梯，建议记住：<br>' +
            '· <b>Of course.</b> — 中性，任何场合<br>' +
            '· <b>You bet.</b> — 随意、朋友之间<br>' +
            '· <b>You bet your ass.</b> — 粗、带劲，只在熟人和非正式场合<br><br>' +
            '<b>笑点在下一句：</b>Maria Hill 立刻说 “Steve, he said a bad language word.”' +
            '（Steve，他说脏话了。）—— 这是在拿 Steve 的"1940 年代老古板"人设开玩笑：' +
            '<b>本片开场</b>的战斗里，Cap 听到有人骂了一句，脱口纠正了一声 ' +
            '<b>“Language!”</b>（注意用词！），此后被全队取笑了一整部电影。' +
            '于是现在只要有人说脏话，大家就<b>条件反射地去告状给 Steve 听</b>。<br>' +
            '注意 Maria Hill 连"脏话"都不肯直说，用了 <b>a bad language word</b> ' +
            '这种<b>幼儿园老师式</b>的绕口说法 —— 这本身就是在模仿 Cap 的口吻。<br>' +
            'Steve 那句 “Did you tell everyone about that?”（你跟所有人都说了？）' +
            '是<b>对着 Tony 说的</b> —— 他一听就知道是谁把这事传开的。',
          contrast: [
            { label: '中性', text: 'Of course. / Definitely.' },
            { label: '这句的位置', text: '粗口边缘，熟人场合专用' },
          ],
          examples: [
            { en: '"Are you coming?" — "You bet."', zh: '"你来吗？" — "那当然。"' },
            { en: '"Was it worth it?" — "You bet your ass it was."', zh: '"值得吗？" — "太值了。"' },
          ],
          pron: {
            shadow: "y'bet-yer-ASS",
            tip: '<b>实测数据：</b>四个词里 <b>ass 是唯一重音</b>（能量 1.00、时长 0.30 秒），' +
                 '前面 You / bet / your 全是弱读 —— 其中 <b>bet 只有 0.06 秒</b>，几乎一闪而过。' +
                 '这就是为什么听起来像一个词：<b>y’bet’yer-ASS</b>。',
            tokens: [
              { w: 'You', weak: true, link: true },
              { w: 'bet', weak: true, link: true },
              { w: 'your', weak: true, link: true },
              { w: 'ASS', stress: true },
            ],
          },
          swap: {
            scene: '好朋友问"这事你真干了？"，你想强调"那当然"',
            say: 'You bet.',
          },
        },

        {
          id: 'a6',
          lineId: 32,
          kind: 'culture',
          tag: '文化梗',
          phrase: "You're all not worthy.",
          zh: '你们都不配。',
          matchKeys: ['worthy', 'not worthy', '不配'],
          headline: '一个词撑起整部电影：worthy 从玩笑变成威胁',
          why:
            '<b>worthy</b> = <b>配得上的、够格的</b>。它是锤子铭文里的关键词：' +
            '「凡<b>配得上</b>者，皆可拥其神力」—— 也就是开场 Clint 阴阳怪气背的那句。<br><br>' +
            'Thor 单手把锤子转了个圈，然后说 “You’re all not worthy.” ——' +
            '表面是"你们都不够格"，实际就是<b>朋友之间的炫耀式吐槽</b>，' +
            '相当于中文"就你们这样，还差得远呢"。<br><br>' +
            '<b>语法上值得注意：</b>标准英语会说 “None of you are worthy.”' +
            'Thor 偏偏把 <b>not 放在 all 后面</b> —— “You’re all not worthy.”<br>' +
            '这不是古英语，也不是错句，而是<b>逐个点名式的否定</b>：' +
            'None of you… 是把你们当一整团否掉，而 You’re all not worthy 更像' +
            '<b>「你们每一个，都不配」</b>，一个个数过去。' +
            '配上他刚炫完那一手，这个别扭的语序反而正是笑点所在。',
          contrast: [
            { label: '标准说法', text: 'None of you are worthy.（把你们当一团否掉）' },
            { label: 'Thor 的说法', text: "You're all not worthy.（你们每一个，都不配）" },
          ],
          culture:
            '这句台词是全片最漂亮的转折支点。<br><br>' +
            'Thor 说完全场哄笑，气氛正好 —— 下一秒 Ultron 就爬进来，' +
            '把同一个词捡起来还给他们：<b>“Worthy… No. How could you be worthy? You’re all killers.”</b>' +
            '（配得上？不。你们怎么可能配得上？你们全是杀人犯。）<br><br>' +
            '同一个 worthy，<b>从朋友间的玩笑变成了敌人的指控</b>，' +
            '派对气氛一秒转为全片主线。<br><br>' +
            '还有个更长的伏笔：这一段里 <b>Steve 让锤子微微动了一下</b>，Thor 的表情立刻变了。' +
            '四年后《终局之战》里 Cap 举起锤子，观众之所以会疯，' +
            '就是因为这个铺垫早在这场派对上埋好了。',
          examples: [
            { en: "He's not worthy of your trust.", zh: '他不值得你信任。' },
            { en: 'This project is worthy of attention.', zh: '这个项目值得关注。' },
          ],
          swap: {
            scene: '你赢了一局游戏，想跟朋友嘴一句',
            say: 'You are all not worthy.',
          },
        },

        {
          id: 'a7',
          lineId: 24,
          kind: 'pron',
          tag: '发音技巧',
          phrase: "That's not a question I need answered.",
          zh: '这个问题我并不需要答案。',
          matchKeys: ['not a question', 'need answered'],
          headline: '英语重音不是均匀分布的 —— 它跟着「信息焦点」走',
          why:
            '这句话是理解英语节奏的好例子。我把音频逐词量过：<br><br>' +
            '<b>重的三个词：no（能量 1.00）、not（0.95）、question（0.77）</b><br>' +
            '<b>轻的三个词：a（0.34）、need（0.26）、answered（0.35）</b><br><br>' +
            '注意 <b>need 和 answered 明明是实义词，却被压得最轻</b>。' +
            '原因是：Natasha 要强调的是<b>「这不是个问题」</b>这件事 ——' +
            '「我需要答案」属于顺带说完的已知信息，所以整句后半段一路滑过去。<br><br>' +
            '这就是英语节奏的核心：<b>重音落在你想强调的信息上，其余全部压平</b>。' +
            '中文母语者最常见的问题是<b>每个词都读得一样重</b>，' +
            '听起来就有一种"逐字念稿"的感觉，也导致听真人说话时抓不到重点。<br><br>' +
            '另外全句相邻词间隔都 ≤ 0.02 秒 —— <b>not a question</b> 连成一串，' +
            'a 弱化到只剩一个 /ə/，听着像 <b>“NOT-uh-QUESTION”</b>。<br><br>' +
            '<b>顺便说一个容易看漏的语法点：</b>为什么是 <b>need answer<u>ed</u></b> 而不是 need to answer？<br>' +
            '因为这里用的是 <b>need + 宾语 + 过去分词</b>（＝ need something <b>done</b>）：' +
            '<b>「我需要（别人／某种方式）把它做掉」</b>，动作不是我做的。' +
            '整句还原是 a question <b>that I need (to be) answered</b> —— ' +
            '问题是"被回答"，所以用过去分词。<br>' +
            '这个结构日常极常用，而且 have / get / want 都能这么接：<br>' +
            '· I need this <b>fixed</b> today.（今天就得把这个修好）<br>' +
            '· I had my hair <b>cut</b>.（我剪了头发 —— 别人给我剪的）<br>' +
            '· I want it <b>done</b> by Friday.（周五之前给我做完）<br>' +
            '对比一下就清楚：I need to answer = <b>我</b>要去回答；' +
            'I need it answered = 我要<b>它被</b>回答。',
          pron: {
            shadow: "Oh NO no, that's NOT-uh-QUESTION I need answered",
            tip: '<b>练法：</b>先只把 no / not / question 三个词读重，其余全部含糊带过，' +
                 '你会发现听起来突然"像了"。再按<b>重听一次</b>对比 Natasha 的原声。',
            tokens: [
              { w: 'that\'s', weak: true, link: true },
              { w: 'NOT', stress: true, link: true },
              { w: 'a', weak: true, link: true },
              { w: 'QUES', stress: true }, { w: 'tion', weak: true, link: true },
              { w: 'I', weak: true, link: true },
              { w: 'need', weak: true, link: true },
              { w: 'answered', weak: true },
            ],
          },
          examples: [
            { en: "That's not a problem I can solve.", zh: '（同样结构）这不是我能解决的问题。' },
            { en: "That's not a risk I'm willing to take.", zh: '这不是我愿意承担的风险。' },
          ],
          swap: {
            scene: '有人问了个你不想回答的问题',
            say: "That's not a question I need answered.",
          },
        },
      ],

      blindQuiz: [
        {
          id: 'b1', type: 'choice',
          q: '这段发生在什么场合？',
          options: ['一场室内派对', '战斗现场', '实验室做实验', '飞机机舱里'],
          answer: 0,
          hint: '听背景音：有音乐、玻璃杯碰撞和很多人的笑声',
        },
        {
          id: 'b2', type: 'choice',
          q: '这群人在做什么？',
          options: ['轮流试着举起一把锤子', '比赛掰手腕', '拆一台机器', '玩牌'],
          answer: 0,
        },
        {
          id: 'b3', type: 'choice',
          q: '最后那个金发大个子说了一句话结束全场。他说的关键词你听到的是？',
          options: ['worthy', 'worried', 'working', '完全没听清'],
          keepLast: 1,
          answer: null,
          reveal: 0,
          pointId: 'a6',
          echoKey: 'Thor 最后那个词',
          note: '这题先不判分 —— 最后一轮我们回来看你第一遍听到的是什么 👀',
        },
        {
          id: 'b4', type: 'text',
          q: '这一遍里，哪句话或哪个说法让你印象最深？（凭印象随手写，中英文都行）',
          placeholder: '比如：be my guest / 那句拉丁语 / 说脏话被告状那段',
          echo: true,
        },
      ],

      finalQuiz: [
        {
          id: 'f1', type: 'choice',
          q: '朋友问"能借下你的充电器吗"，你想说"请便"，最地道的是？',
          options: ['Be my guest.', 'Please be guest.', 'You are my guest.', 'Be my customer.'],
          answer: 0,
          because: 'Be my guest 就是"请便"的固定说法；语气一变还能表示"你试试看啊"的挑衅。',
        },
        {
          id: 'f2', type: 'fill',
          q: '一场比赛明显有猫腻，你想说"整件事就是做了局的"。补全这句：',
          prefix: 'The whole thing was',
          suffix: '.',
          answer: ['rigged'],
          because: 'rigged = 被操纵的、作弊的。a rigged election / the game is rigged 都是高频搭配。',
        },
        {
          id: 'f3', type: 'choice',
          q: 'Clint 说完 "You bet your ass"，Maria Hill 立刻说 "Steve, he said a bad language word"。这句话好笑在哪？',
          options: [
            '在拿 Steve「1940 年代老古板、听不得脏话」的人设开玩笑',
            '因为 Thor 说错了单词',
            '因为 Steve 是他们的队长，必须管纪律',
            '因为这句话在美国是严重的侮辱',
          ],
          answer: 0,
          because: 'Cap 在本片开场因为纠正别人说脏话（"Language!"）被全队笑了一整部电影，之后队友就条件反射地"告状给 Steve 听"。',
        },
        {
          id: 'f4', type: 'choice',
          q: '有人开口说 "With all due respect, ..."。你应该预期他接下来要？',
          options: ['提出反驳或不同意见', '表达真诚的感谢', '请求你帮个忙', '结束这次谈话'],
          answer: 0,
          because: '这类极客气的开场（all deference to / with all due respect）后面几乎一定接反驳 —— 越客气，越要打脸。',
        },
        {
          id: 'f5', type: 'choice',
          q: 'Tony 上场前说 "Never one to shrink from an honest challenge."。他在说什么？',
          options: [
            '正当的挑战我从不回避',
            '我从不因为挑战而降低标准',
            '我讨厌不诚实的对手',
            '这个挑战让我有点紧张',
          ],
          answer: 0,
          because: 'shrink from = 因害怕/不情愿而回避（不是"缩小"）；honest 在这里是"正当的、不掺假的"。开头还省略了 I’m。',
        },
        {
          id: 'f6', type: 'choice',
          q: 'Clint 背铭文时说 "shall haveth the power"。关于 haveth，下面哪句对？',
          options: [
            '他在装古英语，而且装错了 —— have 的古体是 hath，shall 后面也该接原形',
            '这是标准古英语，语法完全正确',
            'haveth 是 have 的英式拼法',
            '这是字幕组的拼写错误',
          ],
          answer: 0,
          because: '-eth 是古英语第三人称单数词尾（he hath / he doth），而 shall 后面必须接原形 have。Clint 是故意乱装古腔（mock-archaic），这正是笑点。',
        },
      ],
    },

    /* ======================================================================
     * 占位卡：说明「换一部剧只是换一份数据」
     * ==================================================================== */
    {
      id: 'the_office',
      available: false,
      show: 'The Office',
      showZh: '办公室',
      episode: 'S2E1',
      title: '（示例）职场尴尬现场',
      subtitle: 'Coming soon',
      cover: null,
      duration: 0,
      genre: '伪纪录片',
      level: '中级 · B1',
      focus: '职场用语 · 冷幽默',
      soonNote: '演示用占位：你在看什么，它就陪你学什么。',
    },
    {
      id: 'local_import',
      available: false,
      isImport: true,
      show: '本地视频',
      showZh: '导入你自己的片段',
      title: '任何一部剧都可以',
      subtitle: 'Import your own clip',
      cover: null,
      duration: 0,
      genre: '你的片单',
      level: '自动识别',
      focus: '兴趣驱动',
      soonNote: '真实产品里，你正在看的任何片子都能被接进来。这个 Demo 只开放了老友记这一段。',
    },
  ],
};
