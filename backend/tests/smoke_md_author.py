"""
冒烟脚本: 单独跑两个写回 Agent, 沙箱 md 目录, 不污染真实 knowledge/。

用法 (在 conda env edu-agent 下):
    python -m tests.smoke_md_author facet-add
    python -m tests.smoke_md_author facet-merge
    python -m tests.smoke_md_author facet-replace
    python -m tests.smoke_md_author concept
    python -m tests.smoke_md_author all

运行后会打印沙箱目录路径,不会自动清理,你可以人工查看 md 文件再决定是否 rm -rf。

设计:
  - 不通过 services.md_author_service.MdAuthorService 的单例
    (因为该单例里 4 个 md 工具都用了默认 knowledge_root 写到真实目录)
  - 直接复用 service 里的 _FACET_AUTHOR_SYSTEM_PROMPT / _CONCEPT_AUTHOR_SYSTEM_PROMPT
  - 4 个 md 工具用沙箱 knowledge_root 构造
  - KG / smart_search 工具不替换 (任务 2 真要联 KG 才有意义,空 KG 也能跑,
    只是 Agent 拿不到邻居,自己挑 subject)

注意:
  - 任务 2 (concept) 依赖向量库, 若你的本地 KG 是空的, Agent 会拿到空邻居,
    仍能完成建档,但 subject/related 会偏弱;首次冒烟主要看「6 步流程是否走完」,
    不要太挑剔产出质量。
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import tempfile
from pathlib import Path

# 让脚本可以独立跑: 把 backend 加进 path
_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from agent_core.agent.events import AgentFinishReason  # noqa: E402
from agent_core.agent.react import ReActAgent  # noqa: E402
from agent_core.context.static import StaticPromptBuilder  # noqa: E402
from agent_core.tool.registry import ToolRegistry  # noqa: E402

from agents.tools.kg_tools import (  # noqa: E402
    KGResolveForAuthoringTool,
    KGSearchForAuthoringTool,
)
from agents.tools.md_writer_tools import (  # noqa: E402
    MdCreateConceptTool,
    MdLoadConceptTool,
    MdLoadFacetSectionTool,
    MdWriteFacetSectionTool,
)

# 引用 service 里写好的两份 prompt, 保证测的就是真品
from services.md_author_service import (  # noqa: E402
    _CONCEPT_AUTHOR_SYSTEM_PROMPT,
    _FACET_AUTHOR_SYSTEM_PROMPT,
)
from services.llm_factory import get_system_llm  # noqa: E402
from services.smart_search.tool import SmartSearchTool  # noqa: E402


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("smoke_md_author")


# ============================================================
# 沙箱
# ============================================================


def _make_sandbox() -> Path:
    """建沙箱目录 (不删, 留给人看)。"""
    root = Path(tempfile.mkdtemp(prefix="edu-smoke-md-"))
    logger.info("[sandbox] %s", root)
    return root


def _seed_concept_md(sandbox: Path, *, subject: str, slug: str) -> Path:
    """给任务 1 冒烟预置一份概念 md, 含「常见误解」H1 下两条 bullet。"""
    target = sandbox / subject / f"{slug}.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        # 注意: front matter 字段名要和 MdLoadConcept/MdLoadFacetSection 期望对得上,
        # 真实工具里只校验 H1 段, front matter 走 YAML 即可
        "---\n"
        f"slug: {slug}\n"
        f"subject: {subject}\n"
        f"canonical_name: 极限的定义\n"
        f"summary: 函数极限的 epsilon-delta 定义\n"
        f"difficulty: 3\n"
        "---\n\n"
        "# 直观理解\n\n"
        "极限描述的是当自变量趋近某点时, 函数值的趋势。\n\n"
        "# 严格定义\n\n"
        "对任意 ε>0, 存在 δ>0, 使得当 0<|x-a|<δ 时, |f(x)-L|<ε。\n\n"
        "# 常见误解\n\n"
        "- 把 lim_{x→a} f(x)=L 理解成 f(a)=L (函数在 a 不一定有定义/连续)\n"
        "- 以为 ε 和 δ 顺序可以颠倒 (实际上必须先给 ε, 再找 δ)\n",
        encoding="utf-8",
    )
    logger.info("[seed] %s", target)
    return target


# ============================================================
# Agent 装配 (沙箱版)
# ============================================================


def _build_facet_agent(sandbox: Path) -> ReActAgent:
    registry = ToolRegistry(
        [
            MdLoadFacetSectionTool(knowledge_root=sandbox),
            MdWriteFacetSectionTool(knowledge_root=sandbox),
        ]
    )
    return ReActAgent(
        llm=get_system_llm(timeout=90),
        prompt_builder=StaticPromptBuilder(_FACET_AUTHOR_SYSTEM_PROMPT),
        tool_registry=registry,
        max_steps=8,
    )


def _build_concept_agent(sandbox: Path) -> ReActAgent:
    registry = ToolRegistry(
        [
            KGResolveForAuthoringTool(),
            KGSearchForAuthoringTool(),
            MdLoadConceptTool(knowledge_root=sandbox),
            SmartSearchTool(),
            MdCreateConceptTool(knowledge_root=sandbox),
        ]
    )
    return ReActAgent(
        llm=get_system_llm(timeout=120),
        prompt_builder=StaticPromptBuilder(_CONCEPT_AUTHOR_SYSTEM_PROMPT),
        tool_registry=registry,
        max_steps=16,
    )


# ============================================================
# 用例输入
# ============================================================


def _facet_input(*, slug: str, h1: str, new_text: str, label: str) -> str:
    return (
        "# 任务: 共性反馈写回\n"
        f"proposal_id: smoke-{label}\n"
        f"slug: {slug}\n"
        f"subject: 数学\n"
        f"h1: {h1}\n"
        "proposer: smoke_test\n"
        "observation_count: 5\n"
        "\n"
        "新反馈正文 (已审核通过):\n"
        "```\n"
        f"{new_text.strip()}\n"
        "```\n"
        "\n"
        "请按 system prompt 描述的 read → think → write 流程完成,"
        "完成后输出 [FACET_DONE] 行结束。"
    )


# 三个 case 的"已审核新反馈" —— 故意构造,看 Agent 是否选对 action
_FACET_CASES = {
    # add: 全新主题,与 seed 中两条都不同
    "add": (
        "学生常常忘记 lim_{x→a} f(x) 是关于 x→a 的极限, 不是关于 x=a 的赋值; "
        "尤其在做分段函数题时容易把 a 处的值和极限混淆。"
    ),
    # merge: 与 seed 第二条 (ε δ 顺序) 是同一个主题, 补充了「为什么不能颠倒」的解释
    "merge": (
        "ε δ 顺序错的本质原因是: ε 是「容许的误差」, δ 是「依赖于 ε 才能确定的邻域宽度」; "
        "因此必须先给定 ε 才能找到 δ, 这是函数极限定义的逻辑结构, 不是约定。"
    ),
    # replace: 故意伪造一个 seed 中第一条「f(a)=L」的"错误旧版"已经在文件里 (其实 seed 里那条是对的描述),
    # 这里我们让"新反馈"主张原条目的措辞误导学生, 给出更准的版本 → 期望 replace
    "replace": (
        "原条目「把 lim_{x→a} f(x)=L 理解成 f(a)=L」措辞容易让人以为只是"
        "「f(a) 与极限相等」的误解; 更准的描述是: 极限的存在与否完全与 f(a) 的值"
        "甚至 f 是否在 a 处有定义无关, 这是关键。"
    ),
}


def _concept_input() -> str:
    return (
        "# 任务: 新概念建档\n"
        "proposal_id: smoke-concept\n"
        "concept_name: 罗尔定理\n"
        "proposer: smoke_test\n"
        "\n"
        "提议理由:\n"
        "  多次观察发现学生在学习中值定理时缺少前置概念「罗尔定理」的独立卡片,"
        "  常常和拉格朗日中值定理混在一起。\n"
        "\n"
        "请按 system prompt 描述的 6 步流程完成建档,完成后输出 [CONCEPT_DONE] 或 [CONCEPT_ABORT] 行。"
    )


# ============================================================
# 跑一个 case
# ============================================================


async def _run_one(agent: ReActAgent, user_input: str, *, label: str) -> dict:
    logger.info("[run:%s] start", label)
    try:
        result = await agent.async_run(user_input)
    except Exception as exc:  # pylint: disable=broad-except
        logger.exception("[run:%s] exception", label)
        return {"ok": False, "error": str(exc)}

    output = (result.output or "").strip()
    finish_reason = (
        result.finish_reason.value
        if isinstance(result.finish_reason, AgentFinishReason)
        else str(result.finish_reason)
    )
    last_line = output.splitlines()[-1].strip() if output else ""

    print(f"\n========== [{label}] result ==========")
    print(f"finish_reason : {finish_reason}")
    print(f"last_line     : {last_line}")
    print(f"history_len   : {len(getattr(result, 'history', []) or [])}")
    print("---------- raw output ----------")
    print(output[-2000:])  # 截尾, 防止太长
    print(f"========== [{label}] end ==========\n")

    return {
        "ok": "[FACET_DONE]" in output
        or "[CONCEPT_DONE]" in output
        or "[CONCEPT_ABORT]" in output,
        "finish_reason": finish_reason,
        "last_line": last_line,
    }


# ============================================================
# main
# ============================================================


async def _cmd_facet(case: str) -> dict:
    sandbox = _make_sandbox()
    slug = "limit-definition"
    _seed_concept_md(sandbox, subject="数学", slug=slug)

    agent = _build_facet_agent(sandbox)
    user_input = _facet_input(
        slug=slug,
        h1="常见误解",
        new_text=_FACET_CASES[case],
        label=case,
    )
    res = await _run_one(agent, user_input, label=f"facet-{case}")

    # 跑完打印当前 md 内容
    md = sandbox / "数学" / f"{slug}.md"
    print(f"---------- final md @ {md} ----------")
    print(md.read_text(encoding="utf-8"))
    return res


async def _cmd_concept() -> dict:
    sandbox = _make_sandbox()
    agent = _build_concept_agent(sandbox)
    res = await _run_one(agent, _concept_input(), label="concept")

    # 列一下沙箱里产生了什么
    print(f"---------- sandbox tree @ {sandbox} ----------")
    for p in sorted(sandbox.rglob("*.md")):
        print(f"  {p.relative_to(sandbox)}  ({p.stat().st_size} bytes)")
    return res


async def _async_main(cmd: str) -> int:
    if cmd in {"facet-add", "facet-merge", "facet-replace"}:
        case = cmd.split("-", 1)[1]
        res = await _cmd_facet(case)
        return 0 if res.get("ok") else 1

    if cmd == "concept":
        res = await _cmd_concept()
        return 0 if res.get("ok") else 1

    if cmd == "all":
        rcs = []
        for c in ["add", "merge", "replace"]:
            rcs.append(await _cmd_facet(c))
        rcs.append(await _cmd_concept())
        ok = all(r.get("ok") for r in rcs)
        print("\n========== summary ==========")
        for c, r in zip(["facet-add", "facet-merge", "facet-replace", "concept"], rcs):
            print(f"  {c:18s} ok={r.get('ok')} last={r.get('last_line', '')[:80]}")
        return 0 if ok else 1

    print(f"未知子命令: {cmd}")
    return 2


def main() -> None:
    parser = argparse.ArgumentParser(description="md_author 写回 Agent 冒烟测试")
    parser.add_argument(
        "cmd",
        choices=[
            "facet-add",
            "facet-merge",
            "facet-replace",
            "concept",
            "all",
        ],
    )
    args = parser.parse_args()

    # 防止误读 .env 里 user 的 OpenAI key:get_system_llm 默认就只读 env, 这里不必特殊处理
    rc = asyncio.run(_async_main(args.cmd))
    sys.exit(rc)


if __name__ == "__main__":
    main()
