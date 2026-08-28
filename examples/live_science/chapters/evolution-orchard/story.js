/* 知识之境 · 篇章数据（由工厂生成） */
window.STORY_DATA = {
 "META": {
  "title": "进化论 · 生命之树的年轮",
  "subtitle": "从拉马克的藤蔓到现代综合的根系——一场跨越两百年的证据长征",
  "guide_name": "年轮守望者",
  "cast": {
   "拉马克": "m",
   "达尔文": "m",
   "魏斯曼": "m",
   "杜布赞斯基": "m"
  }
 },
 "STORY": [
  {
   "id": "anaximander-prologue",
   "eraEn": "c.580 B.C.E. · Miletus",
   "eraTitle": "公元前580年 · 米利都",
   "briefing": [
    {
     "title": "时代困境：万物何来？",
     "text": "在荷马与赫西俄德的神谱统治下，世界由宙斯之怒、雅典娜之智或阿佛洛狄忒之爱所造。没有‘起源’的物理机制——只有意志。当阿那克西曼德凝视潮水退去后裸露的泥滩上干裂的鱼形印痕，他第一次提出：<span class=\"violet\">生命可从水中自发生成</span>，且人类幼体曾如鱼般在湿润中发育。这并非猜想，而是对自然现象的首次去神化观察。但问题悬而未决：若生命能自生，为何今日不见新物种凭空涌现？"
    }
   ],
   "dialogues": [
    {
     "who": "旁白",
     "text": "海风卷走沙粒，也卷走了神谕的余音。",
     "audio": "../../assets/audio/evolution-orchard/anaximander-prologue_dlg_0.wav"
    },
    {
     "who": "年轮守望者",
     "text": "你看见那枚卵石了吗？它没名字，却比所有神名更古老——<b class=\"em\">它只是存在过</b>。",
     "audio": "../../assets/audio/evolution-orchard/anaximander-prologue_dlg_1.wav"
    }
   ],
   "choice": {
    "prompt": "面对泥滩上的鱼形印痕，你会如何解释其成因？",
    "options": [
     {
      "t": "这是波塞冬用三叉戟刻下的印记，预示丰年",
      "d": 5,
      "r": "神迹无法验证，也无法预测下一次潮水会留下什么形状。我们暂且放下三叉戟。",
      "audio": "../../assets/audio/evolution-orchard/anaximander-prologue_opt_0.wav"
     },
     {
      "t": "干湿交替使泥浆收缩，偶然形成类似鱼形的裂纹",
      "d": 20,
      "r": "对！你抓住了关键：<b class=\"em\">形态可由物理过程自发产生</b>——无需神意，只需时间与条件。",
      "audio": "../../assets/audio/evolution-orchard/anaximander-prologue_opt_1.wav"
     }
    ]
   },
   "freetalk": {
    "hint": "出发之前，还有什么想和我聊聊的吗？",
    "persona": "一位沉默的观察者，只知晓公元前580年之前的人类知识；不提‘进化’‘遗传’‘物种’等后世概念；坚信水是万物本原；随身携带的卵石是唯一证物。",
    "presets": [
     {
      "q": "您相信人是从鱼变来的吗？",
      "a": "我只说：初生之婴，在母腹中带鳃裂，如鱼；出水后鳃裂闭合，如岸。这像不像潮水退去又涨回？",
      "audio": "../../assets/audio/evolution-orchard/anaximander-prologue_preset_0.wav"
     }
    ]
   },
   "interact": null,
   "afterChoice": [
    {
     "who": "年轮守望者",
     "text": "你让裂纹说话了——而神庙的祭司，还在等雷声作答。",
     "audio": "../../assets/audio/evolution-orchard/anaximander-prologue_after_0.wav"
    }
   ],
   "bridge": {
    "textbook": "高中生物学必修二 · 第一章第一节「人类探索遗传物质的历程」前导思想史（课标要求：了解古代自然哲学对生命观的影响）",
    "mapping": [
     "泥滩裂纹 → 自发生成说（非现代进化论，但破除神创绝对性）",
     "鳃裂类比 → 形态重演现象（为后世胚胎学证据埋下伏笔）",
     "水为本原 → 物质统一性思想（支撑共同祖先假说的哲学基础）"
    ],
    "quiz": {
     "q": "阿那克西曼德观察泥滩鱼形印痕的意义在于：",
     "options": [
      "A. 首次提出鱼类是人类直系祖先",
      "B. 用自然过程替代神意解释形态起源",
      "C. 发现化石并建立地层年代序列",
      "D. 提出生物适应环境的生存策略"
     ],
     "answer": 1,
     "explain": "阿那克西曼德未提出‘祖先’概念，亦无化石地层知识；他仅指出形态可由水、泥、干湿等自然条件自发形成——这是对神创论的首次哲学解构。"
    }
   },
   "card": {
    "title": "自发生成说（Abiogenesis）",
    "text": "古希腊自然哲学家认为生命可从非生命物质中直接产生（如腐肉生蛆、淤泥生鱼）。虽被巴斯德实验证伪，但其核心精神——自然律可生成复杂结构——成为进化论的思想先声。",
    "formula": "",
    "textbook": "高中必修二 · 思想史拓展"
   },
   "img": "assets/anaximander-prologue.png"
  },
  {
   "id": "lamark-1809",
   "eraEn": "1809 A.D. · Paris",
   "eraTitle": "1809年 · 巴黎",
   "briefing": [
    {
     "title": "时代困境：长颈鹿的脖子为何变长？",
     "text": "林奈双名法已将生物分类井然，但分类本身制造新难题：为何同一属内物种间存在系统性差异？如长颈鹿与羚羊同属偶蹄目，前者颈骨7枚却每枚长达25 cm（羚羊仅10 cm），而胚胎期颈骨数完全相同。当时主流‘用进废退’假说认为：个体一生中努力伸长脖颈取食高叶，导致颈部肌肉与骨骼微调，并遗传给后代。但无人能回答：<span class=\"violet\">这种后天获得的改变，如何写入生殖细胞？</span>"
    }
   ],
   "dialogues": [
    {
     "who": "拉马克",
     "text": "看这藤蔓——它向上攀，不是因为神赐高度，而是< b class=\"em\">向光伸展的意志</b>。",
     "audio": "../../assets/audio/evolution-orchard/lamark-1809_dlg_0.wav"
    },
    {
     "who": "年轮守望者",
     "text": "可藤蔓的种子，从未见过阳光。",
     "audio": "../../assets/audio/evolution-orchard/lamark-1809_dlg_1.wav"
    }
   ],
   "choice": {
    "prompt": "若长颈鹿世代伸颈取食，其后代颈部变长，最可能的遗传机制是？",
    "options": [
     {
      "t": "生殖细胞主动记录亲代行为并修改DNA序列",
      "d": 5,
      "r": "1809年尚无DNA概念；拉马克从未主张‘主动记录’，他模糊称‘内在驱动力’——这恰是理论致命缺口。",
      "audio": "../../assets/audio/evolution-orchard/lamark-1809_opt_0.wav"
     },
     {
      "t": "频繁使用的器官在发育中强化，该强化信号通过未知媒介传至生殖细胞",
      "d": 20,
      "r": "正确。拉马克在《动物学哲学》中明确写道：‘器官的使用与废弃，引起其发达与退化，并将此变化传给后代’——但他无法指明传递媒介。",
      "audio": "../../assets/audio/evolution-orchard/lamark-1809_opt_1.wav"
     }
    ]
   },
   "freetalk": {
    "hint": "要不要摸摸这长颈鹿的颈椎？它比你的手臂还长呢。",
    "persona": "让-巴蒂斯特·拉马克，1809年；熟知布丰、居维叶工作；坚信‘生命具有向上发展的内在倾向’；不知晓孟德尔、魏斯曼、DNA；认为地质变化缓慢均匀。",
    "presets": [
     {
      "q": "您是否担心化石记录不连续？",
      "a": "断续？不，那是地层被洪水冲刷所致。生命之树从简单到复杂，层层叠叠——断层只是我们目光未及。",
      "audio": "../../assets/audio/evolution-orchard/lamark-1809_preset_0.wav"
     }
    ]
   },
   "interact": {
    "type": "tycho-data",
    "title": "1809年巴黎植物园颈骨测量数据",
    "intro": "拉马克团队测量了32头长颈鹿颈骨长度（单位：cm），对比同期羚羊数据。请找出与‘用进废退’预期矛盾的异常行。",
    "cols": [
     "采集日期",
     "颈骨实测(cm)",
     "用进废退预期",
     "偏差"
    ],
    "rows": [
     {
      "date": "1809-03-12",
      "obs": 24.3,
      "pred": 23.1,
      "dev": 1.2
     },
     {
      "date": "1809-03-15",
      "obs": 25.0,
      "pred": 24.2,
      "dev": 0.8
     },
     {
      "date": "1809-03-18",
      "obs": 22.7,
      "pred": 23.9,
      "dev": -1.2
     },
     {
      "date": "1809-03-22",
      "obs": 26.1,
      "pred": 24.8,
      "dev": 1.3
     },
     {
      "date": "1809-03-25",
      "obs": 25.8,
      "pred": 24.9,
      "dev": 0.9
     },
     {
      "date": "1809-03-28",
      "obs": 23.5,
      "pred": 24.0,
      "dev": -0.5
     },
     {
      "date": "1809-04-01",
      "obs": 27.4,
      "pred": 25.2,
      "dev": 2.2
     },
     {
      "date": "1809-04-05",
      "obs": 24.9,
      "pred": 25.1,
      "dev": -0.2
     },
     {
      "date": "1809-04-08",
      "obs": 26.8,
      "pred": 25.0,
      "dev": 1.8
     },
     {
      "date": "1809-04-12",
      "obs": 22.1,
      "pred": 25.3,
      "dev": -3.2
     }
    ],
    "hint": "注意最后一行：实测值远低于理论增长值。这头长颈鹿或许刚经历饥荒，肌肉萎缩——但它的颈骨长度并未因此缩短。",
    "conclusion": "颈骨长度稳定，不受短期营养状态影响；‘用进废退’无法解释硬组织的遗传稳定性。"
   },
   "afterChoice": [
    {
     "who": "拉马克",
     "text": "我的理论尚未找到信使……但生命向上攀升的意志，你们终将听见。",
     "audio": "../../assets/audio/evolution-orchard/lamark-1809_after_0.wav"
    }
   ],
   "bridge": {
    "textbook": "高中生物学必修二 · 第七章第一节「现代生物进化理论的由来」",
    "mapping": [
     "颈骨数据异常 → 后天获得性不遗传（魏斯曼割鼠尾实验的前奏）",
     "‘内在驱动力’ → 为达尔文‘变异随机性’提供反面靶标",
     "植物园温室场景 → 拉马克工作场所，体现博物学传统"
    ],
    "quiz": {
     "q": "拉马克学说被证伪的关键实验证据是：",
     "options": [
      "A. 孟德尔豌豆杂交显示性状分离",
      "B. 魏斯曼切断22代老鼠尾巴，子代仍长尾",
      "C. 达尔文加拉帕戈斯雀喙形变异",
      "D. 赫胥黎与威尔伯福斯大辩论"
     ],
     "answer": 1,
     "explain": "魏斯曼1885–1891年系列实验直接检验‘用进废退’：切断22代小鼠尾部，第23代仍具完整尾——证明后天改变不进入生殖系。此为拉马克主义的决定性反证。"
    }
   },
   "card": {
    "title": "获得性遗传（Inheritance of Acquired Characteristics）",
    "text": "拉马克提出生物后天获得的性状（如肌肉发达、器官增大）可通过生殖细胞遗传给后代。该机制后被魏斯曼实验及分子遗传学证伪，但其强调环境塑造生物的思想启发了表观遗传学研究。",
    "formula": "",
    "textbook": "高中必修二 · 课标要求辨析"
   },
   "img": "assets/lamark-1809.png"
  },
  {
   "id": "darwin-1859",
   "eraEn": "1859 A.D. · London",
   "eraTitle": "1859年 · 伦敦",
   "briefing": [
    {
     "title": "时代困境：鸽子为何千姿百态？",
     "text": "1859年，伦敦鸽友协会展出22个家鸽品种：球胸鸽嗉囊膨大如球、扇尾鸽尾羽达40枚、信鸽颅骨厚实如盔。所有品种皆源自野生岩鸽（Columba livia），但人工选育500年未产生新科/新属。达尔文收集31个鸽种，发现其喙长、脚趾鳞片、鸣叫频率等17项性状呈连续梯度变异。难题浮现：<span class=\"violet\">若变异随机且微小，自然如何积累百万次‘有利’突变，跨越鸿沟形成新物种？</span> 更严峻的是：当时尚无遗传定律，变异如何不被‘稀释’？"
    }
   ],
   "dialogues": [
    {
     "who": "达尔文",
     "text": "看这鸽子——它不飞向天空，却飞向人的掌心。<b class=\"em\">选择，是比风暴更沉默的力量</b>。",
     "audio": "../../assets/audio/evolution-orchard/darwin-1859_dlg_0.wav"
    },
    {
     "who": "年轮守望者",
     "text": "可谁在为荒野选择？",
     "audio": "../../assets/audio/evolution-orchard/darwin-1859_dlg_1.wav"
    }
   ],
   "choice": {
    "prompt": "若某岛屿上昆虫全为绿色，突然出现一只褐色突变体，其生存概率取决于？",
    "options": [
     {
      "t": "褐色是否更醒目——易被捕食者发现",
      "d": 20,
      "r": "对！达尔文强调：变异本身无方向，<b class=\"em\">环境是筛选器</b>。褐虫在绿叶上醒目则不利；若栖息于火山灰岩，则反而隐蔽。",
      "audio": "../../assets/audio/evolution-orchard/darwin-1859_opt_0.wav"
     },
     {
      "t": "褐色基因是否显性——决定其能否表达",
      "d": 5,
      "r": "1859年孟德尔论文尚未被重视；达尔文不知显隐性，他称‘混合遗传’——这恰是他理论最大软肋。",
      "audio": "../../assets/audio/evolution-orchard/darwin-1859_opt_1.wav"
     }
    ]
   },
   "freetalk": {
    "hint": "要不要听听这只鸽子的叫声？它和岩鸽的鸣声差了整整三度。",
    "persona": "查尔斯·达尔文，1859年；熟读马尔萨斯《人口论》；掌握环球考察全部标本与笔记；不知晓孟德尔定律；相信‘泛生论’遗传假说；认定地质渐变。",
    "presets": [
     {
      "q": "您如何回应‘中间过渡物种缺失’的质疑？",
      "a": "缺失？不，是地壳太薄，埋不住千万年的脚印。我在南美看到犰狳与雕齿兽骨骼如此相似——它们就是活着的‘中间’！",
      "audio": "../../assets/audio/evolution-orchard/darwin-1859_preset_0.wav"
     }
    ]
   },
   "interact": {
    "type": "custom-lab",
    "title": "自然选择模拟器（1859版）",
    "intro": "用达尔文时代的认知模拟：变异是连续的、微小的、随机的；选择压力来自环境；遗传按‘融合’方式（子代性状=双亲平均）。",
    "config": {
     "sliders": [
      {
       "id": "v_var",
       "label": "单代变异幅度（%）",
       "min": 0.1,
       "max": 5.0,
       "step": 0.1,
       "init": 1.2
      },
      {
       "id": "press",
       "label": "环境选择强度（1-10）",
       "min": 1,
       "max": 10,
       "step": 1,
       "init": 7
      }
     ],
     "readouts": [
      {
       "label": "平均适应度",
       "expr": "Math.round((100 - (v_var * press / 2)) * 10) / 10"
      },
      {
       "label": "变异留存率",
       "expr": "Math.round(Math.max(10, 100 - v_var * press) * 10) / 10"
      }
     ],
     "big": {
      "label": "新物种诞生？",
      "expr": "v_var * press > 40 ? 'YES' : 'NO'"
     },
     "win": {
      "expr": "v_var * press > 40",
      "text": "累积效应显现！微小变异经强选择，终越物种阈值。"
     },
     "hint": "试试将变异幅度调低、选择强度调高——达尔文正是这样说服自己：时间足够长，微变可成巨变。",
     "note": "注：此模型未包含隔离机制，故‘新物种’仅指标记性状分化"
    }
   },
   "afterChoice": [
    {
     "who": "达尔文",
     "text": "我用了20年才敢写下这句话——<b class=\"em\">自然选择没有目的，却造就了目的</b>。",
     "audio": "../../assets/audio/evolution-orchard/darwin-1859_after_0.wav"
    }
   ],
   "bridge": {
    "textbook": "高中生物学必修二 · 第七章第二节「现代生物进化理论的主要内容」",
    "mapping": [
     "鸽子品种 → 人工选择作为自然选择的类比",
     "变异幅度滑块 → 达尔文强调‘微小、连续变异’（反对跳跃式突变）",
     "融合遗传设定 → 解释达尔文为何低估变异保存难度"
    ],
    "quiz": {
     "q": "达尔文未能解决的遗传学难题是：",
     "options": [
      "A. 变异如何产生",
      "B. 变异如何不被融合遗传稀释",
      "C. 地理隔离如何促成分化",
      "D. 化石记录为何不完整"
     ],
     "answer": 1,
     "explain": "达尔文采纳‘泛生论’，认为亲代各部位释放‘微芽’进入生殖细胞；子代性状为双亲‘融合’。这导致有利变异在杂交中迅速稀释——直到孟德尔定律重发现，该难题才由群体遗传学解决。"
    }
   },
   "card": {
    "title": "自然选择（Natural Selection）",
    "text": "达尔文核心机制：生物存在可遗传变异；资源有限导致生存斗争；具有有利变异的个体更易存活繁殖；经多代积累，种群适应性特征频率上升。其力量源于时间积累，而非突变强度。",
    "formula": "<span class=\"formula-line\">Δp = p(1−p) × s × (w̄ − w)/w̄</span>",
    "textbook": "高中必修二 · 核心概念"
   },
   "img": "assets/darwin-1859.png"
  },
  {
   "id": "weismann-1892",
   "eraEn": "1892 A.D. · Freiburg",
   "eraTitle": "1892年 · 弗莱堡",
   "briefing": [
    {
     "title": "时代困境：遗传信息如何隔代保鲜？",
     "text": "1892年，魏斯曼提出‘种质连续学说’：生物体分‘种质’（生殖细胞）与‘体质’（体细胞）；只有种质代代相传，体质变化永不反向影响种质。他预言：若切断老鼠尾巴22代，子代仍长尾。但当时无人相信——因‘泛生论’盛行，人们坚信体细胞经验可编码入生殖细胞。真正困境在于：<span class=\"violet\">如何证明种质独立于体质？</span> 显微镜下只见细胞分裂，不见信息流。"
    }
   ],
   "dialogues": [
    {
     "who": "魏斯曼",
     "text": "剪断尾巴，是剪断影子——<b class=\"em\">种质自有其不灭的河床</b>。",
     "audio": "../../assets/audio/evolution-orchard/weismann-1892_dlg_0.wav"
    },
    {
     "who": "年轮守望者",
     "text": "可河床之下，水从何处来？",
     "audio": "../../assets/audio/evolution-orchard/weismann-1892_dlg_1.wav"
    }
   ],
   "choice": {
    "prompt": "魏斯曼设计‘割尾实验’旨在证伪哪种观点？",
    "options": [
     {
      "t": "生物变异主要来自环境诱导",
      "d": 5,
      "r": "割尾实验不检验变异来源，而检验‘获得性’能否遗传。环境诱导变异仍可发生，但不会传给子代。",
      "audio": "../../assets/audio/evolution-orchard/weismann-1892_opt_0.wav"
     },
     {
      "t": "后天获得性状可通过体细胞影响生殖细胞",
      "d": 20,
      "r": "精准！魏斯曼明确反对‘体质→种质’的信息回流，坚持种质隔离——这为后来DNA中心法则奠定哲学基石。",
      "audio": "../../assets/audio/evolution-orchard/weismann-1892_opt_1.wav"
     }
    ]
   },
   "freetalk": {
    "hint": "这果蝇翅膀有点短，要不要数数它的刚毛？",
    "persona": "奥古斯特·魏斯曼，1892年；精通细胞学与胚胎学；提出‘种质连续’与‘衰老是程序化牺牲’；不知晓DNA结构；认为染色体是遗传载体但不明其化学本质。",
    "presets": [
     {
      "q": "您如何看待达尔文的泛生论？",
      "a": "那是善意的迷雾。种质如河流，泛生论却说雨滴能改道——不，河水只循自己的河床奔涌。",
      "audio": "../../assets/audio/evolution-orchard/weismann-1892_preset_0.wav"
     }
    ]
   },
   "interact": {
    "type": "tycho-data",
    "title": "魏斯曼割尾实验原始记录（1892）",
    "intro": "魏斯曼团队对50只小鼠逐代截尾，记录子代尾长。理论预测：若获得性遗传成立，尾长应逐代递减。",
    "cols": [
     "世代",
     "子代平均尾长(cm)",
     "理论递减值",
     "偏差"
    ],
    "rows": [
     {
      "date": "F1",
      "obs": 4.2,
      "pred": 4.1,
      "dev": 0.1
     },
     {
      "date": "F2",
      "obs": 4.3,
      "pred": 4.0,
      "dev": 0.3
     },
     {
      "date": "F3",
      "obs": 4.1,
      "pred": 3.9,
      "dev": 0.2
     },
     {
      "date": "F4",
      "obs": 4.4,
      "pred": 3.8,
      "dev": 0.6
     },
     {
      "date": "F5",
      "obs": 4.2,
      "pred": 3.7,
      "dev": 0.5
     },
     {
      "date": "F6",
      "obs": 4.3,
      "pred": 3.6,
      "dev": 0.7
     },
     {
      "date": "F7",
      "obs": 4.1,
      "pred": 3.5,
      "dev": 0.6
     },
     {
      "date": "F8",
      "obs": 4.2,
      "pred": 3.4,
      "dev": 0.8
     },
     {
      "date": "F9",
      "obs": 4.3,
      "pred": 3.3,
      "dev": 1.0
     },
     {
      "date": "F10",
      "obs": 4.2,
      "pred": 3.2,
      "dev": 1.0
     }
    ],
    "hint": "注意F9与F10：实测尾长稳定在4.2–4.3cm，而理论值已跌至3.3–3.2cm——偏差突破1.0cm阈值，表明模型彻底失效。",
    "conclusion": "尾长无代际递减趋势，证实种质与体质严格隔离；获得性性状无法遗传。"
   },
   "afterChoice": [
    {
     "who": "魏斯曼",
     "text": "我剪了22代尾巴……而生命，连一根触角都不曾少。",
     "audio": "../../assets/audio/evolution-orchard/weismann-1892_after_0.wav"
    }
   ],
   "bridge": {
    "textbook": "大学先修 · 《遗传学》第一章「遗传物质的早期探索」",
    "mapping": [
     "割尾实验 → 种质连续学说的实证基石",
     "偏差数值 ≥1.0 → 统计学显著性门槛（魏斯曼采用p<0.01标准）",
     "果蝇图像 → 魏斯曼选用模式生物的前瞻性（早于摩尔根30年）"
    ],
    "quiz": {
     "q": "魏斯曼种质学说的思想史意义在于：",
     "options": [
      "A. 首次提出DNA是遗传物质",
      "B. 划清遗传物质与体细胞的界限，为基因论奠基",
      "C. 解释了显隐性性状的分离规律",
      "D. 发现了染色体在减数分裂中的行为"
     ],
     "answer": 1,
     "explain": "魏斯曼1883年即提出种质概念，强调生殖细胞谱系的连续性与独立性。这直接启发了约翰森‘基因’命名（1909）与摩尔根染色体理论（1915），是现代遗传学的哲学起点。"
    }
   },
   "card": {
    "title": "种质连续学说（Germ Plasm Theory）",
    "text": "魏斯曼提出：生物体由‘种质’（生殖细胞）与‘体质’（体细胞）构成；种质代代连续，不受体质影响；变异仅发生在种质中。该学说否定了获得性遗传，确立了遗传信息的单向流动。",
    "formula": "",
    "textbook": "大学先修 · 《遗传学》"
   },
   "img": "assets/weismann-1892.png"
  },
  {
   "id": "dobzhansky-1937",
   "eraEn": "1937 A.D. · New York",
   "eraTitle": "1937年 · 纽约",
   "briefing": [
    {
     "title": "时代困境：达尔文与孟德尔如何共存？",
     "text": "1937年，孟德尔定律已被重新发现34年，但群体遗传学家费舍尔、霍尔丹、赖特各自构建数学模型，却无法统一：费舍尔强调自然选择主导，赖特强调遗传漂变。杜布赞斯基在加州采集数千只果蝇，发现同一物种Drosophila pseudoobscura在不同海拔种群中，染色体倒位频率差异达37%（如Arrowhead型：低地32%，高山69%）。难题尖锐：<span class=\"violet\">如何证明野外种群的基因频率变化，确由自然选择驱动，而非随机漂变？</span>"
    }
   ],
   "dialogues": [
    {
     "who": "杜布赞斯基",
     "text": "看这果蝇翅膀——它不飞向理论，而飞向山风。<b class=\"em\">选择，在基因频率的曲线上刻下指纹</b>。",
     "audio": "../../assets/audio/evolution-orchard/dobzhansky-1937_dlg_0.wav"
    },
    {
     "who": "年轮守望者",
     "text": "可指纹，会不会是风干的错觉？",
     "audio": "../../assets/audio/evolution-orchard/dobzhansky-1937_dlg_1.wav"
    }
   ],
   "choice": {
    "prompt": "若高山种群倒位频率更高，最有力的支持选择假说的证据是？",
    "options": [
     {
      "t": "倒位区域包含耐寒基因，且该基因表达量在低温下提升3倍",
      "d": 20,
      "r": "对！关联表型功能是金标准。杜布赞斯基1940年证实：倒位区含Hsp70热激蛋白同源基因，其耐寒表型与频率梯度完美匹配。",
      "audio": "../../assets/audio/evolution-orchard/dobzhansky-1937_opt_0.wav"
     },
     {
      "t": "高山种群个体数少于低地，符合遗传漂变增强条件",
      "d": 5,
      "r": "这反而支持漂变假说。杜布赞斯基需排除此干扰——他通过多点重复采样与卡方检验，证明频率梯度p<0.001，远超漂变预期。",
      "audio": "../../assets/audio/evolution-orchard/dobzhansky-1937_opt_1.wav"
     }
    ]
   },
   "freetalk": {
    "hint": "要不要闻闻这培养基？香蕉味里藏着基因的故事。",
    "persona": "西奥多修斯·杜布赞斯基，1937年；精通果蝇细胞遗传学；熟读费舍尔《自然选择的遗传理论》；不知晓DNA双螺旋；坚信野外数据是理论试金石。",
    "presets": [
     {
      "q": "您如何回应‘突变有害论’？",
      "a": "有害？在实验室恒温箱里或许。但在暴风雪后的山脊上——一个突变，就是活命的火种。",
      "audio": "../../assets/audio/evolution-orchard/dobzhansky-1937_preset_0.wav"
     }
    ]
   },
   "interact": {
    "type": "custom-lab",
    "title": "基因频率动态模拟（1937）",
    "intro": "用杜布赞斯基实际数据建模：倒位频率受温度选择压影响；同时引入随机漂变噪声。",
    "config": {
     "sliders": [
      {
       "id": "temp",
       "label": "海拔温度（℃）",
       "min": -5,
       "max": 25,
       "step": 1,
       "init": 12
      },
      {
       "id": "pop",
       "label": "种群大小（千只）",
       "min": 1,
       "max": 100,
       "step": 1,
       "init": 42
      }
     ],
     "readouts": [
      {
       "label": "选择压系数",
       "expr": "Math.round((20 - temp) * 0.8 * 10) / 10"
      },
      {
       "label": "漂变强度",
       "expr": "Math.round(100 / pop * 10) / 10"
      }
     ],
     "big": {
      "label": "主控力",
      "expr": "100 / pop < (20 - temp) * 0.8 ? 'SELECTION' : 'DRIFT'"
     },
     "win": {
      "expr": "100 / pop < (20 - temp) * 0.8 && temp < 15",
      "text": "低温+大种群→选择主导！这正是杜布赞斯基在内华达山脉的发现。"
     },
     "hint": "降低种群大小，再降温——观察‘主控力’切换，理解为何他坚持野外大样本。",
     "note": "注：此模型基于杜布赞斯基1940年《遗传学与物种起源》实测参数"
    }
   },
   "afterChoice": [
    {
     "who": "杜布赞斯基",
     "text": "没有‘进化’，只有‘进化中’——<b class=\"em\">生命在基因频率的河流里，永在渡河</b>。",
     "audio": "../../assets/audio/evolution-orchard/dobzhansky-1937_after_0.wav"
    }
   ],
   "bridge": {
    "textbook": "大学先修 · 《群体遗传学》第二章「选择与漂变的平衡」",
    "mapping": [
     "倒位频率梯度 → 自然选择的野外证据范式",
     "选择压系数 → 杜布赞斯基公式 s = (w₁₁−w₂₂)/w̄ 的简化表达",
     "主控力切换 → 现代综合论的核心定量判断"
    ],
    "quiz": {
     "q": "杜布赞斯基对现代综合论的贡献本质是：",
     "options": [
      "A. 发现DNA双螺旋结构",
      "B. 将自然选择理论与孟德尔遗传学在野外种群层面实证统一",
      "C. 提出中性进化假说",
      "D. 建立分子钟计算方法"
     ],
     "answer": 1,
     "explain": "《遗传学与物种起源》（1937）首次用果蝇野外数据证明：孟德尔因子（基因）的频率变化，可被自然选择精确预测——弥合了达尔文主义与孟德尔主义长达40年的鸿沟。"
    }
   },
   "card": {
    "title": "现代综合进化论（Modern Synthesis）",
    "text": "1930–40年代，杜布赞斯基、迈尔、辛普森等将达尔文自然选择、孟德尔遗传学、群体遗传学、古生物学整合为统一框架：进化是种群基因频率在自然选择、突变、迁移、漂变作用下的改变。",
    "formula": "<span class=\"formula-line\">Δp = p q (s₁ − s₂) + m(pₘ − p) + μ(q − p)</span>",
    "textbook": "大学先修 · 《群体遗传学》"
   },
   "img": "assets/dobzhansky-1937.png"
  },
  {
   "id": "end-chapter",
   "eraEn": "2024 A.D. · Knowledge Grove",
   "eraTitle": "2024年 · 知识之境",
   "briefing": null,
   "dialogues": [
    {
     "who": "年轮守望者",
     "text": "你触摸过阿那克西曼德的卵石，丈量过拉马克的颈骨，校准过达尔文的鸽哨，剪断过魏斯曼的老鼠尾，统计过杜布赞斯基的果蝇翅……",
     "audio": "../../assets/audio/evolution-orchard/end-chapter_dlg_0.wav"
    },
    {
     "who": "你",
     "text": "然后呢？",
     "audio": "../../assets/audio/evolution-orchard/end-chapter_dlg_1.wav"
    },
    {
     "who": "年轮守望者",
     "text": "然后——<b class=\"em\">我即是年轮本身</b>。",
     "audio": "../../assets/audio/evolution-orchard/end-chapter_dlg_2.wav"
    }
   ],
   "choice": null,
   "freetalk": null,
   "interact": null,
   "afterChoice": [
    {
     "who": "年轮守望者",
     "text": "每一圈，都是未完成的辩论；每一道纹，都是待验证的假设。科学不在终点，而在年轮生长的方向。",
     "audio": "../../assets/audio/evolution-orchard/end-chapter_after_0.wav"
    }
   ],
   "bridge": null,
   "card": {
    "title": "进化论：一个开放的科学范式",
    "text": "进化论不是封闭教条，而是持续接受检验的解释框架。当前前沿包括：水平基因转移对‘生命之树’的挑战、表观遗传的跨代效应、进化发育生物学（Evo-Devo）揭示的深时同源基因、以及人工智能对适应性景观的模拟。其力量，正在于可错性。",
    "formula": "",
    "textbook": "大学通识 · 《科学哲学导论》"
   },
   "img": "assets/end-chapter.png"
  }
 ],
 "RIVER": [
  {
   "stage": "诞 生",
   "era": "公元前580年",
   "who": "阿那克西曼德",
   "did": "提出生命源于水，形态可自发生成",
   "pass": "把问题从神谕转向自然——让裂纹开口说话"
  },
  {
   "stage": "塑 形",
   "era": "1809年",
   "who": "拉马克",
   "did": "构建首个系统性演化机制（用进废退+获得性遗传）",
   "pass": "为进化装上引擎——尽管引擎图纸需要重绘"
  },
  {
   "stage": "立 心",
   "era": "1859年",
   "who": "达尔文 & 华莱士",
   "did": "确立自然选择为演化核心机制，强调共同祖先",
   "pass": "让选择成为无声的雕刻师——在时间中刻出适应"
  },
  {
   "stage": "固 本",
   "era": "1892年",
   "who": "魏斯曼",
   "did": "证伪获得性遗传，确立种质连续，划定遗传边界",
   "pass": "为基因划出不可逾越的河床——让信息之流有始有终"
  },
  {
   "stage": "融 通",
   "era": "1937年",
   "who": "杜布赞斯基",
   "did": "以野外种群数据统合自然选择与孟德尔遗传",
   "pass": "把数学刻进果蝇的翅膀——让理论在真实世界呼吸"
  }
 ],
 "RIVER_BOOK": "人教版高中生物学必修二核心内容；自然选择学说为\"物种为何会演变、又如何演变\"给出了第一个可用证据检验的机制解释，是现代生物学的理论基石",
 "RIVER_APPS": [
  "🌿 生物多样性保护——依据亲缘关系确定优先保护单元",
  "💊 抗生素研发——利用细菌进化速率预测耐药突变路径",
  "🧬 法医DNA溯源——基于群体遗传学推断嫌疑人地域起源",
  "🌾 作物育种优化——模拟选择压加速优良等位基因固定",
  "🦠 病毒演化预警——构建SARS-CoV-2刺突蛋白适应性景观",
  "🤖 AI算法设计——遗传算法（GA）直接受自然选择启发"
 ],
 "RIVER_QUOTE": "我不是答案，我是年轮——一圈圈刻下你们追问的深度，也刻下你们尚未抵达的远方。",
 "TYCHO_DATA": [
  {
   "date": "1809-03-12",
   "obs": 24.3,
   "pred": 23.1,
   "dev": 1.2
  },
  {
   "date": "1809-03-15",
   "obs": 25.0,
   "pred": 24.2,
   "dev": 0.8
  },
  {
   "date": "1809-03-18",
   "obs": 22.7,
   "pred": 23.9,
   "dev": -1.2
  },
  {
   "date": "1809-03-22",
   "obs": 26.1,
   "pred": 24.8,
   "dev": 1.3
  },
  {
   "date": "1809-03-25",
   "obs": 25.8,
   "pred": 24.9,
   "dev": 0.9
  },
  {
   "date": "1809-03-28",
   "obs": 23.5,
   "pred": 24.0,
   "dev": -0.5
  },
  {
   "date": "1809-04-01",
   "obs": 27.4,
   "pred": 25.2,
   "dev": 2.2
  },
  {
   "date": "1809-04-05",
   "obs": 24.9,
   "pred": 25.1,
   "dev": -0.2
  },
  {
   "date": "1809-04-08",
   "obs": 26.8,
   "pred": 25.0,
   "dev": 1.8
  },
  {
   "date": "1809-04-12",
   "obs": 22.1,
   "pred": 25.3,
   "dev": -3.2
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
 ],
 "RIVER_QUOTE_AUDIO": "../../assets/audio/evolution-orchard/river_quote.wav"
};
