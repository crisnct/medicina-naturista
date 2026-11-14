"""Operator-supplied arithmetic over named variables (L1/L2/L3 for the product tops, P1/P2/L/V/K for
the fragment score); parsed from a whitelist, never `eval`-ed."""

from __future__ import annotations

import ast
import math
import operator
from collections.abc import Callable
from functools import lru_cache
from itertools import product

DEFAULT_FORMULA = "2*L1+L2+100*L3"
# L and V are ranks (reciprocal rank fusion, see ai/search.py); K is SEARCH_RRF_K.
DEFAULT_SEARCH_FORMULA = "4*P1+2*P2+(K+1)/(K+L)+(K+1)/(K+V)"
DEFAULT_SEARCH_RRF_K = 10
VARIABLES = ("L1", "L2", "L3")
MAX_LENGTH = 200
MAX_NODES = 64
ScoreFormula = Callable[[int, int, int], float]
NamedFormula = Callable[..., float]

_BINARY = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
}
# Probe values include 0 and 1 so divisions by (L-1) or by L are rejected at startup.
_PROBES = (0, 1, 2, 1000)


def _build(node: ast.expr, variables: tuple[str, ...]) -> Callable[[tuple[float, ...]], float]:
    if isinstance(node, ast.Constant) and type(node.value) in (int, float):
        value = node.value
        return lambda _: value
    if isinstance(node, ast.Name) and node.id in variables:
        index = variables.index(node.id)
        return lambda values: values[index]
    if isinstance(node, ast.BinOp) and type(node.op) in _BINARY:
        function = _BINARY[type(node.op)]
        left, right = _build(node.left, variables), _build(node.right, variables)
        return lambda values: function(left(values), right(values))
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        operand = _build(node.operand, variables)
        sign = -1 if isinstance(node.op, ast.USub) else 1
        return lambda values: sign * operand(values)
    raise ValueError("unsupported element in formula")


def _parse(source: str, variables: tuple[str, ...]) -> ast.expr:
    if not isinstance(source, str) or not source.strip() or len(source) > MAX_LENGTH:
        raise ValueError(f"formula must be 1-{MAX_LENGTH} characters")
    try:
        tree = ast.parse(source.strip(), mode="eval")
    except SyntaxError:
        raise ValueError("formula is not a valid arithmetic expression") from None
    if sum(1 for _ in ast.walk(tree)) > MAX_NODES:
        raise ValueError("formula is too complex")
    _build(tree.body, variables)  # rejects anything outside the whitelist
    return tree.body


# Raises ValueError with a configuration-safe message; the formula text is never echoed.
@lru_cache(maxsize=8)
def compile_formula(source: str) -> ScoreFormula:
    evaluate = _build(_parse(source, VARIABLES), VARIABLES)

    def score(l1: int, l2: int, l3: int) -> float:
        return float(evaluate((l1, l2, l3)))

    try:
        for values in product(_PROBES, repeat=3):
            if not math.isfinite(score(*values)):
                raise ValueError("formula must be finite for every count")
    except (ZeroDivisionError, OverflowError):
        raise ValueError("formula must be defined for every count") from None
    return score


# The fragment score: P1, P2 in {0, 1}; L and V are ranks (1 = the best fragment of the signal,
# infinity = the signal gave the fragment none: no match, at or below the median cosine, signal
# off), so (K+1)/(K+L) is 0 for those; K is the RRF constant (SEARCH_RRF_K). Checked on a grid
# of those values that the formula is defined, never negative, and highest when P1 = P2 = 1 and
# both ranks are 1, so the relevance percentage (score / the score of a perfect fragment)
# stays between 0 and 100.
SEARCH_VARIABLES = ("P1", "P2", "L", "V", "K")
SEARCH_PROBES = (0, 0.5, 1)
SEARCH_RANK_PROBES = (1, 2, 10, 1000, math.inf)


@lru_cache(maxsize=8)
def compile_search_formula(source: str, k: int) -> NamedFormula:
    evaluate = _build(_parse(source, SEARCH_VARIABLES), SEARCH_VARIABLES)

    def score(p1: float, p2: float, l: float, v: float) -> float:  # noqa: E741
        return float(evaluate((p1, p2, l, v, float(k))))

    try:
        best = score(1, 1, 1, 1)
        if not math.isfinite(best) or best <= 0:
            raise ValueError("formula must be positive for P1=P2=1 and L=V=1")
        for p1, p2 in product(SEARCH_PROBES, repeat=2):
            for rank_l, rank_v in product(SEARCH_RANK_PROBES, repeat=2):
                result = score(p1, p2, rank_l, rank_v)
                if not math.isfinite(result) or result < 0 or result > best + 1e-9:
                    raise ValueError("formula must be between 0 and its value at P1=P2=1, L=V=1")
    except (ZeroDivisionError, OverflowError):
        raise ValueError("formula must be defined for every value") from None
    return score


# The same formula as one SQL expression over the given columns; every number is written as
# a double and a division by zero gives NULL, so the database never evaluates user text.
def search_formula_sql(source: str, columns: dict[str, str], k: int) -> str:
    compile_search_formula(source, k)

    def render(node: ast.expr) -> str:
        if isinstance(node, ast.Constant):
            return f"({float(node.value)!r}::double precision)"
        if isinstance(node, ast.Name):
            if node.id == "K":
                return f"({float(k)!r}::double precision)"
            return f"({columns[node.id]}::double precision)"
        if isinstance(node, ast.BinOp):
            left, right = render(node.left), render(node.right)
            if isinstance(node.op, ast.Div):
                return f"({left} / nullif({right}, 0))"
            symbol = {ast.Add: "+", ast.Sub: "-", ast.Mult: "*"}[type(node.op)]
            return f"({left} {symbol} {right})"
        if isinstance(node, ast.UnaryOp):
            return f"({'-' if isinstance(node.op, ast.USub) else '+'}{render(node.operand)})"
        raise ValueError("unsupported element in formula")

    return render(_parse(source, SEARCH_VARIABLES))
