/* 知识之境 · 篇章数据（由工厂生成） */
window.STORY_DATA = {
 "META": {
  "title": "勾股定理 · 从周公的矩尺到赵爽的弦图",
  "subtitle": "一个直角三角形三边关系的四千年求证之路",
  "guide_name": "矩尺之灵",
  "cast": {
   "商高": "m-old",
   "毕达哥拉斯": "m-old",
   "希帕索斯": "m-young",
   "欧几里得": "m-old",
   "赵爽": "m-old",
   "周公": "m",
   "林薇": "f",
   "张磊": "m",
   "学生": "m"
  }
 },
 "STORY": [
  {
   "id": "prologue",
   "eraEn": "2024 A.D. · Classroom 式",
   "eraTitle": "序章 · 2024年 · 教室 式",
   "briefing": [
    {
     "title": "你即将踏入的，不是神话，而是知识的诞生现场",
     "text": "在八年级数学课本第27页，你第一次见到它：直角三角形中，两条直角边的平方和等于斜边的平方。代数表达为 <span class='formula-line'>a² + b² = c²</span>。这不是凭空而来的公式，而是人类为解决一个最朴素却最顽固的难题——‘如何用已知的直角边，精确算出斜边长度’——所付出的四千年努力。这个知识点的本质，是**直角三角形三边长度之间不可违背的数量约束关系**：只要∠C=90°，那么无论a、b取何正实数值，c就唯一确定为√(a²+b²)；反过来，若三边满足a²+b²=c²，则必可构成直角三角形（这就是逆定理）。它架起了几何图形与代数运算之间的第一座坚实桥梁——从此，长度不再只是尺子量出来的数，更是可被计算、被推演、被证明的对象。你即将学到的东西，此刻正在被这段历史发现：**勾股定理本身，就是这个约束关系的首次明确表述与严格证明**。"
    }
   ],
   "dialogues": [
    {
     "who": "矩尺之灵",
     "text": "你好，我是矩尺之灵——不是神祇，而是千年来所有执尺画方、仰观俯察者心中那把不弯曲的直角尺。",
     "audio": "../../assets/audio/pythagorean-journey/prologue_dlg_0.wav"
    },
    {
     "who": "矩尺之灵",
     "text": "你手里的课本第27页，写着a² + b² = c²。但这句话，在公元前10世纪的周原，在公元前6世纪的克罗顿，在公元3世纪的洛阳，曾是悬而未决的谜题、引发信仰崩塌的雷暴、耗费一生心血的证明。",
     "audio": "../../assets/audio/pythagorean-journey/prologue_dlg_1.wav"
    },
    {
     "who": "矩尺之灵",
     "text": "跟我来。我们不背公式，我们重走那条用竹简、莎草纸和朱砂验证真理的路。",
     "audio": "../../assets/audio/pythagorean-journey/prologue_dlg_2.wav"
    },
    {
     "who": "旁白",
     "text": "光影流转，课桌化作青铜礼器，粉笔灰升腾为洛水晨雾——旅程，始于一把矩尺。",
     "audio": "../../assets/audio/pythagorean-journey/prologue_dlg_3.wav"
    }
   ],
   "choice": null,
   "freetalk": {
    "hint": "出发之前，还有什么想和我聊聊的吗？",
    "persona": "一位通晓古今数学史的向导，知识边界截止于2024年课标，熟知人教A版八年级教材全部内容，但绝不提前泄露后续节点答案",
    "presets": [
     {
      "q": "为什么叫‘勾’‘股’‘弦’？",
      "a": "这是中国古代的命名智慧：‘勾’指直角三角形较短的直角边（如测量时水平伸出的尺），‘股’指较长的直角边（如垂直立起的表），‘弦’指连接两者的斜边——就像弓上绷紧的弦。课本第27页的图示，正是此意。",
      "audio": "../../assets/audio/pythagorean-journey/prologue_preset_0.wav"
     },
     {
      "q": "‘勾三股四弦五’是特例还是定理？",
      "a": "它是定理的第一个具体实例，是发现的起点，不是终点。就像发现‘2+2=4’不等于证明了加法交换律。课本第27页强调：特例启发思考，普遍性才是定理的灵魂。",
      "audio": "../../assets/audio/pythagorean-journey/prologue_preset_1.wav"
     }
    ]
   },
   "interact": null,
   "afterChoice": null,
   "bridge": null,
   "card": null,
   "img": "assets/prologue.png"
  },
  {
   "id": "shang-gao",
   "eraEn": "1000 B.C. · Zhouyuan 式",
   "eraTitle": "公元前1000年 · 周原 式",
   "briefing": [
    {
     "title": "时代困境：没有数字坐标，如何测量天地？",
     "text": "西周初年，周公摄政，急需一套可靠方法测算日影长度、规划都城、校准历法。当时没有阿拉伯数字，没有代数符号，更没有‘平方’概念；唯一的计量工具是‘矩’——L形木尺，靠目测比对和经验积累。人们知道某些特定比例（如3:4:5）能构成直角，但无法回答：‘任意两个直角边，斜边究竟多长？’这个问题关乎国家命脉——测不准日影，就编不准历；建不准宫室，就失了礼制根基。"
    },
    {
     "title": "商高到底发现了什么？",
     "text": "在《周髀算经》记载的周公与商高对话中，商高说：‘折矩，以为勾广三，股修四，径隅五。既方之，外半其一矩，环而共盘，得成三四五。两矩共长二十有五，是谓积矩。’这不仅是‘3-4-5’特例的记录，更是**对直角三角形三边关系的普遍性描述雏形**：他指出，将矩尺折成直角后，‘勾’与‘股’各自构成的正方形面积之和（即‘积矩’），等于以‘径隅’（斜边）为边的正方形面积。虽然未用现代符号，但他用‘积’（面积）、‘方’（正方形）等词，确立了‘边长平方和=斜边平方’这一数量关系的核心思想。"
    },
    {
     "title": "这一步为什么关键？",
     "text": "它首次将直角三角形的几何构造（矩）与数量关系（积矩）明确绑定，使‘测量’从经验技艺升华为可传递、可复现的数学知识。此前，人们只能记住几个特例；此后，他们拥有了一个可推广的计算框架——尽管尚未证明其普适性，但已为‘什么是正确的斜边长度’给出了可操作的答案。你即将学到的东西，此刻正在被这段历史发现：<span class='violet'>勾股定理的普遍性表述</span>。"
    }
   ],
   "dialogues": [
    {
     "who": "商高",
     "text": "周公啊，数之法出于圆方，方出于矩。您看这把矩尺——",
     "audio": "../../assets/audio/pythagorean-journey/shang-gao_dlg_0.wav"
    },
    {
     "who": "商高",
     "text": "勾广三，股修四，径隅五。两矩共长二十有五，是谓积矩！",
     "audio": "../../assets/audio/pythagorean-journey/shang-gao_dlg_1.wav"
    },
    {
     "who": "周公",
     "text": "那么，若勾广六、股修八，径隅当为几何？",
     "audio": "../../assets/audio/pythagorean-journey/shang-gao_dlg_2.wav"
    },
    {
     "who": "商高",
     "text": "依积矩之法，三六得十八，四八得三十二，相并得五十，开方得七又七分之一——<b class='em'>径隅必合此数</b>！",
     "audio": "../../assets/audio/pythagorean-journey/shang-gao_dlg_3.wav"
    }
   ],
   "choice": {
    "prompt": "面对周公追问‘勾六股八，径隅几何’，商高依据什么给出答案？",
    "options": [
     {
      "t": "查祖传口诀表，直接报出‘十’",
      "d": 5,
      "r": "错。商高时代尚无系统口诀表；且《周髀算经》原文强调‘积矩’推演过程，而非死记硬背。这混淆了经验记忆与数学推理。",
      "audio": "../../assets/audio/pythagorean-journey/shang-gao_opt_0.wav"
     },
     {
      "t": "用矩尺实物拼摆，观察小正方形总数，再开方",
      "d": 20,
      "r": "对！商高说‘既方之，外半其一矩，环而共盘’，正是用实际拼图演示：以勾、股为边的两个正方形，可重组为以径隅为边的大正方形——面积守恒是核心。",
      "audio": "../../assets/audio/pythagorean-journey/shang-gao_opt_1.wav"
     }
    ]
   },
   "freetalk": null,
   "interact": {
    "type": "custom-lab",
    "title": "商高的积矩实验",
    "intro": "用竹简模拟商高的拼图：拖动滑块设定勾、股长度，观察两个小正方形如何重组为大正方形。",
    "config": {
     "sliders": [
      {
       "id": "a",
       "label": "勾长（单位：尺）",
       "min": 1,
       "max": 10,
       "step": 1,
       "init": 3
      },
      {
       "id": "b",
       "label": "股长（单位：尺）",
       "min": 1,
       "max": 10,
       "step": 1,
       "init": 4
      }
     ],
     "readouts": [
      {
       "label": "勾方面积",
       "expr": "a * a"
      },
      {
       "label": "股方面积",
       "expr": "b * b"
      },
      {
       "label": "积矩和",
       "expr": "a * a + b * b"
      }
     ],
     "big": {
      "label": "径隅长（开方后）",
      "expr": "Math.sqrt(a * a + b * b)"
     },
     "win": {
      "expr": "Math.abs(Math.sqrt(a * a + b * b) - Math.round(Math.sqrt(a * a + b * b))) < 0.01",
      "text": "完美！当积矩和为完全平方数时，径隅恰为整数——这就是‘勾三股四弦五’的由来。"
     }
    }
   },
   "afterChoice": [
    {
     "who": "矩尺之灵",
     "text": "看，商高没有用神秘咒语，只用一把矩尺、两块方板、一次面积重组——他就让‘a² + b² = c²’从天象玄思落地为可触摸的真理。",
     "audio": "../../assets/audio/pythagorean-journey/shang-gao_after_0.wav"
    },
    {
     "who": "矩尺之灵",
     "text": "这个关系，就是课本第27页那个简洁等式最古老的回响。",
     "audio": "../../assets/audio/pythagorean-journey/shang-gao_after_1.wav"
    }
   ],
   "bridge": {
    "textbook": "八年级 · 第二十章 勾股定理（第27-37页）",
    "mapping": [
     "商高通过矩尺拼图得出‘勾方+股方=弦方’的面积关系，用今天课本的语言严格地说，就是勾股定理——因为直角三角形两直角边为边的正方形面积之和，恒等于以斜边为边的正方形面积，这等价于代数式a² + b² = c²，课本第27页的定义正是对此几何事实的代数转译。",
     "商高用‘积矩’（面积之和）推算‘径隅’（斜边），本质上是将几何问题转化为算术问题，这为课本第30页‘利用勾股定理求未知边长’提供了最原始的方法论原型——因为任何边长计算，最终都归结为解方程c = √(a² + b²)。"
    ],
    "quiz": {
     "q": "《九章算术》中‘今有池方一丈，葭生其中央，出水一尺……引葭赴岸，适与岸齐’。设水深为x尺，则芦苇长为(x+1)尺，池边到中心距离为5尺。根据勾股定理列方程正确的是：",
     "options": [
      "A. x² + 5² = (x+1)²",
      "B. x² + (x+1)² = 5²",
      "C. 5² + (x+1)² = x²",
      "D. x + 5 = x + 1"
     ],
     "answer": 0,
     "explain": "题中直角三角形：水深x（勾）、池边到中心5尺（股）、芦苇长x+1（弦），符合勾股定理结构。选项A正确列出x² + 5² = (x+1)²；B、C颠倒了直角边与斜边关系；D是线性错误，未体现平方关系。本题直接对应课本第40页例2及第42页习题10。"
    }
   },
   "card": {
    "title": "勾股定理",
    "text": "在直角三角形中，两条直角边的平方和等于斜边的平方。这个概念解决了商高时代‘如何用已知直角边精确计算斜边长度’这一测量困境。",
    "formula": "a² + b² = c²",
    "textbook": "八年级 · 第二十章 勾股定理（第27页）"
   },
   "img": "assets/shang-gao.png"
  },
  {
   "id": "pythagoras",
   "eraEn": "550 B.C. · Croton 式",
   "eraTitle": "公元前550年 · 克罗顿 式",
   "briefing": [
    {
     "title": "时代困境：万物皆数，但‘数’是什么？",
     "text": "毕达哥拉斯学派信奉‘万物皆数’，但这里的‘数’仅指正整数及其比值（有理数）。他们用石子（pebbles）排成三角形、正方形来研究数的性质，认为一切几何量都可表示为整数之比。然而，当他们试图用‘数’描述最简单的等腰直角三角形（直角边长为1）的斜边时，陷入了困境：若斜边c是有理数，则存在互质整数p、q使c=p/q，代入c²=2得p²=2q²，推出p为偶数，进而q也为偶数，与‘互质’矛盾。这个困境暴露了‘有理数’不足以刻画所有几何长度。"
    },
    {
     "title": "毕达哥拉斯到底发现了什么？",
     "text": "史料虽未留存其原始证明，但据亚里士多德等后世记载，毕达哥拉斯学派确证了‘在直角三角形中，斜边上的正方形面积等于两直角边上正方形面积之和’。他们的证明是纯几何的：通过将斜边正方形分割、旋转、平移，恰好填满两个直角边正方形——不依赖代数运算，仅靠图形全等与面积守恒。这标志着**从特例计算到普遍性演绎证明的关键跃迁**：不再是‘对3-4-5成立’，而是‘对一切直角三角形必然成立’。"
    },
    {
     "title": "这一步为什么关键？",
     "text": "它首次将勾股关系确立为一条**必须被逻辑证明的几何定理**，而非经验归纳。这种演绎证明范式，成为欧氏几何的基石。更重要的是，它直接催生了数学史上第一次危机——当证明无可辩驳地显示‘√2’无法表示为整数比时，整个学派的哲学根基动摇。你即将学到的东西，此刻正在被这段历史发现：<span class='violet'>勾股定理的演绎证明</span>。"
    }
   ],
   "dialogues": [
    {
     "who": "毕达哥拉斯",
     "text": "看这石子阵！以勾、股为边的两方阵，其石子总数，必等于以弦为边的方阵。",
     "audio": "../../assets/audio/pythagorean-journey/pythagoras_dlg_0.wav"
    },
    {
     "who": "毕达哥拉斯",
     "text": "这不是巧合，是几何的必然——因全等变换不改变面积。",
     "audio": "../../assets/audio/pythagorean-journey/pythagoras_dlg_1.wav"
    },
    {
     "who": "学生",
     "text": "老师，若勾股皆为一，弦长该是多少？",
     "audio": "../../assets/audio/pythagorean-journey/pythagoras_dlg_2.wav"
    },
    {
     "who": "毕达哥拉斯",
     "text": "……此数不可通约。它动摇根基，却更显真理之坚——<b class='em'>证明本身，比结论更神圣</b>。",
     "audio": "../../assets/audio/pythagorean-journey/pythagoras_dlg_3.wav"
    }
   ],
   "choice": {
    "prompt": "面对‘勾股皆为一，弦长为何’的提问，毕达哥拉斯学派最可能持有的观点是：",
    "options": [
     {
      "t": "弦长是7/5，因(7/5)²=49/25≈2，足够精确",
      "d": 5,
      "r": "错。毕达哥拉斯学派追求绝对精确的理性证明，而非近似值。7/5只是逼近，不能消除‘不可通约’的根本矛盾。",
      "audio": "../../assets/audio/pythagorean-journey/pythagoras_opt_0.wav"
     },
     {
      "t": "弦长无法用整数或整数比表示，它是另一种新数",
      "d": 20,
      "r": "对！希帕索斯正是基于此发现不可通约量。学派虽震惊，但承认证明的效力——这体现了希腊数学‘宁信逻辑，不信直觉’的精神。",
      "audio": "../../assets/audio/pythagorean-journey/pythagoras_opt_1.wav"
     }
    ]
   },
   "freetalk": null,
   "interact": {
    "type": "custom-lab",
    "title": "毕达哥拉斯的石子证明",
    "intro": "用虚拟石子重现古希腊证明：拖动滑块改变直角边，观察斜边正方形如何被分割、移动，严丝合缝填满两个直角边正方形。",
    "config": {
     "sliders": [
      {
       "id": "a",
       "label": "勾长",
       "min": 1,
       "max": 6,
       "step": 1,
       "init": 3
      },
      {
       "id": "b",
       "label": "股长",
       "min": 1,
       "max": 6,
       "step": 1,
       "init": 4
      }
     ],
     "readouts": [
      {
       "label": "勾方石子数",
       "expr": "a * a"
      },
      {
       "label": "股方石子数",
       "expr": "b * b"
      },
      {
       "label": "弦方石子数",
       "expr": "a * a + b * b"
      }
     ],
     "big": {
      "label": "弦方边长",
      "expr": "Math.sqrt(a * a + b * b)"
     },
     "win": {
      "expr": "a > 0 && b > 0",
      "text": "见证奇迹：无论a、b取何值，弦方总能被精准分割、移动，严丝合缝覆盖勾方与股方！"
     }
    }
   },
   "afterChoice": [
    {
     "who": "矩尺之灵",
     "text": "毕达哥拉斯没有发明公式，他锻造了证明的铁砧——从此，数学不再是经验的汇总，而是逻辑的殿堂。",
     "audio": "../../assets/audio/pythagorean-journey/pythagoras_after_0.wav"
    },
    {
     "who": "矩尺之灵",
     "text": "课本第27页的定理，正是这座殿堂的第一根梁柱。",
     "audio": "../../assets/audio/pythagorean-journey/pythagoras_after_1.wav"
    }
   ],
   "bridge": {
    "textbook": "八年级 · 第二十章 勾股定理（第27页）",
    "mapping": [
     "毕达哥拉斯学派通过几何分割与全等变换，证明斜边正方形面积恒等于两直角边正方形面积之和，用今天课本的语言严格地说，就是勾股定理的几何证明——因为面积守恒是欧氏几何的基本公理，而a² + b² = c²正是该面积等式的代数表达，课本第27页的定理陈述，正是对此几何证明结论的凝练。"
    ],
    "quiz": {
     "q": "下列哪项是毕达哥拉斯学派证明勾股定理所依赖的核心思想？",
     "options": [
      "A. 代数运算的交换律",
      "B. 图形全等与面积守恒",
      "C. 相似三角形的比例关系",
      "D. 无限小量的极限思想"
     ],
     "answer": 1,
     "explain": "毕达哥拉斯证明是纯几何的，依靠将斜边正方形切割、旋转、平移后，与两个直角边正方形完全重合，其基础是图形全等（形状大小相同）与面积守恒（变换不改变面积）。A是代数性质，C是欧几里得后来发展的方法，D属微积分范畴，均非其时代知识。本题对应课本第28页‘探究’栏目对证明思路的引导。"
    }
   },
   "card": {
    "title": "勾股定理的几何证明",
    "text": "通过图形分割、旋转、平移实现面积守恒，从而证明斜边正方形面积等于两直角边正方形面积之和。这个概念解决了毕达哥拉斯时代‘如何为普遍性关系提供不可辩驳的逻辑依据’这一哲学困境。",
    "formula": "S_{弦方} = S_{勾方} + S_{股方}",
    "textbook": "八年级 · 第二十章 勾股定理（第28页）"
   },
   "img": "assets/pythagoras.png"
  },
  {
   "id": "hippasus",
   "eraEn": "500 B.C. · Mediterranean Sea 式",
   "eraTitle": "公元前500年 · 地中海 式",
   "briefing": [
    {
     "title": "时代困境：当‘万物皆数’遭遇√2",
     "text": "毕达哥拉斯学派将‘数’严格限定为正整数及其比值（有理数），并认为所有几何量（如线段长度）都可表示为两整数之比（即可通约）。这一信条是其整个宇宙观的基础。然而，对等腰直角三角形（直角边长为1）的斜边长度，按勾股定理得c²=2。若c是有理数，则存在互质整数p、q使c=p/q，代入得p²=2q²，故p为偶数，设p=2k，则4k²=2q² ⇒ q²=2k² ⇒ q也为偶数，与p、q互质矛盾。这个困境直接挑战了学派的哲学根基。"
    },
    {
     "title": "希帕索斯到底发现了什么？",
     "text": "希帕索斯通过严谨的反证法，证明了‘√2是无理数’——即它不能表示为两个整数的比。这不是数值计算的失败，而是对‘数’之定义的根本突破：存在一类新的数，它们是几何存在的（作为真实线段长度），却无法用当时定义的‘数’来表达。他的发现表明，勾股定理揭示的不仅是边长关系，更是一道横亘在算术与几何之间的深渊。"
    },
    {
     "title": "这一步为什么关键？",
     "text": "它引发了数学史上第一次危机，迫使数学家重新思考‘数’的本质，最终催生了实数理论。更重要的是，它证明了勾股定理不仅是一个计算工具，更是一面照见数学基础的镜子——它既统一了几何与代数，也暴露了二者最初的裂痕。你即将学到的东西，此刻正在被这段历史发现：<span class='violet'>无理数的存在性</span>。"
    }
   ],
   "dialogues": [
    {
     "who": "希帕索斯",
     "text": "老师，若勾股皆为一，弦长c必满足c²=2。",
     "audio": "../../assets/audio/pythagorean-journey/hippasus_dlg_0.wav"
    },
    {
     "who": "希帕索斯",
     "text": "假设c=p/q（p,q互质），则p²=2q²，故p为偶数……q亦为偶数！矛盾！",
     "audio": "../../assets/audio/pythagorean-journey/hippasus_dlg_1.wav"
    },
    {
     "who": "毕达哥拉斯",
     "text": "……此乃渎神。将他逐出学派。",
     "audio": "../../assets/audio/pythagorean-journey/hippasus_dlg_2.wav"
    },
    {
     "who": "希帕索斯",
     "text": "不，老师，这是真理——<b class='em'>√2真实存在，只是我们的‘数’还不够</b>。",
     "audio": "../../assets/audio/pythagorean-journey/hippasus_dlg_3.wav"
    }
   ],
   "choice": {
    "prompt": "希帕索斯的证明中，最关键的前提假设是：",
    "options": [
     {
      "t": "所有数都能写成分数形式",
      "d": 5,
      "r": "错。这是毕达哥拉斯学派的信条，但希帕索斯恰恰要推翻它。他的证明始于‘假设c是有理数’，然后导出矛盾，从而否定该假设。",
      "audio": "../../assets/audio/pythagorean-journey/hippasus_opt_0.wav"
     },
     {
      "t": "p和q可以约去所有公因数，成为互质整数",
      "d": 20,
      "r": "对！‘互质’是反证法的关键：若p、q有公因数，可不断约简直至互质。正因如此，p、q同为偶数才构成矛盾——因为互质数不可能同为偶数。",
      "audio": "../../assets/audio/pythagorean-journey/hippasus_opt_1.wav"
     }
    ]
   },
   "freetalk": null,
   "interact": {
    "type": "tycho-data",
    "title": "不可通约的证据",
    "intro": "希帕索斯检查了不同边长的等腰直角三角形，计算斜边长是否可表示为分数。",
    "rows": [
     {
      "date": "边长1",
      "obs": 25.1,
      "pred": 19.7,
      "dev": 5.4
     },
     {
      "date": "边长2",
      "obs": 18.7,
      "pred": 17.7,
      "dev": 1.0
     },
     {
      "date": "边长3",
      "obs": 18.2,
      "pred": 17.3,
      "dev": 0.9
     },
     {
      "date": "边长4",
      "obs": 17.2,
      "pred": 18.3,
      "dev": -1.1
     },
     {
      "date": "边长5",
      "obs": 19.8,
      "pred": 20.8,
      "dev": -1.0
     },
     {
      "date": "边长6",
      "obs": 18.2,
      "pred": 19.3,
      "dev": -1.1
     },
     {
      "date": "边长7",
      "obs": 18.8,
      "pred": 19.5,
      "dev": -0.7
     },
     {
      "date": "边长8",
      "obs": 18.8,
      "pred": 18.1,
      "dev": 0.7
     },
     {
      "date": "边长9",
      "obs": 20.8,
      "pred": 20.4,
      "dev": 0.4
     },
     {
      "date": "边长10",
      "obs": 20.8,
      "pred": 19.9,
      "dev": 0.9
     }
    ],
    "cols": [
     "边长",
     "实测斜边长",
     "理论值√2×边长",
     "偏差"
    ],
    "hint": "希帕索斯发现，无论边长取何整数，斜边长都无法精确表示为分数。请找出哪一行的数据最有力地支持了他的结论？",
    "conclusion": "所有行的‘偏差’均为0，说明理论预测完美，但‘实测斜边长’列的小数都是无限不循环的——这正是无理数的特征：它存在、可测、但无法用有限小数或分数精确表达。"
   },
   "afterChoice": [
    {
     "who": "矩尺之灵",
     "text": "希帕索斯没有推翻勾股定理，他让定理变得更深刻——原来，真理有时会刺破我们最珍视的信念。",
     "audio": "../../assets/audio/pythagorean-journey/hippasus_after_0.wav"
    },
    {
     "who": "矩尺之灵",
     "text": "课本第32页‘二次根式’的学习，正是为了拥抱√2这样的新朋友。",
     "audio": "../../assets/audio/pythagorean-journey/hippasus_after_1.wav"
    }
   ],
   "bridge": {
    "textbook": "八年级 · 第十九章 二次根式（第27-37页）",
    "mapping": [
     "希帕索斯证明√2不能表示为整数之比，这在今天的课本语言里就是引入二次根式——因为形如√a（a为非完全平方数）的数，其本质是求解x²=a所得的正实数解，它无法化为有理数，必须作为独立的数类处理，课本第27页‘二次根式’的定义，正是为容纳此类由勾股定理自然产生的数。"
    ],
    "quiz": {
     "q": "下列各式中，属于最简二次根式的是：",
     "options": [
      "A. √8",
      "B. √12",
      "C. √18",
      "D. √2"
     ],
     "answer": 3,
     "explain": "最简二次根式要求被开方数不含能开得尽方的因数。A=√(4×2)=2√2，B=√(4×3)=2√3，C=√(9×2)=3√2，均含平方因数；D=√2，2是质数，无平方因数，故为最简。本题对应课本第29页‘最简二次根式’定义及例3。"
    }
   },
   "card": {
    "title": "二次根式",
    "text": "形如√a（a≥0）的式子，其中a是非负数。这个概念解决了希帕索斯时代‘如何表示和运算像√2这样无法用整数比表达的几何长度’这一基础困境。",
    "formula": "√a \\quad (a \\geq 0)",
    "textbook": "八年级 · 第十九章 二次根式（第27页）"
   },
   "img": "assets/hippasus.png"
  },
  {
   "id": "euclid",
   "eraEn": "300 B.C. · Alexandria 式",
   "eraTitle": "公元前300年 · 亚历山大 式",
   "briefing": [
    {
     "title": "时代困境：如何让几何知识自洽且可传播？",
     "text": "在欧几里得之前，几何知识零散分布于各种实践手册（如埃及土地测量）和学派秘传（如毕达哥拉斯学派）。缺乏统一公理体系，不同结论间可能存在隐含矛盾，知识难以系统传授。欧几里得的目标，是构建一座‘几何大厦’：从少数不证自明的公理（如‘两点确定一条直线’）出发，通过逻辑演绎，推导出所有几何定理。勾股定理，必须成为这座大厦中一块被严格奠基的基石。"
    },
    {
     "title": "欧几里得到底证明了什么？",
     "text": "在《几何原本》第一卷命题47，欧几里得给出了勾股定理的经典证明。他构造了以直角三角形三边为边的三个正方形，然后通过作辅助线（从直角顶点向斜边正方形作垂线），证明了勾方、股方分别与斜边正方形内的两个矩形面积相等。其核心是运用了三角形全等（SAS）和等底等高三角形面积相等这两个基本公理。这是一个**完全公理化的、可被任何人按步骤复现的证明**。"
    },
    {
     "title": "这一步为什么关键？",
     "text": "它将勾股定理彻底纳入公理化体系，使其不再是孤立的结论，而是欧氏几何逻辑链条中必然的一环。从此，任何关于直角三角形的计算，都有了坚不可摧的理论保障。更重要的是，这种‘公理-定义-定理-证明’的范式，成为后世所有数学分支的模板。你即将学到的东西，此刻正在被这段历史发现：<span class='violet'>公理化证明体系</span>。"
    }
   ],
   "dialogues": [
    {
     "who": "欧几里得",
     "text": "公理如基石，定义如梁柱，定理如屋宇。",
     "audio": "../../assets/audio/pythagorean-journey/euclid_dlg_0.wav"
    },
    {
     "who": "欧几里得",
     "text": "看，由公理可知：全等三角形面积相等；等底等高三角形面积相等。",
     "audio": "../../assets/audio/pythagorean-journey/euclid_dlg_1.wav"
    },
    {
     "who": "学生",
     "text": "那么，勾方与股方，如何等于弦方？",
     "audio": "../../assets/audio/pythagorean-journey/euclid_dlg_2.wav"
    },
    {
     "who": "欧几里得",
     "text": "只需作此垂线，证此两组全等——<b class='em'>逻辑自会铺就道路</b>。",
     "audio": "../../assets/audio/pythagorean-journey/euclid_dlg_3.wav"
    }
   ],
   "choice": {
    "prompt": "欧几里得证明中，最关键的辅助线是：",
    "options": [
     {
      "t": "连接斜边中点与直角顶点",
      "d": 5,
      "r": "错。这会产生中线，但与面积分割无关。欧几里得的证明依赖将弦方分割为两个矩形，需从直角顶点向弦方作垂线。",
      "audio": "../../assets/audio/pythagorean-journey/euclid_opt_0.wav"
     },
     {
      "t": "从直角顶点向斜边作垂线，并延长交弦方对边",
      "d": 20,
      "r": "对！这条垂线将弦方分为两个矩形，再通过全等三角形证明每个矩形面积分别等于勾方、股方。这是《几何原本》I.47的标准构造。",
      "audio": "../../assets/audio/pythagorean-journey/euclid_opt_1.wav"
     }
    ]
   },
   "freetalk": null,
   "interact": {
    "type": "custom-lab",
    "title": "欧几里得的公理之桥",
    "intro": "跟随《几何原本》的步骤：拖动滑块设定直角边，观察欧几里得如何用辅助线与全等三角形，将勾方、股方‘搬进’弦方。",
    "config": {
     "sliders": [
      {
       "id": "a",
       "label": "勾长",
       "min": 2,
       "max": 8,
       "step": 1,
       "init": 3
      },
      {
       "id": "b",
       "label": "股长",
       "min": 2,
       "max": 8,
       "step": 1,
       "init": 4
      }
     ],
     "readouts": [
      {
       "label": "勾方面积",
       "expr": "a * a"
      },
      {
       "label": "股方面积",
       "expr": "b * b"
      },
      {
       "label": "弦方面积",
       "expr": "a * a + b * b"
      }
     ],
     "big": {
      "label": "弦方边长",
      "expr": "Math.sqrt(a * a + b * b)"
     },
     "win": {
      "expr": "a > 0 && b > 0",
      "text": "公理在此：全等三角形面积相等，等底等高三角形面积相等——逻辑的齿轮严丝合缝咬合！"
     }
    }
   },
   "afterChoice": [
    {
     "who": "矩尺之灵",
     "text": "欧几里得没有创造新定理，他为旧真理建造了不朽的殿堂。",
     "audio": "../../assets/audio/pythagorean-journey/euclid_after_0.wav"
    },
    {
     "who": "矩尺之灵",
     "text": "课本第27页的定理，就站在这个殿堂最醒目的位置。",
     "audio": "../../assets/audio/pythagorean-journey/euclid_after_1.wav"
    }
   ],
   "bridge": {
    "textbook": "八年级 · 第二十章 勾股定理（第27页）",
    "mapping": [
     "欧几里得在《几何原本》中，从公理‘等底等高三角形面积相等’和‘SAS全等判定’出发，严格证明了勾方与股方面积之和等于弦方面积，用今天课本的语言严格地说，就是勾股定理的公理化证明——因为课本第27页的定理，正是建立在欧氏几何公理体系之上，其有效性依赖于这些不证自明的基本原理。"
    ],
    "quiz": {
     "q": "在Rt△ABC中，∠C=90°，AC=2.1，BC=2.8。求斜边AB的长。",
     "options": [
      "A. 4.9",
      "B. 3.5",
      "C. 7.0",
      "D. 5.0"
     ],
     "answer": 1,
     "explain": "根据勾股定理，AB² = AC² + BC² = 2.1² + 2.8² = 4.41 + 7.84 = 12.25，故AB = √12.25 = 3.5。本题直接应用课本第27页定理，对应课本第38页习题8(2)。"
    }
   },
   "card": {
    "title": "公理化体系",
    "text": "从少数不证自明的公理出发，通过逻辑演绎推导出全部定理的数学体系。这个概念解决了欧几里得时代‘如何确保几何知识自洽、无矛盾且可系统传承’这一结构性困境。",
    "formula": "公理 → 定义 → 定理 → 证明",
    "textbook": "八年级 · 第二十章 勾股定理（第27页）"
   },
   "img": "assets/euclid.png"
  },
  {
   "id": "zhao-shuang",
   "eraEn": "220 A.D. · Luoyang 式",
   "eraTitle": "公元220年 · 洛阳 式",
   "briefing": [
    {
     "title": "时代困境：如何让证明既严谨又直观？",
     "text": "三国时期，中国数学家面临一个独特挑战：既要符合《九章算术》‘出入相补’（面积守恒）的传统，又要超越商高的特例，给出普遍性证明。当时的主流是‘算术化’证明（如刘徽注《九章》），但赵爽选择了一条视觉震撼的道路——他需要一种方法，让任何文化程度的人，一眼就能看出‘a² + b² = c²’为何必然成立。"
    },
    {
     "title": "赵爽到底证明了什么？",
     "text": "赵爽在为《周髀算经》作注时，创造了著名的‘弦图’：将四个全等的直角三角形（勾a、股b、弦c）按特定方式排列在一个大正方形内，中间留出一个小正方形空隙。他计算大正方形面积为c²，同时它又等于四个三角形面积（4×½ab）加中间小正方形面积（b−a）²，即c² = 2ab + (b−a)² = a² + b²。这是一个**代数与几何完美融合的证明**：用面积守恒（几何）导出代数恒等式（a² + b² = c²）。"
    },
    {
     "title": "这一步为什么关键？",
     "text": "它是中国数学史上首个对勾股定理的严格证明，且以极其简洁、优美的图形呈现。‘弦图’不仅是证明，更是教学神器——它让抽象关系变得可视、可触、可讲。2002年北京国际数学家大会会标，正是赵爽弦图，彰显其跨越时空的智慧光芒。你即将学到的东西，此刻正在被这段历史发现：<span class='violet'>勾股定理的代数-几何综合证明</span>。"
    }
   ],
   "dialogues": [
    {
     "who": "赵爽",
     "text": "请看此图：四直角三角形，围成一弦方。",
     "audio": "../../assets/audio/pythagorean-journey/zhao-shuang_dlg_0.wav"
    },
    {
     "who": "赵爽",
     "text": "弦方之积，即四勾股之积，加中黄实之积。",
     "audio": "../../assets/audio/pythagorean-journey/zhao-shuang_dlg_1.wav"
    },
    {
     "who": "学生",
     "text": "即(b−a)²，故c² = 2ab + (b−a)² = a² + b²。",
     "audio": "../../assets/audio/pythagorean-journey/zhao-shuang_dlg_2.wav"
    },
    {
     "who": "赵爽",
     "text": "此乃‘以形证数’——<b class='em'>图在，理在</b>！",
     "audio": "../../assets/audio/pythagorean-journey/zhao-shuang_dlg_3.wav"
    }
   ],
   "choice": {
    "prompt": "赵爽弦图中，中间小正方形（中黄实）的边长是：",
    "options": [
     {
      "t": "a + b",
      "d": 5,
      "r": "错。a+b是大正方形边长，中间小正方形边长应为两直角边之差。",
      "audio": "../../assets/audio/pythagorean-journey/zhao-shuang_opt_0.wav"
     },
     {
      "t": "|b − a|",
      "d": 20,
      "r": "对！当b>a时，小正方形边长为b−a；反之为a−b。赵爽原文‘中黄实’即指此差值的平方，是弦图证明的关键。",
      "audio": "../../assets/audio/pythagorean-journey/zhao-shuang_opt_1.wav"
     }
    ]
   },
   "freetalk": null,
   "interact": {
    "type": "custom-lab",
    "title": "赵爽弦图",
    "intro": "亲手组装赵爽的智慧：拖动滑块设定勾、股，观察四个三角形如何排列，中间小正方形如何浮现，面积关系如何自动成立。",
    "config": {
     "sliders": [
      {
       "id": "a",
       "label": "勾长",
       "min": 1,
       "max": 6,
       "step": 1,
       "init": 3
      },
      {
       "id": "b",
       "label": "股长",
       "min": 1,
       "max": 6,
       "step": 1,
       "init": 4
      }
     ],
     "readouts": [
      {
       "label": "弦方面积 c²",
       "expr": "(a*a + b*b)"
      },
      {
       "label": "四三角形面积",
       "expr": "2 * a * b"
      },
      {
       "label": "中黄实面积 (b−a)²",
       "expr": "(b - a) * (b - a)"
      }
     ],
     "big": {
      "label": "验证：c² = 2ab + (b−a)²",
      "expr": "(a*a + b*b) === (2*a*b + (b-a)*(b-a))"
     },
     "win": {
      "expr": "(a*a + b*b) === (2*a*b + (b-a)*(b-a))",
      "text": "弦图成立！代数与几何在此刻握手言和。"
     }
    }
   },
   "afterChoice": [
    {
     "who": "矩尺之灵",
     "text": "赵爽没有用希腊的公理，也没有用巴比伦的表格，他用一幅画，让真理自己开口说话。",
     "audio": "../../assets/audio/pythagorean-journey/zhao-shuang_after_0.wav"
    },
    {
     "who": "矩尺之灵",
     "text": "课本第27页的等式，就是这幅画最凝练的题跋。",
     "audio": "../../assets/audio/pythagorean-journey/zhao-shuang_after_1.wav"
    }
   ],
   "bridge": {
    "textbook": "八年级 · 第二十章 勾股定理（第27页）",
    "mapping": [
     "赵爽通过弦图，将大正方形面积c²表示为四个直角三角形面积2ab与中间小正方形面积(b−a)²之和，从而得到c² = 2ab + (b−a)² = a² + b²，用今天课本的语言严格地说，就是勾股定理的代数-几何综合证明——因为该恒等式是代数运算的直接结果，而其几何背景（面积守恒）又为代数推导提供了坚实支撑，课本第27页的定理，正是这种双重验证的结晶。"
    ],
    "quiz": {
     "q": "我国汉代数学家赵爽的‘弦图’，巧妙地证明了勾股定理。若直角三角形两直角边分别为a、b（a<b），则弦图中中间小正方形的面积为：",
     "options": [
      "A. a² + b²",
      "B. (a + b)²",
      "C. (b − a)²",
      "D. ab"
     ],
     "answer": 2,
     "explain": "弦图中，四个全等直角三角形围成大正方形（边长为c），中间空隙为小正方形，其边长为两直角边之差，即b−a（因a<b），故面积为(b−a)²。本题直接考查课本第28页‘赵爽弦图’插图的理解，对应教材‘阅读与思考’栏目。"
    }
   },
   "card": {
    "title": "赵爽弦图",
    "text": "用四个全等直角三角形拼成大正方形，中间形成小正方形，通过面积计算证明a² + b² = c²。这个概念解决了赵爽时代‘如何让普遍性定理既逻辑严谨又直观易懂’这一教学困境。",
    "formula": "c^2 = 4 \\times \\frac{1}{2}ab + (b-a)^2 = a^2 + b^2",
    "textbook": "八年级 · 第二十章 勾股定理（第28页）"
   },
   "img": "assets/zhao-shuang.png"
  },
  {
   "id": "epilogue",
   "eraEn": "2024 A.D. · Classroom 式",
   "eraTitle": "终章 · 2024年 · 教室 式",
   "briefing": [
    {
     "title": "你手中握着的，是四千年的重量",
     "text": "从商高‘积矩’的朴素洞察，到毕达哥拉斯的几何证明；从希帕索斯撕开‘万物皆数’的帷幕，到欧几里得为其铸就公理基石；再到赵爽以‘弦图’让真理跃然纸上——这条路上，没有神谕，只有尺规、石子、竹简与墨迹。你课本第27页的那个等式，不是冰冷的符号，而是人类用理性丈量世界时，刻下的第一道永恒刻度。它告诉我们：在看似混沌的天地间，存在着不容置疑的、可被计算的秩序。"
    }
   ],
   "dialogues": [
    {
     "who": "矩尺之灵",
     "text": "现在，你知道我的真名了吗？",
     "audio": "../../assets/audio/pythagorean-journey/epilogue_dlg_0.wav"
    },
    {
     "who": "矩尺之灵",
     "text": "我不是神，不是仙，不是某个遥远的名字——",
     "audio": "../../assets/audio/pythagorean-journey/epilogue_dlg_1.wav"
    },
    {
     "who": "矩尺之灵",
     "text": "我是你笔下写出的 <b class='em'>a² + b² = c²</b>，",
     "audio": "../../assets/audio/pythagorean-journey/epilogue_dlg_2.wav"
    },
    {
     "who": "矩尺之灵",
     "text": "是课本第27页那个简洁、坚定、穿越四千年风雨的——<b class='em'>勾股定理</b>。",
     "audio": "../../assets/audio/pythagorean-journey/epilogue_dlg_3.wav"
    }
   ],
   "choice": null,
   "freetalk": null,
   "interact": null,
   "afterChoice": null,
   "bridge": null,
   "card": null,
   "img": "assets/epilogue.png"
  }
 ],
 "APP_STORY": [
  {
   "id": "surveying",
   "eraEn": "2024 A.D. · Yangtze River 式",
   "eraTitle": "应用篇 · 2024年 · 长江大桥测绘现场",
   "briefing": [
    {
     "title": "测绘工程师林薇的挑战",
     "text": "长江某支流需新建一座斜拉桥。设计要求主塔A与锚碇B的直线距离（跨径）必须精确为850米。但河面宽阔、地形复杂，无法直接拉尺测量。林薇团队采用‘三角测量法’：在岸边选定第三点C，测得AC=500米，BC=600米，且∠ACB=90°（通过精密经纬仪调校）。此刻，她需要立刻确认AB是否真为850米，以决定是否调整C点位置。"
    }
   ],
   "dialogues": [
    {
     "who": "林薇",
     "text": "AC是五百米，BC是六百米，夹角是直角。那么AB应该等于根号下五百的平方加六百的平方。",
     "audio": "../../assets/audio/pythagorean-journey/surveying_dlg_0.wav"
    },
    {
     "who": "林薇",
     "text": "五百平方是二十五万，六百平方是三十六万，加起来是六十一万。",
     "audio": "../../assets/audio/pythagorean-journey/surveying_dlg_1.wav"
    },
    {
     "who": "林薇",
     "text": "六十一万的平方根……让我心算一下，七百八十的平方是六十万八千四百，七百八十一的平方是六十一万零一百六十一。所以大约是七百八十一米。",
     "audio": "../../assets/audio/pythagorean-journey/surveying_dlg_2.wav"
    },
    {
     "who": "林薇",
     "text": "但设计要求是八百五十米——差了六十多米！必须重新选点C。",
     "audio": "../../assets/audio/pythagorean-journey/surveying_dlg_3.wav"
    }
   ],
   "choice": {
    "prompt": "林薇的计算哪里出错了？",
    "options": [
     {
      "t": "她误用了余弦定理，没注意角度是九十度",
      "d": 5,
      "r": "错。余弦定理在直角时退化为勾股定理，她用的就是勾股定理，方向正确。",
      "audio": "../../assets/audio/pythagorean-journey/surveying_opt_0.wav"
     },
     {
      "t": "她计算500²+600²时出错：500²=250000，600²=360000，和应为610000，但√610000≠781，正确值是√610000≈781.02，仍远小于850",
      "d": 20,
      "r": "对！她的计算过程正确，但结果781米与850米差距显著，说明∠ACB并非严格90°，或距离测量有误差。必须调整C点或复核仪器。",
      "audio": "../../assets/audio/pythagorean-journey/surveying_opt_1.wav"
     }
    ]
   },
   "afterChoice": [
    {
     "who": "林薇",
     "text": "明白了！勾股定理是检验直角的金标准——如果AC²+BC²≠AB²，那这个角就不是真正的直角。",
     "audio": "../../assets/audio/pythagorean-journey/surveying_after_0.wav"
    },
    {
     "who": "林薇",
     "text": "现在，我要重新校准仪器，或者换个更开阔的C点。",
     "audio": "../../assets/audio/pythagorean-journey/surveying_after_1.wav"
    }
   ],
   "img": "assets/surveying.png"
  },
  {
   "id": "navigation",
   "eraEn": "2024 A.D. · Shanghai Port 式",
   "eraTitle": "应用篇 · 2024年 · 上海洋山港智能调度中心",
   "briefing": [
    {
     "title": "调度员张磊的实时决策",
     "text": "洋山港四期自动化码头，AGV（自动导引车）需从堆场A点（坐标(0,0)）运送集装箱至码头B点（坐标(120,160)）。系统规划路径为直线，但需实时计算行驶距离以预估耗时和电量。当前AGV电量仅够行驶200米，张磊必须立刻判断：此单任务是否可行？"
    }
   ],
   "dialogues": [
    {
     "who": "张磊",
     "text": "A点是零零，B点是一二零、一六零。那么横向距离是一百二十米，纵向是一百六十米。",
     "audio": "../../assets/audio/pythagorean-journey/navigation_dlg_0.wav"
    },
    {
     "who": "张磊",
     "text": "因为是直角坐标系，所以行驶距离就是根号下一百二十的平方加一百六十的平方。",
     "audio": "../../assets/audio/pythagorean-journey/navigation_dlg_1.wav"
    },
    {
     "who": "张磊",
     "text": "一百二十平方是一万四千四百，一百六十平方是两万五千六百，加起来是四万。",
     "audio": "../../assets/audio/pythagorean-journey/navigation_dlg_2.wav"
    },
    {
     "who": "张磊",
     "text": "四万的平方根是二百。刚好！电量够用，可以派车。",
     "audio": "../../assets/audio/pythagorean-journey/navigation_dlg_3.wav"
    }
   ],
   "choice": {
    "prompt": "张磊的判断依据是什么？",
    "options": [
     {
      "t": "他使用了相似三角形比例关系估算距离",
      "d": 5,
      "r": "错。相似三角形用于未知边长比例，此处坐标已知，需精确距离，勾股定理是唯一标准方法。",
      "audio": "../../assets/audio/pythagorean-journey/navigation_opt_0.wav"
     },
     {
      "t": "他用坐标差值构造直角三角形，应用勾股定理计算斜边长",
      "d": 20,
      "r": "对！在平面直角坐标系中，两点间距离公式d=√[(x₂−x₁)²+(y₂−y₁)²]正是勾股定理的直接应用。张磊的计算完全正确。",
      "audio": "../../assets/audio/pythagorean-journey/navigation_opt_1.wav"
     }
    ]
   },
   "afterChoice": [
    {
     "who": "张磊",
     "text": "课本上学的勾股定理，此刻就是AGV车轮下真实的二百米。",
     "audio": "../../assets/audio/pythagorean-journey/navigation_after_0.wav"
    },
    {
     "who": "张磊",
     "text": "每一个精确的‘根号下’，都在为港口的脉搏计时。",
     "audio": "../../assets/audio/pythagorean-journey/navigation_after_1.wav"
    }
   ],
   "img": "assets/navigation.png"
  }
 ],
 "RIVER": [
  {
   "stage": "诞 生",
   "era": "公元前1000年",
   "who": "商高",
   "did": "提出‘勾广三，股修四，径隅五’的特例与‘积矩’的普遍性思想",
   "pass": "将直角三角形的边长关系，从经验口诀升华为可计算的数学对象"
  },
  {
   "stage": "证 明",
   "era": "公元前550年",
   "who": "毕达哥拉斯学派",
   "did": "完成首个演绎几何证明，确立其为普遍定理",
   "pass": "为数学注入逻辑证明的灵魂，让真理不再依赖权威，而依赖推理"
  },
  {
   "stage": "震 撼",
   "era": "公元前500年",
   "who": "希帕索斯",
   "did": "发现√2不可通约，揭示有理数的局限",
   "pass": "逼迫人类拓展‘数’的疆域，为实数理论埋下第一颗种子"
  },
  {
   "stage": "体 系",
   "era": "公元前300年",
   "who": "欧几里得",
   "did": "在《几何原本》中将其纳入公理化体系",
   "pass": "让勾股定理成为一座宏伟几何大厦中，最稳固的基石之一"
  },
  {
   "stage": "融 合",
   "era": "公元220年",
   "who": "赵爽",
   "did": "创制‘弦图’，实现代数与几何的完美统一",
   "pass": "证明可以既是严谨的，又是美的；既是理性的，又可被所有人看见"
  }
 ],
 "RIVER_BOOK": "八年级数学核心内容，是连接几何直观与代数运算的枢纽，为后续学习二次根式、平面直角坐标系、三角函数奠定不可或缺的基础。",
 "RIVER_APPS": [
  "⚓ 海港调度 —— 平面直角坐标系中两点距离计算",
  "🏗️ 大桥测绘 —— 利用勾股定理检验直角与测量精度",
  "🛰️ 卫星定位 —— GPS接收器通过多颗卫星信号时间差解算三维位置（本质是空间勾股定理）",
  "🏥 医学影像 —— CT扫描重建图像时，像素点强度由多个方向投影数据按勾股关系合成",
  "🎮 游戏物理 —— 角色移动、碰撞检测、视角旋转均依赖向量模长（即勾股定理）计算"
 ],
 "RIVER_QUOTE": "我不是来自神庙的启示，也不是刻在石碑上的律令。我是你每一次用尺规丈量、用笔尖计算、用心灵确认时，心底响起的那个清晰而坚定的声音：a² + b² = c²。",
 "RIVER_QUOTE_AUDIO": "../../assets/audio/pythagorean-journey/river_quote.wav",
 "TYCHO_DATA": [
  {
   "date": "边长1",
   "obs": 25.1,
   "pred": 19.7,
   "dev": 5.4
  },
  {
   "date": "边长2",
   "obs": 18.7,
   "pred": 17.7,
   "dev": 1.0
  },
  {
   "date": "边长3",
   "obs": 18.2,
   "pred": 17.3,
   "dev": 0.9
  },
  {
   "date": "边长4",
   "obs": 17.2,
   "pred": 18.3,
   "dev": -1.1
  },
  {
   "date": "边长5",
   "obs": 19.8,
   "pred": 20.8,
   "dev": -1.0
  },
  {
   "date": "边长6",
   "obs": 18.2,
   "pred": 19.3,
   "dev": -1.1
  },
  {
   "date": "边长7",
   "obs": 18.8,
   "pred": 19.5,
   "dev": -0.7
  },
  {
   "date": "边长8",
   "obs": 18.8,
   "pred": 18.1,
   "dev": 0.7
  },
  {
   "date": "边长9",
   "obs": 20.8,
   "pred": 20.4,
   "dev": 0.4
  },
  {
   "date": "边长10",
   "obs": 20.8,
   "pred": 19.9,
   "dev": 0.9
  }
 ],
 "ENDINGS": [
  {
   "min": 149,
   "rank": "TRUE END",
   "title": "执 火 者",
   "text": "你没有“学完”它——你和它一起，重新诞生了一次。这条长河，如今有一部分属于你。"
  },
  {
   "min": 104,
   "rank": "GOOD END",
   "title": "同 行 者",
   "text": "你见证了它的重生，并在大多数历史关头做出了与伟大心灵相同的选择。仍有一些岔路值得重返。"
  },
  {
   "min": 0,
   "rank": "NORMAL END",
   "title": "拾 星 者",
   "text": "你走完了整条长河，捡起了一些星光。知识之境没有时间的尽头——随时回来。"
  }
 ]
};
