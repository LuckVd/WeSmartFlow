"""
ProposalService:轻提议（最小形态）的审核入口

设计
====
Proposal 表只承载两类**轻量信号**给管理员看：

  - ``suggest_missing_concept``  教学 Agent 发现 KG 缺一个有教学价值的概念
                                  payload: {concept_name, reason_brief}
  - ``suggest_facet_pattern``    Aggregator 从一桶 observations 归纳出一个共性
                                  payload: {concept_id, kind, content,
                                            observation_ids, ...}

approve / reject 由管理员在 admin 审核台触发：

  - ``reject`` 纯打 status 标记。
  - ``approve`` 打 status=approved 后，把异步落盘流水线推到 ``apply_status=queued``，
    并戳一下 ``apply_worker`` 的 asyncio.Event，让后台 worker 调
    ``MdAuthorService`` 把内容真正写到 OKF .md 文件里。
    approve 接口本身**立即返回**，不等 Agent 跑完。
"""

from __future__ import annotations

import logging
from typing import Optional

from ..models import (
    ProposalCreate,
    ProposalSchema,
)
from ..repositories import ProposalRepository

logger = logging.getLogger(__name__)


class ProposalService:
    def __init__(self) -> None:
        self.proposal_repo = ProposalRepository()

    # ---------- 创建 ----------

    def create(self, data: ProposalCreate) -> ProposalSchema:
        """统一入口：把外部提议落成一条 pending proposal。"""
        return self.proposal_repo.create(data)

    # ---------- 审核 ----------
    #
    # approve：打 status=approved，并把异步落盘流水线推到 'queued'，
    #          然后戳一下 apply_worker 的 asyncio.Event 让它去跑 Agent 写 OKF。
    # reject ：纯打 status=rejected，不入流水线。

    def approve(
        self,
        proposal_id: str,
        reviewer_id: str = "",
        review_note: str = "",
    ) -> Optional[ProposalSchema]:
        p = self.proposal_repo.get_by_id(proposal_id)
        if not p:
            return None
        if p.status != "pending":
            logger.info("approve: proposal %s 已是 %s，跳过", proposal_id, p.status)
            return p

        self.proposal_repo.update_status(
            p.id,
            status="approved",
            reviewer_id=reviewer_id,
            review_note=review_note,
        )
        # 推进异步落盘流水线 idle -> queued
        self.proposal_repo.mark_apply_queued(p.id)

        # 戳 worker（延迟 import 避免启动期循环依赖）
        try:
            from services.apply_worker import notify_apply_pending

            notify_apply_pending()
        except Exception:  # pylint: disable=broad-except
            logger.exception(
                "approve: 通知 apply_worker 失败（已写 queued，不影响数据）"
            )

        return self.proposal_repo.get_by_id(p.id)

    def reject(
        self,
        proposal_id: str,
        reviewer_id: str = "",
        review_note: str = "",
    ) -> Optional[ProposalSchema]:
        p = self.proposal_repo.get_by_id(proposal_id)
        if not p:
            return None
        if p.status != "pending":
            logger.info("reject: proposal %s 已是 %s，跳过", proposal_id, p.status)
            return p

        self.proposal_repo.update_status(
            p.id,
            status="rejected",
            reviewer_id=reviewer_id,
            review_note=review_note,
        )
        return self.proposal_repo.get_by_id(p.id)
