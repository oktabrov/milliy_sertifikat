"""Turning what a student typed into a 0/1 per item, then into three results.

The answer sheet asks for short answers and explicitly tells students not to
write units:

    "iloji boricha qisqa javob yozing. 'ta, nafar, m, litr, so'm, a=, h=,
     jami, gradus' kabi so'zlarni ishlatmang."

Students write them anyway, so `normalize` strips them. It also canonicalises
the LaTeX that MathLive emits, so `\\frac{50}{3}`, `50/3` and `\\dfrac{50}{3}`
all compare equal.
"""

from __future__ import annotations

import ast
import math
import operator
import re
from dataclasses import dataclass, field
from typing import Any, Iterable

from app.scoring.scenarios import (
    SCENARIOS,
    BallScale,
    ScenarioTable,
    build_all_tables,
    default_difficulties,
)

# Numeric answers are compared with this relative tolerance, so 0.333333 and
# 1/3 agree but 3.1 and 3.2 do not.
NUMERIC_TOLERANCE = 1e-6

# Applied longest-first so "litr" is consumed before "l" would be.
_UNIT_WORDS = (
    "nafar",
    "gradus",
    "daraja",
    "kishi",
    "litr",
    "soat",
    "jami",
    "dona",
    "marta",
    "so'm",
    "so`m",
    "so‘m",
    "som",
    "sek",
    "min",
    "kg",
    "km",
    "sm",
    "mm",
    "ta",
)

# Single-letter units are only stripped when they trail a number ("12m"),
# otherwise we would mangle variable names.
_TRAILING_SINGLE_UNITS = re.compile(r"(?<=\d)(m|l|g|s)$")

# "a=", "h=", "x =" prefixes.
_LEADING_ASSIGNMENT = re.compile(r"^[a-z]\s*=")

_LATEX_NOISE = (
    r"\left",
    r"\right",
    r"\!",
    r"\,",
    r"\;",
    r"\:",
    r"\ ",
    r"\quad",
    r"\qquad",
    "$",
    "~",
    "&",
)

_FRAC = re.compile(r"\\[dt]?frac\s*\{([^{}]*)\}\s*\{([^{}]*)\}")
_SQRT_N = re.compile(r"\\sqrt\s*\[([^\]]*)\]\s*\{([^{}]*)\}")
_SQRT = re.compile(r"\\sqrt\s*\{([^{}]*)\}")
_POWER_BRACED = re.compile(r"\^\s*\{([^{}]*)\}")
_POWER_BARE = re.compile(r"\^\s*(-?\w)")


def _strip_latex(text: str) -> str:
    for token in _LATEX_NOISE:
        text = text.replace(token, "")

    # Nested fractions need repeated passes; the regex only matches innermost.
    for _ in range(6):
        replaced = _FRAC.sub(r"((\1)/(\2))", text)
        if replaced == text:
            break
        text = replaced

    text = _SQRT_N.sub(r"((\2)**(1/(\1)))", text)
    for _ in range(4):
        replaced = _SQRT.sub(r"sqrt(\1)", text)
        if replaced == text:
            break
        text = replaced

    text = _POWER_BRACED.sub(r"**(\1)", text)
    text = _POWER_BARE.sub(r"**\1", text)

    replacements = {
        r"\cdot": "*",
        r"\times": "*",
        r"\div": "/",
        r"\pi": "pi",
        r"\infty": "inf",
        r"\ge": ">=",
        r"\le": "<=",
        r"\ne": "!=",
        r"\approx": "=",
        "·": "*",
        "×": "*",
        "÷": "/",
        "−": "-",
        "–": "-",
        "π": "pi",
        "∞": "inf",
        "√": "sqrt",
        ",": ".",
        "{": "(",
        "}": ")",
    }
    for source, target in replacements.items():
        text = text.replace(source, target)

    # Anything left starting with a backslash is a command we do not model;
    # drop the backslash and keep the name so it still compares as text.
    return text.replace("\\", "")


def normalize(answer: str | None) -> str:
    """Canonical form of a student answer, for equality comparison."""
    if answer is None:
        return ""

    text = str(answer).strip().lower()
    if not text:
        return ""

    text = _strip_latex(text)
    text = _LEADING_ASSIGNMENT.sub("", text, count=1)
    text = re.sub(r"\s+", "", text)

    # Order matters: strip after whitespace removal so "3 marta" and "3marta"
    # both reduce to "3".
    for word in _UNIT_WORDS:
        text = text.replace(word, "")

    text = _TRAILING_SINGLE_UNITS.sub("", text)
    text = _LEADING_ASSIGNMENT.sub("", text, count=1)

    # Trailing zeros: 3.50 == 3.5, and 3.0 == 3.
    if re.fullmatch(r"-?\d+\.\d+", text):
        text = text.rstrip("0").rstrip(".")

    return text


_SAFE_BINARY = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
}
_SAFE_UNARY = {ast.UAdd: operator.pos, ast.USub: operator.neg}
_SAFE_NAMES = {"pi": math.pi, "e": math.e, "inf": math.inf}
_SAFE_CALLS = {"sqrt": math.sqrt, "abs": abs}


def _eval_node(node: ast.AST) -> float:
    if isinstance(node, ast.Expression):
        return _eval_node(node.body)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return float(node.value)
        raise ValueError("non-numeric constant")
    if isinstance(node, ast.BinOp) and type(node.op) in _SAFE_BINARY:
        return _SAFE_BINARY[type(node.op)](_eval_node(node.left), _eval_node(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _SAFE_UNARY:
        return _SAFE_UNARY[type(node.op)](_eval_node(node.operand))
    if isinstance(node, ast.Name) and node.id in _SAFE_NAMES:
        return _SAFE_NAMES[node.id]
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in _SAFE_CALLS
        and not node.keywords
    ):
        return _SAFE_CALLS[node.func.id](*[_eval_node(arg) for arg in node.args])
    raise ValueError("unsupported expression")


def to_number(text: str) -> float | None:
    """Evaluate a canonicalised answer numerically, or None if it is not arithmetic.

    Deliberately not `eval`: only literals, + - * / **, unary sign, `pi`/`e`,
    and `sqrt`/`abs` are reachable.
    """
    if not text or len(text) > 200:
        return None
    if not re.fullmatch(r"[0-9a-z_+\-*/().]*", text):
        return None
    try:
        value = _eval_node(ast.parse(text, mode="eval"))
    except (ValueError, SyntaxError, TypeError, ZeroDivisionError, OverflowError, RecursionError):
        return None
    return value if math.isfinite(value) else None


def answers_match(submitted: str | None, expected: str | None) -> bool:
    """True when the student's answer counts as correct."""
    left = normalize(submitted)
    right = normalize(expected)
    if not right:
        return False
    if left == right:
        return True

    left_number = to_number(left)
    right_number = to_number(right)
    if left_number is None or right_number is None:
        return False
    return math.isclose(left_number, right_number, rel_tol=NUMERIC_TOLERANCE, abs_tol=1e-12)


def accepted_list(value: Any) -> list[str]:
    """Normalise an answer key entry into a list of accepted answers.

    Authors may record several equivalent forms of the same answer — `3/4`,
    `0.75`, `\\frac{3}{4}` — because no amount of canonicalisation catches every
    way a student might legitimately write one. A bare string is still accepted
    so answer keys written before this existed keep working.
    """
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value)]


@dataclass
class Item:
    """One scorable slot. An open question with parts a and b yields two items.

    `accepted` holds every answer the author counts as correct: exactly one
    letter for multiple choice, one or more forms for an open answer.
    """

    key: str
    number: int
    part: str | None
    kind: str
    accepted: list[str]

    @property
    def expected(self) -> str:
        """First accepted answer. Convenience for messages and debugging."""
        return self.accepted[0] if self.accepted else ""


def build_items(questions: Iterable[dict[str, Any]]) -> list[Item]:
    """Flatten a test's questions into the item list the Rasch model scores."""
    items: list[Item] = []
    for question in questions:
        number = int(question["number"])
        if question.get("type") == "open":
            for part in ("a", "b"):
                accepted = accepted_list((question.get("parts") or {}).get(part))
                if not accepted:
                    continue
                items.append(
                    Item(
                        key=f"{number}{part}",
                        number=number,
                        part=part,
                        kind="open",
                        accepted=accepted,
                    )
                )
        else:
            letter = str(question.get("answer", "")).strip().upper()
            items.append(
                Item(
                    key=str(number),
                    number=number,
                    part=None,
                    kind="mc",
                    accepted=[letter] if letter else [],
                )
            )
    return items


@dataclass
class ScenarioResult:
    key: str
    label_uz: str
    ball: int
    percentile: float
    grade: str
    theta: float


@dataclass
class AttemptResult:
    raw_correct: int
    total_items: int
    per_item: dict[str, bool] = field(default_factory=dict)
    scenarios: list[ScenarioResult] = field(default_factory=list)


def grade_answers(items: list[Item], submitted: dict[str, Any]) -> tuple[int, dict[str, bool]]:
    """Score each item.

    Multiple choice is a letter match. An open answer is correct when it matches
    *any* of the forms the author accepted — the student writes one answer, the
    author may have listed several equivalent ways of writing it.
    """
    per_item: dict[str, bool] = {}
    for item in items:
        value = submitted.get(item.key)
        if item.kind == "mc":
            correct = bool(item.accepted) and str(value or "").strip().upper() == item.accepted[0]
        else:
            correct = any(answers_match(value, option) for option in item.accepted)
        per_item[item.key] = correct
    return sum(per_item.values()), per_item


def score_attempt(
    items: list[Item],
    submitted: dict[str, Any],
    tables: dict[str, ScenarioTable],
) -> AttemptResult:
    """Grade, then look the raw score up in each precomputed scenario table."""
    raw_correct, per_item = grade_answers(items, submitted)

    results = []
    for scenario in SCENARIOS:
        table = tables.get(scenario.key)
        if table is None:
            continue
        row = table.row_for(raw_correct)
        results.append(
            ScenarioResult(
                key=scenario.key,
                label_uz=scenario.label_uz,
                ball=row.ball,
                percentile=row.percentile,
                grade=row.grade,
                theta=row.theta,
            )
        )

    return AttemptResult(
        raw_correct=raw_correct,
        total_items=len(items),
        per_item=per_item,
        scenarios=results,
    )


def tables_for_test(
    items: list[Item],
    observed: list[float] | None = None,
    scale: BallScale | None = None,
    size: int | None = None,
) -> dict[str, ScenarioTable]:
    """Build the three scenario tables for a test.

    `observed` is a real-data calibration once enough students have sat the
    test; without it we fall back to the default difficulty profile.
    """
    if observed and len(observed) == len(items):
        true_difficulties = list(observed)
    else:
        mc_items = sum(1 for item in items if item.kind == "mc")
        true_difficulties = default_difficulties(mc_items, len(items) - mc_items)

    kwargs: dict[str, Any] = {"scale": scale}
    if size is not None:
        kwargs["size"] = size
    return build_all_tables(true_difficulties, **kwargs)
