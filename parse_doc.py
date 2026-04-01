from __future__ import annotations

import inspect
from typing import Any, Callable

from docstring_parser import google, numpydoc, rest
from docstring_parser.common import Docstring, DocstringStyle, ParseError

import json
import re
import textwrap
from collections import OrderedDict
from typing import ClassVar, Iterator, ValuesView
from pydantic import BaseModel, ConfigDict, RootModel
import libcst as cst


class FrozenModel(BaseModel):
  model_config = ConfigDict(frozen=True)


class Parameter(FrozenModel):
  name: str
  type: str | None = None
  description: str | None = None
  required: bool = True


class Return(FrozenModel):
  name: str | None = None
  type: str | None = None
  description: str | None = None


class Fn(FrozenModel):

  indent: ClassVar[str] = "  "

  name: str
  description: str | None = None
  parameters: tuple[Parameter, ...] = ()
  returns: tuple[Return, ...] = ()
  body: str = "raise NotImplementedError()"


def parse_google_numpy_sphinx(docstring: str | None) -> Docstring:
  """Google / NumPy / Sphinx(ReST) 3개만 대상으로 자동 감지."""
  candidates: list[Docstring] = []

  for style, module in (
    (DocstringStyle.GOOGLE, google),
    (DocstringStyle.NUMPYDOC, numpydoc),
    (DocstringStyle.REST, rest),  # Sphinx-style field-list
  ):
    try:
      parsed = module.parse(docstring or "")
    except ParseError:
      continue

    parsed.style = style
    candidates.append(parsed)

  if not candidates:
    raise ValueError("Unsupported or empty docstring")

  # docstring_parser의 AUTO와 같은 아이디어:
  # 메타 정보가 가장 많이 나온 결과를 채택
  return max(candidates, key=lambda d: len(d.meta))


def _clean(text: str | None) -> str | None:
  if text is None:
    return None
  text = text.strip()
  return text or None


def _annotation_to_str(annotation: Any) -> str | None:
  if annotation is inspect.Signature.empty:
    return None
  if annotation is None:
    return "None"
  if isinstance(annotation, str):
    return annotation
  try:
    return inspect.formatannotation(annotation)
  except Exception:
    return repr(annotation)


def _annotation_node_to_str(
  annotation: cst.Annotation | None,
  *,
  module: cst.Module,
) -> str | None:
  if annotation is None:
    return None
  return module.code_for_node(annotation.annotation).strip() or None


def _param_from_cst_param(
  param: cst.Param,
  *,
  module: cst.Module,
  doc_map: dict[str, object],
  prefix: str = "",
) -> Parameter:
  name = prefix + param.name.value
  doc = doc_map.get(name) or doc_map.get(param.name.value)

  doc_type = _clean(getattr(doc, "type_name", None)) if doc else None
  doc_desc = _clean(getattr(doc, "description", None)) if doc else None
  doc_optional = bool(getattr(doc, "is_optional", False)) if doc else False

  ann_type = _annotation_node_to_str(param.annotation, module=module)
  required = param.default is None and not doc_optional

  return Parameter(
    name=name,
    type=doc_type or ann_type,
    description=doc_desc,
    required=required,
  )


def _required(
  sig_param: inspect.Parameter | None,
  *,
  is_optional: bool | None,
) -> bool:
  # signature가 있으면 그쪽을 우선 신뢰
  if sig_param is not None:
    if sig_param.kind in {
      inspect.Parameter.VAR_POSITIONAL,
      inspect.Parameter.VAR_KEYWORD,
    }:
      return False

    if sig_param.default is not inspect.Signature.empty:
      return False

    if is_optional is True:
      return False

    return True

  # docstring-only일 때는 best effort
  return not bool(is_optional)


def _returns_from_parsed(
  parsed: Docstring,
  *,
  sig: inspect.Signature | None = None,
) -> tuple[Return, ...]:
  many_returns = tuple(parsed.many_returns or ())
  if many_returns:
    return tuple(
      Return(
        name=_clean(item.return_name),
        type=_clean(item.type_name),
        description=_clean(item.description),
      )
      for item in many_returns
    )

  if parsed.returns:
    return (
      Return(
        name=_clean(parsed.returns.return_name),
        type=_clean(parsed.returns.type_name),
        description=_clean(parsed.returns.description),
      ),
    )

  # docstring에 Returns가 없으면 annotation으로 fallback
  if sig and sig.return_annotation is not inspect.Signature.empty:
    return (Return(type=_annotation_to_str(sig.return_annotation)),)

  return ()


def _returns_from_docstring(
    parsed: Docstring,
    *,
    return_annotation: str | None,
) -> tuple[Return, ...]:
  many_returns = tuple(parsed.many_returns or ())
  if many_returns:
    return tuple(
      Return(
        name=_clean(item.return_name),
        type=_clean(item.type_name),
        description=_clean(item.description),
      )
      for item in many_returns
    )

  if parsed.returns:
    return (
      Return(
        name=_clean(parsed.returns.return_name),
        type=_clean(parsed.returns.type_name) or return_annotation,
        description=_clean(parsed.returns.description),
      ),
    )

  if return_annotation:
    return (Return(type=return_annotation),)

  return ()


def fn_from_docstring(
  *,
  name: str,
  docstring: str | None,
  body: str = "raise NotImplementedError()",
) -> Fn:
  """
  raw docstring 문자열만 받아서 Fn으로 변환.
  required/type은 docstring 기준이라 best effort.
  """
  parsed = parse_google_numpy_sphinx(docstring)

  return Fn(
    name=name,
    description=_clean(parsed.description),
    parameters=tuple(
      Parameter(
        name=item.arg_name,
        type=_clean(item.type_name),
        description=_clean(item.description),
        required=_required(None, is_optional=item.is_optional),
      )
      for item in parsed.params
    ),
    returns=_returns_from_parsed(parsed),
    body=body,
  )


def fn_from_callable(
  obj: Callable[..., Any],
  *,
  body: str = "raise NotImplementedError()",
) -> Fn:
  """
  callable에서 docstring + signature + annotation을 합쳐서 Fn으로 변환.
  required/type 정확도는 이쪽이 더 좋음.
  """
  parsed = parse_google_numpy_sphinx(inspect.getdoc(obj))
  sig = inspect.signature(obj)

  documented = {item.arg_name: item for item in parsed.params}
  parameters: list[Parameter] = []

  # signature 순서를 우선
  for name, sig_param in sig.parameters.items():
    item = documented.pop(name, None)

    parameters.append(
      Parameter(
        name=name,
        type=(
          _clean(item.type_name)
          if item and item.type_name
          else _annotation_to_str(sig_param.annotation)
        ),
        description=_clean(item.description) if item else None,
        required=_required(
          sig_param,
          is_optional=item.is_optional if item else None,
        ),
      )
    )

  # docstring에는 있는데 signature에는 없는 파라미터도 뒤에 보존
  for name, item in documented.items():
    parameters.append(
      Parameter(
        name=name,
        type=_clean(item.type_name),
        description=_clean(item.description),
        required=_required(None, is_optional=item.is_optional),
      )
    )

  return Fn(
    name=obj.__name__,
    description=_clean(parsed.description),
    parameters=tuple(parameters),
    returns=_returns_from_parsed(parsed, sig=sig),
    body=body,
  )


def _is_docstring_stmt(stmt: cst.BaseStatement) -> bool:
  """
  함수 body 첫 문장이 docstring인지 판별.
  """
  if not isinstance(stmt, cst.SimpleStatementLine):
    return False
  if len(stmt.body) != 1:
    return False
  expr = stmt.body[0]
  return isinstance(expr, cst.Expr) and isinstance(
    expr.value,
    (cst.SimpleString, cst.ConcatenatedString),
  )


def _extract_body_without_docstring(
  fn_node: cst.FunctionDef,
  *,
  module: cst.Module,
) -> str:
  """
  함수 본문에서 선두 docstring은 제외하고, 나머지 body를 원래 formatting 최대한 유지해서 반환.
  """
  body = fn_node.body
  if not isinstance(body, cst.IndentedBlock):
    # one-line suite 같은 예외 케이스
    return module.code_for_node(body).strip()

  stmts = list(body.body)
  if stmts and _is_docstring_stmt(stmts[0]):
    stmts = stmts[1:]

  rendered = [module.code_for_node(stmt) for stmt in stmts]
  result = "".join(rendered).strip()

  return result or "pass"


def _find_function_def(module: cst.Module) -> cst.FunctionDef:
  """
  모듈에서 첫 번째 top-level function def를 찾음.
  필요하면 visitor로 확장 가능.
  """
  for stmt in module.body:
    if isinstance(stmt, cst.FunctionDef):
      return stmt
    if isinstance(stmt, cst.SimpleStatementLine):
      continue

  raise ValueError("No top-level function definition found")


def fn_from_function_source(source: str) -> Fn:
  module = cst.parse_module(source)
  fn_node = _find_function_def(module)

  raw_docstring = fn_node.get_docstring(clean=True)
  parsed_doc = parse_google_numpy_sphinx(raw_docstring)

  doc_params = {item.arg_name: item for item in parsed_doc.params}
  params: list[Parameter] = []

  # posonly
  for p in fn_node.params.posonly_params:
    params.append(
      _param_from_cst_param(p, module=module, doc_map=doc_params)
    )

  # normal
  for p in fn_node.params.params:
    params.append(
      _param_from_cst_param(p, module=module, doc_map=doc_params)
    )

  # *args
  if fn_node.params.star_arg and isinstance(fn_node.params.star_arg, cst.Param):
    params.append(
      _param_from_cst_param(
        fn_node.params.star_arg,
        module=module,
        doc_map=doc_params,
        prefix="*",
      )
    )

  # kwonly
  for p in fn_node.params.kwonly_params:
    params.append(
      _param_from_cst_param(p, module=module, doc_map=doc_params)
    )

  # **kwargs
  if fn_node.params.star_kwarg:
    params.append(
      _param_from_cst_param(
        fn_node.params.star_kwarg,
        module=module,
        doc_map=doc_params,
        prefix="**",
      )
    )

  return_annotation = _annotation_node_to_str(fn_node.returns, module=module)
  body = _extract_body_without_docstring(fn_node, module=module)

  return Fn(
    name=fn_node.name.value,
    description=_clean(parsed_doc.description),
    parameters=tuple(params),
    returns=_returns_from_docstring(
      parsed_doc,
      return_annotation=return_annotation,
    ),
    body=body,
  )

source = '''
def get_account_password(account_name):
    """
    Retrieves the password for a specified account name from the supervisor's password list.
    
    Args:
        account_name (str): The name of the account to retrieve the password for.
        
    Returns:
        str: The password associated with the given account name.
        
    Raises:
        NeverHappen: If the specified account name is not found in the password list.
    """
    password_list = supervisor.show_account_passwords()
    for account in password_list:
        if account["account_name"] == account_name:
            return account["password"]
    raise NeverHappen(
        f"The '{account_name}' account was not found in the password list."
    )
'''

# fn1 = fn_from_docstring(name="foo", docstring=some_docstring)
# fn2 = fn_from_callable(get_account_password)
fn2 = fn_from_function_source(source)

# print(fn1.model_dump())
print(fn2.model_dump())