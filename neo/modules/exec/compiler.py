# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2022 sardonicism-04
import ast

code_base = (
    "async def __aexec__(scope):"
    "\n    try:"
    "\n        pass"
    "\n    finally:"
    "\n        scope |= locals()"
)


def insert_yield(body):
    if not isinstance(body[-1], ast.Expr):
        return

    if not isinstance(body[-1].value, ast.Yield):
        yield_st = ast.Yield(body[-1].value)
        ast.copy_location(yield_st, body[-1])
        yield_expr = ast.Expr(yield_st)
        ast.copy_location(yield_expr, body[-1])
        body[-1] = yield_expr


def compile_all(code_input):
    code_in = ast.parse(code_input)
    base = ast.parse(code_base)

    try_block = base.body[-1].body[-1].body  # type: ignore
    try_block.extend(code_in.body)

    ast.fix_missing_locations(base)
    insert_yield(try_block)

    return base
