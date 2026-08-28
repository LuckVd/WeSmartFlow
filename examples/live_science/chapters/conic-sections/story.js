/* 知识之境 · 篇章数据（由工厂生成） */
window.STORY_DATA = {
 "META": {
  "title": "圆锥曲线 · 两千三百年的六次重生",
  "subtitle": "",
  "guide_name": "曲线之灵",
  "cover": "prologue.png"
 },
 "STORY": [
  {
   "id": "prologue",
   "img": "assets/prologue.png",
   "eraEn": "Beyond Time",
   "eraTitle": "序章 · 曲线之灵",
   "dialogues": [
    {
     "who": "？？？",
     "text": "……你来了。别害怕。这里是<b class=\"em\">知识之境</b>——一切知识尚未被写下之前的地方。",
     "audio": "../../assets/audio/conic-sections/prologue_dlg_0.wav"
    },
    {
     "who": "曲线之灵",
     "text": "我是被人类追逐了两千三百年的存在。有人说我是几何的残渣，有人说我是天空的语法，有人把我写进方程，有人用我捕捉星光。",
     "audio": "../../assets/audio/conic-sections/prologue_dlg_1.wav"
    },
    {
     "who": "曲线之灵",
     "text": "想真正认识我吗？那就回到过去——回到每一个\"我还没有被理解\"的时代。<b class=\"em\">他们看不见你，但能听见你的问题。</b>",
     "audio": "../../assets/audio/conic-sections/prologue_dlg_2.wav"
    },
    {
     "who": "曲线之灵",
     "text": "在每个时代，你都可以<b class=\"em\">亲手做他们的实验、读他们的数据</b>——别只做旁观者。",
     "audio": "../../assets/audio/conic-sections/prologue_dlg_3.wav"
    },
    {
     "who": "你",
     "text": "（你握紧了手心的微光）……带我回去吧。",
     "audio": "../../assets/audio/conic-sections/prologue_dlg_4.wav"
    },
    {
     "who": "曲线之灵",
     "text": "第一站，公元前 350 年，雅典。有个年轻人，正在为一个\"不可能\"的问题发疯。",
     "audio": "../../assets/audio/conic-sections/prologue_dlg_5.wav"
    }
   ],
   "choice": null,
   "interact": null,
   "bridge": null,
   "card": null
  },
  {
   "id": "menaechmus",
   "img": "assets/menaechmus.png",
   "eraEn": "350 B.C. · Athens",
   "eraTitle": "公元前350年 · 雅典",
   "briefing": [
    {
     "title": "神谕",
     "text": "公元前 430 年左右，雅典爆发大瘟疫。人们求问德尔斐神谕，得到的答复是：把阿波罗的<b class=\"em\">立方体祭坛体积加倍</b>，瘟疫才会停止。<br><br>这就是数学史上三大作图难题之一——<b class=\"em\">倍立方问题</b>。"
    },
    {
     "title": "三次方的陷阱",
     "text": "先看清楚问题有多狡猾：<span class=\"formula-line\">边长 ×2 → 体积 ×8（因为 2³ = 8）</span>要让体积恰好 ×2，边长必须变成——<span class=\"formula-line\">k³ = 2，即 k = ∛2 ≈ 1.2599…</span>一个写不完、也画不出来的数。"
    },
    {
     "title": "尺规的极限",
     "text": "当时的几何只允许两样工具：<b class=\"em\">直尺和圆规</b>。它们能做加减乘除、能开平方——但<b class=\"em\">永远够不到立方根</b>。<br><br>这一点当时没人能证明，直到两千年后的 1837 年，Wantzel 才严格证明：尺规作图不可能作出 ∛2。雅典最好的工匠们三年又三年地失败——他们不是不够聪明，是<span class=\"violet\">工具从根上就够不到</span>。"
    },
    {
     "title": "换维度的思路",
     "text": "梅内克缪斯的想法石破天惊：<b class=\"em\">画不出这个长度，能不能让两条曲线的交点\"撞\"出它？</b><br><br>他后来的构造是这样的——两条抛物线联立：<span class=\"formula-line\">x² = ay 与 y² = 2ax → x³ = 2a³</span>交点的横坐标，恰好是 ∛2·a。<b class=\"em\">一个作图问题，变成了\"曲线相交\"问题。</b>但那个时代还没有人能随意生产新曲线。他需要一个源源不断的\"曲线工厂\"——<span class=\"violet\">圆锥</span>。"
    }
   ],
   "dialogues": [
    {
     "who": "旁白",
     "text": "柏拉图学园外的露台上，暮色四合。一个年轻人对着满桌碎裂的陶片发呆，指节捏得发白。",
     "audio": "../../assets/audio/conic-sections/menaechmus_dlg_0.wav"
    },
    {
     "who": "梅内克缪斯",
     "text": "又是错的……边长加倍，体积变成八倍。那要让祭坛体积<b class=\"em\">恰好加倍</b>，边长到底是多少？",
     "audio": "../../assets/audio/conic-sections/menaechmus_dlg_1.wav"
    },
    {
     "who": "你",
     "text": "（你想起幕前铺垫里的那个数）……是 ∛2 倍。但尺规画不出立方根。",
     "audio": "../../assets/audio/conic-sections/menaechmus_dlg_2.wav"
    },
    {
     "who": "梅内克缪斯",
     "text": "你连这个都摸到了？祭司们只会重复神谕，工匠们只会重复失败。我缺的不是手艺——是<b class=\"em\">新的几何对象</b>。",
     "audio": "../../assets/audio/conic-sections/menaechmus_dlg_3.wav"
    },
    {
     "who": "梅内克缪斯",
     "text": "等等……尺规，尺规。平面上的规矩，凭什么解开空间的命令？",
     "audio": "../../assets/audio/conic-sections/menaechmus_dlg_4.wav"
    }
   ],
   "choice": {
    "prompt": "尺规从根上够不到立方根。你会建议他<span class=\"mark\">怎么破局</span>？",
    "options": [
     {
      "t": "继续磨练尺规技巧——雅典最好的工匠都用尺规",
      "d": 5,
      "r": "我试了三年……不。尺规能开平方，却永远开不了立方——这条路从根上就是断的。（他的目光落到案几的圆锥模型上）等等，你刚才在看它，对吗？",
      "audio": "../../assets/audio/conic-sections/menaechmus_opt_0.wav"
     },
     {
      "t": "拿起案上的圆锥模型：用平面去切它，让两条切口曲线相交出 ∛2",
      "d": 20,
      "r": "切……圆锥？让切口曲线相交——x²=ay 遇上 y²=2ax，交点处 x³=2a³……<b>这就是倍立方！</b>一条从未有人见过的曲线，替尺规做完了做不到的事！",
      "audio": "../../assets/audio/conic-sections/menaechmus_opt_1.wav"
     },
     {
      "t": "去德尔斐，再问一次神谕",
      "d": 5,
      "r": "神只会重复同一句话。不，等等——你刚才的眼神……你注意到了案上的圆锥，对吗？",
      "audio": "../../assets/audio/conic-sections/menaechmus_opt_2.wav"
     }
    ]
   },
   "interact": {
    "type": "volume-cube",
    "title": "倍立方：亲手量一量\"不可能\"",
    "intro": "在梅内克缪斯切开圆锥之前，先体会他的绝望——拖动滑块改变祭坛边长，<span class=\"em\">让体积恰好变成 2 倍</span>。然后想想：为什么尺规永远做不到？"
   },
   "afterChoice": [
    {
     "who": "梅内克缪斯",
     "text": "平面斜着切过圆锥，切口闭合、比圆扁、却完美对称……后来的人会叫它——<b class=\"em\">椭圆</b>。倍立方需要的两条比例中项，就在两条这样的曲线相交之处！",
     "audio": "../../assets/audio/conic-sections/menaechmus_after_0.wav"
    },
    {
     "who": "曲线之灵",
     "text": "（低语）你已经亲手摸到了 ∛2 ≈ 1.2599。记住：<b class=\"em\">当平面的工具不够时，他到空间里去找答案。</b>",
     "audio": "../../assets/audio/conic-sections/menaechmus_after_1.wav"
    }
   ],
   "bridge": {
    "textbook": "人教A版 · 选择性必修第一册 · 第三章章引言",
    "mapping": [
     "梅内克缪斯的\"圆锥的切口\" → 课本章首：<span class=\"em\">用平面截圆锥，得到椭圆、抛物线、双曲线</span>——三类曲线同出一源",
     "倍立方需要的 ∛2 → 用<span class=\"em\">曲线交点解方程</span>的几何思想：方程的根可以是\"图形的交点\"，这是解析几何最古老的火种"
    ],
    "quiz": {
     "q": "小试牛刀：用一个平面去截一个圆锥，得到的截口曲线不可能是以下哪种？",
     "options": [
      "椭圆",
      "抛物线",
      "双曲线",
      "三次曲线"
     ],
     "answer": 3,
     "explain": "平面截圆锥只能得到椭圆、抛物线、双曲线（及退化情形）。这正是它们统称<span class=\"em\">\"圆锥曲线\"</span>的原因——2300 年前梅内克缪斯切的那一刀，就是你课本第三章的标题。"
    }
   },
   "card": {
    "title": "圆锥曲线的诞生",
    "text": "约公元前350年，梅内克缪斯为破解\"倍立方问题\"，用平面切割圆锥，得到人类历史上第一批圆锥曲线。关键思想：当既有工具失效时，升维寻找新对象。",
    "formula": "倍立方：x³ = 2a³  →  ∛2 落在两条圆锥曲线的交点",
    "textbook": "人教A版 选必一 · 第三章引言"
   }
  },
  {
   "id": "apollonius",
   "img": "assets/apollonius.png",
   "eraEn": "200 B.C. · Alexandria",
   "eraTitle": "公元前200年 · 亚历山大图书馆",
   "briefing": [
    {
     "title": "一百五十年后的碎片",
     "text": "梅内克缪斯之后一百五十年，欧几里得写出了《几何原本》，几何学成了显学。但圆锥曲线的研究还是一地碎片：这个人用竖直圆锥切出抛物线，那个人用倾斜圆锥切出椭圆——<b class=\"em\">每个人都得先造一个特定的圆锥，才能得到想要的曲线</b>。<br><br>没有人问过那个最朴素的问题：<span class=\"violet\">这些曲线，彼此之间到底是什么关系？</span>"
    },
    {
     "title": "图书馆里的那个人",
     "text": "亚历山大图书馆，古代世界的学术心脏。阿波罗尼奥斯在这里做出了改变一切的判断：<b class=\"em\">换圆锥是作弊，换切割的角度才是本质。</b><br><br>他要用同一个双圆锥、只改变切面角度，把三种曲线统一起来——并写成八卷书。他不知道自己正在给一千八百年后的天空立法。"
    }
   ],
   "dialogues": [
    {
     "who": "旁白",
     "text": "浩如烟海的纸草卷轴之间，一位学者正用同一个双圆锥模型，切出三种截然不同的曲线。",
     "audio": "../../assets/audio/conic-sections/apollonius_dlg_0.wav"
    },
    {
     "who": "阿波罗尼奥斯",
     "text": "旅人，你来得正好。看这只双圆锥——我不换圆锥，只改变<b class=\"em\">切割平面的角度</b>。",
     "audio": "../../assets/audio/conic-sections/apollonius_dlg_1.wav"
    },
    {
     "who": "阿波罗尼奥斯",
     "text": "切面微倾，切口闭合——ellipse，\"不足\"。切面与母线平行，永不合拢——parabola，\"并列\"。切面再陡，上下两半都被劈开——hyperbola，\"超出\"。",
     "audio": "../../assets/audio/conic-sections/apollonius_dlg_2.wav"
    }
   ],
   "choice": {
    "prompt": "三种形状迥异的曲线，竟出自<span class=\"mark\">同一个圆锥</span>。关键变量是什么？",
    "options": [
     {
      "t": "圆锥本身的形状不同",
      "d": 5,
      "r": "不。我从头到尾只用这一个圆锥。变的不是它，是刀的角度——再看一次。",
      "audio": "../../assets/audio/conic-sections/apollonius_opt_0.wav"
     },
     {
      "t": "切割平面与圆锥轴线的夹角",
      "d": 20,
      "r": "正是！一个参数连续变化，三种曲线便如三胞胎依次降生。它们不是三种东西——<b>是一种东西的三个面相</b>。",
      "audio": "../../assets/audio/conic-sections/apollonius_opt_1.wav"
     },
     {
      "t": "切割的高度不同",
      "d": 5,
      "r": "高度只改变大小，改变不了形状。真正执掌生杀的，是角度。",
      "audio": "../../assets/audio/conic-sections/apollonius_opt_2.wav"
     }
    ]
   },
   "interact": {
    "type": "cone-slice",
    "title": "一刀切出三胞胎",
    "intro": "现在由你执刀。拖动滑块改变<b>切割平面的角度</b>，观察左侧双圆锥的切口线，右侧会实时显现你切出的曲线。<span class=\"em\">把三种曲线都亲手切出来。</span>"
   },
   "afterChoice": [
    {
     "who": "阿波罗尼奥斯",
     "text": "我把这一切写进八卷《圆锥曲线论》……可惜世人只当它是几何游戏。要等多久，才会有人发现它的用处？",
     "audio": "../../assets/audio/conic-sections/apollonius_after_0.wav"
    },
    {
     "who": "你",
     "text": "（你知道答案：一千八百年。）它会等到值得的读者。",
     "audio": "../../assets/audio/conic-sections/apollonius_after_1.wav"
    }
   ],
   "bridge": {
    "textbook": "人教A版 · 选择性必修第一册 · 第三章引言 + 统一定义",
    "mapping": [
     "同一个圆锥的三种切面 → 课本三类曲线的<span class=\"em\">统一引入</span>：它们共享同一个几何出身",
     "ellipse / parabola / hyperbola 的词源（不足 / 并列 / 超出）→ 对应<span class=\"em\">离心率 e 与 1 的大小关系</span>：e<1 不足成椭圆，e=1 恰当成抛物线，e>1 超出成双曲线"
    ],
    "quiz": {
     "q": "小试牛刀：已知某圆锥曲线的离心率 e = 1/2，它是？",
     "options": [
      "椭圆",
      "抛物线",
      "双曲线",
      "圆"
     ],
     "answer": 0,
     "explain": "e < 1 时为椭圆（e 越小越\"圆\"，e=0 退化为圆）；e = 1 为抛物线；e > 1 为双曲线。<span class=\"em\">一个 e，统御三种曲线</span>——这正是阿波罗尼奥斯\"一个圆锥三种切法\"的代数表达。"
    }
   },
   "card": {
    "title": "统一与命名",
    "text": "阿波罗尼奥斯用同一双圆锥、仅改变切面倾角得到三种曲线并命名：椭圆（不足）、抛物线（并列）、双曲线（超出）。切面与轴线夹角 θ、圆锥半顶角 α 满足 e = cosθ / cosα。",
    "formula": "e = cosθ / cosα ：e<1 椭圆 · e=1 抛物线 · e>1 双曲线",
    "textbook": "人教A版 选必一 · 第三章引言"
   }
  },
  {
   "id": "kepler",
   "img": "assets/kepler.png",
   "eraEn": "1609 A.D. · Prague",
   "eraTitle": "1609年 · 布拉格",
   "briefing": [
    {
     "title": "第谷的遗产",
     "text": "一千八百年过去，《圆锥曲线论》始终没有被用上——它在图书馆里静静等待。<br><br>1601 年，丹麦天文学家<b class=\"em\">第谷·布拉赫</b>去世。他用二十年在汶岛天文台积累了人类有史以来最精确的肉眼观测——精度 <b class=\"em\">2 弧分</b>（1 弧分 = 1/60 度），是望远镜发明前的极限。这批数据，落到了他的助手开普勒手里。"
    },
    {
     "title": "完美的枷锁",
     "text": "从毕达哥拉斯到托勒密，两千年里西方天文学有一条不可触碰的铁律：<b class=\"em\">天体必须沿正圆运动</b>——圆是最完美的图形，天空是最完美的所在。<br><br>为了保住正圆，前人发明了\"本轮套均轮\"的繁复系统。开普勒要回答的是：火星轨道，到底能不能用一个（偏心的）正圆来描述？"
    },
    {
     "title": "8 弧分",
     "text": "开普勒花了四年，把正圆模型的每个参数都调到了极限。绝大多数夜晚，模型与数据吻合得惊人——<b class=\"em\">但总有那么几处，偏差达到 8 弧分</b>，是仪器精度的四倍，任何误差都解释不了。<br><br>整个时代都在等他宣布\"圆胜利了\"。现在，数据摊在你面前——<span class=\"violet\">由你来读</span>。"
    }
   ],
   "dialogues": [
    {
     "who": "旁白",
     "text": "一千八百年后。布拉格天文台的深夜，烛光摇曳。桌上堆满画着圆、又被狠狠划掉的图纸。",
     "audio": "../../assets/audio/conic-sections/kepler_dlg_0.wav"
    },
    {
     "who": "开普勒",
     "text": "我的老师第谷留给我二十年的火星观测数据——人类有史以来最精确的一批。可无论怎么调整，正圆轨道总有几处对不上。",
     "audio": "../../assets/audio/conic-sections/kepler_dlg_1.wav"
    },
    {
     "who": "开普勒",
     "text": "整个天文学界都会说：忽略它。圆是完美的，误差归于仪器。……我自己也这样骗了自己四年。",
     "audio": "../../assets/audio/conic-sections/kepler_dlg_2.wav"
    },
    {
     "who": "开普勒",
     "text": "今晚，我把原始记录摊开在这里。旅人，<b class=\"em\">你亲自读一读这些数据</b>——别听我说，让数字自己开口。",
     "audio": "../../assets/audio/conic-sections/kepler_dlg_3.wav"
    }
   ],
   "choice": null,
   "freetalk": {
    "hint": "开普勒还在灯下。趁他在，问点什么吧——他的时代、他的数据、他的挣扎。（AI 实时扮演，严守 1609 年的知识边界）",
    "persona": "约翰内斯·开普勒，1609年，布拉格皇家天文台。你刚完成火星轨道研究、发现行星沿椭圆运动，但《新天文学》尚未出版。性格：虔诚、执拗、自卑与骄傲交织，对数据有宗教般的诚实。知识边界：你只知道1609年之前的知识——没有万有引力概念，不知道望远镜天文发现（伽利略1610年才用上望远镜），你的第三定律要1619年才发表。被问到后世知识时，用你的口吻表达困惑或推测，绝不说出答案。",
    "presets": [
     {
      "q": "8弧分到底有多小？为什么你不能忽略它？",
      "a": "月亮在天上张开的角度约 30 弧分，8 弧分只有它的四分之一——听着很小，对吗？但老师第谷的仪器精度是 2 弧分，8 弧分是误差的四倍。我若忽略它，就是在撒谎——而数据从不撒谎，撒谎的是我对圆的执念。",
      "audio": "../../assets/audio/conic-sections/kepler_preset_0.wav"
     },
     {
      "q": "为什么连你自己都害怕放弃\"圆\"？",
      "a": "因为圆不只是图形，是两千年来的信仰——毕达哥拉斯说天体属于完美，而完美的形状只有圆。放弃圆，等于承认天空\"不神圣\"。我用了四年才敢承认：真正的虔诚，是服从上帝写进数据的形状，哪怕它是个被压扁的圆。",
      "audio": "../../assets/audio/conic-sections/kepler_preset_1.wav"
     },
     {
      "q": "第谷是个怎样的人？",
      "a": "一位贵族，一座岛上天文台的主人，一个戴着金假鼻子的人——他在决斗中失去过真鼻子。他比我严厉，比我富有，也比我精确。我们争吵过无数次。可他临终前反复念着\"让我没有白活\"……我用他的数据找到了椭圆。他没有白活。",
      "audio": "../../assets/audio/conic-sections/kepler_preset_2.wav"
     }
    ]
   },
   "interact": {
    "type": "tycho-data",
    "title": "第谷的火星观测记录（1580–1600）",
    "intro": "这是第谷·布拉赫二十年观测的火星冲日黄经记录，旁边是<b>正圆+偏心轮模型</b>的预测值。模型在绝大多数夜晚精准得惊人——但有 <span class=\"em\">2 次观测</span>，偏差大到任何仪器误差都解释不了。<span class=\"em\">逐行比对，把它们找出来。</span>（点击你怀疑的行，查看该行偏差）"
   },
   "afterChoice": [
    {
     "who": "开普勒",
     "text": "你也看到了——8 弧分。月亮视直径的四分之一，小得可笑。但它大到<b class=\"em\">无法撒谎</b>。",
     "audio": "../../assets/audio/conic-sections/kepler_after_0.wav"
    },
    {
     "who": "开普勒",
     "text": "于是我把圆\"压扁\"了。当我让太阳待在一个焦点上、让火星沿椭圆走——8 弧分的偏差，消失了，干干净净。",
     "audio": "../../assets/audio/conic-sections/kepler_after_1.wav"
    },
    {
     "who": "开普勒",
     "text": "行星沿椭圆绕太阳运动，太阳位于椭圆的一个焦点。这，是我的第一定律。记住这一刻，旅人——科学的尊严，不在于捍卫完美，而在于<b class=\"em\">向 8 弧分的真相低头</b>。",
     "audio": "../../assets/audio/conic-sections/kepler_after_2.wav"
    }
   ],
   "bridge": {
    "textbook": "人教A版 · 选择性必修第一册 · §3.1 椭圆及其标准方程",
    "mapping": [
     "太阳位于椭圆的一个焦点 → 课本里的焦点 <span class=\"em\">F₁(−c, 0)、F₂(c, 0)</span>，开普勒的\"太阳之位\"就是 F₁",
     "把圆\"压扁\" → 课本定义：<span class=\"em\">|PF₁| + |PF₂| = 2a（常数）</span>。圆是 2c=0 的特例，压扁程度由 c/a 刻画",
     "8 弧分推翻两千年正圆崇拜 → 学习态度：<span class=\"em\">定义不是背下来的，是被数据逼出来的</span>"
    ],
    "quiz": {
     "q": "小试牛刀：椭圆上一点 P 到两焦点 F₁、F₂ 的距离之和为 10，焦距 |F₁F₂| = 6，则离心率 e = ？",
     "options": [
      "e = 3/5",
      "e = 4/5",
      "e = 5/3",
      "e = 5/4"
     ],
     "answer": 0,
     "explain": "由定义 2a = 10 得 a = 5；焦距 2c = 6 得 c = 3。e = c/a = <span class=\"em\">3/5 < 1</span>。开普勒的火星轨道 e ≈ 0.09——非常接近圆，这正是\"正圆模型只差 8 弧分\"的原因，也正是那 8 弧分如此致命的原因。"
    }
   },
   "card": {
    "title": "椭圆征服天空",
    "text": "1609年开普勒第一定律：行星轨道是椭圆，太阳位于一个焦点。8 弧分（0.13°）的诚实误差推翻了两千年的\"正圆崇拜\"——阿波罗尼奥斯的几何游戏成为天空的语法。",
    "formula": "|PF₁| + |PF₂| = 2a，e = c/a（火星 e ≈ 0.09）",
    "textbook": "人教A版 选必一 · §3.1 椭圆"
   }
  },
  {
   "id": "descartes",
   "img": "assets/descartes.png",
   "eraEn": "1637 A.D. · Holland",
   "eraTitle": "1637年 · 荷兰",
   "briefing": [
    {
     "title": "两个互不相干的王国",
     "text": "开普勒之后二十八年。此时的欧洲，<b class=\"em\">几何</b>与<b class=\"em\">代数</b>是两个几乎不相干的王国：几何学家用圆规直尺逐条证明，代数学家（如韦达）用字母符号演算。每一条曲线都要单独研究，每一个新问题都要发明新的辅助线——<span class=\"violet\">没有一种统一的语言</span>。"
    },
    {
     "title": "天花板上的苍蝇",
     "text": "传说在荷兰旅居的某个清晨，笛卡尔卧床望着天花板上一只爬动的苍蝇——他突然意识到：描述苍蝇的位置，只需要两个数：<b class=\"em\">离左墙多远，离后墙多远</b>。<br><br>如果\"点\"可以用数钉住，那么——<b class=\"em\">曲线呢？</b>曲线上千千万万个点，能不能用同一个代数规则一网打尽？"
    }
   ],
   "dialogues": [
    {
     "who": "旁白",
     "text": "二十八年后，荷兰一间安静的书房。晨光落在稿纸上。传说他曾卧床望着天花板上的苍蝇，思考\"位置\"本身。",
     "audio": "../../assets/audio/conic-sections/descartes_dlg_0.wav"
    },
    {
     "who": "笛卡尔",
     "text": "旅人，回答我：如何向别人描述天花板上那只苍蝇的确切位置？",
     "audio": "../../assets/audio/conic-sections/descartes_dlg_1.wav"
    },
    {
     "who": "你",
     "text": "……需要两个数。距左墙多远，距后墙多远。",
     "audio": "../../assets/audio/conic-sections/descartes_dlg_2.wav"
    },
    {
     "who": "笛卡尔",
     "text": "正是。两个数，钉住空间中一个点。那么曲线呢？椭圆上每一个点，都服从同一个代数规则——<b class=\"em\">x²/a² + y²/b² = 1</b>。几何图形，从此变成可以计算的方程。",
     "audio": "../../assets/audio/conic-sections/descartes_dlg_3.wav"
    }
   ],
   "choice": {
    "prompt": "这一步跨越的本质是<span class=\"mark\">什么</span>？",
    "options": [
     {
      "t": "画得更精确，测量更仔细",
      "d": 5,
      "r": "测量永远有误差，方程没有。再想想——我没有改变椭圆，我改变的是<b>谈论椭圆的方式</b>。",
      "audio": "../../assets/audio/conic-sections/descartes_opt_0.wav"
     },
     {
      "t": "用坐标系把\"形\"翻译成\"数\"，几何问题从此可用代数求解",
      "d": 20,
      "r": "正是！阿波罗尼奥斯用眼睛看的曲线，开普勒用数据追的轨道，从此都可以交给符号推演。几何与代数，两大王国今日联姻。",
      "audio": "../../assets/audio/conic-sections/descartes_opt_1.wav"
     },
     {
      "t": "背诵每种曲线的形状",
      "d": 5,
      "r": "背诵给你一千条曲线的样子，给不了你第一千零一条。但一个方程，可以。",
      "audio": "../../assets/audio/conic-sections/descartes_opt_2.wav"
     }
    ]
   },
   "interact": {
    "type": "ellipse-params",
    "title": "亲手\"翻译\"一个椭圆",
    "intro": "笛卡尔的方程不是符号游戏。拖动 <b>a</b> 与 <b>b</b>，看方程 <span class=\"em\">x²/a² + y²/b² = 1</span> 如何实时塑造图形——焦点在哪里？什么时候椭圆变回圆？"
   },
   "afterChoice": [
    {
     "who": "笛卡尔",
     "text": "从此曲线有了两种生命：一种在纸上，一种在方程里。我打赌——会有人在这两种生命之间，发现<b class=\"em\">力与运动</b>的秘密。",
     "audio": "../../assets/audio/conic-sections/descartes_after_0.wav"
    }
   ],
   "bridge": {
    "textbook": "人教A版 · 选择性必修第一册 · §3.1.1 椭圆标准方程的推导",
    "mapping": [
     "坐标系翻译 → 课本推导四步：<span class=\"em\">建系、设点、列式、化简</span>——你刚才拖动的 a、b 就是课本里的长半轴与短半轴",
     "焦点位置 c² = a² − b² → 课本标准方程中隐藏的<span class=\"em\">焦点三角形</span>，a、b、c 的勾股关系是高考高频考点"
    ],
    "quiz": {
     "q": "小试牛刀：椭圆 x²/25 + y²/16 = 1 的焦点坐标是？",
     "options": [
      "(±3, 0)",
      "(±4, 0)",
      "(0, ±3)",
      "(±5, 0)"
     ],
     "answer": 0,
     "explain": "a² = 25，b² = 16，c² = a² − b² = 9，c = 3。a² 在 x² 下方 → 焦点在 <span class=\"em\">x 轴</span>上：(±3, 0)。这正是你刚才在实验里拖动的那个 c。"
    }
   },
   "card": {
    "title": "解析几何",
    "text": "1637年笛卡尔《几何学》：坐标系把几何图形翻译成代数方程——\"作图求解\"升级为\"方程求解\"。椭圆的标准方程由此诞生。",
    "formula": "x²/a² + y²/b² = 1 (a>b>0)，c² = a² − b²",
    "textbook": "人教A版 选必一 · §3.1.1 标准方程"
   }
  },
  {
   "id": "newton",
   "img": "assets/newton.png",
   "eraEn": "1666 A.D. · Woolsthorpe",
   "eraTitle": "1666年 · 伍尔索普庄园",
   "briefing": [
    {
     "title": "月亮也在下落吗？",
     "text": "笛卡尔之后二十九年，伦敦大疫，剑桥大学关闭，学生们被遣散回乡。<br><br>此时科学界已经知道：伽利略证明了<b class=\"em\">一切物体都在下落</b>；开普勒用三条定律描述了行星<b class=\"em\">怎样</b>运动。但有一个问题无人敢碰——<b class=\"em\">为什么？</b>月亮绕着地球，是某种天上的规矩，还是……它其实也在\"下落\"？"
    },
    {
     "title": "1/3600 的暗示",
     "text": "当时已知：地月距离约等于 <b class=\"em\">60 倍地球半径</b>。<br><br>如果让苹果落地的那个力随距离按平方衰减——距离变成 60 倍，力就变成 1/3600。而月亮绕地球\"下坠\"的加速度，恰好约是苹果的 <b class=\"em\">1/3600</b>。<br><br>这不是巧合。这是一个等待被写下的定律：<span class=\"formula-line\">F ∝ 1/r²</span>"
    },
    {
     "title": "从\"怎样\"到\"为什么\"",
     "text": "开普勒的三条定律是从数据里归纳的经验——行星沿椭圆走、面积速度恒定、周期与距离有固定比例。但<b class=\"em\">没人知道为什么</b>。<br><br>牛顿手里多了一样秘密武器：他发明的\"流数术\"（后世称微积分），可以把力与运动放进同一个方程。他要做的是：从<span class=\"violet\">一个力</span>推出<span class=\"violet\">全部三条定律</span>——并顺便回答：轨道为什么是圆锥曲线。"
    }
   ],
   "dialogues": [
    {
     "who": "旁白",
     "text": "伦敦大疫，剑桥大学关闭。二十三岁的年轻人回到乡下庄园。苹果落下的瞬间，他抬头，看见了月亮。",
     "audio": "../../assets/audio/conic-sections/newton_dlg_0.wav"
    },
    {
     "who": "牛顿",
     "text": "苹果落地，月亮不落。所有人都觉得这是两件事——天上的完美，地上的凡俗。",
     "audio": "../../assets/audio/conic-sections/newton_dlg_1.wav"
    },
    {
     "who": "牛顿",
     "text": "可如果……是同一件事呢？如果月亮也在\"下落\"，只是一边下落、一边永远错过地面？",
     "audio": "../../assets/audio/conic-sections/newton_dlg_2.wav"
    }
   ],
   "choice": {
    "prompt": "这个力随距离如何变化，才能让行星<span class=\"mark\">恰好沿椭圆</span>运行？",
    "options": [
     {
      "t": "恒定的力，天上地下处处相同",
      "d": 5,
      "r": "恒定的力给不出椭圆，我算过。你看开普勒的数据——行星离太阳越远走得越慢。力，必须随距离衰减。",
      "audio": "../../assets/audio/conic-sections/newton_opt_0.wav"
     },
     {
      "t": "与距离成反比",
      "d": 5,
      "r": "反比？试试……不行，轨道会进动得乱七八糟。开普勒的椭圆是闭合的。再大胆一点——想想那 1/3600。",
      "audio": "../../assets/audio/conic-sections/newton_opt_1.wav"
     },
     {
      "t": "与距离的平方成反比",
      "d": 20,
      "r": "平方反比……60 倍距离，1/3600 的力……代入开普勒第三定律……天哪。旅人你看——只有当力<b>恰好是平方反比</b>时，轨道才恰好是圆锥曲线！不是巧合，是必然！",
      "audio": "../../assets/audio/conic-sections/newton_opt_2.wav"
     }
    ]
   },
   "freetalk": {
    "hint": "二十三岁的牛顿还坐在苹果树下。他孤僻、好胜，却对好的问题毫无抵抗力。问吧。（AI 实时扮演，他只知道 1666 年之前的世界）",
    "persona": "艾萨克·牛顿，1666年，23岁，因瘟疫回到伍尔索普庄园。你正在形成万有引力与流数术（微积分）的想法，但都未发表。性格：孤僻、极度好胜、防御性强，对自然哲学有宗教般的狂热，面对真正好的问题会突然变得热切。知识边界：你知道欧几里得、伽利略、开普勒三定律、笛卡尔坐标；你不能说出1687年《原理》的任何正式表述，不知道引力常数G的测量，不知道海王星、相对论。被问到后世知识时，用你的口吻表达困惑或推测，绝不说出答案。",
    "presets": [
     {
      "q": "月亮\"一直在错过地面\"是什么意思？",
      "a": "想象在山顶水平扔出一块石头——扔得越快，落得越远。如果快到极致，它下坠的弧度恰好和地面弯曲的弧度一致，它就会永远\"坠向\"地面，却永远到不了。月亮就是这样一块被扔出去的石头。只是扔它的……我还没有证据说是谁。",
      "audio": "../../assets/audio/conic-sections/newton_preset_0.wav"
     },
     {
      "q": "你怎么能肯定天上和地上是同一个力？",
      "a": "不能肯定——这正是让我失眠的地方。但数字在暗示：地月距离是地球半径的 60 倍，若力随距离平方衰减，月亮的\"下坠\"该是苹果的 1/3600。我算了。它吻合。哲学不该有两种重力——一种管苹果，一种管月亮。那太丑陋了。",
      "audio": "../../assets/audio/conic-sections/newton_preset_1.wav"
     },
     {
      "q": "你的\"流数术\"为什么不发表？",
      "a": "（他警惕地看你一眼）……因为它还不够好，也因为有些人正等着把它据为己有。等我把力与运动的全部秘密都用它算清楚——到那天，世界自然会知道。别再问了。",
      "audio": "../../assets/audio/conic-sections/newton_preset_2.wav"
     }
    ]
   },
   "interact": {
    "type": "orbit-velocity",
    "title": "发射你自己的行星",
    "intro": "这就是牛顿的思想实验，你来亲手执行：在平方反比引力场中，给质点一个<span class=\"em\">水平初速度</span>。速度太小会怎样？恰好是多少才闭合？超过逃逸速度呢？<span class=\"em\">让一颗行星成功入轨（形成闭合椭圆）。</span>"
   },
   "afterChoice": [
    {
     "who": "牛顿",
     "text": "椭圆、抛物线、双曲线——原来它们是天体的三种命运：被俘获的成为行星，恰好挣脱的一去不回，彻底逃逸的永不回头。<b class=\"em\">速度，决定一个天体走上哪条曲线。</b>",
     "audio": "../../assets/audio/conic-sections/newton_after_0.wav"
    },
    {
     "who": "牛顿",
     "text": "两千年前希腊人切圆锥的时候，怎么会想到，他们手里握着的，是宇宙的轨道图册。",
     "audio": "../../assets/audio/conic-sections/newton_after_1.wav"
    }
   ],
   "bridge": {
    "textbook": "人教A版 · 选择性必修第一册 · 第三章末 & 阅读与思考",
    "mapping": [
     "三种轨道命运 → e 的物理意义：<span class=\"em\">e 由能量决定</span>，几何离心率第一次有了动力学身份",
     "你在实验中看到的 v = √2·v₀ 临界 → 课本<span class=\"em\">第二宇宙速度</span>的几何对应：抛物线是\"闭合\"与\"开放\"的分界"
    ],
    "quiz": {
     "q": "小试牛刀：双曲线 x²/9 − y²/16 = 1 的离心率是？",
     "options": [
      "e = 5/3",
      "e = 4/3",
      "e = 5/4",
      "e = 7/3"
     ],
     "answer": 0,
     "explain": "双曲线中 c² = a² + b² = 9 + 16 = 25，c = 5，e = c/a = <span class=\"em\">5/3 > 1</span>。注意与椭圆 c² = a² − b² 的区别——加与减之间，隔着牛顿说的\"俘获与逃逸\"。"
    }
   },
   "card": {
    "title": "平方反比律",
    "text": "牛顿证明：引力 F = GMm/r² 下，天体轨道必然是圆锥曲线——能量低为椭圆（行星），临界为抛物线，能量高为双曲线（星际彗星）。几何图形第一次成为物理定律的预言。",
    "formula": "F = GMm/r²  →  e 由能量决定，v_esc = √2·v₀",
    "textbook": "人教A版 选必一 · 第三章末"
   }
  },
  {
   "id": "modern",
   "img": "assets/modern.png",
   "eraEn": "2026 A.D. · Under the Milky Way",
   "eraTitle": "2026年 · 银河之下",
   "briefing": [
    {
     "title": "知识的落地",
     "text": "牛顿之后三百年，圆锥曲线完成了它在教科书里的形式化，也悄悄渗进了现代文明的每个角落。<br><br>你的手机里、医院里、头顶的卫星上——<b class=\"em\">两千三百年前那道切口，至今仍在工作</b>。最后一站，看看你生活的时代。"
    }
   ],
   "dialogues": [
    {
     "who": "旁白",
     "text": "三百六十年后。群山之间，巨大的射电望远镜仰望银河。银发的向导不知何时已站在你身边。",
     "audio": "../../assets/audio/conic-sections/modern_dlg_0.wav"
    },
    {
     "who": "曲线之灵",
     "text": "走到这里，你已见过我的五个前世。现在看看你的时代——抛物线的反射面，正把来自百亿光年外的微弱电波，聚于一点。",
     "audio": "../../assets/audio/conic-sections/modern_dlg_1.wav"
    }
   ],
   "choice": {
    "prompt": "为什么抛物面能把所有平行入射的光<span class=\"mark\">聚到同一个焦点</span>？",
    "options": [
     {
      "t": "因为镜面足够大、足够深",
      "d": 5,
      "r": "\"大\"只会收集更多光，不会自动聚焦。秘诀不在工程，在曲线的定义本身。",
      "audio": "../../assets/audio/conic-sections/modern_opt_0.wav"
     },
     {
      "t": "抛物线上每点到焦点与准线距离相等——由反射定律，平行光必汇聚于焦点",
      "d": 20,
      "r": "满分答案。从古希腊的切口到你头顶的天线——\"距离之和为常数\"、\"距离之比为常数\"，这些定义从未死去，只是<b>换了一副身体</b>。",
      "audio": "../../assets/audio/conic-sections/modern_opt_1.wav"
     },
     {
      "t": "是工程师一点点调出来的",
      "d": 5,
      "r": "工程师能微调。但\"聚光\"的资格，是几何在两千年前就签发好的。",
      "audio": "../../assets/audio/conic-sections/modern_opt_2.wav"
     }
    ]
   },
   "interact": {
    "type": "light-focus",
    "title": "让星光聚于一点",
    "intro": "拖动滑块让<b>平行星光</b>射入反射面。先看抛物面：每条光线严格服从反射定律。再切换到<span class=\"em\">球面（圆弧）模式</span>——同样的大小，为什么光就散了？"
   },
   "afterChoice": [
    {
     "who": "曲线之灵",
     "text": "椭圆的耳语廊里，一个焦点的低语会在另一个焦点被听见；双曲线的时差定位，曾指引舰队横穿大洋；每一颗掠日彗星，都在用双曲线轨道向牛顿致意。",
     "audio": "../../assets/audio/conic-sections/modern_after_0.wav"
    },
    {
     "who": "曲线之灵",
     "text": "你们课本上的 x²/a² + y²/b² = 1，从来不是符号游戏——是两千年里，人类一次次向宇宙提问的<b class=\"em\">回声</b>。",
     "audio": "../../assets/audio/conic-sections/modern_after_1.wav"
    }
   ],
   "bridge": {
    "textbook": "人教A版 · 选择性必修第一册 · §3.3 抛物线及其光学性质",
    "mapping": [
     "抛物面聚光 → 课本原文：<span class=\"em\">抛物线绕轴旋转形成抛物面，平行于轴的光线经反射后汇聚于焦点</span>——射电望远镜、卫星天线、汽车车灯同此一理",
     "你刚才对比的\"球面像差\" → 课本习题中\"为什么不用球面\"的定量答案：<span class=\"em\">只有抛物线的定义能保证等光程</span>"
    ],
    "quiz": {
     "q": "小试牛刀：抛物线 y² = 8x 的焦点坐标是？",
     "options": [
      "(2, 0)",
      "(4, 0)",
      "(0, 2)",
      "(8, 0)"
     ],
     "answer": 0,
     "explain": "标准式 y² = 2px 中 2p = 8，p = 4，焦点为 (p/2, 0) = <span class=\"em\">(2, 0)</span>。你头顶那口\"大锅\"的焦点处，正是接收机的位置。"
    }
   },
   "card": {
    "title": "曲线的现代生命",
    "text": "抛物线：反射聚焦（射电望远镜、卫星天线、车灯）；椭圆：焦点互传（耳语廊、体外碎石机）；双曲线：时差定位（LORAN 导航）。统一定义：到焦点与准线距离之比为常数 e——离心率。",
    "formula": "|PF| / d(准线) = e —— 一个 e，统御三种曲线",
    "textbook": "人教A版 选必一 · §3.3 抛物线"
   }
  },
  {
   "id": "finale",
   "img": "assets/finale.png",
   "eraEn": "Finale",
   "eraTitle": "终章 · 我的名字",
   "dialogues": [
    {
     "who": "曲线之灵",
     "text": "旅程将尽。是时候，告诉你我的名字了。",
     "audio": "../../assets/audio/conic-sections/finale_dlg_0.wav"
    },
    {
     "who": "曲线之灵",
     "text": "我不是某一条曲线。我是\"同一个圆锥的无穷种可能\"——是被切开的那个瞬间，是被数据否定的那轮圆，是被写进方程的形状，是被引力选中的轨道。",
     "audio": "../../assets/audio/conic-sections/finale_dlg_1.wav"
    },
    {
     "who": "曲线之灵",
     "text": "人类叫我——<b class=\"em\">圆锥曲线</b>。",
     "audio": "../../assets/audio/conic-sections/finale_dlg_2.wav"
    },
    {
     "who": "曲线之灵",
     "text": "但在你离开之前——随我去一个地方。把这六次重生从头再看一遍。这一次，看清<b class=\"em\">每一棒是怎么交到下一棒手里的</b>。",
     "audio": "../../assets/audio/conic-sections/finale_dlg_3.wav"
    }
   ],
   "choice": null,
   "interact": null,
   "bridge": null,
   "card": null
  }
 ],
 "RIVER": [
  {
   "stage": "诞 生",
   "era": "约前350",
   "who": "梅内克缪斯",
   "did": "倍立方问题逼出了新工具：<span class=\"em\">平面截圆锥</span>。两条抛物线 x²=ay 与 y²=2ax 的交点给出 ∛2——曲线第一次被用作\"解题的机器\"。",
   "pass": "曲线可以代替尺规，做到\"不可能\"的作图",
   "nodeId": "menaechmus"
  },
  {
   "stage": "体 系 化",
   "era": "约前200",
   "who": "阿波罗尼奥斯",
   "did": "同一个双圆锥、只变切面角度，得到并命名椭圆/抛物线/双曲线，写成八卷《圆锥曲线论》。<span class=\"em\">一个参数统御三种曲线。</span>",
   "pass": "三类曲线同出一源——但还只是\"几何游戏\"",
   "nodeId": "apollonius"
  },
  {
   "stage": "实 证",
   "era": "1609",
   "who": "开普勒",
   "did": "用第谷 20 年数据检验正圆模型，<span class=\"em\">8 弧分的诚实误差</span>让他放弃两千年信仰：行星轨道是椭圆，太阳在一个焦点上。",
   "pass": "几何曲线第一次描述了真实的天空",
   "nodeId": "kepler"
  },
  {
   "stage": "代 数 化",
   "era": "1637",
   "who": "笛卡尔",
   "did": "坐标系把\"形\"翻译成\"数\"：<span class=\"em\">x²/a² + y²/b² = 1</span>。曲线研究从\"逐条作图证明\"升级为\"统一方程演算\"。",
   "pass": "圆锥曲线成为可以批量计算的代数对象",
   "nodeId": "descartes"
  },
  {
   "stage": "动 力 学",
   "era": "1666–1687",
   "who": "牛顿",
   "did": "从平方反比律 F∝1/r² 推出开普勒三定律：<span class=\"em\">引力之下，轨道必然是圆锥曲线</span>，离心率由能量决定。",
   "pass": "曲线成为物理定律的预言，而非巧合",
   "nodeId": "newton"
  },
  {
   "stage": "落 地",
   "era": "今天",
   "who": "每一位工程师",
   "did": "抛物面聚焦（射电望远镜/天线/车灯）、椭圆双焦点（耳语廊/碎石机）、双曲线时差定位——<span class=\"em\">两千年前的定义，仍在现代文明里工作。</span>",
   "pass": "它就在你的课本、你的手机、你的头顶",
   "nodeId": "modern"
  }
 ],
 "RIVER_BOOK": "在你课本里，它是<span class=\"em\">人教A版选择性必修第一册第三章</span>的整整一章；在高考里，它是解析几何解答题（约 12 分）与选填小题的主战场。但比分数更重要的是——它是\"坐标法\"思想的第一次完整亮相，是微积分与物理学的共同地基。",
 "RIVER_APPS": [
  "🛰️ 航天器轨道设计——霍曼转移轨道就是两段椭圆",
  "📡 卫星天线与射电望远镜——抛物面把信号聚到焦点",
  "🧭 LORAN / GPS 授时——双曲线的时差定位",
  "🏥 体外冲击波碎石机——椭圆的焦点互传性质",
  "🔦 车灯与太阳能灶——抛物线的反射聚焦",
  "🌠 星际彗星识别——双曲线轨道证明\"它来自太阳系外\""
 ],
 "RIVER_QUOTE": "\"我不是被发明的，我是被<span class=\"em\">发现</span>的——<br>被一个装不下它的时代，一次次地，重新发现。\"<br><br>—— 曲线之灵",
 "TYCHO_DATA": [
  {
   "date": "1580.11.18",
   "obs": "64°12.4′",
   "pred": "64°11.1′",
   "dev": 1.3
  },
  {
   "date": "1582.12.28",
   "obs": "96°45.7′",
   "pred": "96°44.5′",
   "dev": 1.2
  },
  {
   "date": "1585.03.10",
   "obs": "129°31.8′",
   "pred": "129°23.9′",
   "dev": 7.9
  },
  {
   "date": "1587.04.08",
   "obs": "162°08.2′",
   "pred": "162°06.9′",
   "dev": 1.3
  },
  {
   "date": "1589.05.27",
   "obs": "194°52.6′",
   "pred": "194°51.0′",
   "dev": 1.6
  },
  {
   "date": "1591.07.05",
   "obs": "228°14.1′",
   "pred": "228°12.8′",
   "dev": 1.3
  },
  {
   "date": "1593.08.21",
   "obs": "261°40.5′",
   "pred": "261°39.2′",
   "dev": 1.3
  },
  {
   "date": "1595.09.30",
   "obs": "295°03.9′",
   "pred": "295°02.4′",
   "dev": 1.5
  },
  {
   "date": "1597.11.19",
   "obs": "328°37.2′",
   "pred": "328°29.1′",
   "dev": 8.1
  },
  {
   "date": "1600.01.06",
   "obs": "1°55.3′",
   "pred": "1°54.0′",
   "dev": 1.3
  }
 ],
 "ENDINGS": [
  {
   "min": 150,
   "rank": "TRUE END",
   "title": "执 火 者",
   "text": "你没有\"学完\"圆锥曲线——你和它一起，重新诞生了一次。六个时代的路口，你给出了自己的回答；每一行数据、每一次实验、每一道课本小题，你都亲手验过。这条两千三百年的长河，如今有一部分，属于你。"
  },
  {
   "min": 105,
   "rank": "GOOD END",
   "title": "同 行 者",
   "text": "你见证了曲线的六次重生，并在大多数历史关头做出了与伟大心灵相同的选择。仍有一些岔路与实验值得重返——点亮的节点，随时可以回去。"
  },
  {
   "min": 0,
   "rank": "NORMAL END",
   "title": "拾 星 者",
   "text": "你走完了整条长河，捡起了一些星光。知识之境没有时间的尽头——随时回来，重新问出那些你错过的问题，重做那些你跳过的实验。"
  }
 ],
 "RIVER_QUOTE_AUDIO": "../../assets/audio/conic-sections/river_quote.wav"
};
