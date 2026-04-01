
from __future__ import annotations

import json
import libcst as cst
import re
import textwrap
from collections import defaultdict, OrderedDict
from docstring_parser import google, numpydoc, rest
from docstring_parser.common import Docstring, DocstringStyle, ParseError
from typing import Any, ClassVar, Iterator, ValuesView, Self
from pydantic import BaseModel, ConfigDict, Field
from appworld_agents.code.my.message import *

from appworld.common.my_code_parsing import *
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


class Diagnosis(FrozenModel):
  cause: str
  fix: str
  category: str


class Fn(FrozenModel):

  indent: ClassVar[str] = "  "

  name: str
  description: str | None = None
  concise_description: str | None = None
  parameters: tuple[Parameter, ...] = ()
  returns: tuple[Return, ...] = ()
  body: str = "raise NotImplementedError()"
  assure_return_value_type: bool = False
  obtaining_missing_info: bool = False
  diagnosis: Diagnosis | None = None

  def __init__(self, name: str, **kwargs):
    super().__init__(name=name, **kwargs)

  @classmethod
  def from_code(cls, code: str, ignore_docstring: bool = False):

    print(cls)
    def from_code_wo_docstring(code):
      return cls(
        name=parse_fn_name(code),
        parameters=parse_fn_params(code),
        body=parse_fn_body(code),
      )

    if ignore_docstring:
      return from_code_wo_docstring(code)

    try:
      fn = fn_from_function_source(code)
      return fn.update(body=reindent(fn.body, indent=cls.indent))
    except ParseError:
      return from_code_wo_docstring(code)

  def update(self, **kwargs):
    if "body" in kwargs:
      assert not kwargs["body"].endswith("\n"), f"Fn.update: body must not end with newline for fn='{self.name}'"

    # model_copy() 대신, 기존 속성(self.__dict__)에
    # 새로운 kwargs를 병합하여 아예 새로 인스턴스를 만듭니다.
    # 이렇게 하면 Pydantic의 __init__이 실행되면서 dict가 Parameter 객체로 자동 변환됩니다.
    return type(self)(**{**self.__dict__, **kwargs})

  def update_from_code(self, code: str):
    parsed = fn_from_function_source(code)
    return self.update(
      body=reindent(parsed.body, indent=self.indent),
      parameters=parsed.parameters,
      returns=parsed.returns,
    )

  def header(self, with_types: bool = False):
    parameters = []
    for param in self.parameters:
      expr = param.name
      if with_types and param.type is not None:
        expr += f": {param.type}"
      parameters.append(expr)
    return_annotation = ""
    if with_types:
      return_types = []
      for r in self.returns:
        if r.type is not None:
          return_types.append(r.type)
      return_annotation = f" -> {' | '.join(return_types)}"
    return f"def {self.name}({', '.join(parameters)}){return_annotation}"

  def doc(self, fmt: str = "numpy"):

    indent = self.indent
    sections = []

    if fmt == "markdown":
      # 1. Description
      if self.description:
        sections.append(self.description)
      # 2. Arguments
      if len(self.parameters) > 0:
        lines = ["- Parameters"]
        for param in self.parameters:
          header = f"`{param.name}`"
          if param.type is not None:
            header += f" ({param.type})"
          lines.append(f"{indent}- {header}: {param.description}")
        sections.append("\n".join(lines))
      # 3. Returns
      if len(self.returns) > 0:
        lines = ["- Returns"]
        for r in self.returns:
          if r.name and r.type:
            header = f"`{r.name}` ({r.type})"
          elif r.name:
            raise
            header = f"`{r.name}`"
          elif r.type:
            header = f"({r.type})"
          else:
            assert len(self.returns) == 1, f"Fn.doc: return with no name/type must be the only return, but got {len(self.returns)} returns for fn='{self.name}'"
            header = ""
          if header:
            lines.append(f"{indent}- {header}: {r.description}")
          else:
            lines.append(f"{indent}- {r.description}")
        sections.append("\n".join(lines))
      return "\n".join(sections)
    else:  # numpy
      # 1. Description
      if self.description:
        sections.append(self.description)
      # 2. Arguments
      if len(self.parameters) > 0:
        lines = ["Parameters", "----------"]
        for param in self.parameters:
          header = param.name
          if param.type is not None:
            header += f" : {param.type}"
          lines.append(f"{header}")
          lines.append(f"{indent}{param.description}")
        sections.append("\n".join(lines))
      # 3. Returns
      if len(self.returns) > 0:
        lines = ["Returns", "-------"]
        for r in self.returns:
          if r.name and r.type:
            header = f"{r.name} : {r.type}"
          elif r.name:
            raise
            header = f"{r.name}"
          elif r.type:
            header = f"{r.type}"
          else:
            assert len(self.returns) == 1, f"Fn.doc: return with no name/type must be the only return, but got {len(self.returns)} returns for fn='{self.name}'"
            header = ""
          if header:
            lines.append(f"{header}")
            lines.append(f"{indent}{r.description}")
          else:
            lines.append(f"{r.description}")
        sections.append("\n".join(lines))
      return "\n\n".join(sections)

  def dumps(
    self,
    with_types: bool = False,
    with_docstring: bool = False,
    ctx: Ctx | None = None,
    print_locals: bool = False,
    comment_locals: bool = False,
    truncate_after: bool = False,
    comment_return: bool = True,
  ):
    body = re.sub(r'\n[ \t]*# An exception is raised by the following code\.\n', '\n', self.body)
    code = self.header(with_types=with_types) + ":"
    code += f"\n{textwrap.indent(reindent(body, indent=self.indent), prefix=self.indent)}"
    if truncate_after:
      code = truncate_execution_flow_by_line(code, after=ctx.line - ctx.firstline + 1 - 1)
    if ctx is not None:
      comments = []
      if ctx.locals and (print_locals or comment_locals):
        locals = ctx.filter_locals(fn=self)
        if print_locals:
          for var in locals:
            comments.append(f'print(f"{var.id} = {{{var.id}}}")')
        elif comment_locals:
          comments.append("# Local variables")
          for line in Ctx.dumps_locals_list(locals).split("\n"):
            comments.append(f"# {line}")
      if ctx.exc is not None and ctx.exc.tb is not None:
        comments.append("# An exception is raised by the following code.")
        # comments.append(textwrap.indent(ctx.exc.tb.message, prefix="# "))
      if ctx.exc.type == "ReturnAsException":
        return_value, return_value_type = ctx.exc.arguments
        if (self.assure_return_value_type or return_value is None) and comment_return:
          if return_value is None:
            comment = f"# About to return `{return_value}`."
          else:
            comment = f"# About to return an object of type `{return_value_type}`."
          if self.returns and self.returns[0].type is not None:
            comment += f" Expected type is {self.returns[0].type}."
          comments.append(comment)
      if comments:
        code = put_code(
          defn=code, 
          where=(ctx.line - ctx.firstline + 1 - 1), 
          code="\n".join([*comments, '"qwer1234"']).strip()
        )
        code = re.sub(r'\n\s*"qwer1234"', '', code)
        assert "qwer1234" not in code, f"Fn.dumps: internal placeholder 'qwer1234' was not fully removed from code of fn='{self.name}'"
    if with_docstring:
      docstring = self.doc()
      if docstring:
        return add_docstring_to_function(code, self.name, docstring)
    return code


class FnApiParam(Fn):

  class Consumer(FrozenModel):
    var_name: str
    app_name: str
    api_name: str
    param_name: str

  return_passed_to: Consumer



class Solution(BaseModel):

  fns: OrderedDict[str, Fn | FnApiParam]

  def __init__(self, *fns: Fn, **kwargs):
    kwargs["fns"] = OrderedDict([
      (fn.name, fn) for fn in fns
    ])
    super().__init__(**kwargs)

  def __hash__(self):
    # 딕셔너리의 (키, 값) 쌍들을 튜플로 묶어서 해시값을 만듭니다.
    # Fn이 이미 FrozenModel이므로 완벽하게 동작합니다!
    return hash(tuple(self.fns.items()))

  def __eq__(self, other):
    # 해시 충돌 시, 두 Solution이 가진 함수(Fn)들의 내용이 완전히 같은지 비교합니다.
    if isinstance(other, Solution):
      return self.fns == other.fns
    return False

  def defns(self) -> ValuesView[Fn]:
    return self.fns.values()

  def update(self, *defns: Fn | FnApiParam) -> Self:
    # 1. 기존 환경(root)을 얕은 복사하여 새로운 딕셔너리 생성
    new_root = OrderedDict(self.fns)
    # 2. 새로운 함수 정의들로 복사된 딕셔너리 업데이트
    new_root.update([
      (defn.name, defn) for defn in defns
    ])
    # 3. 새로운 환경 상태를 가진 새로운 Solution 객체 생성 후 반환 (Π[f ↦ 𝜆′])
    return type(self)(*new_root.values())

  def __getitem__(self, name: str) -> Fn:
    return self.fns[name]

  def __setitem__(self, name: str, defn: Fn):
    self.fns[name] = defn

  def __contains__(self, name: str) -> bool:
    return name in self.fns

  def get(self, name: str, default: Any = None) -> Fn | Any:
    return self.fns.get(name, default)

  def __iter__(self) -> Iterator[str]:
    return iter(self.fns)

  def __len__(self) -> int:
    return len(self.fns)

  def __repr__(self):
    return str(id(self))

  def dumps(self, current_scope: str | None = None, pause_after: str | None = None):
    def transform(defn):
      if defn.name == current_scope:
        return save_callers_on_entry(return_as_exception(defn.dumps()))
      if defn.name == pause_after:
        return save_callers_on_entry(return_as_exception(defn.dumps(), exception_cls="HelperReturnAsException", include_name=True))
      return defn.dumps()
    return render_template(
      "templates/v11/program.py",
      defns=(transform(defn) for defn in self.defns()),
    )


class Library(Solution):

  migrations: dict[str, list[tuple[str, str]]] = Field(default_factory=dict)

  # def update(self, *defns: Fn) -> Library:
  #   new_root = OrderedDict(self.fns)
  #   new_root.update([
  #     (defn.name, defn) for defn in defns
  #   ])
  #   return self.model_copy(
  #     update={"fns": new_root}
  #   )

  def add_migration(
    self, 
    scope: str, 
    call_site: str, 
    generalized_call_site: str
  ) -> Library:

    new_migrations = defaultdict(list, {k: v.copy() for k, v in self.migrations.items()})
    new_migrations[scope].append((call_site, generalized_call_site))
    return self.model_copy(
      update={"migrations": new_migrations}
    )


class Var(BaseModel):
  id: str
  value: Any
  type: str | None


class Traceback(BaseModel):

  class Frame(BaseModel):
    file: str; line: int; scope: str; code: str

  message: str
  frames: list[Frame]
  raw: str

  @classmethod
  def from_str(self, raw_traceback: str):
    # 1. 스택 프레임 파싱 (File "...", line ..., in ...)
    # Python 3.11+의 ^^^^ 라인은 무시하도록 처리

    # 이 정규표현식은 Python의 **Traceback 문자열**에서 하나의 **스택 프레임(Stack Frame)** 정보를 추출하기 위해 설계되었습니다.
    # 크게 **"헤더 부분(파일, 라인, 함수명)"**과 **"코드 부분(실제 소스코드)"** 두 덩어리로 나뉩니다. 하나씩 뜯어서 설명해 드릴게요.
    # ---
    # ### **2. 상세 토큰 설명**
    # #### **Part 1: 헤더 파싱 (File, Line, Scope)**
    # 1. `File "`
    #     * 문자열 `File "`을 그대로 찾습니다. (Traceback의 시작점)
    # 2. `(?P<file>[^"]+)`
    #     * **`(?P<name>...)`**: **Named Capture Group**입니다. 찾은 값을 `file`이라는 이름으로 저장합니다.
    #     * **`[^"]+`**: 큰따옴표(`"`)가 **아닌** 문자가 1개 이상 연속되는 구간을 찾습니다. (즉, 파일 경로 추출)
    # 3. `", line `
    #     * 문자열 `", line `을 그대로 찾습니다.
    # 4. `(?P<line>\d+)`
    #     * **`\d+`**: 숫자(digit)가 1개 이상인 구간입니다. (라인 번호 추출)
    # 5. `, in `
    #     * 문자열 `, in `을 그대로 찾습니다.
    # 6. `(?P<scope>.+?)`
    #     * **`.+?`**: 아무 문자나 1개 이상 매칭하되, **Non-greedy(최소 매칭)**하게 찾습니다.
    #     * 바로 뒤에 나오는 `\n`(줄바꿈)을 만나기 전까지만 찾아서 함수/모듈 이름을 `scope`에 저장합니다.
    # #### **Part 2: 코드 파싱 (Code)**
    # 7. `\n\s+`
    #     * **`\n`**: 줄바꿈 문자.
    #     * **`\s+`**: 공백(들여쓰기)이 1개 이상.
    #     * Traceback에서 실제 코드는 항상 다음 줄에 들여쓰기 된 상태로 나오므로 이를 처리합니다.
    # 8. `(?P<code>.+?)`
    #     * 실제 소스 코드를 `code`라는 이름으로 추출합니다.
    #     * **`.+?`**: 아무 문자나 매칭하되 최소한으로 매칭합니다. (어디까지? 바로 뒤의 **Lookahead 조건**을 만날 때까지)
    # #### **Part 3: 종료 조건 (Positive Lookahead)**
    # 이 부분이 가장 핵심입니다. **"코드가 어디서 끝나는지"**를 결정합니다.
    # 9. `(?=\n\s*File|\n\s*[^\s]+:|$)`
    #     * **`(?= ... )`**: **전방 탐색(Positive Lookahead)**입니다. "뒤에 이런 패턴이 오는지 확인만 하고, 문자를 소비(Consume)하지는 않는다"는 뜻입니다.
    #     * 즉, `code` 그룹은 **다음 세 가지 조건 중 하나**가 나오기 직전까지만 매칭됩니다.
    #     **조건 (OR 연산 `|` 로 연결됨):**
    #         1. `\n\s*File`: 다음 스택 프레임의 시작(`File "..."`)이 나올 때.
    #         2. `\n\s*[^\s]+:`: 에러 메시지의 시작(예: `Exception:` 또는 `ValueError:`)이 나올 때.
    #         3. `$`: 문자열의 끝(End of String)일 때.
    # ### **팁: `re.DOTALL**`
    # 코드에 `re.DOTALL` 플래그를 사용하셨는데, 이는 `.`이 줄바꿈 문자(`\n`)도 포함하게 만듭니다. 덕분에 `scope`나 `code` 부분에서 줄바꿈이 섞여 있어도 유연하게 잡아낼 수 있지만, 그렇기에 **Part 3의 종료 조건(Lookahead)**이 더더욱 중요해집니다. 종료 조건이 없으면 끝까지 다 잡아먹어 버리기 때문입니다.
    pattern = re.compile(
      pattern=(
        r'File "(?P<file>[^"]+)", '
        r'line (?P<line>\d+), '
        r'in (?P<scope>.+?)\n'
        r'\s+(?P<code>.+?)(?=\n\s*File|\n\s*[^\s]+:|$)'
      ),
      flags=re.DOTALL
    )
    body = raw_traceback.split("Execution failed. Traceback:")[-1]
    frames = []
    for m in pattern.finditer(body):
      file, line, scope, code = m.groups()
      frames.append(
        Traceback.Frame(
          file=file,
          line=int(line),
          scope=scope,
          code=code.split("\n")[0].strip() # 코드 부분에서 ^^^^ 같은 에러 마커 제거
        )
      )
    # 2. Exception 타입과 메시지 파싱
    # 스택 프레임들이 끝나고 나오는 마지막 부분이 에러 메시지
    # 예: "Exception: Response status code is 422:..."
    # 마지막 프레임 이후의 텍스트 찾기
    message = body[m.end():].strip()
    # if ":" in message:
    #   type, message = message.split(":", maxsplit=1)
    # else:
    #   type = "Exception"
    #   message = message
    return Traceback(
      message=message, 
      raw=raw_traceback,
      frames=(
        frame for frame in frames if not frame.scope.startswith("__")
      ), 
    )


class Exc(BaseModel):

  type: str
  arguments: tuple[Any, ...]
  tb: Traceback | None


class Ctx(BaseModel):
  # at: AfterDef | AfterCall
  scope: str
  outer_scope: str
  outer_scope_call_site: str | None = None
  locals: list[Var]
  locals_in_outer_scopes: Any
  line: int
  firstline: int
  exc: Exc | None = None

  @staticmethod
  def dumps_locals_list(locals: list[Var]) -> str:
    def dumps_value(value):
      if value is None:
        return "None"
      return json.dumps(value)
    lines = []
    for var in locals:
      lines.append(f"{var.id} = {dumps_value(var.value)}")
    return "\n".join(lines)

  def filter_locals(self, fn: Fn | None = None) -> list[Var]:
    locals = self.locals
    if fn is not None and locals:
      code = fn.header() + ":\n" + textwrap.indent(reindent(fn.body, indent=fn.indent), prefix=fn.indent)
      try:
        leaked = block_scope_leaked_vars(
          code,
          var_names=[var.id for var in locals],
          target_line=self.line - self.firstline + 1 - 1,
        )
        locals = [var for var in locals if var.id not in leaked]
      except Exception:
        pass
    return locals

  def dumps_locals(self, fn: Fn | None = None):
    return self.dumps_locals_list(self.filter_locals(fn=fn))

  def unexpected_error(self):
    return self.exc.type not in (
      "ReturnAsException",
      "HelperReturnAsException",
      "FunctionNotFound",
      "NotImplementedError",
    )

  def before_return(self):
    return self.exc.type == "ReturnAsException"

  def function_not_found(self):
    if self.exc.type == "FunctionNotFound":
      return self.exc.arguments[0]
    return None

  def helper_returned(self):
    if self.exc.type == "HelperReturnAsException":
      return self.exc.arguments[0], self.exc.arguments[2]
    return None


class Lessons(FrozenModel):

  lessons: dict[str, list[str]] = {
    "strategies_and_hard_rules": [
    ],
    "observed_facts_about_user_and_user_environment": [
    ],
    "api_common_mistakes": [
      """Many APIs return items in "pages". Make sure to run through all the pages by looping over `page_index`."""
    ],
    # "apis_to_use_for_specific_information": [
    #   """I can use the "supervisor" app to get information about the user's accounts.""",
    #   """I can use the "phone" app to get information about the user's friends and family."""
    # ],
    "others": [
    ]
  }

  def dumps(self, fmt="markdown", sections: list[str] | None = None):
    _sections = []
    for category, items in self.lessons.items():
      if sections is not None and category not in sections:
        continue
      lines = [f"## `{category}`"]
      if not items:
        lines.append("[empty]")
      else:
        for i, item in enumerate(items, 1):
          lines.append(f"{i}. {item}")
      _sections.append("\n".join(lines))
    return "\n\n".join(_sections)

  def update(self, operations: list[dict[str, str]]):
    for operation in operations:
      self.lessons[operation["section"]].append(operation["content"])


class WorkingMemory(FrozenModel):

  # observed variables until ... `ctx_by_scope[function_name]`
  ctx_by_scope: dict[str, Ctx] = dict()
  lessons: Lessons = Lessons()
  # solved_helpers[caller_name][helper_name] = Fn
  solved_helpers: dict[str, dict[str, Fn]] = dict()


class Snapshot(FrozenModel):
  
  fn: Fn
  solution: Solution
  ctx: Ctx

  def __hash__(self):
    # 오직 'fn'만을 기준으로 노드의 정체성을 결정합니다.
    # (Fn 모델이 FrozenModel이므로 hash(self.fn)이 가능합니다)
    return hash(self.fn)

  def __eq__(self, other):
    # 해시 충돌 시, fn이 같으면 완벽히 같은 노드로 취급합니다.
    if isinstance(other, Snapshot):
      return self.fn == other.fn
    return False




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
    raise ParseError("Unsupported or empty docstring")

  # docstring_parser의 AUTO와 같은 아이디어:
  # 메타 정보가 가장 많이 나온 결과를 채택
  return max(candidates, key=lambda d: len(d.meta))


def _clean(text: str | None) -> str | None:
  if text is None:
    return None
  text = text.strip()
  return text or None


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