"""Server-side allowlist for model-produced Chemistry Lab results.

The lab bench state (materials, vessel, conditions) is authoritative and comes
from the browser. The model may only describe *what happens*; it can never
invent a condition the learner did not choose, unlock a material the learner
never produced, or hand out progress. Everything the model returns is clamped,
re-typed and filtered here before it reaches the page.

Chemical correctness is enforced too: every equation is re-counted atom by atom
(see equation_check) and a provably unbalanced one is refused rather than shown.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from equation_check import balance_report

logger = logging.getLogger("chemistry-lab-contract")

REACTION_TYPES = {
    "化合反应",
    "分解反应",
    "置换反应",
    "复分解反应",
    "氧化还原反应",
    "其他",
}
PRODUCT_STATES = {"固体", "液体", "气体", "沉淀", "溶液"}
VARIANTS = {"", "浓", "稀", "饱和"}
VERDICTS = {"need", "extra", "bad"}
# Whether a reaction is on the school syllabus. It labels the verdict; it must
# never decide it. A reaction beyond the syllabus still happens.
SCOPES = {"中学", "超纲"}

MAX_PRODUCTS = 6
MAX_CONDITION_CHECKS = 8

_SUBSCRIPTS = str.maketrans("₀₁₂₃₄₅₆₇₈₉", "0123456789")
_STATE_SUFFIX = re.compile(r"\((?:g|s|l|aq|固|液|气|水溶液)\)", re.IGNORECASE)
_NAME_NOISE = re.compile(r"(白色|蓝色|红色|红棕色|黄色|绿色|无色)?(沉淀|气体|溶液|试液|晶体)$")

# There used to be a regex here that rewrote every "170℃" into "某个特定温度" and
# every catalyst name into "某种特定催化剂", so that hints could not leak an answer
# the learner had yet to discover.
#
# It is gone on purpose. Redacting text after generation cannot tell a hint from
# an explanation, so it also mangled plain chemistry facts — "水在某个特定温度沸腾"
# — and made the assistant look broken. Whether a hint points at a direction or
# states a value is a matter of tone, and tone belongs in the prompt, not in a
# find-and-replace over finished sentences. See REACTION_PROMPT / CHAT_PROMPT.


def _text(value: Any, limit: int) -> str:
    """Collapse whitespace, drop NULs and clamp length."""
    if not isinstance(value, str):
        return ""
    return " ".join(value.replace("\x00", "").split()).strip()[:limit]


# Phrases that place a reaction outside the school syllabus. Mentioning one is
# perfectly fine — "这是傅-克烷基化，属于大学有机内容" is a useful aside. What is
# not fine is offering it as the *reason* nothing happened.
_OFF_SYLLABUS = (
    "超纲",
    "超出中学",
    "超出高中",
    "不作要求",
    "不做要求",
    "不要求掌握",
    "中学不要求",
    "高中不要求",
    "大学有机",
    "大学化学",
    "大学阶段",
    "竞赛",
    "教学大纲",
    "课程标准",
    "中学范围",
    "高中范围",
    "中学阶段",
)
# The reason-giving turn of phrase that makes it a verdict rather than a remark.
_AS_REASON = ("故", "因此", "所以", "判断为", "判定为", "视为", "按不反应", "认为不反应")


def _blames_syllabus(raw: Any) -> bool:
    """True when a "no reaction" verdict is justified by the syllabus.

    Chemistry decides `reacts`; a curriculum cannot. Telling a learner that
    AlCl₃ + CH₃Cl + C₆H₆ are inert because Friedel-Crafts alkylation is taught at
    university level leaves them with a false fact, which is worse than an
    admitted "I could not work this one out".

    Only fires when an off-syllabus phrase sits next to reason-giving wording, so
    a verdict that reacts *and* notes the level is untouched.
    """
    if not isinstance(raw, dict):
        return False
    blob = " ".join(
        _text(raw.get(key), 400) for key in ("why", "missing", "hint", "phenomenon")
    )
    if not blob:
        return False
    return any(term in blob for term in _OFF_SYLLABUS) and any(
        term in blob for term in _AS_REASON
    )


def _clean_formula(value: Any) -> str:
    """Keep only the bare formula: no coefficients, arrows or state markers."""
    formula = _text(value, 40)
    if not formula:
        return ""
    formula = formula.replace("（", "(").replace("）", ")")
    formula = formula.replace("↑", "").replace("↓", "")
    formula = _STATE_SUFFIX.sub("", formula)
    formula = re.sub(r"\((?:浓|稀|饱和)\)", "", formula)
    formula = re.sub(r"^\d+(?=[A-Za-z(])", "", formula)
    return formula.strip()


def _clean_name(value: Any) -> str:
    """Strip observation words so the material library stays clean."""
    name = _text(value, 24)
    if not name:
        return ""
    previous = None
    while name and name != previous:
        previous = name
        name = _NAME_NOISE.sub("", name).strip()
    return name


def _is_formula_like(value: str) -> bool:
    """Reject prose that the model tried to pass off as a formula."""
    if not value:
        return False
    ascii_form = value.translate(_SUBSCRIPTS)
    return bool(re.fullmatch(r"[A-Za-z0-9()\[\]·.]+", ascii_form))


def _products(raw: Any) -> list[dict[str, str]]:
    if not isinstance(raw, list):
        return []
    products: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, dict):
            continue
        formula = _clean_formula(item.get("formula"))
        name = _clean_name(item.get("name"))
        if not _is_formula_like(formula):
            # A product without a usable formula cannot enter the library.
            formula = ""
        if not formula and not name:
            continue
        key = (formula or name).upper().translate(_SUBSCRIPTS)
        if key in seen:
            continue
        seen.add(key)
        state = item.get("state")
        variant = _text(item.get("variant"), 4)
        products.append(
            {
                "formula": formula,
                "name": name or formula,
                "state": state if state in PRODUCT_STATES else "",
                "variant": variant if variant in VARIANTS else "",
            }
        )
        if len(products) >= MAX_PRODUCTS:
            break
    return products


def _condition_checks(raw: Any, submitted: list[str]) -> list[dict[str, str]]:
    """Only conditions the learner actually chose may be reported back."""
    if not isinstance(raw, list) or not submitted:
        return []
    allowed = {condition: index for index, condition in enumerate(submitted)}
    checks: dict[str, dict[str, str]] = {}
    for item in raw:
        if not isinstance(item, dict):
            continue
        label = _text(item.get("c"), 12)
        if label not in allowed or label in checks:
            continue
        verdict = item.get("verdict")
        checks[label] = {
            "c": label,
            "verdict": verdict if verdict in VERDICTS else "extra",
            "note": _text(item.get("note"), 16),
        }
        if len(checks) >= MAX_CONDITION_CHECKS:
            break
    return sorted(checks.values(), key=lambda check: allowed[check["c"]])


def normalize_reaction(
    raw: Any,
    submitted_conditions: list[str],
) -> dict[str, Any]:
    """Clamp a raw reaction verdict into the shape the lab bench renders."""
    if not isinstance(raw, dict):
        raw = {}

    danger = _text(raw.get("danger"), 200)
    reacts = bool(raw.get("reacts")) and not danger

    scope = raw.get("scope")
    reaction_type = raw.get("type")
    result: dict[str, Any] = {
        "reacts": reacts,
        "type": reaction_type if reaction_type in REACTION_TYPES else "",
        "equation": "" if not reacts else _text(raw.get("equation"), 160),
        "products": _products(raw.get("products")) if reacts else [],
        "phenomenon": _text(raw.get("phenomenon"), 200) if reacts else "",
        "why": _text(raw.get("why"), 200),
        # Only a label for the card. Being off-syllabus never changes `reacts`.
        "scope": scope if scope in SCOPES else "中学",
        "cond_check": _condition_checks(raw.get("cond_check"), submitted_conditions),
        "missing": "" if reacts else _text(raw.get("missing"), 120),
        "danger": danger,
        "hint": "" if reacts else _text(raw.get("hint"), 160),
        # Set when the verdict was thrown away for being chemically wrong, so the
        # page can offer a retry instead of claiming "no reaction happens".
        "unresolved": False,
    }

    # A verdict that says "no reaction" *because* the chemistry is off-syllabus is
    # not a chemical fact, it is a wrong one — the learner walks away believing
    # these substances are inert. The prompt forbids it; catch it here too, and
    # downgrade to "could not decide" so the page offers a retry instead.
    if not reacts and not danger and _blames_syllabus(raw):
        logger.warning(
            "Rejected a verdict that used the syllabus as the reason for no reaction: %s",
            result["why"],
        )
        result["unresolved"] = True
        result["why"] = (
            "这一轮没判定出来：不能因为「超纲」就说不反应。"
            "超出中学范围只是不要求掌握，反应该不该发生是另一回事。"
        )
        result["missing"] = ""
        result["hint"] = "再点一次「开始反应」，或直接问实验助手这几样东西会不会反应。"
        result["cond_check"] = []

    if reacts and not result["equation"]:
        # A reaction without an equation is not teachable material.
        result["reacts"] = False
        result["products"] = []
        result["phenomenon"] = ""
        result["unresolved"] = True
        result["why"] = result["why"] or "这一轮没有给出配平的方程式，换个组合再试。"
    elif reacts:
        # The prompt asks the model to balance and self-check, but a prompt is a
        # request, not a guarantee. An unbalanced equation is worse than none at
        # all, because the learner will copy it down — so re-count every atom and
        # drop the verdict rather than teach something wrong.
        balanced, detail = balance_report(result["equation"])
        if not balanced:
            logger.warning("Rejected an unbalanced equation: %s (%s)", result["equation"], detail)
            result["reacts"] = False
            result["equation"] = ""
            result["products"] = []
            result["phenomenon"] = ""
            result["cond_check"] = []
            result["unresolved"] = True
            result["why"] = "这一轮算出来的方程式两边原子数不相等，没有采用。再试一次这个组合。"
    if not result["reacts"] and not result["why"]:
        result["why"] = "在这套条件下不发生反应。"
    return result


def normalize_chat(raw: Any) -> dict[str, Any]:
    """Clamp a lab-assistant chat turn.

    The assistant answers questions, so nothing here redacts temperatures or
    catalyst names. Asking a question is itself an act of learning, and a reply
    with `170℃` rewritten to "某个特定温度" is not a nudge, it is a broken answer.
    Only the bench's own unprompted hints hold anything back; see
    `normalize_reaction`.
    """
    if not isinstance(raw, dict):
        raw = {}

    return {
        "reply": _text(raw.get("reply"), 400) or "再说说你的想法？",
        "suggestion": _text(raw.get("suggestion"), 80),
    }
