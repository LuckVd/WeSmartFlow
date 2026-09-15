"""
调用钩子：把 ``pre -> 真实调用 -> post`` 编排成一条可改写数据的管道。

为什么需要它
------------
记账、限流、参数注入、结果加工这类横切关注点，如果直接写进被调用者
（例如某个 LLM provider）的实现里，会带来三个问题：

1. **实现被污染**：想知道「记账何时发生」得读懂 provider 内部代码，
   响应转换这种本该是纯函数的地方出现副作用。
2. **易漏**：每新增一个实现都要「记得」在自己内部插一遍。
3. **状态泄漏**：闭包捕获的 user_id / scene 属于单次运行状态，
   挂到可复用的客户端实例上会破坏无状态约定、阻碍连接池化。

本模块只负责编排，不认识 LLM、不认识业务，可用于任何可调用对象。

两类 hook
---------
按「是否动手改数据」把 hook 分成两类，声明时指定，无需两套 API：

====================  ==============================  ==========================
类型                  行为                            返回值
====================  ==============================  ==========================
``OBSERVE``（观察）   只看不动手                      **被忽略**，数据原样透传
``HANDLE``（处理）    动手改写                        **成为新的数据**
====================  ==============================  ==========================

区分它们的实际收益：

* **观察型不会因为忘记 return 而吞掉数据**。用量记账、日志、埋点这类
  hook 若按处理型写，一旦漏写 ``return result`` 就会把调用结果变成
  ``None``——这是极易犯且难排查的错误。
* **观察型的异常可以安全吞掉**。它不在数据路径上，失败只影响观测本身，
  不该拖垮业务。处理型则必须让异常传播，否则无法构造出合理的返回值。
* **意图自解释**。读到 ``observe(record_usage)`` 就知道它不会改数据。

用 :func:`observe` / :func:`handle` 包装函数来声明类型：

.. code-block:: python

    # 观察型：返回值随便，不影响结果；内部异常被吞
    hookwrapper(fn, post=observe(lambda r: log(r.usage)))

    # 处理型：返回值即最终结果
    hookwrapper(fn, post=handle(lambda r: sanitize(r)))

未声明类型的裸函数**默认按处理型对待**（向后兼容，且「返回值有意义」
是更保守的假设——不会静默丢弃调用方本意要生效的改写）。

管道语义
--------
hook 是**数据管道上的两个节点**：

.. code-block:: text

    (*args, **kwargs)
           │
           ▼
      ┌─────────┐
      │   pre   │  观察型：只读入参 / 处理型：返回改造后的入参
      └─────────┘
           │  (args, kwargs)
           ▼
      ┌─────────┐
      │   fn    │  真实调用，完全不感知 hook 的存在
      └─────────┘
           │  result
           ▼
      ┌─────────┐
      │  post   │  观察型：只读结果 / 处理型：返回值成为最终结果
      └─────────┘
           │
           ▼
      最终返回值

pre 契约
--------
签名 ``pre(*args, **kwargs)``，可为同步或异步函数。

**观察型**：返回值被忽略，入参原样传给 ``fn``。

**处理型**：返回值决定 ``fn`` 的入参——

======================  =====================================================
返回值                  含义
======================  =====================================================
``None``                入参保持不变
``(args, kwargs)``      二元组（第二项须为 dict），分别替换两者
``dict``                只替换关键字参数
``tuple``/``list``      只替换位置参数
======================  =====================================================

两类 pre 抛出的异常都会原样传播且**阻断真实调用**——
这正是额度拦截、参数非法校验所需的语义。

post 契约
---------
签名 ``post(result)``，可为同步或异步函数。

**观察型**：返回值被忽略，``result`` 原样返回；hook 内部异常被吞并记日志。

**处理型**：返回值即最终结果；异常原样传播。

支持的被包装形态
----------------
挂 pre 无限制；挂 post 时被包装函数只能是以下三种形态之一：

====================  ==========================  ==========================
形态                  判定                        post 接收的 result
====================  ==========================  ==========================
普通函数              普通 ``def``                返回值
异步函数              ``iscoroutinefunction``     await 后的返回值
异步生成器函数        ``isasyncgenfunction``      **最后一个** yield 的元素
====================  ==========================  ==========================

异步生成器场景下，前 N-1 个元素原样透传；最后一个元素交给 post，
处理型 post 的返回值取代它，观察型则保持原样。
实现上需要向前多看一个元素才能判断"哪个是最后一个"，
因此最后一个元素的产出会被推迟到生成器耗尽之后。

**同步生成器函数不支持挂 post**：它的返回值语义与上述三种都不同，
且本项目无此用例，故直接报错而非给出可疑的默认行为。

异常语义
--------
======================  =====================================================
位置                    行为
======================  =====================================================
pre 抛出                原样传播，真实调用**不执行**（两类相同）
fn 抛出                 原样传播，post **不触发**（失败不产生副作用/计费）
post 抛出（处理型）      原样传播
post 抛出（观察型）      吞掉并记 warning，结果原样返回
======================  =====================================================
"""

from __future__ import annotations

import asyncio
import functools
import inspect
import logging
from enum import Enum
from typing import Any, AsyncGenerator, Callable, Dict, Optional, Tuple, TypeVar

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])

#: pre hook：``(*args, **kwargs) -> None | (args, kwargs) | dict | tuple``
PreHook = Callable[..., Any]
#: post hook：``(result) -> final_result``
PostHook = Callable[[Any], Any]

# 用于区分"没有元素"与"元素恰好是 None"
_MISSING = object()

# 声明 hook 类型的属性名，挂在函数对象上
_KIND_ATTR = "__hook_kind__"


class HookKind(str, Enum):
    """hook 类型。

    OBSERVE
        观察型——只读数据，返回值被忽略，内部异常被吞。
    HANDLE
        处理型——返回值成为新的数据，异常向上传播。
    """

    OBSERVE = "observe"
    HANDLE = "handle"


def observe(fn: Callable) -> Callable:
    """把 ``fn`` 声明为**观察型** hook。

    观察型 hook 不参与数据改写：返回值被忽略、数据原样透传，
    且内部异常会被吞掉并记 warning——观测失败不该拖垮业务。

    适用于记账、日志、埋点、指标上报等旁路场景：

    .. code-block:: python

        hookwrapper(llm.async_think, post=observe(record_usage))

    Returns:
        同一个函数对象（附加了类型标记），可直接作为 hook 传入。
    """
    setattr(fn, _KIND_ATTR, HookKind.OBSERVE)
    return fn


def handle(fn: Callable) -> Callable:
    """把 ``fn`` 声明为**处理型** hook（默认行为，声明后意图更清晰）。

    处理型 hook 的返回值会成为新的入参 / 最终结果，异常向上传播。

    .. code-block:: python

        hookwrapper(fn, pre=handle(inject_default_params))

    Returns:
        同一个函数对象（附加了类型标记）。
    """
    setattr(fn, _KIND_ATTR, HookKind.HANDLE)
    return fn


def _kind_of(hook: Optional[Callable]) -> HookKind:
    """取 hook 的声明类型；未声明则视为处理型。

    默认处理型是更保守的假设：不会静默丢弃调用方本意要生效的改写。
    """
    if hook is None:
        return HookKind.HANDLE
    return getattr(hook, _KIND_ATTR, HookKind.HANDLE)


def _normalize_pre_result(
    ret: Any, args: Tuple[Any, ...], kwargs: Dict[str, Any]
) -> Tuple[Tuple[Any, ...], Dict[str, Any]]:
    """把 pre 的返回值归一化为 ``(args, kwargs)``。

    支持四种返回形态，详见模块文档的 pre 契约表。
    """
    if ret is None:
        return args, kwargs

    # 只替换关键字参数
    if isinstance(ret, dict):
        return args, ret

    if isinstance(ret, (tuple, list)):
        # (args, kwargs) 二元组：第二项必须是 dict 才视为该形态，
        # 否则按"只替换位置参数"处理，避免误吞形如 (a, b) 的普通参数元组
        if len(ret) == 2 and isinstance(ret[1], dict):
            new_args = ret[0]
            if not isinstance(new_args, (tuple, list)):
                new_args = (new_args,)
            return tuple(new_args), ret[1]
        return tuple(ret), kwargs

    raise TypeError(
        "pre hook 返回值形态非法：应为 None / (args, kwargs) / dict / tuple，"
        f"实际为 {type(ret).__name__}"
    )


def _apply_pre_sync(
    pre: Optional[PreHook], args: Tuple[Any, ...], kwargs: Dict[str, Any]
) -> Tuple[Tuple[Any, ...], Dict[str, Any]]:
    """同步路径下执行 pre 并取得改造后的入参。

    pre 返回协程时必须就地跑完——不能 fire-and-forget，
    否则「必须先完成才能继续」的语义（如额度检查）会失效。
    """
    if pre is None:
        return args, kwargs

    ret = pre(*args, **kwargs)
    if inspect.isawaitable(ret):
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            # 当前线程无运行中的事件循环，可安全就地执行
            ret = asyncio.run(_resolve(ret))
        else:
            # 同步函数运行在事件循环线程内，无法在此 await。
            # 静默丢弃会让 pre 形同虚设，故显式报错。
            raise RuntimeError(
                "同步调用路径下 pre hook 返回了协程，且当前线程已有运行中的"
                "事件循环，无法安全等待。请改用异步入口，或提供同步版 pre hook。"
            )
    if _kind_of(pre) is HookKind.OBSERVE:
        return args, kwargs
    return _normalize_pre_result(ret, args, kwargs)


async def _resolve(awaitable: Any) -> Any:
    return await awaitable


async def _apply_pre_async(
    pre: Optional[PreHook], args: Tuple[Any, ...], kwargs: Dict[str, Any]
) -> Tuple[Tuple[Any, ...], Dict[str, Any]]:
    """异步路径下执行 pre，兼容同步与异步实现。"""
    if pre is None:
        return args, kwargs

    ret = pre(*args, **kwargs)
    if inspect.isawaitable(ret):
        ret = await ret
    # 观察型不改写入参
    if _kind_of(pre) is HookKind.OBSERVE:
        return args, kwargs
    return _normalize_pre_result(ret, args, kwargs)


def _apply_post_sync(post: Optional[PostHook], result: Any) -> Any:
    """同步路径下执行 post。

    观察型：返回值被忽略，异常被吞，``result`` 原样返回。
    处理型：返回值即最终结果，异常向上传播。
    """
    if post is None:
        return result

    observing = _kind_of(post) is HookKind.OBSERVE
    try:
        out = post(result)
        if inspect.isawaitable(out):
            try:
                asyncio.get_running_loop()
            except RuntimeError:
                out = asyncio.run(_resolve(out))
            else:
                # 无法安全等待：观察型可放弃（仅丢失观测），处理型必须报错
                if observing:
                    out.close()
                    logger.warning(
                        "同步路径下观察型 post hook 是 async 且已有运行中的事件循环，"
                        "本次观测被跳过。建议改用异步入口或提供同步版 hook。"
                    )
                    return result
                raise RuntimeError(
                    "同步调用路径下处理型 post hook 返回了协程，且当前线程已有"
                    "运行中的事件循环，无法安全等待。请改用异步入口，"
                    "或提供同步版 post hook。"
                )
    except Exception:  # pylint: disable=broad-except
        if not observing:
            raise
        logger.warning("观察型 post hook 执行失败，已忽略", exc_info=True)
        return result

    return result if observing else out


async def _apply_post_async(post: Optional[PostHook], result: Any) -> Any:
    """异步路径下执行 post，兼容同步与异步实现。

    观察型：返回值被忽略，异常被吞，``result`` 原样返回。
    处理型：返回值即最终结果，异常向上传播。
    """
    if post is None:
        return result

    observing = _kind_of(post) is HookKind.OBSERVE
    try:
        out = post(result)
        if inspect.isawaitable(out):
            out = await out
    except Exception:  # pylint: disable=broad-except
        if not observing:
            raise
        logger.warning("观察型 post hook 执行失败，已忽略", exc_info=True)
        return result

    return result if observing else out


def hookwrapper(
    fn: F,
    pre: Optional[PreHook] = None,
    post: Optional[PostHook] = None,
) -> F:
    """把 ``fn`` 包装成 ``pre -> fn -> post`` 的数据管道。

    被包装函数本身不做任何改动、也不感知 hook 的存在。
    自动识别同步函数 / 异步函数 / 异步生成器函数三种形态。

    hook 分观察型与处理型两类，用 :func:`observe` / :func:`handle` 声明；
    未声明按处理型对待。两者语义差异见模块文档。

    Args:
        fn:   被包装的可调用对象。
        pre:  见模块文档的 pre 契约。抛出异常会阻断真实调用。
        post: 见模块文档的 post 契约。处理型的返回值即最终结果；
              观察型的返回值被忽略、异常被吞。

    Returns:
        与 ``fn`` 形态一致的包装函数（``functools.wraps`` 保留元信息）。
        ``pre`` 与 ``post`` 均为 ``None`` 时直接返回 ``fn`` 本身，零开销。

    Raises:
        TypeError: 对同步生成器函数挂 post（该形态不受支持）。

    Note:
        **不要对存在委托关系的方法重复装饰**。例如某基类的
        ``stream_think`` 默认实现内部会调用 ``async_think``，
        若两者都装饰，一次调用会触发两次 post。
        装饰应只在单一层面进行。
    """
    if pre is None and post is None:
        return fn

    if post is not None and inspect.isgeneratorfunction(fn):
        raise TypeError(
            f"同步生成器函数 {getattr(fn, '__qualname__', fn)!r} 不支持挂 post hook："
            "其返回值语义与支持的三种形态均不同。请改用异步生成器，"
            "或仅挂 pre hook。"
        )

    if inspect.isasyncgenfunction(fn):

        @functools.wraps(fn)
        async def _agen_wrapper(*args: Any, **kwargs: Any) -> AsyncGenerator[Any, None]:
            args, kwargs = await _apply_pre_async(pre, args, kwargs)

            # 需要向前多看一个元素才能判断谁是最后一个：
            # 始终暂存当前元素，取到下一个时再把暂存的那个 yield 出去。
            pending: Any = _MISSING
            async for item in fn(*args, **kwargs):
                if pending is not _MISSING:
                    yield pending
                pending = item

            # 生成器耗尽：pending 即最后一个元素，交给 post 改写后产出。
            # 一个元素都没产出时不触发 post——没有可供改写的结果。
            if pending is not _MISSING:
                yield await _apply_post_async(post, pending)
            elif post is not None:
                logger.debug(
                    "异步生成器 %s 未产出任何元素，post hook 未触发",
                    getattr(fn, "__qualname__", fn),
                )

        return _agen_wrapper  # type: ignore[return-value]

    if inspect.iscoroutinefunction(fn):

        @functools.wraps(fn)
        async def _coro_wrapper(*args: Any, **kwargs: Any) -> Any:
            args, kwargs = await _apply_pre_async(pre, args, kwargs)
            result = await fn(*args, **kwargs)
            return await _apply_post_async(post, result)

        return _coro_wrapper  # type: ignore[return-value]

    @functools.wraps(fn)
    def _sync_wrapper(*args: Any, **kwargs: Any) -> Any:
        args, kwargs = _apply_pre_sync(pre, args, kwargs)
        result = fn(*args, **kwargs)
        return _apply_post_sync(post, result)

    return _sync_wrapper  # type: ignore[return-value]
