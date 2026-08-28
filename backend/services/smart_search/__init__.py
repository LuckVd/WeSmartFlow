"""
SmartSearch: 多源并行检索服务

架构：
  Router（路由决策）→ 多源并行 Retrieve → Filter（筛选去重）→ 结构化输出

对外暴露：
  - SmartSearchService  — 可独立调用的 async 检索服务
  - SmartSearchTool     — 可注册给 Agent 的工具（依赖 agent_core，延迟导入）
"""

from .service import SmartSearchService


def SmartSearchTool(*args, **kwargs):
    """延迟导入，避免在纯评测场景下拉入 agent_core 依赖链。"""
    from .tool import SmartSearchTool as _Tool

    return _Tool(*args, **kwargs)


__all__ = ["SmartSearchService", "SmartSearchTool"]
