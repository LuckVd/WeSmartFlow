# BingeMate · 追剧搭子

> WeSmartFlow 的一个**具体学习场景 Demo**：追剧的时候，旁边有个懂英语的搭子。

定位一句话：

> **英语不用被动听讲，追着剧就学进去了。**
> 挑一段你想追的剧，照平时那样看；遇到值得说两句的地方，旁边这位会招呼你一声——
> 表达怎么用、梗从哪儿来、音是怎么连怎么吞的，都在剧情里当场拆开。

目前收了两段，**刻意选了两种完全不同的风格**，用来说明「换部剧就换套重点」：

| 片段 | 时长 | 教学重点 |
|---|---|---|
| **Friends** S5E16 · 沙发抬不上去（PIVOT!） | 2:14 | 生活口语 · 吐槽艺术（习语、口语缩合） |
| **Avengers: Age of Ultron** · 谁能举起雷神之锤 | 1:58 | 反讽语气 · 文化梗（语域反差、拉丁语典故、双关） |

---

## 怎么跑

**方式一：双击打开（零依赖）**

直接双击 `index.html`。数据放在 `data.js`（而不是 json + fetch），
就是为了绕开 `file://` 下的 CORS 限制，让它不需要任何服务器就能演示。

**方式二：静态服务器（推荐用于正式演示）**

```bash
cd examples/English_clip_mate
npx serve          # 或 nginx / Vite 的 public 目录
```

> ⚠️ **别用 `python -m http.server`**：它**不支持 HTTP Range 请求**，
> 视频会**无法拖动、无法单句回放**——而整个 demo 的核心交互都依赖 seek。

**方式三：从 WeSmartFlow 探索页进入（正式入口）**

```bash
cd frontend
npm install               # 首次
npm run dev               # predev 会自动构建本目录
# 打开 http://localhost:5173/#/explore ，点「追剧搭子 BingeMate」
```

只重新构建本主题：

```bash
cd frontend && npm run build:examples -- --only bingemate
```

主站读取的是 `frontend/public/bingemate/`，不是本目录的 `dist/`。改完源码若页面没变，就是漏了上面这步。

---

## 五分钟演示路线

| 步骤 | 操作 | 想让人看到什么 |
|---|---|---|
| 1 | 首页停 5 秒 | 两段风格完全不同的片子 + 三张灰色占位卡 —— **你在看什么，它就陪你学什么** |
| 2 | 点开老友记，第 1 轮**别急着快进** | 侧栏写着「我先不说话」—— **AI 主动保持沉默** |
| 3 | 点 `⏭ 直接跳到问答` | 4 道低门槛题；第 3 题**故意不判分**，留到最后回声 |
| 4 | 第 2 轮点 `⏭ 下一个举手点` | ✋ 气泡弹出。**先故意不理它**，看它 3.5 秒后自己走开 |
| 5 | 再跳一个，这次点开 | 讲解卡的三个 Tab：**💬 用法 / 🔊 发音 / 🎭 背景梗** |
| 6 | 打开 `I just don't think it's going to fit.` | 发音标记 + **实测数据**（全句只有 fit 一个重音） |
| 7 | 第 4 轮答完题 | 顶部回声条：「你当时听成 People，其实是 Pivot」+ 三维掌握度 |
| 8 | **回片单，换复联那段** | 同一套流程，重点全变了：从「生活口语」变成「反讽 + 文化梗 + 古英语腔」 |
| 9 | 打开复联第 1 张卡 `Whosoever be he worthy shall haveth…` | 一句台词拆出四层：古体词 / 虚拟语气倒装 / 泛指 he / **故意造错的 -eth** |

---

## ⭐ 获取高质量片段的标准流程（SOP）

> **这是整个 demo 里最重要的一节。**
> Demo 的质量天花板由素材质量决定：字幕差 1 秒，单句回放就会切掉词头；
> 台词错一个词，整张讲解卡就是错的。下面每一条注意事项都是踩过坑之后写下来的。

### Step 1 · 找片源

优先级：**无硬字幕的原片 > 带官方双语硬字幕的源 > 只有中文字幕的源**

带官方双语字幕的源其实很有价值——英文硬字幕可以用来**交叉校对** Whisper 的结果。

- 检查项：时长 40–150s、情节完整、**不是混剪花絮**、台标/水印位置可接受
- 工具：`yt-dlp`。YouTube 现在普遍触发 *Sign in to confirm you're not a bot*，
  换 player_client / cookies 都不一定绕得过；**B 站搜索 API** 反而更实用：

```bash
curl -s -c c.txt -A "$UA" https://www.bilibili.com/ -o /dev/null
curl -s -b c.txt -A "$UA" -H "Referer: https://www.bilibili.com/" \
  "https://api.bilibili.com/x/web-interface/search/type?search_type=video&keyword=老友记pivot"
# 分P 列表（定位合集里的某一集）
curl -s "https://api.bilibili.com/x/player/pagelist?bvid=BVxxxx"
```

- ⚠️ B 站搬运源常有 UP 主**自加的特效字幕、片头、竖版拼接**，
  必须先抽帧确认，别下完才发现是花絮混剪。
- B 站是 DASH 音视频分离，合流需要 ffmpeg：`-f "30032+30232" --merge-output-format mp4`

### Step 2 · 抽帧验证内容（下载后必做）

```bash
# 3x3 缩略图网格，一眼看清是不是要的场景
ffmpeg -i raw.mp4 -vf "fps=1/9,scale=400:-1,tile=3x3" -frames:v 1 grid.png
# 只裁字幕条并逐秒堆叠，用来确认硬字幕位置（决定遮罩参数）
ffmpeg -ss 46 -t 23 -i raw.mp4 -vf "fps=1,crop=852:132:0:348,tile=1x23" -frames:v 1 subs.png
```

### Step 3 · 时间戳 → Whisper（不要用硬字幕估）

```python
from faster_whisper import WhisperModel
m = WhisperModel('small.en', device='cpu', compute_type='int8')
segs, _ = m.transcribe('clip.mp4', word_timestamps=True, language='en',
                       vad_filter=False,                 # ← 关键
                       condition_on_previous_text=False,  # ← 防重复幻觉
                       temperature=0.0)
```

⚠️ **三条踩坑记录**：

1. **`vad_filter` 必须关掉。** 情景喜剧的**罐头笑声**会被 VAD 判成噪音，
   整段丢掉。第一次跑就把 `Turn / fit / PIVOT / Shut up` 这段高潮全丢了。
2. **别用逐帧读硬字幕估时间戳。** 第一版这么干，精度号称 ±0.5s，
   实测**最大偏差 2.3 秒** —— 这就是"单句循环总切词"的根源。
3. `small.en` 比 `base.en` 明显准；134s 音频在 CPU 上约 80 秒，完全可接受。

### Step 4 · 台词与说话人 → 官方剧本裁决

Whisper 的时间戳可信，**文本不可全信**。实测错误：

| Whisper 听到 | 实际台词 | 错误性质 |
|---|---|---|
| I **wouldn't** be offended | I **would** be offended | 语义反了 |
| Please, **start**, by all means | Please, **Stark**, by all means | 专有名词 |
| but it's **Rick** | but it's **rigged** | 关键词 |
| Come on, **Charlie** | Come on, **Chandler** | 人名 |

剧本站：`livesinabox.com` / `fangj.github.io/friends`（Friends 全剧本）、
`springfieldspringfield.co.uk`（电影）、IMDb Quotes 与 `moviequotedb.com`（**带说话人**）。

剧本还提供 Whisper **完全没有**的东西：**说话人标注**。而这一栏是最容易翻车的：

> 🚨 **说话人错了，讲解就是错的 —— 这是本 demo 踩过的最大的坑。**
> 复联那段第一版凭印象把好几句记在了 Thor 头上，于是讲解卡里写着
> 「Thor 一本正经地开黄腔」、「Thor 说了粗口被告状」。
> 拿两个独立来源逐句对完才发现：**损 Clint 的是 Tony**、
> **说 `You bet your ass` 的是 Clint**、**`Smell the silent judgment` 是 Tony**、
> **`Please, Stark, by all means` 是刚出丑的 Clint**（这个细节反而更有意思）。
> 老友记那版也有 4 处搞反（`I brought reinforcements` 是 Rachel 不是 Ross）。
>
> **做法：至少两个独立来源交叉核对**，且只认带 speaker 标注的来源。
> 一句台词由谁说，往往就是这句话好笑的原因 —— 说话人错了，整张卡都得重写。

> 🚨 **第二个禁区：编造不存在的台词。**
> 第一版照片源翻译组的压缩字幕写了 `I don't think it'll fit`，
> 而原句是 `I just don't think it's going to fit` —— 压根没有 `it'll`。
> 结果整张发音讲解卡（连"影子拼写"一起）全部作废。

### Step 5 · 发音标记 → 声学实测，不靠感觉

用 Whisper 的**词级时间戳**切音频，逐词算 RMS 能量：

```python
import av, numpy as np
c = av.open('clip.mp4'); st = c.streams.audio[0]; sr = st.rate
buf = []
for f in c.decode(st):
    a = f.to_ndarray(); buf.append(a.mean(axis=0) if a.ndim > 1 else a)
audio = np.concatenate(buf).astype(np.float32)
if audio.max() > 1.5: audio /= 32768.0

def rms(a, b):
    g = audio[int(a*sr):int(b*sr)]
    return float(np.sqrt((g**2).mean())) if len(g) else 0.0
# 对每个词算 rms(w.start, w.end)，再除以句内峰值得到相对能量
```

判定阈值（相对句内峰值）：

| 标记 | 判据 |
|---|---|
| `stress` 重音 | 相对能量 **> 0.72** |
| `weak` 弱读 | 相对能量 **< 0.45**，或时长异常短 |
| `link` 连读 | 与后一词间隔 **≤ 0.02s**（词界消失） |
| `swallow` 吞音 | 音素级现象，**词级数据测不到** → 用公认规则判定（/t/ 在 /θ/ 前脱落等） |

⚠️ **实测经常和直觉相反，这正是必须实测的理由：**

- `I just don't think it's going to fit` —— **全句只有 `fit` 一个重音**（0.36s / 能量 1.00）；
  `think` 反而是被压得最扁的词之一（0.14s / 0.36）。凭感觉标一定会把 think 标成重音。
- `You certainly think a lot of yourself` —— **只有 `lot` 是重音**；
  `Certainly` 拖了 0.58 秒但能量只有 0.34 —— **说得长 ≠ 重读**。
- `going` + `to` 合计只有 0.18 秒 → 物理上读不完整，`gonna` 有了铁证。
- `You bet your ass` —— `bet` 只有 0.06 秒，`ass` 独占重音。

### Step 6 · 遮挡参数（拿不到无字幕源时的退路）

**别靠目测定遮罩高度。** 第一版凭感觉给老友记遮了 29%，实测硬字幕只占 14.6%，
白挡了一倍的画面。正确做法是把视频帧画到 canvas 上逐行扫亮像素，
在浏览器控制台跑一次就有答案：

```js
// 找出硬字幕（亮白文字）占据的行范围
const v = document.createElement('video'); v.src = 'clip.mp4'; v.muted = true;
await new Promise(r => v.onloadeddata = r);
const W = v.videoWidth, H = v.videoHeight;
const cv = Object.assign(document.createElement('canvas'), {width: W, height: H});
const cx = cv.getContext('2d');
for (const t of [16, 35, 76, 128]) {              // 多取几个有字幕的时刻
  await new Promise(r => { v.onseeked = r; v.currentTime = t; });
  cx.drawImage(v, 0, 0);
  const d = cx.getImageData(0, 0, W, H).data;
  let top = null, bot = null;
  for (let y = (H * 0.55) | 0; y < H; y++) {
    let bright = 0, run = 0, maxRun = 0;
    for (let x = 0; x < W; x++) {
      const i = (y * W + x) * 4;
      const lum = 0.299*d[i] + 0.587*d[i+1] + 0.114*d[i+2];
      if (lum > 205) { bright++; if (++run > maxRun) maxRun = run; } else run = 0;
    }
    // 亮点够多但没有长条 → 是文字，不是高光平面
    if (bright > 25 && maxRun < 120) { top ??= y; bot = y; }
  }
  console.log(t, {top, bot,需要遮: (100 - top / H * 100).toFixed(1) + '%'});
}
```

静态台标（顶部水印）要换个判据：**取多帧的逐像素最小亮度**，
一直亮的才是台标，画面里的高光会被过滤掉。

两段的实测结果与最终参数：

| 片源 | 实测硬字幕 / 台标位置 | 方案 | 参数 |
|---|---|---|---|
| 老友记（明亮室内） | 单行时 y=411 → 底部 14.4%；**英文折两行时顶到 y=376 → 底部 21.7%** | **渐变遮罩**（纯色会突兀） | `hardsubMask: 25`, `maskOpaque: 22.5` |
| 复联（letterbox 电影画幅） | 字幕 y=385~408 → 底部 **19.8%**；台标下沿 y=73 → 顶部 **15.2%** | **近似纯色遮罩**，视觉像黑边加宽 | `maskStyle:'solid'`, `hardsubMask: 23`, `maskOpaque: 22`, `topMask: 16`, `topMaskOpaque: 15.2` |

⚠️ **只抽几个时间点是不够的 —— 要逐秒扫全片取极值。**
老友记第二版按"单行字幕"量出 14.6%，遮到 22%，看着没问题；
但 6–7s 和 46s 这些**英文台词折成两行**的时刻，字幕上沿会往上顶 35px，
于是从渐变的半透明段漏出来。把上面的脚本改成 `for (let t = 0.5; t < duration; t += 1)`
逐秒扫一遍，才能拿到真正的最坏情况。

**高度和不透明度是两个参数，必须分开给。**
遮罩高 22% 但渐变里纯色只占 64%，等于只遮住了 14% —— 字幕照样透。所以：

| 参数 | 含义 |
|---|---|
| `hardsubMask` | 遮罩**总高度**（含上沿淡出段），决定挡掉多少画面 |
| `maskOpaque` | 其中**完全不透明**的高度，必须 ≥ 实测的最坏字幕上沿 |
| `topMask` / `topMaskOpaque` | 顶部台标同理 |

`app.js` 会把 `maskOpaque` 折算成 CSS 变量 `--solid-stop` 注进渐变，
所以**每个片段各调各的**，改老友记不会连累复联。

### 验收清单

- [ ] 随机抽 3 句用「重听一次」听，**没有切词头/带进下一句**
- [ ] 说话人**两个独立来源交叉核对**过（错一处，讲解卡就得重写）
- [ ] 每个发音标记都有声学数据支持，没有凭感觉标的
- [ ] 遮罩高度是**逐秒扫全片取极值**得来的，不是抽几帧估的
- [ ] 拖着进度条走一遍，**字幕折两行的时刻**也不漏字
- [ ] 片源尾部若接了别的戏，用 `clipEnd` 掐掉
- [ ] `moments`（第 2 轮举手点）与 `points`（第 3 轮精讲点）**一一对应**

---

## 目录

```
English_clip_mate/
├── index.html          页面结构
├── styles.css          样式（设计 token 对齐 frontend/src/style.css）
├── app.js              全部交互逻辑
├── data.js             课程数据 ← 换一部剧只改这一个文件
├── friends_pivot.mp4   老友记片段（134s / 7.3MB / 480p）
├── raw_avengers.mp4    复联片段（137s / 8.7MB，用 clipEnd 只播前 118s）
├── cover_friends.jpg · cover_avengers.jpg
├── EXTENSIONS.md       扩展方案清单
└── README.md
```

**没有构建步骤，没有依赖，没有网络请求。** 字体走系统兜底，不拉 Google Fonts。

---

## 设计上的几个刻意选择

**1. 第一轮 AI 必须闭嘴**
一个真正的「陪看搭子」不会在你刚开始看剧就打断你。
Round 1 侧栏只有一个呼吸灯和一句「我在旁边看着，有需要叫我」。

**2. 举手可以被无视**
气泡出现 3.5 秒无人理会就自动淡出，并记进「稍后再看」。
**能被忽略**这件事本身，才说明主导权在学习者手里。

**3. 用原片真人原声当标准发音，不做 TTS**
点「重听一次」是把视频 seek 回该句**单次播放**（不是循环——短句循环很烦）。
演员原声永远比合成语音自然。

**4. 讲解卡的三个 Tab 而不是全局开关**
同一个知识点有三个面：**用法 / 发音 / 背景梗**。做成 Tab 是因为点了立刻看到内容切换、
反馈直接；早期版本做成全局偏好开关，结果切了没有任何直观变化，还要弹提示，反而更糊。
只显示这个点真有内容的 Tab；发音专项卡默认落在「发音」。

**5. 四个阶段可以随便点**
不强制按顺序走完。演示时经常需要直接跳到某一轮。

**6. 一次只举一只手，但过点不丢**
台词密集处（复联 94–100 秒连着三个点）不会同时弹两个气泡。
注意这里**不能用「到点那一瞬间的时间窗口」判断**：气泡要占 3.5 秒，
而 `a4`(97.3s) 和 `a5`(98.3s) 只差 1 秒，后一个会被整个吞掉。
实现改成**取所有"已到点、还没举过"里最早的那个**，前一个收掉就自然接上；
只有距到点超过 12 秒（说明是拖进度条跳过去的）才记作跳过。

**7. 选择题的选项每次都重新洗牌**
否则正确答案总落在 A，一眼就能猜。按钮上的 `data-k` 始终是数据里的原始下标，
判分和状态恢复都按它走；`keepLast: 1` 可以把「完全没听清」这类兜底项钉在最后。

**8. 知识点宁可讲深，不要讲多**
这是整个 demo 真正的内容核心。一句台词值不值得做成卡，标准是
**"不讲你就真的看不懂/说不对"**，而不是"这里有个生词"。
所以像 `whosoever be he worthy shall haveth` 这种一句里叠了
古体词 + 虚拟语气倒装 + 泛指 he + **故意造错的 -eth** 的台词，
必须整句拆开讲；而 `Be right back` 这类查一下就懂的，一个字都不用写。
`kind: 'grammar'` 就是为这种"必须讲结构"的点加的。

---

## 数据结构（换剧只改 data.js）

```js
{
  id, show, showZh, episode, title, video, cover, duration,
  clipEnd,                      // 片源尾部还接着别的戏时，掐掉
  maskStyle: 'solid',           // letterbox 片源用近似纯色遮罩
  hardsubMask: 23,              // 遮罩总高度（%）
  maskOpaque: 22,               // 其中纯色段高度（%），须 ≥ 逐秒扫出的最坏字幕上沿
  topMask: 16, topMaskOpaque: 15.2,   // 顶部台标同理
  recommendPoints: ['a1','a6'], // 第 1 轮末题没命中时的兜底推荐
  lines:    [{ id, start, end, sp, en, zh }],   // sp 须两来源交叉核对
  glossary: { word: { pos, zh, note } },        // key 必须能在台词里点到
  moments:  [{ at, pointId, hook }],   // 与 points 一一对应
  points:   [{ id, lineId, kind, tag, phrase, zh, matchKeys, headline,
               why, contrast, examples, culture, swap, pron }],
  blindQuiz: [...],   // answer:null 不当场判分；pointId 指向回声链接的卡；keepLast 固定末位选项
  finalQuiz: [...],
}
```

`kind` 有四种，决定标签配色和讲解卡默认打开哪个 Tab：
`idiom` 地道表达 ／ `pron` 发音（默认落发音 Tab）／ `culture` 文化梗 ／ `grammar` 语法。
`matchKeys` 用于第 1 轮「印象最深的表达」的回声匹配。
`glossary` 的 key 要用**台词里真实出现的形式**（小写、去标点后能对上），
否则那个词在字幕里点不开 —— 校验脚本会把对不上的 key 报出来。

---

## 接入 WeSmartFlow 探索页

已按 [examples/README.md](../README.md) 的三类契约接入，不再需要软链：

| 契约 | 本主题的实现 |
|---|---|
| 内容契约 | `explore-catalog.json` 中 id 为 `bingemate` 的条目 |
| 构建契约 | `package.json` 的 `build:wesmartflow` → `build-wesmartflow.mjs` |
| 服务契约 | 同源静态路径 `/bingemate/`；不需要后端 |

```text
examples/English_clip_mate/     源码
  └── build-wesmartflow.mjs     白名单复制 8 个文件
        ↓  WESMARTFLOW_EXAMPLE_OUT_DIR
frontend/public/bingemate/       主站托管产物（已被 gitignore）
        ↓
/bingemate/index.html?source=wesmartflow
```

三点实现说明：

1. **不需要重写资源路径。** 页面里 `styles.css`、`app.js`、`*.mp4` 全是同目录相对路径，
   复制到任何 `publicPath` 下都能正确解析，所以构建脚本只做复制。
2. **`?source=wesmartflow` 切换返回入口。** 带该参数时顶栏变成「← 返回探索」指向 `/#/explore`；
   直接打开或独立部署时保持原来的 WeSmartFlow 外链，两种入口互不影响。
3. **`localStorage` 带命名空间和版本**：`bingemate:<key>:v1`。
   早期无版本号的 `bingemate_<key>` 会在首次读取时自动迁移，老进度不丢。

新增视频或图片素材后，记得同步 `build-wesmartflow.mjs` 里的 `ASSETS` 白名单，否则不会进入产物。

> 视频片段仅作教学演示用途引用，版权归原权利人所有。
> 若要公开发布，建议进一步缩短片段或替换为无版权素材。
