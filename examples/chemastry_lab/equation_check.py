"""Verify that a model-produced chemical equation actually balances.

The prompt tells the model to balance and self-check, but a prompt is a request,
not a guarantee: an unbalanced equation is worse than no equation, because a
learner will copy it into their notebook. So every equation is re-counted here,
atom by atom, before the bench is allowed to render it.

Design rule: only reject what is *provably* unbalanced. Anything this module
cannot parse with confidence (placeholder reagents like 石蕊, hydrates,
polymers, reversible equilibria with unusual notation) is passed through
untouched — a false rejection would block correct chemistry, which is worse than
letting a rare oddity through to the reaction referee's own judgement.
"""

from __future__ import annotations

import re
from collections import Counter

_SUBSCRIPT_DIGITS = str.maketrans("₀₁₂₃₄₅₆₇₈₉", "0123456789")
_COEFFICIENT = re.compile(r"^(\d+)")
# CJK text is a placeholder reagent (石蕊) or prose, never a countable formula.
_HAS_CJK = re.compile(r"[\u4e00-\u9fff]")
# A lone lowercase letter is a polymer/variable subscript, as in (C6H10O5)n.
# Checked as a standalone token so it never touches real symbols like Zn or Mn.
_VARIABLE_SUBSCRIPT = re.compile(r"(?<![A-Za-z])[nxyzm](?![a-z])")


class Unparseable(Exception):
    """The species is not a formula this module can count atoms in."""


def _strip_state_markers(species: str) -> str:
    """Remove notation that carries no atoms: states, bonds, arrows."""
    cleaned = species.strip()
    cleaned = cleaned.replace("（", "(").replace("）", ")")
    cleaned = re.sub(r"\((?:g|s|l|aq|固|液|气|水溶液|浓|稀|饱和)\)", "", cleaned, flags=re.IGNORECASE)
    cleaned = cleaned.replace("↑", "").replace("↓", "")
    # Structural bonds inside an organic formula hold no atoms of their own:
    # CH₂=CH₂ has the same atom count as C₂H₄.
    cleaned = cleaned.replace("≡", "").replace("=", "").replace("＝", "").replace("-", "")
    return cleaned.strip()


def _count_atoms(formula: str) -> Counter[str]:
    """Count atoms in a single formula, honouring groups and hydrate dots.

    Raises Unparseable when the string contains anything this counter cannot
    account for, so the caller can skip verification instead of guessing.
    """
    text = _strip_state_markers(formula).translate(_SUBSCRIPT_DIGITS)
    if not text:
        raise Unparseable(formula)
    if _HAS_CJK.search(text) or _VARIABLE_SUBSCRIPT.search(text):
        raise Unparseable(formula)
    # A charge marker means an ionic half-equation, which balances by charge too.
    if re.search(r"[⁺⁻]|\^\s*\d*[+-]", text):
        raise Unparseable(formula)

    # A hydrate (CuSO4·5H2O) is a sum of independently multiplied parts.
    if "·" in text or "•" in text:
        total: Counter[str] = Counter()
        for part in re.split(r"[·•]", text):
            if not part:
                continue
            multiplier_match = _COEFFICIENT.match(part)
            multiplier = 1
            if multiplier_match:
                multiplier = int(multiplier_match.group(1))
                part = part[multiplier_match.end() :]
            for element, count in _count_atoms(part).items():
                total[element] += count * multiplier
        return total

    # Stack-based walk so nested groups like Ca3(PO4)2 multiply correctly.
    stack: list[Counter[str]] = [Counter()]
    index = 0
    while index < len(text):
        char = text[index]
        if char == "(" or char == "[":
            stack.append(Counter())
            index += 1
            continue
        if char == ")" or char == "]":
            if len(stack) == 1:
                raise Unparseable(formula)
            group = stack.pop()
            index += 1
            digits = _COEFFICIENT.match(text[index:])
            multiplier = 1
            if digits:
                multiplier = int(digits.group(1))
                index += digits.end()
            for element, count in group.items():
                stack[-1][element] += count * multiplier
            continue
        element_match = re.match(r"([A-Z][a-z]?)(\d*)", text[index:])
        if not element_match:
            raise Unparseable(formula)
        element = element_match.group(1)
        count = int(element_match.group(2)) if element_match.group(2) else 1
        stack[-1][element] += count
        index += element_match.end()

    if len(stack) != 1:
        raise Unparseable(formula)
    if not stack[0]:
        raise Unparseable(formula)
    return stack[0]


def _side_atoms(side: str) -> Counter[str]:
    """Count every atom on one side of the arrow, applying coefficients."""
    total: Counter[str] = Counter()
    # Split on + that separates species, not the + inside a charge notation.
    for species in re.split(r"\s\+\s|\+", side):
        term = species.strip()
        if not term:
            continue
        coefficient_match = _COEFFICIENT.match(term)
        coefficient = 1
        if coefficient_match:
            coefficient = int(coefficient_match.group(1))
            term = term[coefficient_match.end() :].strip()
        if not term:
            raise Unparseable(side)
        for element, count in _count_atoms(term).items():
            total[element] += count * coefficient
    if not total:
        raise Unparseable(side)
    return total


def _split_equation(equation: str) -> tuple[str, str]:
    """Separate reactants from products, dropping any condition annotation."""
    text = equation.strip()
    # Conditions ride above the arrow as →(170℃,浓硫酸); they hold no atoms.
    text = re.sub(r"(?<=[→=⇌⇋>])\s*\([^)]*\)", "", text)
    text = re.sub(r"\([^)]*(?:℃|°C|催化|高温|加热|点燃|通电|光照|加压|条件)[^)]*\)", "", text)

    # Real arrows first. "=" is ambiguous — it is also a double bond in CH₂=CH₂ —
    # so only fall back to it when no unambiguous arrow is present.
    for arrow in ("⇌", "⇋", "<=>", "->", "→"):
        if arrow in text:
            left, _, right = text.partition(arrow)
            if left.strip() and right.strip():
                return left, right
    for arrow in ("＝", "="):
        if arrow in text:
            left, _, right = text.partition(arrow)
            # A double bond has element letters on both sides with no separator;
            # a reaction arrow has whitespace or a coefficient around it.
            if left.strip() and right.strip() and (left.endswith((" ", "\t")) or right.startswith((" ", "\t"))):
                return left, right
    raise Unparseable(equation)


def balance_report(equation: str) -> tuple[bool, str]:
    """Check an equation's atom balance.

    Returns (ok, detail). `ok` is False only when the equation was fully parsed
    and the two sides genuinely disagree; anything unparseable returns True so
    the verdict is not discarded over notation this module does not model.
    """
    if not equation or not equation.strip():
        return True, "empty"
    try:
        left_text, right_text = _split_equation(equation)
        left = _side_atoms(left_text)
        right = _side_atoms(right_text)
    except Unparseable:
        return True, "unparseable"
    except (ValueError, RecursionError):
        return True, "unparseable"

    if left == right:
        return True, "balanced"

    differences = []
    for element in sorted(set(left) | set(right)):
        got, want = left.get(element, 0), right.get(element, 0)
        if got != want:
            differences.append(f"{element} {got}≠{want}")
    return False, "; ".join(differences)


def is_balanced(equation: str) -> bool:
    """True unless the equation is provably unbalanced."""
    return balance_report(equation)[0]
