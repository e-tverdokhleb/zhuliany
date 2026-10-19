"""Безпечний обчислювач виразів для конфігу.

Дозволено: числа, імена параметрів, посилання на кімнати (R02.right),
+ - * / та дужки. Жодних викликів функцій чи атрибутів Python.
"""

import ast
import operator

_BINOPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
}
_UNARY = {ast.USub: operator.neg, ast.UAdd: operator.pos}


class ExprError(Exception):
    pass


class Unresolved(Exception):
    """Вираз посилається на значення, яке ще не обчислене."""

    def __init__(self, name):
        Exception.__init__(self, name)
        self.name = name


def names_in(expr):
    """Множина імен, на які посилається вираз ("R02.right" рахується як одне ім'я)."""
    if isinstance(expr, (int, float)):
        return set()
    tree = _parse(expr)
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            found.add(node.value.id + "." + node.attr)
        elif isinstance(node, ast.Name):
            found.add(node.id)
    return found


def _parse(expr):
    try:
        return ast.parse(str(expr), mode="eval")
    except SyntaxError as e:
        raise ExprError("Синтаксична помилка у виразі '{}': {}".format(expr, e))


def evaluate(expr, lookup):
    """Обчислити вираз. lookup(name) повертає число або кидає Unresolved / KeyError."""
    if isinstance(expr, bool):
        raise ExprError("Булеве значення замість числа: {}".format(expr))
    if isinstance(expr, (int, float)):
        return float(expr)
    tree = _parse(expr)
    return float(_eval(tree.body, lookup, expr))


def _eval(node, lookup, src):
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) \
            and not isinstance(node.value, bool):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _BINOPS:
        return _BINOPS[type(node.op)](_eval(node.left, lookup, src), _eval(node.right, lookup, src))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY:
        return _UNARY[type(node.op)](_eval(node.operand, lookup, src))
    if isinstance(node, ast.Name):
        return lookup(node.id)
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
        return lookup(node.value.id + "." + node.attr)
    raise ExprError("Недозволена конструкція у виразі '{}'".format(src))
