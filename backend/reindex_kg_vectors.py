"""KG 向量全量重建（换 embedding 模型 / 维度后使用）。

做什么
------
把 ``kg.db`` 里全部 approved concept 与 active facet，用**当前** ``KG_EMBEDDING_*``
配置重新 embed，写入一份**全新**的向量库文件（默认 ``<KG_DATA_DIR>/kg_vec.new.db``）。
线上正在使用的 ``kg_vec.db`` 不会被触碰，检索全程不受影响；确认无误后再换文件、重启。

为什么必须重建
--------------
向量库只存 float，不记录是哪个模型生成的。换模型后维度若不变（例如
text-embedding-v4 → text-embedding-3-large@1024），vec0 表不会触发"维度不匹配
DROP 重建"，新 query 向量会拿去和旧模型的向量做余弦——结果静默失真。

不在这里重建的东西
------------------
- 关系语义 probe（``relation_semantics``）：进程内缓存，重启自动重建。
- 入口条件 probe 的 ``lru_cache``：同上，重启即清。
- ``kg.db`` 里的 concept / facet / edge 本身：不改，只刷新其 ``embedding_model``、
  ``vector_id`` 两列（记录向量由哪个模型生成）。

用法（在 ``backend/`` 目录下）::

    python -m reindex_kg_vectors --dry-run          # 只统计，不调用 embedding
    python -m reindex_kg_vectors                    # 重建到 kg_vec.new.db
    python -m reindex_kg_vectors --out /path/x.db   # 指定输出文件
    python -m reindex_kg_vectors --overwrite        # 输出文件已存在时先删除

完成后（先停服务或在低峰期）::

    cd <KG_DATA_DIR>
    mv kg_vec.db kg_vec.old.db && rm -f kg_vec.db-wal kg_vec.db-shm
    mv kg_vec.new.db kg_vec.db
    # 重启后端；回滚 = 把 kg_vec.old.db 改回 kg_vec.db 再重启
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="KG 向量全量重建（写入新文件，不动线上库）")
    p.add_argument("--out", type=Path, default=None, help="输出向量库文件路径")
    p.add_argument(
        "--dry-run", action="store_true", help="只统计数量，不调用 embedding"
    )
    p.add_argument("--overwrite", action="store_true", help="输出文件已存在时先删除")
    p.add_argument("--chunk", type=int, default=200, help="每次处理的条数（默认 200）")
    return p.parse_args()


def _remove_db_files(path: Path) -> None:
    for suffix in ("", "-wal", "-shm"):
        Path(str(path) + suffix).unlink(missing_ok=True)


def main() -> int:
    args = _parse_args()

    # 必须在 import kg.* 之前设置：kg.config 在 import 时读取 KG_VEC_DB_PATH。
    # .env 以 override=False 加载，所以这里先设的值优先。
    data_dir = Path(
        os.getenv("KG_DATA_DIR") or Path(__file__).resolve().parents[1] / "data"
    )
    out = (args.out or (data_dir / "kg_vec.new.db")).expanduser().resolve()
    os.environ["KG_VEC_DB_PATH"] = str(out)

    from kg.config import (  # noqa: E402
        KG_DB_PATH,
        KG_EMBEDDING_DIM,
        KG_EMBEDDING_MODEL,
    )
    from kg.embedder import get_embedder  # noqa: E402
    from kg.database import get_kg_db  # noqa: E402
    from kg.repositories.concept_repo import ConceptRepository  # noqa: E402
    from kg.repositories.concept_repo import _row_to_schema as concept_row  # noqa: E402
    from kg.repositories.facet_repo import FacetRepository  # noqa: E402
    from kg.repositories.facet_repo import _row_to_schema as facet_row  # noqa: E402
    from kg.text_for_embedding import build_concept_text, build_facet_text  # noqa: E402
    from kg.vector_store import (  # noqa: E402
        COLLECTION_CONCEPT,
        COLLECTION_FACET,
        get_vector_store,
    )

    concept_repo, facet_repo = ConceptRepository(), FacetRepository()
    concepts = [
        concept_row(r)
        for r in concept_repo._fetchall("SELECT * FROM concept WHERE status='approved'")
    ]
    facets = [
        facet_row(r)
        for r in facet_repo._fetchall("SELECT * FROM facet WHERE status='active'")
    ]
    stale_c = sum(1 for c in concepts if c.embedding_model != KG_EMBEDDING_MODEL)
    stale_f = sum(1 for f in facets if f.embedding_model != KG_EMBEDDING_MODEL)

    print(f"KG 主库        : {KG_DB_PATH}")
    print(f"目标模型/维度  : {KG_EMBEDDING_MODEL} / {KG_EMBEDDING_DIM}")
    print(
        f"待重建         : concept {len(concepts)} 条（其中记录的旧模型 {stale_c}），"
        f"facet {len(facets)} 条（其中记录的旧模型 {stale_f}）"
    )
    print(f"输出向量库     : {out}")
    if args.dry_run:
        print("--dry-run：未调用 embedding，退出。")
        return 0

    embedder = get_embedder()
    if getattr(embedder, "dim", 0) <= 0:
        print(
            "错误：embedder 未启用（检查 KG_EMBEDDING_API_KEY / BASE_URL）",
            file=sys.stderr,
        )
        return 2
    if out.exists():
        if not args.overwrite:
            print(f"错误：{out} 已存在；确认可删除请加 --overwrite", file=sys.stderr)
            return 2
        _remove_db_files(out)

    store = get_vector_store()
    if not store.enabled:
        print("错误：向量库未能初始化（是否安装 sqlite-vec？）", file=sys.stderr)
        return 2

    concept_by_id = {c.id: c for c in concepts}
    failed: list[tuple[str, str]] = []
    started = time.time()

    def _write_meta(table: str, rows: list[tuple[str, str, str]]) -> None:
        if not rows:
            return
        with get_kg_db() as conn:
            conn.executemany(
                f"UPDATE {table} SET embedding_model=?, vector_id=? WHERE id=?",
                [(model, vid, biz_id) for biz_id, vid, model in rows],
            )
            conn.commit()

    def _run(
        label: str, collection: str, table: str, items: list[tuple[str, str, dict]]
    ):
        done = 0
        for i in range(0, len(items), args.chunk):
            chunk = items[i : i + args.chunk]
            results = store.upsert_many(collection, chunk)
            ok_rows = []
            for (biz_id, _text, _payload), (vid, model) in zip(chunk, results):
                if vid:
                    ok_rows.append((biz_id, vid, model))
                else:
                    failed.append((collection, biz_id))
            _write_meta(table, ok_rows)
            done += len(chunk)
            print(
                f"  [{label}] {done}/{len(items)}  ({time.time() - started:.0f}s)",
                flush=True,
            )

    concept_items = [
        (
            c.id,
            build_concept_text(c),
            {"concept_id": c.id, "slug": c.slug, "subject": c.subject},
        )
        for c in concepts
    ]

    def _facet_ctx(concept_id: str):
        c = concept_by_id.get(concept_id)
        return c if c is not None else concept_repo.get_by_id(concept_id)

    facet_items = [
        (
            f.id,
            build_facet_text(f, concept=_facet_ctx(f.concept_id)),
            {"facet_id": f.id, "concept_id": f.concept_id, "kind": f.kind},
        )
        for f in facets
    ]

    _run("concept", COLLECTION_CONCEPT, "concept", concept_items)
    _run("facet", COLLECTION_FACET, "facet", facet_items)

    # ---- 校验 ----
    meta = {
        r["collection"]: r["n"]
        for r in store._conn.execute(  # type: ignore[union-attr]
            "SELECT collection, COUNT(*) AS n FROM vec_meta GROUP BY collection"
        ).fetchall()
    }
    got_c, got_f = meta.get(COLLECTION_CONCEPT, 0), meta.get(COLLECTION_FACET, 0)
    print(f"校验：向量库 concept {got_c}/{len(concepts)}，facet {got_f}/{len(facets)}")

    sanity_ok = True
    if concepts:
        probe = concepts[0]
        hits = store.search(COLLECTION_CONCEPT, build_concept_text(probe), top_k=1)
        sanity_ok = bool(hits) and hits[0]["biz_id"] == probe.id
        print(
            f"自检：用「{probe.canonical_name}」自身文本检索 top1 = "
            f"{'自己 ✓' if sanity_ok else '不是自己 ✗'}"
        )

    store.close()  # 关闭连接以合并 WAL，输出为单个干净文件

    if failed:
        print(f"失败 {len(failed)} 条（未写入新库，请修复后重跑）：", file=sys.stderr)
        for coll, biz_id in failed[:20]:
            print(f"  {coll}  {biz_id}", file=sys.stderr)
        return 1
    if got_c != len(concepts) or got_f != len(facets) or not sanity_ok:
        print("校验未通过，请勿切换。", file=sys.stderr)
        return 1

    print(f"完成，用时 {time.time() - started:.0f}s。新向量库：{out}")
    print("下一步：停服务/低峰期 → 替换 kg_vec.db → 重启（见本文件头部说明）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
