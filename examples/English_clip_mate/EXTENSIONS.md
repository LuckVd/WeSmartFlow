# 扩展方案清单

当前版本：**两段片子、四轮闭环、预置数据、纯静态**。
下面按「性价比」排序，每项标了预估工时、风险和依赖。

图例：⭐ 推荐优先 · 🔬 需额外技术栈 · ⚠️ 有明显风险

---

## 1. 发音标记：已做到哪一步，还差什么

### ✅ 已经做到的：重音 / 弱读 / 连读都是**实测**的

不是凭语感标的。做法是用 Whisper 的**词级时间戳**切音频，逐词算 RMS 能量：

```python
import av, numpy as np
from faster_whisper import WhisperModel

c = av.open('clip.mp4'); st = c.streams.audio[0]; sr = st.rate
buf = []
for f in c.decode(st):
    a = f.to_ndarray(); buf.append(a.mean(axis=0) if a.ndim > 1 else a)
audio = np.concatenate(buf).astype(np.float32)
if audio.max() > 1.5: audio /= 32768.0

m = WhisperModel('small.en', device='cpu', compute_type='int8')
segs, _ = m.transcribe('clip.mp4', word_timestamps=True, language='en',
                       vad_filter=False, condition_on_previous_text=False)

def rms(a, b):
    g = audio[int(a*sr):int(b*sr)]
    return float(np.sqrt((g**2).mean())) if len(g) else 0.0

# 每个词：时长 = w.end - w.start；相对能量 = rms(w.start, w.end) / 句内峰值
# 相对能量 > 0.72 → stress ；< 0.45 → weak ；与后词间隔 ≤ 0.02s → link
```

**这一步为什么必要**——实测结果经常和直觉相反：

| 句子 | 凭感觉会标 | 实测结果 |
|---|---|---|
| `I just don't think it's going to fit` | think 和 fit 都是重音 | **只有 fit**（0.36s/1.00）；think 反而最扁（0.14s/0.36） |
| `You certainly think a lot of yourself` | Certainly、think、lot、yourself 都重 | **只有 lot**；Certainly 拖了 0.58s 但能量仅 0.34 |
| `You bet your ass` | bet 和 ass 都重 | **只有 ass**；bet 只有 0.06 秒 |

一句话结论：**说得长 ≠ 重读**。没有实测，这类标记基本靠不住。

### ⚠️ 还差什么（诚实说明）

| 项目 | 现状 | 缺口 |
|---|---|---|
| 重音（词级） | ✅ 音频能量实测 | — |
| 弱读 | ✅ 能量 + 时长实测 | — |
| 连读 | ✅ 词间隔实测 | — |
| **吞音** | ⚠️ **规则推断**（/t/ 在 /θ/ 前脱落等） | 音素级现象，**词级数据测不到**，目前无客观验证 |
| **音节级重音**（`PI-vot` 而非 `pi-VOT`） | ⚠️ 人工查词典 | 没有自动化，换片段要重查 |
| 升降调（`You think?!` 的挑衅升调） | ❌ 完全没做 | 需要 F0 基频曲线 |

### 补上缺口的三条路

**A. CMU Pronouncing Dictionary（解决音节级重音）⭐ 最容易**
免费词典，约 13.4 万词，每词给出音素串 + 重音等级：

```
PIVOT  P IH1 V AH0 T     ← 1 = 主重音, 2 = 次重音, 0 = 无重音
```

直接映射成音节级 stress 标记，**完全自动、可复现、零成本**。
工时 0.5 天，依赖只是一个 txt 文件。

**B. 音素级强制对齐（唯一能客观验证吞音的方法）🔬**
WhisperX / Montreal Forced Aligner 能给出**音素级**时间戳。
于是可以直接检查：`don't` 里的 /t/ 音素时长是否趋近 0 → **客观判定吞音**。
同时顺带拿到音素级切分，可以做真正的卡拉OK级高亮。
工时 1–2 天（含环境折腾），WhisperX 比 MFA 轻，建议先试。

**C. F0 基频曲线（升降调）🔬**
用 `librosa.pyin` 或 `praat-parselmouth` 提基频，画出句末是升还是降。
`You think?!`、`Really?` 这类**靠语调传递态度**的句子，靠标记根本表达不出来，
但一条 F0 曲线图就说清了。工时 0.5 天，视觉效果也好。

**推荐顺序**：`A（音节重音，立刻做）→ C（语调曲线，性价比高）→ B（吞音验证，最重）`

---

## 2. 口语跟读打分 ⭐
**浏览器原生 Web Speech API**（`webkitSpeechRecognition`），不需要后端和 ASR 服务：

- 用户跟读台词 → 实时转写 → 与原文**词级 diff** → 高亮错词
- 打三个分：准确度（词匹配率）/ 完成度 / 流利度（用时对比原句时长）
- 现在有了实测重音数据，还能给更狠的反馈：
  **「你把 think 读重了，原声里这个词其实是被压掉的」**
- ⚠️ 需 Chrome/Edge + 联网 + HTTPS（或 localhost）
- **兜底**：不可用时降级为 `MediaRecorder` 录音回放 + 自评三星

工时 2–3 小时

## 3. 波形 / 节奏对照 ⭐ 视觉性价比最高
把**用户录音**和**原声**的波形叠画在同一 canvas 上。
配合已有的词级时间戳，可以直接画出「原声的重音落在哪、你的落在哪」——
这比任何文字说明都直观。纯前端、无 AI 依赖。

工时 2–3 小时

## 4. 「台词侦探」小游戏 ⭐
先只放声音不给字幕，让用户猜**说话人的真实意图/情绪**
（例：Natasha 说 *That's not a question I need answered* 是害羞还是回避？），
选完再揭晓 + 解释。题目全部预生成，成本极低。

工时 1 小时

## 5. 双人对戏
片段里两个角色，AI 演 A（原声），用户演 B（麦克风），按时间轴轮流。
复联那段的 Tony ↔ Thor 斗嘴非常适合。演示效果最强，但时序同步要调。

工时 半天 · ⚠️ 依赖第 2 项

## 6. 表达关系图谱
把两段片子里的表达连成图谱，比如「**假客气族**」：
`Be my guest` / `By all means` / `With all due respect` / `All deference to` ——
它们共享同一个机制（越客气越欠）。直接呼应 WeSmartFlow 的知识图谱能力。

工时 3 小时

## 7. 用户导入本地视频
`<input type="file">` + `URL.createObjectURL` 就能播放本地任意视频，
把首页那张「＋ 导入你自己的片段」占位卡变成真功能。
只是没有配套讲解数据 —— 除非接第 8 项。

工时 1 小时（仅播放）

## 8. 接入 WeSmartFlow 后端，真正做到「任何剧都能学」🔬
从 Demo 走向产品的那一步。注意这条流水线**就是 README 里那份 SOP 的自动化版本**：

```
用户丢进一个视频
   ↓ WhisperX          字幕 + 词级/音素级时间戳
   ↓ LLM (DeepSeek)    挑 5~7 个值得讲的点 + 写讲解卡 + 出题
   ↓ 声学分析 + CMU    自动生成发音标记（重音/弱读/连读/音节重音）
   ↓ 知识图谱写入      表达进图谱，三维掌握度 + SM-2 复习调度
   ↓ 前端              就是现在这个页面，只是 data.js 变成接口返回
```

⚠️ 唯一无法自动化的一环：**台词与说话人的剧本校对**。
Whisper 会听错否定式和专有名词（`would/wouldn't`、`Stark/start`、`rigged/Rick`），
而说话人标注它压根没有。产品化时要么接字幕库/剧本库，要么保留人工校对工位。

现有框架可直接复用：
- `backend/agent_core/llm/` —— OpenAI 兼容 LLM 适配层
- `backend/agents/tools/generate_card.py` —— HTML 知识卡片生成
- `backend/kg/` —— 知识图谱 + 三维掌握度 + SM-2

工时 3–5 天 · 做完「灰色占位卡」就都能点亮

## 9. 更好的片源（当前的已知妥协）⚠️
现在两段都靠**遮罩**盖掉片源自带的中文硬字幕和台标。已试过但没成的路：

- YouTube 官方 clip（无字幕）→ 普遍触发 bot 校验，换 client / cookies 都没绕过
- B 站【4K】全季合集 → 结构查清了（P16–P25 每季一 P，P20 = 第五季，S5E16 约在 339 分钟处），
  理论上可用 `yt-dlp --download-sections` 只切 7 分钟；
  但**无法预先确认该源是否压了硬字幕**（预览图 API 返回的是无效占位图），
  盲下一个 543 分钟 4K 分P 的片段成本偏高
- 裁掉字幕区 → 老友记的字幕压在画面上，裁完损失约 25% 画面高度

若要彻底解决，值得投入的方向：**找到无硬字幕片源后，把字幕移到视频下方的独立字幕面板**
（画面完全干净、字幕区空间更大、点词更好点）。前端改动约 2 小时。

## 10. 其它小项
- **深浅色主题**：CSS 变量已就位，加 `[data-theme='light']` 即可（框架里已有配色）
- **移动端**：现在能用但没细调，竖屏下播放器和侧栏需要堆叠优化
- **多片段串联**：学完一段推荐下一段，形成"追剧式"学习路径
- **导出学习卡**：把收获卡渲染成图片分享（html2canvas）
- **实测数据可视化**：把每个词的时长/能量画成小柱状图放进发音卡 ——
  数据已经有了，纯展示层，视觉说服力很强
