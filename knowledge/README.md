## 一句话

老师在这个目录下用 markdown 写概念，每个 `.md` 文件 = 一个 concept，frontmatter 表达元数据 + 关系，body 按 `# H1` 切段成 facet。

## 目录组织

```
knowledge/
├── README.md                  # 本文件，ingester 跳过
├── math/                      # 一级目录 = subject
│   ├── calculus/              # 子目录纯组织用，不进 KG
│   │   ├── derivative.md
│   │   ├── limit.md
│   │   └── chain_rule.md
│   └── algebra/
│       └── function.md
├── physics/
│   └── newton_law_2.md
└── _drafts/                   # _ 开头跳过，不进 KG
```

约定：

- 一级目录名 = `subject` 字段（如果文件 frontmatter 没显式写 `subject`，会自动从这里推断）
- 子目录任意嵌套，纯人类组织用，**ingester 不解析**
- `_` 开头的目录或文件 ingester 跳过（草稿区）
- 任意名为 `README.md` 的文件 ingester 跳过

## 文件结构

```markdown
---
slug: derivative                    # 必填：全局唯一，URL 友好
name: 导数                          # 必填：人类可读名
summary: 函数在某点的瞬时变化率。     # 可选：≤80 字
difficulty: 3                       # 可选：0-5
aliases: [导函数, derivative]
tags: [微积分, 一元函数]

# 关系（按类型分桶，值是 slug 数组）
prerequisites: [limit, function]
generalizes: [directional_derivative]
related: [differential]
contrasts: [continuity]
part_of: [calculus]
---

# 直观理解

… 段落正文 …

## 几何意义

H2 不切 facet，跟随所在 H1 段落一起进入 facet.content。

# 严格定义

…

# 例子

…
```

## 切分规则

| 区域 | 进哪张表 | 怎么进 |
|---|---|---|
| frontmatter 标量字段 | `concept` | 字段直接映射 |
| frontmatter 关系字段 | `concept_edge` | 按字段名映射 relation_type，按 slug 解析目标 |
| 第一个 `# H1` 之前的内容 | 丢弃 | 老师必须从 `# H1` 开始正文 |
| 每个 `# H1` 段落 | `facet` | `kind = H1 标题原文`，`content = 段落正文` |
| `## H2` 及更深 | 不切 | 跟所在 H1 段落一起进 `facet.content` |

## 关系字段映射

| frontmatter 字段 | KG relation_type | 语义（src --rel--> dst） |
|---|---|---|
| `prerequisites` | `prerequisite` | dst 是 src 的前置（先学 dst 再学 src） |
| `generalizes` | `generalizes` | src 推广了 dst |
| `special_case_of` | `special_case_of` | src 是 dst 的特例 |
| `equivalent_to` | `equivalent_to` | 等价（对称） |
| `part_of` | `part_of` | src 是 dst 的一部分 |
| `application_of` | `application_of` | src 是 dst 的应用 |
| `contrasts` | `contrasts` | 易混淆/对照（对称） |
| `related` | `related` | 主题相关（兜底，对称） |

**关系单向写**：在 `derivative.md` 里写 `prerequisites: [limit]` 即可，不必在 `limit.md` 反向再写。检索由 KG 图查询自动处理。

## frontmatter 字段汇总

| 字段 | 必填 | 类型 | 说明 |
|---|---|---|---|
| `slug` | ✅ | str | 全局唯一标识，建议小写英数+下划线/连字符 |
| `name` | ✅ | str | 概念的规范名（中文 OK） |
| `summary` |  | str | ≤80 字一句话定义 |
| `subject` |  | str | 学科；不写则从一级目录推断 |
| `difficulty` |  | int 0-5 | 难度，缺省 3 |
| `aliases` |  | list[str / dict] | 同义词；可写字符串或 `{name, lang}` |
| `tags` |  | list[str] | 自由标签 |
| `prerequisites` |  | list[slug] | 前置概念 |
| `generalizes` |  | list[slug] | 推广了哪些概念 |
| `special_case_of` |  | list[slug] | 是哪些概念的特例 |
| `equivalent_to` |  | list[slug] | 等价概念 |
| `part_of` |  | list[slug] | 父级（结构包含关系） |
| `application_of` |  | list[slug] | 应用了哪些概念 |
| `contrasts` |  | list[slug] | 易混淆 |
| `related` |  | list[slug] | 松散相关 |

## 同步方式

```bash
# 试运行（不写 DB）
conda run -n edu-agent python -m backend.ingest_okf --dry-run

# 全量同步：删 origin='okf' 的旧数据，重新建
conda run -n edu-agent python -m backend.ingest_okf

# 指定其他根目录
conda run -n edu-agent python -m backend.ingest_okf --root my_kb
```

**注意**：

- 全量同步策略下，每次会先删 KG 中所有 `origin='okf'` 的 facet/edge 和 `created_by='okf'` 的 concept，再重建。
- 飞轮产生的 facet（`origin='dialog_aggregated'`/`agent_authored'`）**完全保留**。
- 写错关系不阻塞同步：dangling link / self-loop 会以警告形式报告，但其他数据照常入库。

## 写作建议

1. **slug 一旦发布就别改**：飞轮可能挂 facet 在 concept 上，改 slug 等于换身份。
2. **先写规范名 + summary，关系字段稍后补**：先把概念立住，关系慢慢织。
3. **正文从 `# H1` 开始**：H1 之前的内容会被丢弃，别把重要文字写在那里。
4. **关系宁缺毋滥**：写 `prerequisite` 务必想清楚教学上的依赖；不确定的统一进 `related`。
5. **一个概念只在一个 .md 里写**：不要拆成多文件，否则 KG 里会出现重名 concept。
