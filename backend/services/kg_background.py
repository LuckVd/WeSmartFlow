"""
KG 后台周期任务

启动时由 main.on_startup 调用 ``start_kg_background_loops()``,
关闭时由 main.on_shutdown 调用 ``stop_kg_background_loops()``。

最小形态下只有一条后台 loop：
  - AggregatorService.run_once : observation → 共性归纳 → 产 suggest_facet_pattern proposal

设计点：
  - 用 asyncio.create_task 跑在 FastAPI 主事件循环里
  - 实际工作放到 to_thread（内部是同步阻塞 IO）
  - 异常被吞掉（仅打日志），永不让循环挂掉
  - 重复调用是幂等的（用 module-level set 防重）
  - 保留对 task 的强引用，防止 asyncio 弱引用回收（官方推荐做法）
"""

from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)

# 用集合代替模块级 bool / Optional[Task]，避免 `global` 语句，
# 同时保留对 task 的强引用，防止 asyncio 弱引用回收。
_started: set[str] = set()
_background_tasks: set[asyncio.Task] = set()


def start_kg_background_loops() -> None:
    """启动所有 KG 后台周期任务（幂等）。"""
    start_kg_aggregator_loop()
    start_kg_probe_warmup()


async def stop_kg_background_loops() -> None:
    """优雅关闭所有 KG 后台周期任务（在 FastAPI on_shutdown 中调用）。"""
    pending = [t for t in _background_tasks if not t.done()]
    for t in pending:
        t.cancel()
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)
    _background_tasks.clear()
    _started.clear()


def _spawn(name: str, coro) -> bool:
    """创建后台 task 并登记，自动在结束时从集合中移除。返回是否成功创建。"""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        logger.warning("no running event loop, skip kg %s loop", name)
        return False
    task = loop.create_task(coro, name=f"kg_{name}_loop")
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    _started.add(name)
    return True


# ============================================================
# 关系语义 probe 预热
# ============================================================


def start_kg_probe_warmup() -> None:
    """后台预热关系语义 probe 表（幂等，daemon 线程，不阻塞启动）。

    probe 表要把几十条探针文本送去远程 embedding，冷启动要好几秒；若留给
    第一个用户请求去建，前置检索会超时、该轮白白跳过 KG 注入。
    只在 embedder 可用**且** KG 已有 approved concept 时才预热，
    空库不发起任何网络调用。
    """
    if "probe_warmup" in _started:
        return
    _started.add("probe_warmup")

    import threading

    threading.Thread(target=_warmup_probes, name="kg-probe-warmup", daemon=True).start()


def _warmup_probes() -> None:
    try:
        from kg.embedder import get_embedder
        from kg.relation_semantics import get_probes
        from kg.repositories import ConceptRepository

        embedder = get_embedder()
        if not embedder or getattr(embedder, "dim", 0) <= 0:
            return
        if not ConceptRepository().exists_any_approved():
            return
        probes = get_probes()
        logger.info("KG 关系语义 probe 预热完成 enabled=%s", probes.enabled)
    except Exception:  # pylint: disable=broad-except
        logger.warning(
            "KG 关系语义 probe 预热失败（首个检索请求会按需构建）", exc_info=True
        )


# ============================================================
# Aggregator loop（observation → suggest_facet_pattern proposal）
# ============================================================


def start_kg_aggregator_loop() -> None:
    """在当前事件循环里启动 KG 聚合器周期任务（幂等）。"""
    if "aggregator" in _started:
        return

    try:
        from kg.config import KG_AGGREGATOR_BATCH_SIZE, KG_AGGREGATOR_PERIOD_SEC
    except Exception:  # pylint: disable=broad-except
        logger.exception("无法读取 KG 聚合器配置，跳过启动")
        return

    if KG_AGGREGATOR_PERIOD_SEC <= 0:
        logger.info("KG_AGGREGATOR_PERIOD_SEC <= 0，跳过启动周期任务")
        return

    if not _spawn(
        "aggregator",
        _aggregator_run_loop(
            period=KG_AGGREGATOR_PERIOD_SEC, batch=KG_AGGREGATOR_BATCH_SIZE
        ),
    ):
        return

    logger.info(
        "KG 聚合器周期任务已启动: period=%ss batch=%d",
        KG_AGGREGATOR_PERIOD_SEC,
        KG_AGGREGATOR_BATCH_SIZE,
    )


async def _aggregator_run_loop(period: int, batch: int) -> None:
    # 启动后稍等一会再跑，避免 startup 期间和其它初始化挤资源
    await asyncio.sleep(min(30, period))
    while True:
        try:
            stats = await asyncio.to_thread(_aggregator_run_once, batch)
            if stats and stats.get("proposed"):
                logger.info("KG 聚合器一轮完成: %s", stats)
        except Exception:  # pylint: disable=broad-except
            logger.exception("KG 聚合器周期任务异常（已吞掉，继续下一轮）")
        await asyncio.sleep(period)


def _aggregator_run_once(batch: int) -> dict:
    from services import kg_facade

    return kg_facade.run_aggregator_once(batch_size=batch)
