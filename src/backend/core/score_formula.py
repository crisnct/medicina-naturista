"""Operator-supplied arithmetic over L1, L2 and L3; parsed from a whitelist, never `eval`-ed."""

from __future__ import annotations

import ast
import math
import operator
from collections.abc import Callable
from functools import lru_cache
from itertools import product

DEFAULT_FORMULA = "2*L1+L2+100*L3"
VARIABLES = ("L1", "L2", "L3")
MAX_LENGTH = 200
MAX_NODES = 64
ScoreFormula = Callable[[int, int, int], float]

_BINARY = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
}
# Probe values include 0 and 1 so divisions by (L-1) or by L are rejected at startup.
_PROBES = (0, 1, 2, 1000)


def _build(node: ast.expr) -> Callable[[tuple[int, int, int]], float]:
    if isinstance(node, ast.Constant) and type(node.value) in (int, float):
        value = node.value
        return lambda _: value
    if isinstance(node, ast.Name) and node.id in VARIABLES:
        index = VARIABLES.index(node.id)
        return lambda values: values[index]
    if isinstance(node, ast.BinOp) and type(node.op) in _BINARY:
        function, left, right = _BINARY[type(node.op)], _build(node.left), _build(node.right)
        return lambda values: function(left(values), right(values))
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        operand = _build(node.operand)
        sign = -1 if isinstance(node.op, ast.USub) else 1
        return lambda values: sign * operand(values)
    raise ValueError("unsupported element in formula")


# Raises ValueError with a configuration-safe message; the formula text is never echoed.
@lru_cache(maxsize=8)
def compile_formula(source: str) -> ScoreFormula:
    if not isinstance(source, str) or not source.strip() or len(source) > MAX_LENGTH:
        raise ValueError(f"formula must be 1-{MAX_LENGTH} characters")
    try:
        tree = ast.parse(source.strip(), mode="eval")
    except SyntaxError:
        raise ValueError("formula is not a valid arithmetic expression") from None
    if sum(1 for _ in ast.walk(tree)) > MAX_NODES:
        raise ValueError("formula is too complex")
    evaluate = _build(tree.body)

    def score(l1: int, l2: int, l3: int) -> float:
        return float(evaluate((l1, l2, l3)))

    try:
        for values in product(_PROBES, repeat=3):
            if not math.isfinite(score(*values)):
                raise ValueError("formula must be finite for every count")
    except (ZeroDivisionError, OverflowError):
        raise ValueError("formula must be defined for every count") from None
    return score
