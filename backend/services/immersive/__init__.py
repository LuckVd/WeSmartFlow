"""沉浸式学习（AI主导学习）服务包。

对外暴露：
  - immersive_generate: SSE 异步生成器（首次生成）
  - immersive_resume: SSE 异步生成器（断点续传）
  - get_exercises_for_chapter: 获取某章习题数据
  - import_questions_to_bank: 把解析好的习题沉淀进题库
  - complete_immersive_session: 用户主动确认完成

其余子模块（sse / repository / agents / tts / node_extractor / utils）
均为内部实现细节，不建议外部直接 import。
"""

from services.immersive.service import immersive_generate, immersive_resume
from services.immersive.exercises import (
    get_exercises_for_chapter,
    import_questions_to_bank,
)
from services.immersive.completion import complete_immersive_session

__all__ = [
    "immersive_generate",
    "immersive_resume",
    "get_exercises_for_chapter",
    "import_questions_to_bank",
    "complete_immersive_session",
]
