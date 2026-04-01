import ast
import black
import builtins
import inspect
import libcst as cst
import math
import re
import textwrap

from dataclasses import dataclass
from libcst import Call, CSTNode, Module, matchers
from libcst.helpers import get_full_name_for_node
from libcst.metadata import (
  BuiltinScope,
  GlobalScope,
  MetadataWrapper,
  PositionProvider,
  ParentNodeProvider,
  QualifiedNameProvider,
  QualifiedNameSource,
  ScopeProvider
)
from pydantic import BaseModel
from textwrap import dedent
from types import FunctionType
from typing import Any, Sequence
from rich import print as rprint

from appworld.common.code_tools import find_code_substring_ignoring_identation


@dataclass
class ParsedFunctionCodeOutput:
    definition: str
    docstring: str | None
    body: str
    indent_level: int

    @property
    def body_with_docstring(self) -> str:
        if self.docstring is None:
            return self.body
        return self.docstring + "\n" + self.body

    @property
    def full(self) -> str:
        return self.definition + "\n" + self.body_with_docstring


@dataclass
class ParsedFunctionCallCodeOutput:
    name: str
    code: str | None
    positional_arguments: list[str]
    keyword_arguments: dict[str, Any]


class AttributeTransformer(cst.CSTTransformer):
    def __init__(self, attributes: list[str]) -> None:
        self.attributes = attributes
        self.codes_in_call: set[str] = set()

    def visit_Call(self, node: cst.Call) -> bool:  # noqa: N802
        code = node_to_code(node)
        for attribute in self.attributes:
            if "." + attribute + "(" in code:
                self.codes_in_call.add(code)
        return True

    def leave_Call(  # noqa: N802
        self, original_node: cst.Call, updated_node: cst.Call
    ) -> cst.BaseExpression:
        code = node_to_code(original_node)
        for attribute in self.attributes:
            if "." + attribute + "(" in code:
                self.codes_in_call.remove(code)
        return updated_node

    def leave_Attribute(  # noqa: N802
        self, original_node: cst.Attribute, updated_node: cst.Attribute
    ) -> cst.BaseExpression:
        attribute = updated_node.attr.value
        code = node_to_code(original_node)
        is_in_call = any(code + "(" in code_ for code_ in self.codes_in_call)
        if attribute in self.attributes and not is_in_call:
            return cst.Subscript(
                value=updated_node.value,
                slice=[
                    cst.SubscriptElement(slice=cst.Index(value=cst.SimpleString(f"'{attribute}'")))
                ],
            )
        return updated_node


class AttributeWrapper(cst.CSTTransformer):
    def __init__(
        self,
        wrap_function_name: str,
        attributes: list[str],
        ignore_if_wrapped_with: str | None = None,
    ) -> None:
        self.wrap_function_name: str = wrap_function_name
        self.attributes: list[str] = attributes
        self.ignore_if_wrapped_with: str | None = ignore_if_wrapped_with
        self.ignore_codes: set[str] = set()

    def visit_Call(self, node: cst.Call) -> bool:  # noqa: N802
        if (
            self.ignore_if_wrapped_with and node.func.value == self.ignore_if_wrapped_with  # type: ignore[attr-defined]
        ):
            for code in node.args:
                self.ignore_codes.add(node_to_code(code))
        return True

    def leave_Call(  # noqa: N802
        self, original_node: cst.Call, updated_node: cst.Call
    ) -> cst.BaseExpression:
        if (
            self.ignore_if_wrapped_with and original_node.func.value == self.ignore_if_wrapped_with  # type: ignore[attr-defined]
        ):
            for code in original_node.args:
                self.ignore_codes.remove(node_to_code(code))
        return updated_node

    def leave_Attribute(  # noqa: N802
        self, original_node: cst.Attribute, updated_node: cst.Attribute
    ) -> cst.BaseExpression:
        if self.ignore_if_wrapped_with and node_to_code(original_node) in self.ignore_codes:
            return updated_node
        if isinstance(updated_node.value, cst.Attribute | cst.Name | cst.Subscript):
            if updated_node.attr.value in self.attributes:
                wrapped: Call = cst.Call(
                    func=cst.parse_expression(self.wrap_function_name),
                    args=[cst.Arg(value=updated_node)],
                )
                return wrapped
        return updated_node


class DictKeyWrapper(cst.CSTTransformer):
    def __init__(self, wrap_function_name: str, keys: list[str]) -> None:
        self.keys = keys
        self.wrap_function_name = wrap_function_name
        parts = wrap_function_name.split(".")
        self.wrap_function_node: cst.BaseExpression = cst.Name(parts[0])
        for part in parts[1:]:
            self.wrap_function_node = cst.Attribute(
                value=self.wrap_function_node, attr=cst.Name(part)
            )

    def leave_Subscript(  # noqa: N802
        self, original_node: cst.Subscript, updated_node: cst.Subscript
    ) -> cst.BaseExpression:
        for i, element in enumerate(updated_node.slice):
            if isinstance(element.slice, cst.Index) and isinstance(
                element.slice.value, cst.SimpleString
            ):
                key = element.slice.value.value.strip("'\"")
                if key in self.keys:
                    # Include this key in the wrapped expression
                    value_to_wrap = cst.Subscript(
                        value=updated_node.value, slice=updated_node.slice[: i + 1]
                    )
                    # Wrap the value
                    wrapped_value = cst.Call(
                        func=self.wrap_function_node, args=[cst.Arg(value=value_to_wrap)]
                    )
                    # Handle remaining subscript parts, if any
                    if i + 1 < len(updated_node.slice):
                        return cst.Subscript(value=wrapped_value, slice=updated_node.slice[i + 1 :])
                    else:
                        return wrapped_value
        return updated_node


class UndefinedVariablesChecker(ast.NodeVisitor):
    def __init__(self) -> None:
        self.defined: set[str] = set(builtins.__dict__.keys())
        self.undefined: set[str] = set()
        self.local_scopes: list[set[str]] = []

    def enter_local_scope(self) -> None:
        self.local_scopes.append(set())

    def exit_local_scope(self) -> None:
        if self.local_scopes:
            self.local_scopes.pop()

    def visit_Import(self, node: ast.Import) -> None:  # noqa: N802
        for name in node.names:
            self.defined.add(name.name.split(".")[0])

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:  # noqa: N802
        for name in node.names:
            self.defined.add(name.name)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
        self.enter_local_scope()
        for arg in node.args.args:
            self.local_scopes[-1].add(arg.arg)
        self.generic_visit(node)
        self.exit_local_scope()

    def visit_Lambda(self, node: ast.Lambda) -> None:  # noqa: N802
        self.enter_local_scope()
        for arg in node.args.args:
            self.local_scopes[-1].add(arg.arg)
        self.generic_visit(node)
        self.exit_local_scope()

    def visit_ListComp(self, node: ast.ListComp) -> None:  # noqa: N802
        self.enter_local_scope()
        for generator in node.generators:
            self.visit(generator)
        self.visit(node.elt)
        self.exit_local_scope()

    def visit_DictComp(self, node: ast.DictComp) -> None:  # noqa: N802
        self.enter_local_scope()
        for generator in node.generators:
            self.visit(generator)
        self.visit(node.key)
        self.visit(node.value)
        self.exit_local_scope()

    def visit_SetComp(self, node: ast.SetComp) -> None:  # noqa: N802
        self.enter_local_scope()
        for generator in node.generators:
            self.visit(generator)
        self.visit(node.elt)
        self.exit_local_scope()

    def visit_GeneratorExp(self, node: ast.GeneratorExp) -> None:  # noqa: N802
        self.enter_local_scope()
        for generator in node.generators:
            self.visit(generator)
        self.visit(node.elt)
        self.exit_local_scope()

    def visit_comprehension(self, node: ast.comprehension) -> None:
        self.visit(node.target)
        self.visit(node.iter)
        for if_clause in node.ifs:
            self.visit(if_clause)

    def visit_Name(self, node: ast.Name) -> None:  # noqa: N802
        if (
            isinstance(node.ctx, ast.Load)
            and node.id not in self.defined
            and not any(node.id in scope for scope in self.local_scopes)
        ):
            self.undefined.add(node.id)
        elif isinstance(node.ctx, ast.Store):
            if self.local_scopes:
                self.local_scopes[-1].add(node.id)
            else:
                self.defined.add(node.id)
        self.generic_visit(node)


class FunctionCallVisitor(cst.CSTVisitor):
    def __init__(self, full_code: str):
        self.full_code = full_code
        self.function_calls: list[ParsedFunctionCallCodeOutput] = []

    def leave_Call(self, node: cst.Call) -> None:  # noqa: N802
        function_name = node_to_code(node.func)
        code = node_to_code(node)
        positional_arguments = [
            node_to_code(arg).rstrip(",") for arg in node.args if arg.keyword is None
        ]
        keyword_arguments = {
            arg.keyword.value: node_to_code(arg.value)
            for arg in node.args
            if arg.keyword is not None
        }
        code_sub = find_code_substring_ignoring_identation(self.full_code, code)
        parsed_function_call = ParsedFunctionCallCodeOutput(
            name=function_name,
            code=code_sub,
            positional_arguments=positional_arguments,
            keyword_arguments=keyword_arguments,
        )
        self.function_calls.append(parsed_function_call)


class ConstructVisitor(cst.CSTVisitor):
    def __init__(self) -> None:
        self.loop_depth = 0
        self.constructs = {
            "datetime": False,
            "datastructures": False,
            "numericals": False,
            "exceptions": False,
            "comprehensions": False,
            "iterators": False,
            "loops": False,
            "nested_loops": False,
            "conditionals": False,
            "regex": False,
        }

    def visit_Attribute(self, node: cst.Attribute) -> None:  # noqa: N802
        if isinstance(node.value, cst.Name) and node.value.value in ("datetime", "DateTime"):
            self.constructs["datetime"] = True

    def visit_List(self, node: cst.List) -> None:  # noqa: N802
        self.constructs["datastructures"] = True

    def visit_Dict(self, node: cst.Dict) -> None:  # noqa: N802
        self.constructs["datastructures"] = True

    def visit_Set(self, node: cst.Set) -> None:  # noqa: N802
        self.constructs["datastructures"] = True

    def visit_Call(self, node: cst.Call) -> None:  # noqa: N802
        if isinstance(node.func, cst.Name) and node.func.value in (
            "Counter",
            "defaultdict",
            "namedtuple",
        ):
            self.constructs["datastructures"] = True
        if isinstance(node.func, cst.Name) and node.func.value in (
            "sum",
            "sorted",
            "min",
            "max",
            "heapq",
            "itertools",
        ):
            self.constructs["numericals"] = True
        if (
            isinstance(node.func, cst.Attribute)
            and isinstance(node.func.value, cst.Name)
            and node.func.value.value == "re"
        ):
            if node.func.attr.value in ("match", "search", "findall", "sub", "compile"):
                self.constructs["regex"] = True
        if isinstance(node.func, cst.Name) and node.func.value in ("next", "iter"):
            self.constructs["iterators"] = True

    def visit_Add(self, node: cst.Add) -> None:  # noqa: N802
        self.constructs["numericals"] = True

    def visit_Subtract(self, node: cst.Subtract) -> None:  # noqa: N802
        self.constructs["numericals"] = True

    def visit_Multiply(self, node: cst.Multiply) -> None:  # noqa: N802
        self.constructs["numericals"] = True

    def visit_Divide(self, node: cst.Divide) -> None:  # noqa: N802
        self.constructs["numericals"] = True

    def visit_FloorDivide(self, node: cst.FloorDivide) -> None:  # noqa: N802
        self.constructs["numericals"] = True

    def visit_Modulo(self, node: cst.Modulo) -> None:  # noqa: N802
        self.constructs["numericals"] = True

    def visit_Power(self, node: cst.Power) -> None:  # noqa: N802
        self.constructs["numericals"] = True

    def visit_Try(self, node: cst.Try) -> None:  # noqa: N802
        self.constructs["exceptions"] = True

    def visit_ListComp(self, node: cst.ListComp) -> None:  # noqa: N802
        self.constructs["comprehensions"] = True

    def visit_DictComp(self, node: cst.DictComp) -> None:  # noqa: N802
        self.constructs["comprehensions"] = True

    def visit_SetComp(self, node: cst.SetComp) -> None:  # noqa: N802
        self.constructs["comprehensions"] = True

    def visit_Yield(self, node: cst.Yield) -> None:  # noqa: N802
        self.constructs["iterators"] = True

    def visit_For(self, node: cst.For) -> None:  # noqa: N802
        self.constructs["loops"] = True
        was_already_in_loop = self.loop_depth > 0
        self.loop_depth += 1
        node.body.visit(self)
        if node.orelse:
            node.orelse.visit(self)
        self.loop_depth -= 1
        self.constructs["loops"] = True
        if was_already_in_loop:
            self.constructs["nested_loops"] = True

    def visit_While(self, node: cst.While) -> None:  # noqa: N802
        self.constructs["loops"] = True
        was_already_in_loop = self.loop_depth > 0
        self.loop_depth += 1
        node.body.visit(self)
        if node.orelse:
            node.orelse.visit(self)
        self.loop_depth -= 1
        self.constructs["loops"] = True
        if was_already_in_loop:
            self.constructs["nested_loops"] = True

    def visit_If(self, node: cst.If) -> None:  # noqa: N802
        self.constructs["conditionals"] = True


class FunctionPathVisitor(cst.CSTVisitor):
    def __init__(self, wrapper: MetadataWrapper, aliases: dict[str, str]):
        self.wrapper = wrapper
        self.aliases = aliases
        self.paths: list[str] = []
        self.instance_map: dict[str, str] = {}

    def visit_Assign(self, node: cst.Assign) -> None:  # noqa N802
        if isinstance(node.value, cst.Call):
            if isinstance(node.value.func, cst.Attribute) or isinstance(node.value.func, cst.Name):
                name_parts = self._get_full_name_parts(node.value.func)
                full_name = ".".join(name_parts)
                resolved_name = self._resolve_aliases(full_name)
                for target in node.targets:
                    if isinstance(target.target, cst.Name):
                        self.instance_map[target.target.value] = resolved_name

    def visit_Call(self, node: cst.Call) -> None:  # noqa N802
        func = node.func
        if isinstance(func, cst.Attribute):
            name_parts = self._get_full_name_parts(func)
            full_name = ".".join(name_parts)
            if name_parts[0] in self.instance_map:
                instance_class = self.instance_map[name_parts[0]]
                resolved_name = instance_class + "." + ".".join(name_parts[1:])
            else:
                resolved_name = self._resolve_aliases(full_name)
            self.paths.append(resolved_name)
        elif isinstance(func, cst.Name):
            resolved_name = self._resolve_aliases(func.value)
            self.paths.append(resolved_name)

    def _get_full_name_parts(self, node: cst.CSTNode) -> list[str]:
        name_parts: list[str] = []
        while isinstance(node, cst.Attribute):
            name_parts.insert(0, node.attr.value)
            if isinstance(node.value, cst.Call):
                name_parts.insert(0, node_to_code(node.value.func))
            node = node.value
        if isinstance(node, cst.Name):
            name_parts.insert(0, node.value)
        return name_parts

    def _resolve_aliases(self, full_name: str) -> str:
        parts = full_name.split(".")
        if parts[0] in self.aliases:
            parts[0] = self.aliases[parts[0]]
        return ".".join(parts)


class VariableCollector(cst.CSTVisitor):
    def __init__(self) -> None:
        self.variables: set[str] = set()

    def visit_Assign(self, node: cst.Assign) -> None:  # noqa: N802
        for target in node.targets:
            if isinstance(target.target, cst.Name):
                self.variables.add(target.target.value)
            elif isinstance(target.target, cst.Tuple):
                for element in target.target.elements:
                    if isinstance(element.value, cst.Name):
                        self.variables.add(element.value.value)

    def visit_AnnAssign(self, node: cst.AnnAssign) -> None:  # noqa: N802
        if isinstance(node.target, cst.Name):
            self.variables.add(node.target.value)


class LoopCounter(cst.CSTVisitor):
    def __init__(self) -> None:
        self.loop_count = 0

    def visit_For(self, node: cst.For) -> None:  # noqa: N802
        self.loop_count += 1

    def visit_While(self, node: cst.While) -> None:  # noqa: N802
        self.loop_count += 1

    def visit_CompFor(self, node: cst.CompFor) -> None:  # noqa: N802
        self.loop_count += 1


class ImportVisitor(cst.CSTVisitor):
    def __init__(self) -> None:
        self.imports: set[str] = set()

    def visit_Import(self, node: cst.Import) -> None:  # noqa: N802
        for name in node.names:
            if matchers.matches(name, matchers.ImportAlias()):
                self.imports.add(node_to_code(name.name).split(".")[0])

    def visit_ImportFrom(self, node: cst.ImportFrom) -> None:  # noqa: N802
        if not node.module:
            return
        value = node.module.value
        if not isinstance(value, str):
            value = value.value  # type: ignore[attr-defined]
        if not isinstance(value, str):
            value = value.value  # type: ignore[attr-defined]
        if not isinstance(value, str):
            value = value.value  # type: ignore[attr-defined]
        if not isinstance(value, str):
            return
        import_name = value.split(".")[0]
        if matchers.matches(node.module, matchers.Attribute()):
            self.imports.add(import_name)
        elif matchers.matches(node.module, matchers.Name()):
            self.imports.add(import_name)


def parse_function_code(code: str, function_name: str) -> ParsedFunctionCodeOutput:
    """
    Returns the function definition, docstring, body, and body with docstring. The code
    can be something in which the function is embedded or the function code itself.

    It needs the function to be type annotated for the return type. The '->' is used
    as an indicator of function defintion end. TODO: Revisit to make it more robust.
    """
    # NOTE: Do not remove new lines from the code. It is important to preserve the
    # exact string so it can be checked against the original code.
    lines = code.split("\n")
    function_def_line_start_indices = [
        index for index, line in enumerate(lines) if f"def {function_name}(" in line
    ]
    if not function_def_line_start_indices:
        raise ValueError(f"Function '{function_name}' not found in the class source code.")
    function_def_line_start_index = function_def_line_start_indices[0]
    function_def_line_end_indices = [
        index
        for index, line in enumerate(lines)
        if "->" in line and index >= function_def_line_start_index
    ]
    if not function_def_line_end_indices:
        raise ValueError(
            "Function definition does not have output type annotation '->'. "
            "So couldn't find end of the function definition"
        )
    function_def_line_end_index = function_def_line_end_indices[0]

    def line_to_indent_level(line: str) -> int:
        return math.floor(len(line.removesuffix(line.lstrip())) / 4)

    function_def_intent_level = line_to_indent_level(lines[function_def_line_start_index])
    function_end_indices = [
        index
        for index, line in enumerate(lines)
        if line_to_indent_level(line) == function_def_intent_level
        and index > function_def_line_end_index
    ]
    function_end_index = function_end_indices[0] if function_end_indices else len(lines)
    docstring_indices = [
        index
        for index, line in enumerate(lines)
        if line_to_indent_level(line) == function_def_intent_level + 1
        and index > function_def_line_end_index
        and index < function_end_index
        and line.lstrip().startswith('"""')
    ][:2]
    docstring: str | None = None
    if len(docstring_indices) == 2:
        docstring = "\n".join(lines[docstring_indices[0] : docstring_indices[-1] + 1])
    definition = "\n".join(lines[function_def_line_start_index : function_def_line_end_index + 1])
    body_code_start_index = (
        docstring_indices[-1] + 1 if docstring else function_def_line_end_index + 1
    )
    body = "\n".join(lines[body_code_start_index:function_end_index])
    parsed_function_output = ParsedFunctionCodeOutput(
        definition=definition,
        docstring=docstring,
        body=body,
        indent_level=function_def_intent_level,
    )
    return parsed_function_output


def parse_function(function: FunctionType) -> ParsedFunctionCodeOutput:
    return parse_function_code(inspect.getsource(function), function.__name__)


def parse_code_function_calls(code: str) -> list[ParsedFunctionCallCodeOutput]:
    parsed_code = cst.parse_module(code)
    visitor = FunctionCallVisitor(code)
    parsed_code.visit(visitor)
    return visitor.function_calls


def parse_code_function_paths(code: str) -> set[str]:
    aliases = {}
    module = cst.parse_module(code)
    for statement in module.body:
        if isinstance(statement, cst.SimpleStatementLine):
            for import_ in statement.body:
                if isinstance(import_, cst.Import):
                    for alias in import_.names:
                        if alias.asname:
                            aliases[alias.asname.name.value] = node_to_code(  # type: ignore[union-attr]
                                alias.name
                            )
                elif isinstance(import_, cst.ImportFrom):
                    module_name = ""
                    if isinstance(import_.module, cst.Name):
                        module_name = import_.module.value
                    elif isinstance(import_.module, cst.Attribute):
                        module_name = ".".join(
                            FunctionPathVisitor(None, None)._get_full_name_parts(  # type: ignore[arg-type]
                                import_.module
                            )
                        )
                    for alias in import_.names:  # type: ignore[union-attr]
                        if isinstance(alias, cst.ImportAlias):
                            if alias.asname:
                                aliases[alias.asname.name.value] = (  # type: ignore[union-attr]
                                    f"{module_name}.{alias.name.value}"
                                )
                            else:
                                aliases[alias.name.value] = f"{module_name}.{alias.name.value}"
    wrapper = MetadataWrapper(module)
    visitor = FunctionPathVisitor(wrapper, aliases)
    wrapper.visit(visitor)
    paths_list = visitor.paths
    builtin_functions = {"exit", "quit", "open", "SystemExit", "eval", "exec"}  # No need for more.
    function_paths: set[str] = {
        "builtins." + path if path in builtin_functions else path for path in paths_list
    }
    return function_paths


def parse_code_dict(code_dict_string: str) -> dict[str, str]:
    result_dict = {}
    expression_node = cst.parse_expression(code_dict_string)
    for element in expression_node.elements:  # type: ignore[attr-defined]
        key_string = node_to_code(element.key)
        value_string = node_to_code(element.value)
        result_dict[key_string] = value_string
    return result_dict


def get_undefined_variables(code: str) -> set[str]:
    tree = ast.parse(code)
    checker = UndefinedVariablesChecker()
    checker.visit(tree)
    return checker.undefined


def is_valid_python_code(code: str) -> bool:
    try:
        ast.parse(code)
        return True
    except SyntaxError:
        return False


def parse_comment_and_code_blocks(code: str) -> list[tuple[str, str]]:
    lines = code.splitlines()
    result: list[tuple[str, str]] = []
    current_comment = ""
    current_code = ""
    comment_started = False
    for line in lines:
        if line.strip().startswith("#"):  # Check if the line is a comment
            if comment_started:
                current_comment += "\n" + line
            else:
                # If a new comment starts and there is an existing code block, save it
                if current_code:
                    result.append((current_comment, current_code))
                    current_code = ""
                current_comment = line
                comment_started = True
        else:
            # Add non-empty lines of code
            if line.strip():
                current_code += line + "\n"
                if comment_started:
                    # If this line of code follows a comment, reset the flag
                    comment_started = False
    # Add the last comment and code block if they exist and are non-empty
    if current_comment or current_code.strip():
        result.append((current_comment, current_code))
    return result


def get_indentation_level(code: str) -> int:
    return math.floor(len(code.removesuffix(code.lstrip())) / 4)


def transform_attribute_to_key_access(code: str, attributes: list[str]) -> str:
    tree = cst.parse_module(code)
    transformer = AttributeTransformer(attributes)
    transformed_tree = tree.visit(transformer)
    return transformed_tree.code


def wrap_attribute_access_with_function_call(
    code: str,
    wrap_function_name: str,
    attributes: list[str],
    ignore_if_wrapped_with: str | None = None,
) -> str:
    tree: Module = cst.parse_module(code)
    transformer: AttributeWrapper = AttributeWrapper(
        wrap_function_name, attributes, ignore_if_wrapped_with
    )
    wrapped_tree: Module = tree.visit(transformer)
    return wrapped_tree.code


def wrap_key_access_with_function_call(code: str, wrap_function_name: str, keys: list[str]) -> str:
    tree = cst.parse_module(code)
    wrapper = DictKeyWrapper(wrap_function_name, keys)
    wrapped_tree = tree.visit(wrapper)
    return wrapped_tree.code


def node_to_code(node: CSTNode) -> str:
    return cst.Module([cst.SimpleStatementLine([cst.Expr(node)])]).code.strip()  # type: ignore[arg-type]


def programming_construct_usages(code: str) -> dict[str, bool]:
    """
    Uses cst module to check if which of the following programming
    constructs are used in the code somewhere.

    "datetime": Datetime handling/manipulation using datetime module or DateTime class.
    "datastructures": Data structures such as lists, dictionaries, sets, tuples, counters, defaultdict, namedtuple.
    "Numericals": Algorithmic constructs such as sort, min/max, heapq, itertools and any arithmetic operations.
    "exceptions": Exception handling with try/except blocks.
    "comprehensions": List, dictionary, set comprehensions.
    "iterators": Iterators and generators using yield.
    "loops": For or while loops.
    "nested_loops": Nested loops (two or more levels deep).
    "conditionals": Conditional statements with if/elif/else.
    "regex": Regular expressions using the re module.
    """
    module = cst.parse_module(code)
    visitor = ConstructVisitor()
    module.visit(visitor)
    if "DateTime" in code:  # TODO: move it properly to ConstructVisitor
        visitor.constructs["datetime"] = True
    return visitor.constructs


def variables(code: str) -> set[str]:
    tree = cst.parse_module(code)
    collector = VariableCollector()
    tree.visit(collector)
    return collector.variables


def loop_count(code: str) -> int:
    tree = cst.parse_module(code)
    counter = LoopCounter()
    tree.visit(counter)
    return counter.loop_count


def parse_imports(code: str) -> set[str]:
    code = dedent(code)
    module = cst.parse_module(code)
    collector = ImportVisitor()
    module.visit(collector)
    return collector.imports


def is_same_syntax(text_a: str, text_b: str) -> bool:
  if not text_a or not text_b:
    raise ValueError(f"is_same_syntax: both inputs must be non-empty strings, got text_a={text_a!r}, text_b={text_b!r}")
  try:
    # 1. 두 코드를 AST(추상 구문 트리)로 파싱
    # ast.parse는 공백, 주석을 자동으로 제거하고 순수 논리 구조만 남깁니다.
    tree_a = ast.parse(text_a.strip())
    tree_b = ast.parse(text_b.strip())
    # 2. 구조 덤프(Dump) 비교
    # ast.dump()는 트리를 문자열 표현으로 변환합니다. 
    # 이때 변수명, 함수명, 구조 등은 포함되지만 줄 번호나 공백 정보는 포함되지 않습니다.
    return ast.dump(tree_a) == ast.dump(tree_b)
  except SyntaxError as e:
    raise SyntaxError(
      f"is_same_syntax: cannot parse one or both inputs as valid Python. "
      f"text_a={text_a[:100]!r}, text_b={text_b[:100]!r}"
    ) from e


def substitute_leading_substr(text: str, old: str, new: str) -> str:
  if not old:
    raise ValueError("substr cannot be empty")
  # 1. substr에 정규식 특수문자(., *, ? 등)가 포함되어 있을 수 있으므로 이스케이프 처리
  # 예: substr이 ".."라면 -> "\.\."으로 변환됨
  escaped_substr = re.escape(old)
  # 2. 정규식 패턴 생성
  # ^ : 각 줄의 시작
  # (?:...)+ : 해당 패턴이 1번 이상 반복됨 (비캡처 그룹)
  pattern = re.compile(rf"^(?:{escaped_substr})+", re.MULTILINE)
  return pattern.sub(lambda m: new * (len(m.group(0)) // len(old)), text)


class FormatEmptyLinesTransformer(cst.CSTTransformer):

  def format(
    self, 
    body: Sequence[cst.BaseStatement]
  ) -> Sequence[cst.BaseStatement]:

    formatted_body = []
    for i, statement in enumerate(body):
      # 기존의 leading_lines 중 주석(comment)이 포함된 라인만 남기고 순수 빈 줄은 모두 제거
      leading_lines = getattr(statement, "leading_lines", [])
      leading_lines = [
        line for line in leading_lines if getattr(line, "comment") is not None
      ]
      if i > 0:
        if (
          isinstance(body[i - 1], cst.BaseCompoundStatement) and
          hasattr(body[i - 1], "body") and
          isinstance(body[i - 1].body, cst.IndentedBlock)
        ):
          if not (leading_lines and isinstance(leading_lines[0], cst.EmptyLine)):
            leading_lines.insert(0, cst.EmptyLine())
      
      formatted_body.append(
        statement.with_changes(
          leading_lines=leading_lines
        )
      )
      
    return formatted_body

  def leave_Module(self, original, updated):
    return updated.with_changes(body=self.format(updated.body))

  def leave_IndentedBlock(self, original, updated_node):
    return updated_node.with_changes(body=self.format(updated_node.body))


def format_empty_lines(code):
  tree = cst.parse_module(code)
  return tree.visit(FormatEmptyLinesTransformer()).code.strip()


class Reindent(cst.CSTTransformer):

  """
  모든 IndentedBlock(if, for, def 등의 내부 블록)을 방문하여
  들여쓰기 문자열을 새로운 값으로 교체하는 트랜스포머
  """
  def __init__(self, indent: str):
    self.indent = indent
    self.black_mode = black.Mode(line_length=60)

  def leave_IndentedBlock(
    self, 
    original: cst.IndentedBlock, 
    updated: cst.IndentedBlock
  ) -> cst.IndentedBlock:
    # original_node.indent는 현재 블록의 들여쓰기 문자열(예: "    " 또는 "\t")을 가집니다.
    # 이를 우리가 원하는 indent(예: "  ")로 덮어씁니다.
    # LibCST는 중첩된 구조를 알아서 계산하므로, '한 단계'의 들여쓰기만 지정하면 됩니다.
    return updated.with_changes(indent=self.indent)

  def _reformat(self, node: cst.CSTNode) -> cst.CSTNode:
    try:
      code = cst.Module([]).code_for_node(node)
      code = textwrap.dedent(code)
      code = black.format_str(code, mode=self.black_mode).strip()
      return cst.parse_expression(
        substitute_leading_substr(code, old="    ", new="  ")
      )
    except Exception as e:
      return node

  def leave_Call(self, original, updated): return self._reformat(updated)
  def leave_List(self, original, updated): return self._reformat(updated)
  def leave_Dict(self, original, updated): return self._reformat(updated)
  def leave_Tuple(self, original, updated): return self._reformat(updated)
  def leave_Set(self, original, updated): return self._reformat(updated)


def reindent(code, indent="  "):
  """
  code_str: 파이썬 소스 코드
  num_spaces: 변경할 들여쓰기 스페이스 개수 (기본 2칸)
  """
  # 1. 원하는 들여쓰기 문자열 생성 (예: "  ")
  # 2. 코드를 CST(Concrete Syntax Tree)로 파싱
  tree = cst.parse_module(code)
  # 3. 트랜스포머 적용 (모든 블록의 indent 속성 변경)
  return tree.visit(Reindent(indent)).code


def maybe_reformat(code: str, indent: str | None = None):
  code = format_empty_lines(code)
  if indent is None:
    return code
  return reindent(code, indent)


class FunctionDefVisitor(cst.CSTVisitor):

  def __init__(self, targets: list[str] | None):
    self.targets = targets
    self.function_defs: dict[str, cst.FunctionDef] = {}

  def visit_FunctionDef(self, node: cst.FunctionDef):
    # 함수 이름이 타겟 리스트에 있는지 확인
    if self.targets is None or node.name.value in self.targets:
      # 이미 찾은 함수는 덮어씌울지 말지 결정 (여기선 덮어씌움: 최신 코드 우선)
      self.function_defs[node.name.value] = node
    # 중첩 함수나 클래스 내부 메서드도 찾으려면 True 반환 (계속 탐색)
    return True


_language_marker_pattern = re.compile(r"^\s*```(?:python|py)?[ \t]*", flags=re.IGNORECASE)
def _extract_first_longest_python_code(text: str, start: int, reindent: str | None = None):
  lines = text.splitlines()
  for end in range(len(lines), start, -1):
    chunk = lines[start:end]
    if not any(line.strip() for line in chunk): # empty lines
      continue
    if chunk[0].startswith("```"):
      chunk[0] = _language_marker_pattern.sub("", chunk[0])
    chunk = textwrap.dedent("\n".join(chunk)).strip()
    if not chunk:
      continue
    try:
      cst.parse_module(chunk)
      return maybe_reformat(chunk.strip(), reindent), (start, end)
    except:
      pass
  return None


def extract_python_codes(text: str, reindent: str | None = None) -> list[str]:
  lines = text.splitlines()
  codes = []
  start = 0
  while start < len(lines):
    code = _extract_first_longest_python_code(text, start, reindent)
    if not code:
      start += 1
    else:
      code, (_, start) = code
      codes.append(code)
  return codes


def parse_plain_texts_and_python_codes(text: str, reindent: str | None = None) -> list[dict[str, str]]:
  lines = text.splitlines()
  segments = []
  start = 0
  plain_text = []
  while start < len(lines):
    code = _extract_first_longest_python_code(text, start, reindent)
    if not code:
      if _language_marker_pattern.match(lines[start]) is None:
        plain_text.append(lines[start])
      start += 1
    else:
      code, (_, code_end) = code
      # 1. 코드를 찾았다면, 그동안 누적된 텍스트를 먼저 결과에 저장
      if plain_text:
        plain_text_content = "\n".join(plain_text).strip()
        if plain_text_content:
          segments.append({"type": "text", "content": plain_text_content})
      # 2. 추출된 파이썬 코드를 저장
      segments.append({"type": "code", "content": code})
      # 3. 다음 탐색 위치와 텍스트 시작 기준점을 코드 블록 이후로 점프
      start = code_end
      plain_text = []

  # 4. 루프가 끝난 후, 마지막 코드 블록 뒤에 남은 일반 텍스트 처리
  if plain_text:
    plain_text_content = "\n".join(plain_text).strip()
    if plain_text_content:
      segments.append({"type": "text", "content": plain_text_content})
          
  return segments


def remove_python_codes(text: str, insert_between: str = "\n\n") -> str:
  contents = []
  for segment in parse_plain_texts_and_python_codes(text):
    if segment["type"] != "code":
      contents.append(segment["content"])
  return insert_between.join(contents)


def extract_fenced_chunks(text: str):
  return re.findall(
    r"```(?:python|py|json)?[ \t]*(?:\r?\n)?(.*?)```", 
    text, 
    re.DOTALL | re.IGNORECASE
  )


def extract_python_function_defs(
  text: str, 
  target: str | list[str] | None = None, 
  reindent: str | None = None
):
  target = [target] if isinstance(target, str) else target
  function_defs = {}
  for code in extract_python_codes(text, reindent):
    try:
      tree = cst.parse_module(code)
      visitor = FunctionDefVisitor(target)
      tree.visit(visitor)
      for name, node in visitor.function_defs.items():
        function_defs[name] = tree.code_for_node(node).strip()
    except Exception:
      raise AssertionError("shoud not happen")
  if isinstance(target, list) and len(target) == 1:
    return function_defs[target[0]]
  if len(function_defs) == 0:
    return None
  return function_defs


class AddDocstringTransformer(cst.CSTTransformer):

  def __init__(self, function_name: str, docstring: str, tree: cst.Module):
    self.function_name = function_name
    self.docstring = docstring
    self.indent = tree.default_indent
    self.depth = 0

  def visit_IndentedBlock(self, node: cst.IndentedBlock):
    self.depth += 1
    return True

  def leave_IndentedBlock(
      self, 
      original_node: cst.IndentedBlock, 
      updated_node: cst.IndentedBlock
    ) -> cst.IndentedBlock:
    self.depth -= 1
    return updated_node

  def _get_formatted_docstring(self) -> str:
    depth = self.depth + 1
    indent = self.indent * depth
    doc = textwrap.dedent(self.docstring).strip()
    return f'"""\n{textwrap.indent(doc, indent)}\n{indent}"""'

  def _is_docstring(self, node: cst.CSTNode) -> bool:
    if isinstance(node, cst.SimpleStatementLine):
      if len(node.body) == 1 and isinstance(node.body[0], cst.Expr):
        value = node.body[0].value
        if isinstance(value, (cst.SimpleString, cst.ConcatenatedString)):
          return True
    return False

  def leave_FunctionDef(
    self, 
    original_node: cst.FunctionDef, 
    updated_node: cst.FunctionDef
  ) -> cst.FunctionDef:

    if original_node.name.value != self.function_name:
      return updated_node

    docstring_node = cst.SimpleStatementLine(
      body=[
        cst.Expr(
          value=cst.SimpleString(
            self._get_formatted_docstring()
          )
        )
      ]
    )
    body_statements = list(updated_node.body.body)
    if body_statements and self._is_docstring(body_statements[0]):
      body_statements[0] = docstring_node
    else:
      body_statements.insert(0, docstring_node)
    return updated_node.with_changes(
      body=updated_node.body.with_changes(
        body=body_statements
      )
    )


def add_docstring_to_function(code, name, docstring):
  tree = cst.parse_module(code)
  transformer = AddDocstringTransformer(name, docstring, tree)
  tree = tree.visit(transformer)
  return tree.code


class RemoveDocstringTransformer(cst.CSTTransformer):

  def leave_FunctionDef(
    self, 
    original: cst.FunctionDef, 
    updated: cst.FunctionDef
  ) -> cst.FunctionDef:

    body = updated.body
    statements = list(body.body)
    if not statements:
      return updated
    if matchers.matches(
      statements[0],
      matchers.SimpleStatementLine(
        body=[
          matchers.Expr(
            value=(
              matchers.SimpleString() |
              matchers.ConcatenatedString()
            )
          )
        ]
      )
    ):
      new_statements = statements[1:]
      if not new_statements:
        new_statements.append(
          cst.SimpleStatementLine(body=[cst.Pass()])
        )
      return updated.with_changes(
        body=body.with_changes(body=new_statements)
      )
    return updated


def remove_docstring(defn: str):
  tree = cst.parse_module(defn)
  transformer = RemoveDocstringTransformer()
  tree = tree.visit(transformer)
  return tree.code


class CallVisitor(cst.CSTVisitor):

  def __init__(self, name: str):
    self.name = name
    self.calls: list[cst.Call] = []

  def leave_Call(self, original_node: cst.Call):
    # 함수 이름이 타겟 리스트에 있는지 확인
    name = get_full_name_for_node(original_node.func)
    if name == self.name:
      self.calls.append(original_node)


def extract_python_calls(text: str, name: str, reindent: str | None = None):
  calls = []
  for code in extract_python_codes(text, reindent):
    try:
      tree = cst.parse_module(code)
      visitor = CallVisitor(name)
      tree.visit(visitor)
      for node in visitor.calls:
        calls.append(tree.code_for_node(node).strip())
    except Exception:
      raise AssertionError("shoud not happen")
  return calls


class GatherCallArgumentsVisitor(cst.CSTVisitor):

  def __init__(self, name: str):
    self.name = name
    self.arguments = []

  def visit_Call(self, node: cst.Call) -> cst.Call:
    name = get_full_name_for_node(node.func)
    if name == self.name:
      for argument in node.args:
        keyword = argument.keyword.value if argument.keyword else None
        self.arguments.append((
          keyword, cst.Module([]).code_for_node(argument.value).strip()
        ))


def extract_call_arguments(text: str, name: str):
  tree = cst.parse_module(text)
  visitor = GatherCallArgumentsVisitor(name)
  tree.visit(visitor)
  return visitor.arguments


class SubstitueCallArgumentsTransformer(cst.CSTTransformer):

  def __init__(
    self, name: str, 
    new_arguments: list[tuple[str | None, str]]
  ):
    self.name = name
    self.new_arguments = new_arguments

  def leave_Call(self, original: cst.Call, updated: cst.Call) -> cst.Call:
    name = get_full_name_for_node(original.func)
    if name != self.name:
      return updated
    new_arguments = []
    for old, (keyword, new) in zip(updated.args, self.new_arguments, strict=True):
      if new is None:
        new_arguments.append(old)
      else:
        new_arguments.append(
          old.with_changes(value=cst.parse_expression(new))
        )
    return updated.with_changes(args=new_arguments)


def substitute_call_arguments(
  text: str, 
  name: str, 
  new_arguments: list[tuple[str | None, str]]
):
  tree = cst.parse_module(text)
  transformer = SubstitueCallArgumentsTransformer(name, new_arguments)
  tree = tree.visit(transformer)
  return tree.code


class StorePrintPassTransformer(cst.CSTTransformer):

  def __init__(
    self, 
    call_name: str, 
    argument_index: int,
    store_name: str,
  ):
    self.call_name = call_name
    self.argument_index = argument_index
    self.store_name = store_name
    # 스택: [None, None, ExpressionNode, None]
    # None: 현재 구문에서 아직 추출된 게 없음
    # Node: 현재 구문에서 추출된 표현식이 있음
    self.stack: list[cst.BaseExpression | None] = []

    # self.extracted_expr: cst.BaseExpression | None = None
    # self.found_match = False

  def _visit_stmt(self, node): self.stack.append(None)
  def _leave_stmt(self, original, updated):

    if not self.stack:
      return updated

    extracted_expr = self.stack.pop()
    if extracted_expr is None:
      return updated

    # --- 새로운 구문 생성 ---
    # 1. 할당문 생성: a = get_access_token...()
    store_node = cst.SimpleStatementLine(
      body=[
        cst.Assign(
          targets=[
            cst.AssignTarget(
              target=cst.Name(self.store_name)
            )
          ],
          value=extracted_expr
        )
      ]
    )
    # 2. 출력문 생성: print(a)
    print_node = cst.SimpleStatementLine(
      body=[
        cst.Expr(
          value=cst.Call(
            func=cst.Name("print"),
            args=[
              cst.Arg(
                value=cst.Name(self.store_name)
              )
            ]
          )
        )
      ]
    )
    # 3. FlattenSentinel을 사용하여 [할당 -> 출력 -> 원래구문] 순서로 반환
    #    이렇게 하면 원래의 한 줄이 세 줄로 확장됩니다.
    return cst.FlattenSentinel([store_node, print_node, updated])

  def leave_Call(self, original: cst.Call, updated: cst.Call) -> cst.Call:

    # 스택이 비었거나(구문 밖)
    if not self.stack:
      return updated
    # 현재 구문에 이미 추출된 게 있으면(중복)
    if self.stack[-1] is not None:
      return updated
    # 타겟 아님
    if get_full_name_for_node(original.func) != self.call_name:
      return updated

    # 3. 타겟 인자 가져오기
    argument = updated.args[self.argument_index]
    # 4. 추출할 원래 값 저장 (예: get_access_token_...())
    #    깊은 복사나 재사용을 위해 노드 자체를 저장
    self.stack[-1] = argument.value
    # 5. 함수 호출 내부의 인자를 변수명(pass_name)으로 교체
    #    예: access_token=... -> access_token=a
    new = argument.with_changes(value=cst.Name(self.store_name))
    new_arguments = list(updated.args)
    new_arguments[self.argument_index] = new
    return updated.with_changes(args=new_arguments)

  def visit_SimpleStatementLine(self, node): self._visit_stmt(node)
  def leave_SimpleStatementLine(self, original, updated): return self._leave_stmt(original, updated)
  def visit_For(self, node): self._visit_stmt(node)
  def leave_For(self, original, updated): return self._leave_stmt(original, updated)
  def visit_While(self, node): self._visit_stmt(node)
  def leave_While(self, original, updated): return self._leave_stmt(original, updated)
  def visit_If(self, node): self._visit_stmt(node)
  def leave_If(self, original, updated): return self._leave_stmt(original, updated)
  def visit_With(self, node): self._visit_stmt(node)
  def leave_With(self, original, updated): return self._leave_stmt(original, updated)
  def visit_FunctionDef(self, node): self._visit_stmt(node)
  def leave_FunctionDef(self, original, updated): return self._leave_stmt(original, updated)


def store_print_pass_transform(
  text: str, 
  call_name: str,
  argument_index: int, 
  store_name: str, 
):
  tree = cst.parse_module(text)
  transformer = StorePrintPassTransformer(call_name, argument_index, store_name)
  tree = tree.visit(transformer)
  return tree.code


class FindAssignmentVisitor(cst.CSTVisitor):

  def __init__(self, target: str):
    self.target = target
    self.value: cst.CSTNode | None = None

  def visit_Assign(self, node: cst.Assign):
    for target in node.targets:
      target = target.target
      if isinstance(target, cst.Name) and target.value == self.target:
        self.value = node.value
        return False


def get_assignment_value(text: str, target: str, literal_eval: bool = True):
  tree = cst.parse_module(text)
  visitor = FindAssignmentVisitor(target)
  tree.visit(visitor)
  if visitor.value is None:
    return None
  else:
    rhs = tree.code_for_node(visitor.value)
    if not literal_eval:
      return rhs
    else:
      return ast.literal_eval(rhs)


class RemoveCommentTransformer(cst.CSTTransformer):

  def leave_TrailingWhitespace(
    self, 
    original: cst.TrailingWhitespace, 
    updated: cst.TrailingWhitespace
  ) -> cst.TrailingWhitespace:
    """
    인라인 주석 제거 (예: x = 1 # 주석 -> x = 1)
    코드 뒤에 붙은 주석(Inline Comment)을 처리합니다.
    """
    if updated.comment:
      return updated.with_changes(
        comment=None, 
        whitespace=cst.SimpleWhitespace("")
      )
    return updated

  def leave_EmptyLine(
    self, 
    original: cst.EmptyLine, 
    updated: cst.EmptyLine
  ) -> cst.EmptyLine:
    """
    독립 주석 제거 (예: # 주석 -> 빈 줄)
    줄 전체가 주석인 경우(Block Comment)를 처리합니다.
    """
    if updated.comment:
      return cst.RemoveFromParent()
    return updated


def remove_comments(text: str):
  tree = cst.parse_module(text)
  transformer = RemoveCommentTransformer()
  tree = tree.visit(transformer)
  return tree.code


def _contains_call(name, node):
  visitor = CallVisitor(name)
  node.visit(visitor)
  return len(visitor.calls) > 0


class TruncateExecutionFlowTransformer(cst.CSTTransformer):
  
  def __init__(self, function_call_name: str):
    self.function_call_name = function_call_name

  def _slice_statement_list(
      self, stmts: Sequence[cst.BaseStatement]
  ) -> Sequence[cst.BaseStatement]:
    """
    stmts 중에서 target 호출을 포함하는 "첫 문장"까지 살리고,
    그 뒤 문장들은 제거.
    만약 어떤 문장도 target을 포함하지 않으면 그대로 반환.
    """
    new_stmts: list[cst.BaseStatement] = []
    found = False
    for stmt in stmts:
      if found:
        break
      new_stmts.append(stmt)
      if _contains_call(self.function_call_name, stmt):
        found = True
    return tuple(new_stmts)

  def _slice_small_statements(
    self, 
    small_stmts: Sequence[cst.BaseSmallStatement]
  ) -> Sequence[cst.BaseSmallStatement]:
    new_stmts = []
    found = False
    for stmt in small_stmts:
      if found:
        break
      new_stmts.append(stmt)
      if _contains_call(self.function_call_name, stmt):
        found = True
    return tuple(new_stmts)

  def _slice_suite(self, suite: cst.BaseSuite) -> cst.BaseSuite:
    """
    IndentedBlock 내부의 body(문장 리스트)를 슬라이싱.
    SimpleStatementSuite(if cond: a(); b()) 같은 경우는
    문장 단위로 자르기 애매하니, 우선 그대로 둔다.
    필요하면 여기서 더 세밀하게 자를 수 있음.
    """
    if isinstance(suite, cst.IndentedBlock):
      return suite.with_changes(body=self._slice_statement_list(suite.body))
    elif isinstance(suite, cst.SimpleStatementSuite):
      raise NotImplementedError(
        f"TruncateExecutionFlowTransformer._handle_suite: "
        f"SimpleStatementSuite truncation is not implemented (e.g., 'if cond: a(); b()')"
      )
    else:
      return suite

  def leave_Module(self, original: cst.Module, updated: cst.Module) -> cst.Module:
    new_body = self._slice_statement_list(updated.body)
    return updated.with_changes(body=new_body)

  def leave_IndentedBlock(
    self, original: cst.IndentedBlock, updated: cst.IndentedBlock
  ) -> cst.IndentedBlock:
    # 모든 블록(함수, for, while, class 등) 내의 문장을 슬라이싱
    new_body = self._slice_statement_list(updated.body)
    return updated.with_changes(body=new_body)

  def leave_Else(self, original: cst.Else, updated: cst.Else) -> cst.Else:
    # Else 블록 자체도 내부 문장을 슬라이싱해서 정리된 상태로 만듦
    new_body = self._slice_suite(updated.body)
    return updated.with_changes(body=new_body)

  def leave_If(self, original: cst.If, updated: cst.If) -> cst.If:
    # 1. Body(then-block) 검사
    then_has_target = _contains_call(self.function_call_name, updated.body)
    # 2. Orelse(else/elif block) 검사
    # 중요: orelse.body만 보는 게 아니라 orelse 서브트리 전체를 봐야 
    # 중첩된 elif/else 안쪽의 타겟도 찾을 수 있음.
    orelse_has_target = False
    if updated.orelse is not None:
      orelse_has_target = _contains_call(self.function_call_name, updated.orelse)
    # 둘 다 있음
    if then_has_target and orelse_has_target:
      return updated
    # 둘 다 없음
    if (not then_has_target) and (not orelse_has_target):
      return updated
    # then에만 있음
    if then_has_target:
      return updated.with_changes(orelse=None)
    # else/elif에만 있음
    else:
      return updated.with_changes(
        body=cst.IndentedBlock(
          body=[
            cst.SimpleStatementLine([cst.Pass()])
          ]
        )
      )

  def _handle_loop(self, updated):
    body_has_target = _contains_call(self.function_call_name, updated.body)
    orelse_has_target = False
    if updated.orelse is not None:
      orelse_has_target = _contains_call(self.function_call_name, updated.orelse)
    # 둘 다 없음
    if (not body_has_target) and (not orelse_has_target):
      return updated
    # Case 1: 본문에 타겟 있음 -> 루프 정상 종료 불가 -> else 삭제
    if body_has_target:
      return updated.with_changes(orelse=None)
    # Case 2: else에 타겟 있음 -> 본문은 그저 거쳐가는 길 -> pass로 축소
    else:
      return updated.with_changes(
        body=cst.IndentedBlock(
          body=[
            cst.SimpleStatementLine([cst.Pass()])
          ]
        )
      )

  def leave_For(self, original: cst.For, updated: cst.For) -> cst.For:
    return self._handle_loop(updated)

  def leave_While(self, original: cst.While, updated: cst.While) -> cst.While:
    return self._handle_loop(updated)

  def leave_Try(self, original: cst.Try, updated: cst.Try) -> cst.Try:
    raise NotImplementedError(
      f"TruncateExecutionFlowTransformer.leave_Try: "
      f"truncation of try/except blocks is not implemented"
    )

  def leave_Match(self, original: cst.Match, updated: cst.Match) -> cst.Match:
    raise NotImplementedError(
      f"TruncateExecutionFlowTransformer.leave_Match: "
      f"truncation of match/case blocks is not implemented"
    )


def truncate_execution_flow(text: str, function_call_name: str):
  tree = cst.parse_module(text)
  transformer = TruncateExecutionFlowTransformer(
    function_call_name
  )
  tree = tree.visit(transformer)
  return tree.code


class TruncateExecutionFlowByLineTransformer(cst.CSTTransformer):

  METADATA_DEPENDENCIES = (PositionProvider,)

  def __init__(self, after: int):
    self.after = after

  def _contains_target(self, original: cst.CSTNode) -> bool:
    pos = self.get_metadata(PositionProvider, original)
    return pos.start.line <= self.after <= pos.end.line

  def _slice_statement_list(
      self, 
      original_stmts: Sequence[cst.BaseStatement], 
      updated_stmts: Sequence[cst.BaseStatement]
  ) -> Sequence[cst.BaseStatement]:
    """
    메타데이터는 original 트리에서만 조회 가능하므로, 
    original과 updated를 zip으로 묶어서 순회합니다.

    stmts 중에서 target을 포함하는 "첫 문장"까지 살리고,
    그 뒤 문장들은 제거.
    만약 어떤 문장도 target을 포함하지 않으면 그대로 반환.
    """
    new_stmts: list[cst.BaseStatement] = []
    found = False
    for original_stmt, updated_stmt in zip(original_stmts, updated_stmts):
      if found:
        break
      new_stmts.append(updated_stmt)
      if self._contains_target(original_stmt):
        found = True
    return tuple(new_stmts)

  def _slice_small_statements(
    self, 
    original_stmts: Sequence[cst.BaseSmallStatement],
    updated_stmts: Sequence[cst.BaseSmallStatement]
  ) -> Sequence[cst.BaseSmallStatement]:
    new_stmts = []
    found = False
    for original_stmt, updated_stmt in zip(original_stmts, updated_stmts):
      if found:
        break
      new_stmts.append(updated_stmt)
      if self._contains_target(original_stmt):
        found = True
    return tuple(new_stmts)

  def _slice_suite(self, original_suite: cst.BaseSuite, updated_suite: cst.BaseSuite) -> cst.BaseSuite:
    """
    IndentedBlock 내부의 body(문장 리스트)를 슬라이싱.
    SimpleStatementSuite(if cond: a(); b()) 같은 경우는
    문장 단위로 자르기 애매하니, 우선 그대로 둔다.
    필요하면 여기서 더 세밀하게 자를 수 있음.
    """
    if isinstance(original_suite, cst.IndentedBlock) and isinstance(updated_suite, cst.IndentedBlock):
      return updated_suite.with_changes(
        body=self._slice_statement_list(
          original_suite.body, updated_suite.body
        )
      )
    elif isinstance(original_suite, cst.SimpleStatementSuite) and isinstance(updated_suite, cst.SimpleStatementSuite):
      raise NotImplementedError(
        f"TruncateExecutionFlowByLineTransformer._handle_suite: "
        f"SimpleStatementSuite truncation is not implemented (e.g., 'if cond: a(); b()')"
      )
    else:
      return updated_suite

  def leave_Module(self, original: cst.Module, updated: cst.Module) -> cst.Module:
    new_body = self._slice_statement_list(original.body, updated.body)
    return updated.with_changes(body=new_body)

  def leave_IndentedBlock(
    self, original: cst.IndentedBlock, updated: cst.IndentedBlock
  ) -> cst.IndentedBlock:
    # 모든 블록(함수, for, while, class 등) 내의 문장을 슬라이싱
    new_body = self._slice_statement_list(original.body, updated.body)
    return updated.with_changes(body=new_body)

  def leave_If(self, original: cst.If, updated: cst.If) -> cst.If:
    # 1. Body(then-block) 검사
    then_has_target = self._contains_target(original.body)
    # 2. Orelse(else/elif block) 검사
    # 중요: orelse.body만 보는 게 아니라 orelse 서브트리 전체를 봐야 
    # 중첩된 elif/else 안쪽의 타겟도 찾을 수 있음.
    orelse_has_target = False
    if updated.orelse is not None:
      orelse_has_target = self._contains_target(original.orelse)
    # 둘 다 있음
    if then_has_target and orelse_has_target:
      return updated
    # 둘 다 없음
    if (not then_has_target) and (not orelse_has_target):
      return updated
    # then에만 있음
    if then_has_target:
      return updated.with_changes(orelse=None)
    # else/elif에만 있음
    else:
      return updated.with_changes(
        body=cst.IndentedBlock(
          body=[
            cst.SimpleStatementLine([cst.Pass()])
          ]
        )
      )

  def leave_Else(self, original: cst.Else, updated: cst.Else) -> cst.Else:
    # Else 블록 자체도 내부 문장을 슬라이싱해서 정리된 상태로 만듦
    new_body = self._slice_suite(original.body, updated.body)
    return updated.with_changes(body=new_body)

  def _handle_loop(self, original, updated):
    body_has_target = self._contains_target(original.body)
    orelse_has_target = False
    if updated.orelse is not None:
      orelse_has_target = self._contains_target(original.orelse)
    # 둘 다 없음
    if (not body_has_target) and (not orelse_has_target):
      return updated
    # Case 1: 본문에 타겟 있음 -> 루프 정상 종료 불가 -> else 삭제
    if body_has_target:
      return updated.with_changes(orelse=None)
    # Case 2: else에 타겟 있음 -> 본문은 그저 거쳐가는 길 -> pass로 축소
    else:
      return updated.with_changes(
        body=cst.IndentedBlock(
          body=[
            cst.SimpleStatementLine([cst.Pass()])
          ]
        )
      )

  def leave_For(self, original: cst.For, updated: cst.For) -> cst.For:
    return self._handle_loop(original, updated)

  def leave_While(self, original: cst.While, updated: cst.While) -> cst.While:
    return self._handle_loop(original, updated)

  def leave_Try(self, original: cst.Try, updated: cst.Try) -> cst.Try:
    raise NotImplementedError(
      f"TruncateExecutionFlowByLineTransformer.leave_Try: "
      f"truncation of try/except blocks is not implemented (after line {self.after})"
    )

  def leave_Match(self, original: cst.Match, updated: cst.Match) -> cst.Match:
    raise NotImplementedError(
      f"TruncateExecutionFlowByLineTransformer.leave_Match: "
      f"truncation of match/case blocks is not implemented (after line {self.after})"
    )


def truncate_execution_flow_by_line(text: str, after: int) -> str:
  tree = cst.parse_module(text)
  tree = cst.MetadataWrapper(tree)
  transformer = TruncateExecutionFlowByLineTransformer(after)
  tree = tree.visit(transformer)
  return tree.code


class CleanDeadBranchesTransformer(cst.CSTTransformer):

  def _is_meaningless(self, body: cst.BaseSuite) -> bool:
    """
    블록이 비어있거나 'pass', '...' 만 포함하는지 확인
    """
    is_pass = lambda stmt: matchers.matches(stmt, matchers.Pass())
    is_ellipsis = lambda stmt: (
      matchers.matches(
        stmt,
        matchers.Expr(
          value=matchers.Ellipsis()
        )
      )
    )
    if isinstance(body, cst.SimpleStatementSuite):
      # 한 줄짜리: if A: pass
      for stmt in body.body:
        if is_pass(stmt) or is_ellipsis(stmt):
          continue
        return False
      return True
    elif isinstance(body, cst.IndentedBlock):
      # 여러 줄 블록
      for stmt in body.body:
        if isinstance(stmt, cst.SimpleStatementLine):
          # pass나 ... 인지 확인
          if any(is_pass(s) or is_ellipsis(s) for s in stmt.body):
            continue
        # 의미 있는 코드가 하나라도 있으면 False
        return False
      return True
    return False

  def _negate_condition(
    self, 
    test_node: cst.BaseExpression
  ) -> cst.BaseExpression:
    """
    조건을 반전시킴 (A -> not A)
    """
    # 이미 not이 있으면 벗겨낼 수도 있지만(최적화), 안전하게 not (...)으로 감쌉니다.
    # 괄호 처리를 위해 ParenthesizedExpression을 고려할 수도 있지만,
    # LibCST의 UnaryOperation은 우선순위를 알아서 처리해주진 않으므로
    # 복잡한 식은 괄호로 감싸는 것이 안전합니다.
    if (
      isinstance(test_node, cst.UnaryOperation) and 
      isinstance(test_node.operator, cst.Not)
    ):
      return test_node.expression
    else:
      if test_node.lpar:
        parenthesized_node = test_node
      else:
        parenthesized_node = test_node.with_changes(
          lpar=[cst.LeftParen()], rpar=[cst.RightParen()]
        )
      return cst.UnaryOperation(
        operator=cst.Not(), 
        expression=parenthesized_node
      )

  def leave_Else(
    self, 
    original: cst.Else, 
    updated: cst.Else
  ) -> cst.Else | cst.RemovalSentinel:
    """
    Else 블록이 의미 없다면(pass), 노드 자체를 삭제합니다.
    이렇게 하면 부모 If의 orelse 필드는 None이 됩니다.
    """
    if self._is_meaningless(updated.body):
      return cst.RemoveFromParent()
    return updated

  def leave_If(
    self, 
    original: cst.If, 
    updated: cst.If
  ) -> cst.If | cst.RemovalSentinel:
    # Body에 내용이 있는 경우
    # leave_Else 덕분에, 의미 없는 Else는 이미 사라진 상태입니다.
    # 따라서 여기서 별도로 orelse를 검사하거나 지울 필요가 없습니다. (자동 처리됨)
    if not self._is_meaningless(updated.body):
      return updated
    else:
      # Body도 비고, Else도 없음(또는 지워짐) -> If문 전체 삭제
      if updated.orelse is None:
        return cst.RemoveFromParent()
      # Body는 비었는데, Else/Elif는 내용이 있음 -> 조건 반전 (Inversion)
      else:
        new_test = self._negate_condition(updated.test)
        # else인 경우: else의 본문을 그대로 가져옴
        if isinstance(updated.orelse, cst.Else):
          new_body = updated.orelse.body
        # elif인 경우: IndentedBlock으로 감싸서 본문으로 만듦
        else:
          new_body = cst.IndentedBlock(body=[updated.orelse])
        return updated.with_changes(
          test=new_test, 
          body=new_body, 
          orelse=None
        )


def clean_dead_branches(text: str):
  tree = cst.parse_module(text)
  transformer = CleanDeadBranchesTransformer()
  tree = tree.visit(transformer)
  return tree.code


class FunctionCallNameTransformer(cst.CSTTransformer):

  def __init__(self, old_name: str, new_name: str):
    self.old_name = old_name
    self.new_name = new_name

  def leave_Call(
    self, 
    original: cst.Call, 
    updated: cst.Call
  ) -> cst.BaseExpression:
    if get_full_name_for_node(original.func) == self.old_name:
      return updated.with_changes(
        func=cst.parse_expression(self.new_name)
      )
    return updated


def transform_function_call_name(text: str, old_name: str, new_name: str):
  tree = cst.parse_module(text)
  transformer = FunctionCallNameTransformer(old_name, new_name)
  tree = tree.visit(transformer)
  return tree.code


class SetFunctionCallKwargsTransformer(cst.CSTTransformer):
  def __init__(self, target: str, kwargs: list[tuple[str, str]]):
    self.target = target
    self.kwargs = kwargs

  def leave_Call(self, original_node: cst.Call, updated_node: cst.Call) -> cst.Call:
    # 1. 타겟 함수인지 확인
    if get_full_name_for_node(original_node.func) != self.target:
      return updated_node
    # 2. 새로운 인자(Arg) 리스트 생성
    new_arguments = []
    for keyword, expr in self.kwargs:
      # 키워드 인자 생성 (key=value)
      new_arguments.append(
        cst.Arg(
          keyword=cst.Name(keyword),
          value=cst.parse_expression(expr),
          equal=cst.AssignEqual(
            whitespace_before=cst.SimpleWhitespace(""),
            whitespace_after=cst.SimpleWhitespace("")
          )
        )
      )
    # 3. 기존 args를 모두 버리고 교체
    return updated_node.with_changes(args=new_arguments)


def set_function_call_kwargs(text: str, target: str, kwargs: list[tuple[str, str]]) -> str:
  tree = cst.parse_module(text)
  transformer = SetFunctionCallKwargsTransformer(target, kwargs)
  tree = tree.visit(transformer)
  return tree.code


class PositionalToKeywordTransformer(cst.CSTTransformer):

  def __init__(self, target: str, keywords: list[str]):
    self.target = target
    self.keywords = keywords

  def leave_Call(
    self, 
    original: cst.Call, 
    updated: cst.Call
  ) -> cst.BaseExpression:
    # 1. 함수 이름 확인
    if get_full_name_for_node(original.func) != self.target:
      return updated
    # 2. 인자 순회
    new_arguments = []
    for i, argument in enumerate(updated.args):
      # (A) 이미 Keyword Argument인 경우 -> 패스
      if argument.keyword is not None:
        new_arguments.append(argument)
        continue
      # (B) Starred Argument (*args, **kwargs)인 경우 -> 패스
      # libcst에서 star가 빈 문자열("")이 아니면 * 또는 ** 가 붙은 것임
      if argument.star != "":
        new_arguments.append(argument)
        continue
      # (C) 변환 로직
      # 키워드 리스트가 인자 개수보다 짧은 경우 -> 그냥 둠
      if i >= len(self.keywords):
        new_arguments.append(argument)
      # 현재 인덱스(i)에 해당하는 키워드가 리스트에 있는지 확인
      else:
        # 기존 인자(arg)에 keyword와 equal 속성을 추가하여 새 노드 생성
        new_arguments.append(
          argument.with_changes(
            keyword=cst.Name(self.keywords[i]),
            equal=cst.AssignEqual(
              whitespace_before=cst.SimpleWhitespace(""), # a=b (공백 없음)
              whitespace_after=cst.SimpleWhitespace("")
            )
          )
        )
    return updated.with_changes(args=new_arguments)


def assure_function_call_kwargs(text: str, target: str, keywords: list[str]) -> str:
  tree = cst.parse_module(text)
  transformer = PositionalToKeywordTransformer(target, keywords)
  tree = tree.visit(transformer)
  return tree.code


def is_function_call(text: str, name: str | None = None):
  node = cst.parse_expression(text.strip())
  if not isinstance(node, cst.Call):
    return False
  if name is None:
    return True
  return (name == get_full_name_for_node(node))


# def get_function_call_arguments(text: str):
#   """
#   단일 함수 호출 문자열에서 인자들을 추출합니다.
  
#   Returns:
#       List of (keyword, value_code)
#       - Positional Argument: keyword is None
#       - Keyword Argument: keyword is str
#       - value_code: The raw source code string of the argument value
#   """
#   # 1. 표현식 파싱
#   node = cst.parse_expression(text.strip())
#   # 2. 함수 호출인지 확인
#   if not is_function_call(text):
#     raise
#   arguments = []
#   for argument in node.args:
#     # 3. 키워드 추출
#     keyword = argument.keyword
#     if keyword is not None:
#       keyword = keyword.value

#     # 4. 값(Value)을 소스 코드 문자열로 변환
#     # LibCST 노드를 다시 코드로 변환하기 위해 임시 모듈 래퍼를 사용합니다.
#     # (단독 노드에 대한 .to_code() 메서드가 없으므로 이 방식이 표준입니다)
#     wrapper = cst.Module(
#         body=[cst.SimpleStatementLine(body=[cst.Expr(value=arg.value)])]
#     )
#     value_code = wrapper.code.strip()
    
#     arguments.append((keyword, value_code))

#     return arguments


class AfterDef(BaseModel):
  ...


class AfterCall(BaseModel):
  name: str
  nth: int = 1


class InsertCodeTransformer(cst.CSTTransformer):

  def __init__(self, code: str, position: AfterDef | AfterCall):
    tree = cst.parse_module(code)
    self.inserted_stmts = list(tree.body)
    # [핵심 로직] 상단 주석(Header)이 있다면 첫 번째 문장의 머리 위(leading_lines)로 옮김
    if tree.header and self.inserted_stmts:
      first_stmt = self.inserted_stmts[0]
      # 기존 leading_lines 앞에 header(주석이 포함된 EmptyLine들)를 붙임
      new_leading_lines = list(tree.header) + list(first_stmt.leading_lines)
      self.inserted_stmts[0] = first_stmt.with_changes(leading_lines=new_leading_lines)
    elif tree.header:
        # body에 들어갈 수 있는 최소 단위인 'pass' 문을 생성하여 주석을 담습니다.
        pass_stmt = cst.SimpleStatementLine(
          body=[cst.Pass()],
          leading_lines=tree.header  # 여기에 주석을 넣음
        )
        self.inserted_stmts = [pass_stmt]
    self.position = position
    self.call_count = 0

  def leave_FunctionDef(self, original, updated):
    # 기존 바디 앞에 새 코드 리스트를 '이어 붙임(concatenation)'
    if isinstance(self.position, AfterDef):
      return updated.with_changes(
        body=updated.body.with_changes(
          body=(
            list(self.inserted_stmts) + 
            list(updated.body.body)
          )
        )
      )
    return updated

  def leave_IndentedBlock(self, original, updated):
    if not isinstance(self.position, AfterCall):
      return updated
    new_body = []
    for stmt in updated.body:
      new_body.append(stmt)  # 원래 문장 추가
      if isinstance(stmt, cst.SimpleStatementLine):
        for call in matchers.findall(stmt, matchers.Call()):
          if get_full_name_for_node(call.func) == self.position.name:
            self.call_count += 1
            if self.call_count == self.position.nth:
              new_body.extend(self.inserted_stmts)
    return updated.with_changes(body=new_body)


class ReplaceNodeTransformer(cst.CSTTransformer):
  def __init__(self, old, new): self.old = old; self.new = new
  def on_leave(self, original, updated): return self.new if original == self.old else updated


def insert_code(
  text: str, 
  function_name: str, 
  position: AfterDef | AfterCall,
  code: str, 
):
  # find function def node
  tree = cst.parse_module(text)
  visitor = FunctionDefVisitor([function_name])
  tree.visit(visitor)
  function_def_node = visitor.function_defs.get(function_name, None)
  if function_def_node is None:
    raise ValueError(
      f"insert_code: function '{function_name}' not found in the provided code. "
      f"Available functions: {list(visitor.function_defs.keys())}"
    )
  # insert code to function def
  transformer = InsertCodeTransformer(code, position)
  transformed_function_def_node = function_def_node.visit(transformer)
  # replace
  return tree.visit(
    ReplaceNodeTransformer(
      old=function_def_node,
      new=transformed_function_def_node
    )
  ).code


class PutCodeTransformer(cst.CSTTransformer):

  METADATA_DEPENDENCIES = (PositionProvider,)

  def __init__(self, where: int, code: str):
    tree = cst.parse_module(code)
    self.new = list(tree.body)
    if tree.header:
      # 기존 leading_lines 앞에 header(주석이 포함된 EmptyLine들)를 붙임
      self.new[0] = self.new[0].with_changes(
        leading_lines=[*tree.header, *self.new[0].leading_lines])
    self.where = where
    self.firstline = None
    self.done = False
    self.pass_leading_lines = True

  def visit_FunctionDef(self, node: cst.FunctionDef) -> bool:
    assert self.firstline is None, "PutCodeTransformer.visit_FunctionDef: nested function defs not supported (firstline already set)"
    assert isinstance(node.body, cst.IndentedBlock), f"PutCodeTransformer.visit_FunctionDef: expected IndentedBlock body, got {type(node.body).__name__}"
    assert len(node.body.body) > 0, "PutCodeTransformer.visit_FunctionDef: function body is empty"
    meta = self.get_metadata(PositionProvider, node)
    self.firstline = meta.start.line
    return True

  def leave_FunctionDef(self, original, updated):
    assert self.firstline is not None, "PutCodeTransformer.leave_FunctionDef: firstline was never set — visit_FunctionDef not called"
    if not self.done:
      self.done = True
      body = updated.body
      return updated.with_changes(
        body=body.with_changes(body=[*body.body, *self.new])
      )
    return updated

  def maybe_put(self, original, updated):
    assert self.firstline is not None, "PutCodeTransformer.maybe_put: firstline was never set — visit_FunctionDef not called"
    if not self.done:
      meta = self.get_metadata(PositionProvider, original)
      line = meta.end.line - self.firstline + 1
      if line >= self.where:
        self.done = True
        new = self.new
        if self.pass_leading_lines:
          new[0] = new[0].with_changes(leading_lines=[*updated.leading_lines, *new[0].leading_lines])
          updated = updated.with_changes(leading_lines=[])
        return cst.FlattenSentinel([*new, updated])
    return updated

  def leave_SimpleStatementLine(self, original, updated):
    return self.maybe_put(original, updated)

  def leave_BaseCompoundStatement(self, original, updated):
    return self.maybe_put(original, updated)


def put_code(defn: str, where: int, code: str) -> str:
  tree = MetadataWrapper(cst.parse_module(defn))
  transformer = PutCodeTransformer(where, code)
  tree = tree.visit(transformer)
  return tree.code


class ProducerInfo(BaseModel):
  function_name: str
  variable: str

class ConsumerInfo(BaseModel):
  function_name: str
  parameter: str | int

class DataFlow(BaseModel):
  producer: ProducerInfo
  consumer: ConsumerInfo


class DataFlowTracker(cst.CSTVisitor):
  def __init__(self):
    # 변수명 -> 출처 정보 (Source Info) 매핑
    # 예: {'token': {'type': 'call', 'name': 'get_token'}}
    self.vars: dict[str, Any] = {}
    # 최종 발견된 흐름 (Flows)
    # 예: [{'source': 'get_token', 'consumer': 'api.call', 'param': 'token'}]
    self.flows: list[dict[str, Any]] = []

  def visit_Assign(self, node: cst.Assign) -> None:
    """
    할당문 추적:
    1. var = func()  (New Source)
    2. var2 = var1   (Alias Propagation)
    """
    if len(node.targets) != 1:
      raise NotImplementedError(
        f"ReturnToPassFlowVisitor.visit_Assign: multi-target assignment "
        f"(e.g., unpacking) with {len(node.targets)} targets is not supported"
      )

    # Target이 단순 변수일 때만 처리
    lhs = node.targets[0].target
    if not matchers.matches(lhs, matchers.Name()):
      return
    
    lhs = lhs.value
    rhs = node.value
    # Case 1: 함수 호출의 결과를 할당 (Source)
    if matchers.matches(rhs, matchers.Call()):
      func_name = get_full_name_for_node(rhs.func)
      if func_name:
        self.vars[lhs] = {
          "origin_type": "function_call",
          "origin_name": func_name
        }
    # Case 2: 다른 변수를 할당 (Aliasing / Copy)
    elif matchers.matches(rhs, matchers.Name()):
      var_name = rhs.value
      # 원본 변수가 우리가 추적 중인 변수라면, 정보를 복사해옴
      if var_name in self.vars:
        self.vars[lhs] = self.vars[var_name]

  def visit_Call(self, node: cst.Call) -> None:
    """
    소비처 추적: func(arg=var)
    """
    consumer_name = get_full_name_for_node(node.func)
    if not consumer_name:
      return
    for i, argument in enumerate(node.args):
      # 인자 값이 변수인지 확인
      if matchers.matches(argument.value, matchers.Name()):
        var_name = argument.value.value
        # 추적 중인 변수가 인자로 쓰였는지 확인
        if var_name in self.vars:
          info = self.vars[var_name]
          # 파라미터 이름 추출 (Keyword arg면 이름, Positional이면 인덱스)
          if argument.keyword:
            param_name = argument.keyword.value
          else:
            param_name = i
          # 흐름 기록
          self.flows.append(
            DataFlow(
              producer=ProducerInfo(
                function_name=info["origin_name"], # 누가 만들었나
                variable=var_name,                 # 매개체 변수명
              ),
              consumer=ConsumerInfo(
               function_name=consumer_name, # 누가 썼나
               parameter=param_name,        # 어떤 구멍으로 들어갔나
              )
            )
          )


def return_to_pass_flow(code: str):
  tree = cst.parse_module(code)
  visitor = DataFlowTracker()
  tree.visit(visitor)
  return visitor.flows


class RemoveFunctionCallArgumentsTransformer(cst.CSTTransformer):

  def __init__(self, targets: set[str]):
    self.targets = targets

  def targets_contain_same_syntax(self, code):
    for target in self.targets:
      if is_same_syntax(target, code):
        return True
    return False

  def leave_Call(self, original: cst.Call, updated: cst.Call) -> cst.Call:
    new_arguments = []
    for argument in updated.args:
      if not (
        self.targets_contain_same_syntax(
          code=cst.Module([]).code_for_node(argument.value)
        )
      ):
        new_arguments.append(argument)
    return updated.with_changes(args=new_arguments)


def remove_function_call_arguments(code: str, targets: list[str]) -> str:
  tree = cst.parse_module(code)
  # Set으로 변환하여 검색 속도 향상
  transformer = RemoveFunctionCallArgumentsTransformer(targets)
  tree = tree.visit(transformer)
  return tree.code


class ReturnAsExceptionTransformer(cst.CSTTransformer):

  def __init__(self, exception_cls: str, include_name: bool = False):
    self.exception_cls = exception_cls
    self.include_name = include_name
    self._func_name: str | None = None

  def visit_FunctionDef(self, node):
    if self._func_name is None:
      self._func_name = node.name.value
    return True

  def raise_node(self, return_value_node):
    args = [
      cst.Arg(value=return_value_node),
      cst.Arg(
        keyword=cst.Name("return_value_type"),
        value=cst.Call(
          func=cst.Name("type"),
          args=[
            cst.Arg(value=return_value_node)
          ]
        )
      )
    ]
    if self.include_name and self._func_name is not None:
      args.append(
        cst.Arg(
          keyword=cst.Name("helper_name"),
          value=cst.SimpleString(repr(self._func_name)),
        )
      )
    return cst.Raise(
      exc=cst.Call(
        func=cst.Name(self.exception_cls),
        args=args,
      )
    )

  def leave_Return(self, original, updated):
    return_value = updated.value or cst.Name("None")
    return self.raise_node(return_value)

  def leave_FunctionDef(self, original, updated):
    body = updated.body
    return updated.with_changes(
      body=body.with_changes(
        body=(
          list(body.body) + [
            cst.SimpleStatementLine(
              body=[
                self.raise_node(cst.Name("None"))
              ]
            )
          ]
        )
      )
    )


def return_as_exception(
  function_code: str,
  exception_cls: str = "ReturnAsException",
  include_name: bool = False,
):
  tree = cst.parse_module(function_code)
  transformer = ReturnAsExceptionTransformer(exception_cls, include_name=include_name)
  tree = tree.visit(transformer)
  return tree.code


class ReplaceApiParamTransformer(cst.CSTTransformer):

  def __init__(self, app_name: str, api_name: str, param_name: str, new_value_code: str):
    self.app_name = app_name
    self.api_name = api_name
    self.param_name = param_name
    self.new_value_code = new_value_code

  def leave_Call(self, original, updated):
    func = updated.func
    if (
      isinstance(func, cst.Attribute)
      and isinstance(func.value, cst.Name)
      and func.value.value == self.app_name
      and func.attr.value == self.api_name
    ):
      new_args = []
      for arg in updated.args:
        if arg.keyword and arg.keyword.value == self.param_name:
          arg = arg.with_changes(value=cst.parse_expression(self.new_value_code))
        new_args.append(arg)
      return updated.with_changes(args=new_args)
    return updated


def replace_api_param(
  function_code: str,
  app_name: str,
  api_name: str,
  param_name: str,
  new_value_code: str,
) -> str:
  tree = cst.parse_module(function_code)
  transformer = ReplaceApiParamTransformer(app_name, api_name, param_name, new_value_code)
  tree = tree.visit(transformer)
  return tree.code


import libcst as cst

class SaveVariablesTransformer(cst.CSTTransformer):
  def __init__(self, target_func_name: str = "save_strictly_observed_variables"):
    self.target_func_name = target_func_name

  def get_save_stmt(self):
    """삽입할 `save_strictly_observed_variables()` 호출 노드를 생성합니다."""
    return cst.SimpleStatementLine(
      body=[
        cst.Expr(
          value=cst.Call(
            func=cst.Name(self.target_func_name),
            args=[]
          )
        )
      ]
    )

  def leave_SimpleStatementLine(self, original, updated):
    """한 줄(Line) 내에 return 문이 포함되어 있는지 확인하고, 그 앞에 함수를 삽입합니다."""
    has_return = any(isinstance(stmt, cst.Return) for stmt in updated.body)
    if has_return:
      # 기존 return 라인 앞에 save 함수 호출 라인을 추가하여 FlattenSentinel로 반환
      return cst.FlattenSentinel([
        self.get_save_stmt(),
        updated
      ])
    return updated

  def leave_FunctionDef(self, original, updated):
    """명시적인 return 없이 함수가 종료되는 경우를 위해 함수의 제일 마지막에도 삽입합니다."""
    body = updated.body
    return updated.with_changes(
      body=body.with_changes(
        body=(
          list(body.body) + [
            # cst.SimpleStatementLine(
              # body=[
                self.get_save_stmt()
              # ]
            # )
          ]
        )
      )
    )


def save_before_return(function_code: str, target_func_name: str = "save_strictly_observed_variables"):
  """코드 문자열을 받아 변환된 코드 문자열을 반환하는 헬퍼 함수"""
  tree = cst.parse_module(function_code)
  transformer = SaveVariablesTransformer(target_func_name)
  tree = tree.visit(transformer)
  try:
    return tree.code
  except:
    print(function_code)
    raise


class FunctionEntryTrackerTransformer(cst.CSTTransformer):
  """함수의 맨 처음에 진입 추적 함수(get_...)를 삽입합니다."""
  
  def __init__(self, target_func_name: str = "get_strictly_observed_variables",
        assign_target_name: str = "__caller_contexts__"):
    self.target_func_name = target_func_name
    self.assign_target_name = assign_target_name

  def _create_call_stmt(self):
    # """삽입할 `save_strictly_observed_variables()` 호출 노드를 생성합니다."""
    # return cst.SimpleStatementLine(
    #   body=[
    #     cst.Expr(
    #       value=cst.Call(
    #         func=cst.Name(self.target_func_name),
    #         args=[]
    #       )
    #     )
    #   ]
    # )
    """특정 변수에 함수 호출 결과를 할당하는 Statement 노드를 생성합니다.
       예: target_name = func_name()
    """
    return cst.SimpleStatementLine(
        body=[
            cst.Assign(
                targets=[
                    cst.AssignTarget(
                        target=cst.Name(self.assign_target_name)
                    )
                ],
                value=cst.Call(
                    func=cst.Name(self.target_func_name),
                    args=[]
                )
            )
        ]
    )

  def leave_FunctionDef(self, original, updated):
    body = updated.body
    # 함수 바디의 맨 앞에만 추가
    new_body = [self._create_call_stmt()] + list(body.body)
    
    return updated.with_changes(
      body=body.with_changes(
        body=new_body
      )
    )


def save_callers_on_entry(function_code: str, target_func_name: str = "get_strictly_observed_variables", assign_target_name: str = "_caller_contexts_"):
  """코드 문자열을 받아 변환된 코드 문자열을 반환하는 헬퍼 함수"""
  tree = cst.parse_module(function_code)
  transformer = FunctionEntryTrackerTransformer(target_func_name, assign_target_name)
  tree = tree.visit(transformer)
  return tree.code


def parse_fn_name(defn: str):
  tree = cst.parse_module(defn)
  assert len(tree.body) == 1, f"parse_fn_name: expected exactly 1 top-level statement, got {len(tree.body)}"
  defn = tree.body[0]
  assert isinstance(defn, cst.FunctionDef), f"parse_fn_name: expected FunctionDef, got {type(defn).__name__}"
  return defn.name.value


def parse_fn_body(defn: str):
  tree = cst.parse_module(defn)
  assert len(tree.body) == 1, f"parse_fn_body: expected exactly 1 top-level statement, got {len(tree.body)}"
  defn = tree.body[0]
  assert isinstance(defn, cst.FunctionDef), f"parse_fn_body: expected FunctionDef, got {type(defn).__name__}"
  return cst.Module(body=defn.body.body).code.strip()


def parse_fn_params(defn: str) -> list[dict]:
  """
  source: 'def f(a: int=1, *args, b=2, **kw): ...' 같이 FunctionDef가 포함된 코드.
  반환: list[Parameter]
  """
  def _code_for_expr(
    module: cst.Module, 
    expr: cst.CSTNode | None
  ):
    if expr is None:
      return None
    return module.code_for_node(expr).strip()

  tree = cst.parse_module(defn)
  assert len(tree.body) == 1, f"parse_fn_params: expected exactly 1 top-level statement, got {len(tree.body)}"
  defn: cst.FunctionDef = tree.body[0]
  params: list[dict] = []

  def add_param(
    p: cst.Param, 
    *, 
    is_vararg: bool = False, 
    is_kwarg: bool = False
  ):
    name = p.name.value
    ann = None
    if p.annotation is not None:
      ann = _code_for_expr(tree, p.annotation.annotation)

    default = _code_for_expr(tree, p.default)
    # required 판정:
    # - 기본값 있으면 optional
    # - *args/**kwargs는 호출 시 없어도 되므로 required=False로 두는 편이 자연스러움
    required = (default is None) and (not is_vararg) and (not is_kwarg)
    params.append(
      dict(
        name=name,
        type=ann,
        required=required,
        default=default,
      )
    )

  fp = defn.params
  # posonly params (Python 3.8+)
  for p in fp.posonly_params:
    add_param(p)
  # normal params
  for p in fp.params:
    add_param(p)
  # *args
  if fp.star_arg is not None:
    # star_arg가 `Param`일 수도 있고, `MaybeSentinel.DEFAULT`일 수도 있음
    if isinstance(fp.star_arg, cst.Param):
      add_param(fp.star_arg, is_vararg=True)
    else:
      # def f(*, kwonly=...) 처럼 이름 없는 '*'는 Parameter로 만들지 않음
      pass
  # kwonly params
  for p in fp.kwonly_params:
    add_param(p)
  # **kwargs
  if fp.star_kwarg is not None:
    add_param(fp.star_kwarg, is_kwarg=True)
  return params


def find_function_call(code: str, name: str) -> list[ParsedFunctionCallCodeOutput]:
  function_calls = []
  for function_call in parse_code_function_calls(code):
    if function_call.name == name:
      function_calls.append(function_call)
  return function_calls


class FindVoidCallsVisitor(cst.CSTVisitor):

  METADATA_DEPENDENCIES = (ParentNodeProvider,)

  def __init__(self):
    self.void_calls = []

  def leave_Call(self, node: cst.Call):
    parent = self.get_metadata(ParentNodeProvider, node)
    # 1. 변수에 명시적으로 할당되는 경우 (Captured) -> 우리가 찾고자 하는 대상이 아님
    if matchers.matches(
      node=parent, 
      matcher= (
        matchers.Assign() |
        matchers.AnnAssign() |
        matchers.AugAssign() |
        matchers.NamedExpr()
      )
    ):
      return
    # 함수 이름 추출 (기존에 정의하신 함수 사용)
    func_name = get_full_name_for_node(node.func)
    # 2. 리턴값이 아예 버려지는 경우 (Discarded)
    if matchers.matches(parent, matchers.Expr()):
      self.void_calls.append({"func_name": func_name, "usage": "discarded"})
    # 3. 리턴값이 다른 곳에 직접 사용되는 경우 (Inline usage)
    else:
      # 부모 노드의 클래스 이름을 가져와서 어디에 쓰였는지(If, For, Arg, Return 등) 기록
      match type(parent):
        # 1. Control Flow & Iteration (제어문 및 루프)
        case cst.If: 
          usage = "condition of `if` statement"
        case cst.While: 
          usage = "condition of `while` statement"
        case cst.For: 
          usage = "iterable of `for` loop"
        case cst.CompFor: 
          usage = "iterable of comprehension"
        case cst.WithItem: 
          usage = "context manager in `with` statement"

        # 2. Functions & Returns (함수 및 리턴)
        case cst.Arg: 
          grandparent = self.get_metadata(ParentNodeProvider, parent)
          assert isinstance(grandparent, cst.Call), f"FindVoidCallsVisitor: expected grandparent to be Call for Arg parent, got {type(grandparent).__name__}"
          usage = f"argument of `{get_full_name_for_node(grandparent.func)}` call"
        case cst.Return: 
          usage = "return value"
        case cst.Yield: 
          usage = "yielded value"
        case cst.Call: 
          usage = "another callable"

        # # 3. Operations & Comparisons (연산 및 비교)
        # case cst.BinaryOperation: 
        #   usage = "operand in a binary operation (e.g., +, -)"
        # case cst.BooleanOperation: 
        #   usage = "operand in a boolean operation (e.g., and, or)"
        # case cst.UnaryOperation: 
        #   usage = "operand in a unary operation (e.g., not, -)"
        case cst.Comparison: 
          usage = "operand in a comparison (e.g., ==, >, in)"

        # # 4. Data Structures (데이터 구조)
        # case cst.Element: 
        #   usage = "element of a list/tuple/set"
        # case cst.DictElement: 
        #   usage = "key or value of a dictionary"

        # # 5. Accessors & Miscellaneous (접근자 및 기타)
        # case cst.Attribute: 
        #   usage = "object of an attribute access (e.g., func().attr)"
        # case cst.Subscript | cst.Index: 
        #   usage = "target or index of a subscript (e.g., func())"
        # case cst.Await: 
        #   usage = "target of an `await` expression"
        # case cst.FormattedStringExpression | cst.FormattedString: 
        #   usage = "value inside an f-string"
        # case cst.Assert: 
        #   usage = "condition of an `assert` statement"
        # case cst.Raise: 
        #   usage = "exception in a `raise` statement"
          
        # # 6. Completely discarded (아예 안 쓰이는 경우)
        # case cst.Expr:
        #   usage = "completely discarded (not assigned or used inline)"

        # 7. Fallback (그 외 예상치 못한 경우)
        case _:
          raise NotImplementedError(
            f"FindVoidCallsVisitor: unhandled parent context {type(parent).__name__} "
            f"for call to '{func_name}'"
          )
      self.void_calls.append({
        "func_name": func_name,
        "usage": usage,
      })


def find_void_calls(code: str):
  tree = cst.parse_module(code)
  tree = MetadataWrapper(tree)
  visitor = FindVoidCallsVisitor()
  tree.visit(visitor)
  return visitor.void_calls


class QualifiedNamesVisitor(cst.CSTVisitor):

  METADATA_DEPENDENCIES = (QualifiedNameProvider,)

  def __init__(self):
    self.qualified_names = {}

  def visit_Call(self, node: cst.Call):
    qualified_names = self.get_metadata(QualifiedNameProvider, node.func)
    assert len(qualified_names) <= 1, f"QualifiedNamesVisitor.visit_Call: expected at most 1 qualified name, got {len(qualified_names)} for call"
    for qualified_name in qualified_names:
      name = cst.Module([]).code_for_node(node.func)
      if name in self.qualified_names:
        assert self.qualified_names[name].source == qualified_name.source, (
          f"QualifiedNamesVisitor.visit_Call: conflicting source for '{name}' — "
          f"existing={self.qualified_names[name].source}, new={qualified_name.source}"
        )
      else:
        self.qualified_names[name] = qualified_name

  def visit_Name(self, node: cst.Name):
    qualified_names = self.get_metadata(QualifiedNameProvider, node)
    assert len(qualified_names) <= 1, f"QualifiedNamesVisitor.visit_Name: expected at most 1 qualified name, got {len(qualified_names)} for '{node.value}'"
    for qualified_name in qualified_names:
      name = node.value
      if name in self.qualified_names:
        assert self.qualified_names[name].source == qualified_name.source, (
          f"QualifiedNamesVisitor.visit_Name: conflicting source for '{name}' — "
          f"existing={self.qualified_names[name].source}, new={qualified_name.source}"
        )
      else:
        self.qualified_names[name] = qualified_name

      # source_type = qualified_name.source
      # if source_type == QualifiedNameSource.IMPORT:
      #   status = "✅ Imported"
      # elif source_type == QualifiedNameSource.BUILTIN:
      #   status = "📦 Builtin"
      # elif source_type == QualifiedNameSource.LOCAL:
      #   status = "🏠 Local"
      
      # call_repr = cst.Module([]).code_for_node(node.func)
      # print(f"Call: {call_repr:<20} | Source: {status} ({qualified_name.name})")


def get_qualified_names(code: str):
  tree = cst.parse_module(code)
  tree = MetadataWrapper(tree)
  visitor = QualifiedNamesVisitor()
  tree.visit(visitor)
  return visitor.qualified_names


class RemoveInnerFunctionsTransformer(cst.CSTTransformer):

  def __init__(self):
    super().__init__()
    self.outer_defs = []

  def visit_FunctionDef(self, node):
    self.outer_defs.append(node)
    return super().visit_FunctionDef(node)

  def leave_FunctionDef(self, original, updated):
    self.outer_defs.pop()
    if self.outer_defs:
      return cst.RemoveFromParent()
    return updated


def remove_inner_functions(code: str):
  tree = cst.parse_module(code)
  transformer = RemoveInnerFunctionsTransformer()
  tree = tree.visit(transformer)
  return tree.code


class LiftInnerFunctionsTransformer(cst.CSTTransformer):
  """
  외부 스코프(Closure)에 의존하지 않는 순수 Inner Function을 찾아
  Global Scope로 끌어올리는(Lift/Hoist) Transformer.
  """
  
  # Scope 분석을 위해 메타데이터 의존성 선언
  METADATA_DEPENDENCIES = (ScopeProvider,)

  def __init__(self):
    super().__init__()
    self.lifts = []

  def contains_nonlocal_or_global(self, defn: cst.FunctionDef):
    class NonlocalOrGlobalVisitor(cst.CSTVisitor):
      def __init__(self) -> None:
        self.found = False

      def visit_Nonlocal(self, node):
        self.found = True
        return False

      def visit_Global(self, node):
        self.found = True
        return False

    visitor = NonlocalOrGlobalVisitor()
    defn.visit(visitor)
    return visitor.found

  def free_var_accesses(self, defn: cst.FunctionDef):
    scope = self.get_metadata(ScopeProvider, defn.body)
    free_var_accesses = []
    for access in scope.accesses:
      if any(
        not (
          referent.scope is scope or
          isinstance(
            referent.scope, (
              BuiltinScope, GlobalScope
            )
          )
        ) for referent in access.referents
      ):
        free_var_accesses.append(access)
    return free_var_accesses

  def leave_FunctionDef(self, original: cst.FunctionDef, updated: cst.FunctionDef):
    if (
      self.contains_nonlocal_or_global(original) or 
      self.free_var_accesses(original)
    ):
      return updated

    self.lifts.append(updated)
    return cst.RemoveFromParent()

  def leave_Module(self, original: cst.Module, updated: cst.Module) -> cst.Module:
    return updated.with_changes(body=(self.lifts + list(updated.body)))


def lift_inner_functions(code: str, cleanup: bool = True):
  tree = cst.parse_module(code)
  tree = MetadataWrapper(tree)
  transformer = LiftInnerFunctionsTransformer()
  tree = tree.visit(transformer)

  code = tree.code
  if cleanup:
    code = remove_inner_functions(code)

  tree = cst.parse_module(code)
  visitor = FunctionDefVisitor(targets=None)
  tree.visit(visitor)
  defns = {}
  for name, defn in visitor.function_defs.items():
    defns[name] = tree.code_for_node(defn).strip()
  return defns

  extract_python_function_defs(tree.code, )
  return tree.code


class RemoveStatementsTransformer(cst.CSTTransformer):

  def __init__(self, predicate):
    self.predicate = predicate

  def leave_SimpleStatementLine(
    self,
    original: cst.SimpleStatementLine,
    updated: cst.SimpleStatementLine,
  ) -> cst.SimpleStatementLine | cst.RemovalSentinel:
    code = cst.parse_module("").code_for_node(updated).strip()
    if self.predicate(code):
      return cst.RemoveFromParent()
    return updated


def remove_statements(code: str, predicate) -> str:
  tree = cst.parse_module(code)
  transformer = RemoveStatementsTransformer(predicate)
  tree = tree.visit(transformer)
  return tree.code


class SubstituteFunctionCallTransformer(cst.CSTTransformer):

  def __init__(self, migrations: list[tuple[str, str]]):
    self.migrations = migrations

  def leave_Call(self, original_node: cst.Call, updated_node: cst.Call) -> cst.BaseExpression:
    # 1. 현재 방문 중인 함수 호출(Call) 노드를 문자열로 복원합니다.
    node_code = cst.Module([]).code_for_node(original_node)
    # 2. 저장된 마이그레이션 내역들과 순회하며 비교합니다.
    for call_site, generalized_call in self.migrations:
      try:
        if is_same_syntax(node_code, call_site):
          # 3. 구문이 일치하면, 치환할 일반화된 코드(문자열)를 파싱해서 새 AST 노드로 뱉어냅니다.
          return cst.parse_expression(generalized_call.strip())
      except SyntaxError:
        # 혹시 파싱이 불가능한 조각이라면 무시하고 넘어갑니다.
        continue
    return updated_node


def substitute_function_call(code: str, migrations: list[tuple[str, str]]):
  tree = cst.parse_module(code)
  transformer = SubstituteFunctionCallTransformer(migrations)
  tree = tree.visit(transformer)
  return tree.code


def remove_print_statements_eager(code: str):

  def remove_or_not(s):
    return s.startswith("print(")

  return remove_statements(code, remove_or_not)


class _BlockScopeChecker(cst.CSTVisitor):
  """Identify variables that are assigned only inside blocks that do NOT
  enclose the target line (i.e., "leaked" under block-scoping rules)."""

  METADATA_DEPENDENCIES = (ParentNodeProvider, PositionProvider)

  def __init__(self, target_vars: list[str], target_line: int):
    super().__init__()
    self.target_vars = set(target_vars)
    self.target_line = target_line
    self.target_block = None
    self.assignment_blocks: dict[str, list] = {v: [] for v in target_vars}
    self.leaked_variables: set[str] = set()

  def _get_innermost_block(self, node):
    current = self.get_metadata(ParentNodeProvider, node, None)
    while current is not None:
      if isinstance(current, (cst.IndentedBlock, cst.FunctionDef, cst.Module)):
        return current
      current = self.get_metadata(ParentNodeProvider, current, None)
    return None

  def _is_ancestor(self, ancestor, node):
    current = node
    while current is not None:
      if current is ancestor:
        return True
      current = self.get_metadata(ParentNodeProvider, current, None)
    return False

  def on_visit(self, node):
    if self.target_block is None:
      pos = self.get_metadata(PositionProvider, node, None)
      if pos and pos.start.line == self.target_line:
        self.target_block = self._get_innermost_block(node)
    return super().on_visit(node)

  def visit_AssignTarget(self, node):
    self._record_assignment(node.target)

  def visit_For(self, node):
    self._record_assignment(node.target, block_override=node.body)

  def _record_assignment(self, target_node, block_override=None):
    names = []
    if isinstance(target_node, cst.Name):
      names.append(target_node)
    elif isinstance(target_node, (cst.Tuple, cst.List)):
      for element in target_node.elements:
        if isinstance(element.value, cst.Name):
          names.append(element.value)
    for name_node in names:
      if name_node.value in self.target_vars:
        block = block_override if block_override else self._get_innermost_block(name_node)
        self.assignment_blocks[name_node.value].append(block)

  def leave_Module(self, original_node):
    if not self.target_block:
      return
    for var, blocks in self.assignment_blocks.items():
      if not blocks:
        continue
      if not any(self._is_ancestor(b, self.target_block) for b in blocks):
        self.leaked_variables.add(var)


def block_scope_leaked_vars(code: str, var_names: list[str], target_line: int) -> set[str]:
  """Return variable names that are NOT visible at *target_line* under block-scoping.

  *code* is the full function definition (or module).  *target_line* is
  1-based, relative to the start of *code*.  *var_names* are the candidate
  variable names to check.
  """
  tree = cst.parse_module(code)
  wrapper = MetadataWrapper(tree)
  checker = _BlockScopeChecker(var_names, target_line)
  wrapper.visit(checker)
  return checker.leaked_variables


class RemoveReturnsTransformer(cst.CSTTransformer):
  """Remove explicit return statements from a function body.

  - `return value` → replaced with just `value` as an expression statement
  - `return` (bare) → removed entirely
  """

  def leave_Return(self, original, updated):
    if updated.value is not None:
      return cst.Expr(value=updated.value)
    return cst.RemoveFromParent()


def remove_returns(code: str) -> str:
  tree = cst.parse_module(code)
  tree = tree.visit(RemoveReturnsTransformer())
  return tree.code