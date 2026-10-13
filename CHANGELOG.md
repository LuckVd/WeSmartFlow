# 生成体验改造记录

本文件记录 2026-09-19 起围绕沉浸式学习与交互式例子的性能、质量和可观测性改动。每一项都说明目的、影响范围、验证方式和回滚点。

## 2026-09-19 · 第一批：先让学习开始，再持续补全

### 1. 生产启动不再默认热重载

- **目的：** 防止长时间的课程或交互例子生成被 WatchFiles 重启中断。
- **修改：** `backend/main.py` 改为仅在 `WESMARTFLOW_RELOAD=true` 时启用 reload；`start.sh` 默认传入 `false`；README 补充本地开发启动方式。
- **验证：** 运行 `python -m py_compile backend/main.py`；以默认环境启动后日志中不应出现 `Started reloader process`。
- **回滚：** 设置 `WESMARTFLOW_RELOAD=true` 即可恢复本地热重载，无需改代码。

### 2. 沉浸式课程记录首个可学习节点

- **目的：** 把“第一个有效 PDF 可读”的时间与“整门课生成结束”分开，避免只看到总耗时。
- **修改：** `backend/services/immersive/service.py` 写入 `immersive_timing` 日志，记录会话创建、大纲、学习建议、研究完成、首章 PDF 和后续章节 PDF 的单调时钟耗时；研究并发上限设为 3，降低大纲章节数带来的供应商限流风险。
- **验证：** 开启一门课程后，在 `data/logs/app.log*` 中查看 `immersive_timing`；确认首章 PDF 对应 `first_chapter_ready`。
- **回滚：** 恢复 `max_concurrency=total_ch` 可回到全量并发检索；计时日志不改变产物和业务状态。

### 3. PDF 就绪即提示“可以开始学习”

- **目的：** 音频、习题、归档与图谱还在补全时，学习者仍能开始阅读已经通过 PDF 验证的章节。
- **修改：** 后端在 PDF 登记后写入 `learning_ready` 章节状态并发出 `chapter_learning_ready` SSE；前端加载该状态、在章节页显示“PDF 已就绪，可以开始学习”。完整章节仍在原有 `chapter_done` 事件后标记为 `ready`。
- **验证：** 以 `enable_audio=true` 创建课程；首章 PDF 出现时不等待音频即可打开，后续 `chapter_done` 仍会补齐习题和音频。
- **自动化覆盖：** `backend/tests/test_immersive_readiness.py` 保护章节状态替换与旧工作区兼容。
- **回滚：** 移除 `learning_ready` 写入和事件即可回到仅 `ready` 的旧行为。

### 4. 交互式例子：校验并行与阶段耗时

- **目的：** 缩短自由生成的关键路径，同时保留静态、浏览器和教学质量门。
- **修改：** `backend/agents/tools/generate_viz.py` 在静态检查通过后并行执行浏览器运行检查与教学审查；若浏览器预检立即失败，短路且不额外消耗审查调用。成功产物的 `meta.json → quality.timings_ms` 记录设计、代码、静态检查、浏览器检查、教学审查和代码阶段总耗时。
- **验证：** 运行 `backend/tests/test_viz_quality.py` 与 `backend/tests/test_viz_streaming.py`；生成一个 Viz 后查看对应 `meta.json` 的 `quality.timings_ms`。
- **回滚：** 将运行检查恢复为先 await、再调用 `_review_code`，即可恢复原串行路径。

### 5. 沉浸式逐页语音采用受限并发

- **目的：** 消除一章中 11–17 段旁白逐条等待造成的长尾。
- **修改：** `BaseTTS.synthesize_batch` 支持 `max_concurrency`，默认仍为 1；沉浸式课程显式使用 3 路并发。结果按原输入顺序返回，每段仍独立触发额度和用量 hook，单段失败不会影响其他段。
- **验证：** 运行 `backend/tests/test_tts_batch.py`；生成带音频课程时观察同章音频日志交错完成，且 manifest 帧顺序不变。
- **回滚：** 将沉浸式调用的 `max_concurrency` 改回 1，即恢复顺序合成。

### 6. 保护“PDF 已就绪但补全未完成”的会话

- **目的：** 用户在首章 PDF 已可学习、音频或图谱仍在生成时离开，不能被误判为空壳会话。
- **修改：** 异常收尾逻辑把 `learning_ready` 与 `ready` 一样视为有效产出，保留会话供后续恢复。
- **验证：** `backend/tests/test_immersive_readiness.py` 覆盖章节状态；生成中断后应保留 workspace 和课程目录。

## 后续批次（尚未实施）

- 将沉浸式生成迁移为持久化 job + worker + SSE 事件回放，解决离页即中断。
- 将课程流程改为章节级 DAG：研究完成即送入 PDF 队列，音频/归档/图谱走限流后台队列。
- 给高频交互题型提供参数化模板和独立参考计算器；复杂主题继续使用开放生成与完整质量门。
- 将 VizSpec 的自然语言交互检查转为可执行断言，并为前端补齐阶段进度、失败原因和重试入口。

## 2026-09-19 · 第二批：可脱离页面的课程任务

- 生成任务现在由 `immersive_job_manager` 持有，SSE 变成进度订阅；页面断开默认转入后台继续。
- 离开弹窗提供“留在当前页 / 后台继续 / 停止并离开”。停止会取消当前任务，但保留已经落盘的课程产物。
- 重新进入课程仍可通过已有 workspace 和 `/api/immersive/resume` 进行磁盘审计式续传。
- 当前后台任务生命周期仍依赖后端进程；如果后端进程重启，已落盘内容保留，用户可以重新进入后继续生成。
- 自动化覆盖：`backend/tests/test_immersive_job_manager.py` 验证断开后继续广播、事件回放和取消任务。
- 浏览器直接关闭标签页时不再弹原生中断提示；由于后端默认将断线转后台，该场景等同于“后台继续”。
