"""通用小工具。

放置无业务状态、可被任意 Agent 复用的轻量工具。
"""

from __future__ import annotations

from datetime import datetime

from agent_core.tool.decorator import tool


@tool
def get_current_time() -> str:
    """获取当前的日期和时间（北京时间，CST，UTC+8）"""
    from zoneinfo import ZoneInfo

    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    return now.strftime("%Y年%m月%d日 %H:%M:%S（北京时间，周%A）")


__all__ = ["get_current_time"]
