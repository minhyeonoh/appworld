from __future__ import annotations
import json
import logging

from copy import deepcopy
from collections import defaultdict
from typing import ClassVar, TYPE_CHECKING
from pydantic import BaseModel, ConfigDict

from appworld_agents.code.my.fn import Fn, FnApiParam, Snapshot
from appworld.common.my_code_parsing import *
from appworld_agents.code.my.hashable import UidAsHash
from appworld_agents.code.my.message import *

logger = logging.getLogger("peter.actions")

if TYPE_CHECKING:
  from appworld_agents.code.my.v10 import SubAgent as MyAgent


# ------------------------------------------------------------------
# Truncation helpers
# ------------------------------------------------------------------
_TRUNCATION_MARKER = "# @@TRUNCATE_BELOW@@"


def insert_truncation_marker(code: str, ctx) -> str:
  """Insert a marker comment at the error line (ctx.line) in a function def.

  The marker goes right before the line that caused the error,
  so the LLM sees it as a boundary.
  """
  lines = code.splitlines(keepends=True)
  # ctx.line is absolute, ctx.firstline is the function's first line (+1 for decorator skip).
  # Map to 0-based index within the code string, then insert *before* the error line.
  error_line_idx = ctx.line - ctx.firstline  # 0-based index of the error line
  insert_at = error_line_idx  # insert marker before the error line
  if 0 < insert_at <= len(lines):
    target_line = lines[insert_at] if insert_at < len(lines) else lines[-1]
    indent = len(target_line) - len(target_line.lstrip())
    marker_line = " " * indent + _TRUNCATION_MARKER + "\n"
    lines.insert(insert_at, marker_line)
  return "".join(lines)


def truncate_at_marker(code: str, original_code: str | None = None) -> str:
  return code
  """Remove the marker and everything the LLM wrote after it.

  If original_code is provided, the original tail (from the marker
  position onward) is stitched back after the LLM's head.
  """
  lines = code.splitlines(keepends=True)
  for i, line in enumerate(lines):
    if _TRUNCATION_MARKER in line:
      head = "".join(lines[:i]).rstrip("\n")
      if original_code is not None:
        orig_lines = original_code.splitlines(keepends=True)
        for j, orig_line in enumerate(orig_lines):
          if _TRUNCATION_MARKER in orig_line:
            tail = "".join(orig_lines[j + 1:])
            if tail.strip():
              return head + "\n" + tail.rstrip("\n")
            break
      return head
  # No marker found — return as-is
  return code


# ------------------------------------------------------------------
# 1. Base Todo
# ------------------------------------------------------------------
class Action(UidAsHash):
  """모든 작업의 최상위 Base 클래스"""
  _agent: ClassVar[MyAgent | None] = None
  scope: str  # 작업 대상이 되는 함수명 (f)
  before_action: Action | None

  def _find_ancestor(self, cls):
    action = self
    while action is not None:
      if isinstance(action, cls):
        return action
      action = action.before_action
    return None

  def _is_gathering(self):
    """Walk ancestors: if we hit GatherContext before HotFix, we're still gathering.
    If we hit HotFix first, the sufficiency check already exited gathering."""
    action = self
    while action is not None:
      if isinstance(action, HotFix):
        return False
      if isinstance(action, GatherContext):
        return True
      action = action.before_action
    return False

  def _observed_variables(self, snapshot: Snapshot, include_inner: bool = True) -> dict[str, dict[str, dict[str, Any]]]:
    output = self.agent.world.execute("print(observed_callee_history)")
    observed_variables = {
      "inner": {},
      "outer": {},
    }
    try:
      tmp = json.loads(output).items()
    except:
      print(output)
      raise
    for inner_scope, history in tmp:
      assert len(history) == 1, f"expected exactly 1 history entry for scope '{inner_scope}', got {len(history)}"
      observed_variables["inner"][inner_scope] = history[-1]
    for outer_scope, locals in snapshot.ctx.locals_in_outer_scopes.items():
      observed_variables["outer"][outer_scope] = locals
    if not include_inner:
      observed_variables.pop("inner")
    # Remove empty entries
    for scope in list(observed_variables.keys()):
      if not observed_variables[scope]:
        observed_variables.pop(scope)
      else:
        for function_name in list(observed_variables[scope].keys()):
          if not observed_variables[scope][function_name]:
            observed_variables[scope].pop(function_name)
        if not observed_variables[scope]:
          observed_variables.pop(scope)
    return observed_variables or None

  @classmethod
  def setup_agent(cls, agent: MyAgent) -> None:
    """Action 클래스 전체가 사용할 Agent 인스턴스를 주입합니다."""
    cls._agent = agent

  # 2. 프로퍼티로 접근하기 쉽게 만듦
  @property
  def agent(self) -> MyAgent:
    if self.__class__._agent is None:
      raise RuntimeError("Agent instance is not bound to Action class.")
    return self.__class__._agent

  def __str__(self):
    return str(self.__class__)

  def generate(self, *args, **kwargs):
    return self.agent.generate(*args, **kwargs)

  def generate_with_think(self, *args, **kwargs):
    return self.agent.generate_with_think(*args, **kwargs)

  def generate_fn(self, *args, **kwargs):
    return self.agent.generate_defn(*args, **kwargs)

  def generate_function_defs_with_compound_flow(self, *args, **kwargs):
    return self.agent.generate_function_defs_with_compound_flow(*args, **kwargs)

  def ensure_no_void_calls(self, code: str, snapshot: Snapshot):
    void_calls = find_void_calls(code)
    if not void_calls:
      return code

    while void_calls:
      lines = [f"Assign the return value of the following function call{'s' if len(void_calls) > 1 else ''} to{'' if len(void_calls) > 1 else ' a'} local variable{'s' if len(void_calls) > 1 else ''}:"]
      for call in void_calls:
        if call["usage"] != "discarded":
          lines.append(f"- `{call['func_name']}` (used as {call['usage']})")
        else:
          lines.append(f"- `{call['func_name']}` (not assigned to a local variable; discarded)")
      msgs = Msgs()
      content = f"{'\n'.join(lines)}\n\n```python\n{code}\n```"
      msgs.add(role="user", content=content)
      _, code = self.generate_fn(msgs, snapshot.fn, reasoning={"effort": "none"})
      code = remove_comments(code)
      void_calls = find_void_calls(code)

    return remove_comments(code)

  def rename_existing_helpers(self, code: str, snapshot: Snapshot, max_retries: int = 3) -> str:
    before = snapshot.fn.dumps()
    for attempt in range(max_retries):
      conflicts = self.agent.existing_helpers(code, snapshot.solution, before=before)
      if not conflicts:
        return code
      lines = [f"Use different name{'s' if len(conflicts) > 1 else ''} for:"]
      for name in conflicts:
        lines.append(f"- `{name}`")
      lines.append("\nReturn single function definition.")
      msgs = Msgs()
      msgs.add(role="user", content=f"{'\n'.join(lines)}\n\n```python\n{code}\n```")
      _, code = self.generate_fn(msgs, snapshot.fn, reasoning={"effort": "none", "enabled": False})
      code = remove_comments(code)
    conflicts = self.agent.existing_helpers(code, snapshot.solution, before=before)
    assert not conflicts, f"Failed to rename existing helpers after {max_retries} retries: {conflicts}"
    return code

  def rename_existing_helpers_fns(self, fns: list[Fn], snapshot: Snapshot, max_retries: int = 3) -> list[Fn]:
    before = snapshot.fn.dumps()
    main_name = fns[0].name
    combined = "\n\n".join(fn.dumps() for fn in fns)
    for attempt in range(max_retries):
      conflicts = self.agent.existing_helpers(combined, snapshot.solution, before=before)
      if not conflicts:
        break
      raise AssertionError("not considered at this moment")
      lines = [f"The following helper function name{'s' if len(conflicts) > 1 else ''} already exist{'s' if len(conflicts) == 1 else ''} in the codebase. Rename {'them' if len(conflicts) > 1 else 'it'} (both definitions and calls) to avoid conflict:"]
      for name in conflicts:
        lines.append(f"- `{name}`")
      msgs = Msgs()
      msgs.add(role="user", content=f"{'\n'.join(lines)}\n\n```python\n{combined}\n```")
      response = self.generate(msgs, reasoning={"effort": "none"})
      codes = extract_python_function_defs(response.content)
      main_code = remove_comments(codes.pop(main_name))
      fns = [
        fns[0].update(body=reindent(parse_fn_body(main_code), indent=Fn.indent)),
        *(Fn(name=name, body=reindent(parse_fn_body(remove_comments(code)), indent=Fn.indent), parameters=tuple(parse_fn_params(code)))
          for name, code in codes.items())
      ]
      combined = "\n\n".join(fn.dumps() for fn in fns)
    else:
      conflicts = self.agent.existing_helpers(combined, snapshot.solution, before=before)
      assert not conflicts, f"Failed to rename existing helpers after {max_retries} retries: {conflicts}"
    return fns

  def maybe_substitue_dot(self, code: str):
    substituted_calls = []
    for call in parse_code_function_calls(code):
      name = call.name
      api_doc = self.agent._get_api_doc(name)
      if api_doc is None:
        parts = name.split(".")
        if len(parts) == 2:
          app_name, api_name = parts
          for app in self.agent.show_app_descriptions():
            if app["name"] == app_name:
              code = re.sub(fr"\b{app_name}\.{api_name}", rf"{app_name}_{api_name}", code)
              substituted_calls.append(call)
    return code, substituted_calls


class CodeGenAction(Action):

  def take(self, snapshot: Snapshot) -> list[Fn]:
    raise NotImplementedError(self.__class__)


class MetaAction(Action):

  def take(self, snapshot: Snapshot) -> list[CodeGenAction | MetaAction]:
    raise NotImplementedError(self.__class__)

# ------------------------------------------------------------------
# 2. Implement 계열 (초기 구현)
# ------------------------------------------------------------------
class Initialize(CodeGenAction):
  """함수를 처음부터 구현할 때 사용하는 Base Todo"""
  pass


class Compound(Initialize):
  """
  복잡한 로직을 오케스트레이션(제어 흐름) 중심으로 짜고,
  세부 로직은 하위 Helper 함수로 위임하는 Todo
  """
  msgs: Msgs | None = None
  reason: str

  def take(self, snapshot: Snapshot) -> list[Fn]:
    fn, ctx = snapshot.fn, snapshot.ctx
    msgs = self.agent.system_coder()
    msgs.extend(
      render_messages_template(
        "templates/v11/compound.md",
        snapshot=snapshot,
        global_variables=self.agent.globals(),
      )
    )
    result = self.generate_function_defs_with_compound_flow(msgs, fn, ctx, prefix=False)
    new_fn = result[0]
    msgs.add(role="assistant", content=f"```python\n{new_fn.dumps()}\n```")
    result = self.rename_existing_helpers_fns(result, snapshot)
    self.msgs = msgs
    return result


class ApiSpeculator:

  def __init__(
    self, 
    agent: MyAgent, 
    msgs: Msgs, 
    max_attempts: int = 2, # total
    max_api_attempts: int = 2 # api attempts
  ):
    self.agent = agent
    self.msgs = msgs
    self.attempts: dict[str, list[str]] = defaultdict(list) # {app_name: [api_name1, api_name2, ...]} for each attempt
    self.max_attempts = max_attempts
    self.max_api_attempts = max_api_attempts
    self._gen = None

  def generate_with_think(self, *args, **kwargs):
    return self.agent.generate_with_think(*args, **kwargs)

  def get(self, snapshot: Snapshot) -> str | None:

    if (
      sum(
        len(attempted_apis) 
        for attempted_apis in self.attempts.values()
      ) >= self.max_attempts
    ):
      return None

    if self._gen is None:
      self._gen = self.generator(snapshot)

    try:
      return next(self._gen)
    except StopIteration:
      return None

  def generator(self, snapshot: Snapshot):
    fn = snapshot.fn
    app_descriptions = self.agent.show_app_descriptions()
    for _ in range(100):
      choose_app_msgs, app_name = self.choose_app(self.msgs, fn, app_descriptions)
      api_descriptions = self.agent.show_api_descriptions(app_name=app_name)
      for _ in range(self.max_api_attempts):
        _, api_name = self.choose_api(choose_app_msgs, app_name, api_descriptions)
        self.attempts[app_name].append(api_name)
        yield (app_name, api_name)
        api_descriptions = [
          api for api in api_descriptions if api["name"] != api_name
        ]
      app_descriptions = [
        app for app in app_descriptions if app["name"] != app_name
      ]
    assert False, "ApiSpeculator.generator: exhausted 100 outer iterations without finishing — likely infinite loop"

  def choose_app(
    self,
    msgs: Msgs,
    fn: Fn,
    app_descriptions: list[dict[str, str]],
  ):
    _msgs = msgs.model_copy(deep=True)
    _msgs.extend(
      render_messages_template(
        "templates/v10/choose_app.md", fn=fn
      )
    )
    for _ in range(5):
      _, think, extra = self.generate_with_think(_msgs)
      try:
        app_name = extra["app"]
        break
      except:
        _msgs.add(role="assistant", content=f'```\n{json.dumps({"think": think, **extra}, indent=2)}\n```')
        _msgs.add(role="user", content='Wrong response format. Include "app" field.')
        pass
    msgs.add(role="user", content=f"Select ONE app that is most likely to contain the functionality (i.e., API) you need to implement `{fn.name}`.")
    msgs.add(role="assistant", content=think)
    return msgs, app_name

  def choose_api(
    self,
    msgs: Msgs,
    app_name: str,
    api_descriptions,
  ):
    msgs = msgs.model_copy(deep=True)
    msgs.extend(
      render_messages_template(
        "templates/v10/choose_api.md", 
        app_name=app_name, 
        api_descriptions=api_descriptions
      )
    )
    for _ in range(5):
      _, think, extra = self.generate_with_think(msgs)
      try:
        api_name = extra["api"]
        break
      except:
        msgs.add(role="assistant", content=f'```\n{json.dumps({"think": think, **extra}, indent=2)}\n```')
        msgs.add(role="user", content='Wrong response format. Include "api" field.')
        pass

    api_name = extra["api"]
    for api in api_descriptions:
      if api["name"] == api_name:
        break
    else:
      assert False, f"choose_api: LLM returned api_name='{api_name}' which is not in api_descriptions for app='{app_name}'"
    msgs.remove(-1)
    msgs.add(role="assistant", content=think)
    return msgs, api_name


class ExploreApis(MetaAction):

  def take(self, snapshot: Snapshot) -> list[GoAheadWithApi]:
    # app_descriptions = self.agent.show_app_descriptions(exclude=["api_docs"])
    msgs = self.agent.system_coder()
    # Generate with response format
    gen_msgs = msgs.model_copy(deep=True)
    gen_msgs.extend(
      render_messages_template(
        "templates/v11/explore_apis_1.md",
        snapshot=snapshot
      )
    )
    _, think, extra = self.generate_with_think(gen_msgs, reasoning={"effort": "none"}, max_completion_tokens=512, max_tokens=512)
    apps = extra["apps"]
    apis_by_candidate_app = {}
    for app_name in apps:
      apis_by_candidate_app[app_name] = {}
      for api in self.agent.show_api_descriptions(app_name=app_name):
        apis_by_candidate_app[app_name][api["name"]] = api["description"]
    # Append to thread without response format + LLM response
    msgs.extend(
      render_messages_template(
        "templates/v11/explore_apis_1.md",
        snapshot=snapshot,
        include_response_format=False
      )
    )
    msgs.add(
      role="assistant",
      content=", ".join(f"`{app_name}`" for app_name in apps)
    )
    gen_msgs = msgs.model_copy(deep=True)
    gen_msgs.extend(
      render_messages_template(
        "templates/v11/explore_apis_2.md",
        snapshot=snapshot,
        apis_by_candidate_app=apis_by_candidate_app
      )
    )
    _, think, extra = self.generate_with_think(gen_msgs, reasoning={"effort": "none"}, max_completion_tokens=512, max_tokens=512)
    apis = extra["apis"]
    api_doc_by_api = {}
    for api in apis:
      app_name, api_name = api.split(".")
      api_doc_by_api[api] = self.agent.show_api_doc(app_name, api_name)
    # Append to thread without response format + LLM response
    msgs.extend(
      render_messages_template(
        "templates/v11/explore_apis_2.md",
        snapshot=snapshot,
        apis_by_candidate_app=apis_by_candidate_app,
        include_response_format=False
      )
    )
    msgs.add(
      role="assistant",
      content=", ".join(f"`{api}`" for api in apis)
    )
    gen_msgs = msgs.model_copy(deep=True)
    gen_msgs.extend(
      render_messages_template(
        "templates/v11/explore_apis_3.md",
        snapshot=snapshot,
        api_doc_by_api=api_doc_by_api
      )
    )
    _, think, extra = self.generate_with_think(gen_msgs, reasoning={"effort": "none"}, max_completion_tokens=512, max_tokens=512)
    qualified_apis = extra["qualified_apis"]
    # Append to thread without response format + LLM response
    msgs.extend(
      render_messages_template(
        "templates/v11/explore_apis_3.md",
        snapshot=snapshot,
        api_doc_by_api=api_doc_by_api,
        include_response_format=False
      )
    )
    msgs.add(
      role="assistant",
      content=", ".join(f"Qualified APIs: `{qualified_api}`" for qualified_api in qualified_apis)
    )
    next_actions = []
    for qualified_api in qualified_apis:
      app_name, api_name = qualified_api.split(".")
      next_actions.append(
        GoAheadWithApi(
          scope=self.scope,
          before_action=self,
          app_name=app_name,
          api_name=api_name
        )
      )
    return next_actions


class GoAheadWithApi(CodeGenAction):

  app_name: str
  api_name: str

  def take(self, snapshot: Snapshot) -> list[Fn]:

    msgs = render_messages_template(
      "templates/v11/invoke_api.md", 
      global_variables=self.agent.globals(),
      snapshot=snapshot,
      app_name=self.app_name,
      api_name=self.api_name,
      api_doc=self.agent.show_api_doc(
        app_name=self.app_name, api_name=self.api_name
      ),
      working_memory=self.agent.working_memory
    )
    _, code = self.generate_fn(msgs, snapshot.fn, reasoning={"effort": "none"})
    codes = lift_inner_functions(code, cleanup=True)
    code = codes[snapshot.fn.name]
    code = self.agent.remove_print_statements(code, snapshot.ctx)
    code = remove_comments(code)
    code = self.ensure_no_void_calls(code, snapshot)
    code = self.assure_api_invokation(
      msgs, snapshot.fn, code, self.app_name, self.api_name
    )
    code = truncate_execution_flow(code, f"{self.app_name}.{self.api_name}")
    return [snapshot.fn.update(body=parse_fn_body(code))]

  def assure_api_invokation(
    self,
    msgs: Msgs,
    fn: Fn,
    code: str,
    app_name: str,
    api_name: str,
  ):
    msgs = msgs.model_copy(deep=True)
    [call] = find_function_call(code, name=f"{app_name}.{api_name}")
    assert call, f"assure_api_invokation: no call to '{app_name}.{api_name}' found in generated code"
    api_doc = self.agent.show_api_doc(app_name=app_name, api_name=api_name)
    if call.positional_arguments and api_doc["parameters"]:
      msgs.add(
        role="user", 
        content=f"For `{app_name}.{api_name}`, pass parameters as keyword arguments, not positional arguments."
      )
      _, code = self.generate_fn(msgs, fn, reasoning={"effort": "none"})
    return code



class Atomic(Initialize):
  """
  주어진 환경(AppWorld API 등)이나 기본 내장 함수만으로 
  단일 함수를 끝까지 구현하는 Todo
  """
  model_config = ConfigDict(arbitrary_types_allowed=True)
  speculator: ApiSpeculator
  nth: int  # 같은 스냅샷에서 여러 번 시도할 수 있도록, 시도 횟수에 따라 다른 가설을 적용합니다.

  def take(self, snapshot: Snapshot) -> list[Fn]:
    fn, ctx = snapshot.fn, snapshot.ctx
    res = self.speculator.get(snapshot)
    if res is None:
      return None
    app_name, api_name = res
    invoke_api_msgs, code = self.invoke_api(
      snapshot, app_name, api_name
    )
    code = self.assure_api_invokation(
      invoke_api_msgs, fn, code, app_name, api_name
    )
    code = truncate_execution_flow(code, f"{app_name}.{api_name}")
    return [fn.update(body=parse_fn_body(code))]

  def invoke_api(
    self,
    snapshot: Snapshot,
    app_name: str,
    api_name: str,
  ):
    msgs = render_messages_template(
      "templates/v10/invoke_api.md", 
      global_variables=self.agent.globals(),
      snapshot=snapshot,
      app_name=app_name,
      api_name=api_name,
      api_doc=self.agent.show_api_doc(
        app_name=app_name, api_name=api_name
      ),
      working_memory=self.agent.working_memory
    )
    _, code = self.generate_fn(msgs, snapshot.fn)
    code = self.agent.remove_print_statements(code, snapshot.ctx)
    code = remove_comments(code)
    code = self.ensure_no_void_calls(code, snapshot)
    msgs.add(role="assistant", content=f"```python\n{code}\n```")
    return (msgs, code)


class Complete(CodeGenAction):

  def take(self, snapshot: Snapshot) -> list[Fn]:

    msgs = self.agent.system_coder()
    msgs.extend(
      render_messages_template(
        "templates/v11/summary.md",
        snapshot=snapshot,
      )
    )
    _, code = self.generate_fn(msgs, snapshot.fn)
    after_apis, before_apis = self.agent.new_unknown_calls(before=snapshot.fn.dumps(), after=code, scope=snapshot.fn.name, solution=snapshot.solution)
    new_unknown_calls = sorted(after_apis - before_apis)
    if not new_unknown_calls:
      return [
        snapshot.fn.update(
          body=remove_comments(
            reindent(parse_fn_body(code), indent=Fn.indent)
          )
        )
      ]

    logger.error(
      "Complete.take: new_unknown_calls=%s in `%s`",
      new_unknown_calls,
      snapshot.fn.name
    )
    msgs.add(role="assistant", content=f"```python\n{code}\n```")
    msgs.add(role="user", content=f"New, unknown calls are introduced: {new_unknown_calls}.\nThe code before you transformed is:\n```python\n{snapshot.fn.dumps()}\n```")
    _, code = self.generate_fn(msgs, snapshot.fn)

    return [
      snapshot.fn.update(
        body=remove_comments(
          reindent(parse_fn_body(code), indent=Fn.indent)
        )
      )
    ]

class Adapt(CodeGenAction):

  helper: str
  return_value: dict[str, Any]

  def take(self, snapshot: Snapshot) -> list[Fn]:
    helper_fn = snapshot.solution[self.helper]
    if isinstance(helper_fn, FnApiParam):
      # FnApiParam → originated from Atomic/GatherContext/GoAheadWithApi branch
      assert self._find_ancestor((Atomic, GatherContext, GoAheadWithApi)) is not None, (
        f"Adapt: helper '{self.helper}' is FnApiParam but no Atomic/GatherContext/GoAheadWithApi "
        f"found in before_action chain"
      )
      c = helper_fn.return_passed_to
      new_body = replace_api_param(
        snapshot.fn.dumps(),
        app_name=c.app_name,
        api_name=c.api_name,
        param_name=c.param_name,
        new_value_code=f'{c.var_name}["primary"]',
      )
      return [
        snapshot.fn.update(
          body=reindent(parse_fn_body(new_body), indent=Fn.indent)
        )
      ]
    # Generic case (Compound branch): continue the Compound action's
    # message thread with the helper's return value so the LLM can
    # rewrite the orchestration sketch accordingly.
    compound = self._find_ancestor(Compound)
    assert compound is not None, (
      f"Adapt: helper '{self.helper}' is {type(helper_fn).__name__} (not FnApiParam) "
      f"but no Compound found in before_action chain"
    )
    assert compound.msgs is not None, (
      f"Adapt: Compound action for '{self.helper}' has no stored msgs — "
      f"Compound.take() may not have been called yet"
    )
    msgs = render_messages_template(
      "templates/v11/adapt_data_flow.md",
      global_variables=self.agent.globals(),
      include_global_variables=self.agent.globals_accessed(snapshot.fn),
      snapshot=snapshot,
      helper=self.helper,
      return_value=json.dumps(self.return_value, default=str, indent=2),
    )
    # msgs.add(
    #   role="user",
    #   content=(
    #     f"A programming assistant has implemented the helper function `{self.helper}`, and it has returned the following value with `primary` and `extras` fields:\n"
    #     f"```\n{json.dumps(self.return_value, default=str)}\n```\n\n"
    #     f"Rewrite the data flow of `{snapshot.fn.name}` to incorporate this return value.\n"
    #     f"1. Do NOT introduce additional helpers.\n"
    #     f"2. Do NOT remove existing helpers.\n"
    #   )
    # )
    # msgs = Msgs()
    # msgs.add(
    #   role="user",
    #   content=(
    #     f"A programming assistant has implemented the helper function `{self.helper}`, and it has returned the following value with `primary` and `extras` fields:\n"
    #     f"```\n{json.dumps(self.return_value, default=str)}\n```\n\n"
    #     f"Rewrite the data flow of `{snapshot.fn.name}` to incorporate this return value.\n"
    #     f"1. Do NOT introduce additional helpers.\n"
    #     f"2. Do NOT remove existing helpers.\n"
    #   )
    # )
    _, code = self.generate_fn(msgs, snapshot.fn, reasoning={"effort": "none"})
    return [
      snapshot.fn.update(
        body=reindent(parse_fn_body(code), indent=Fn.indent)
      )
    ]


class GatherContext(CodeGenAction):
  # reason: str
  rationale: str | None = None


class GatherContextNew(GatherContext):
  """
  obtaining_missing_info 함수를 위한 단계적 API 호출 액션.
  ExploreApis처럼 API를 탐색하고, GoAheadWithApi처럼 코드를 생성한다.
  critique에서 추가 정보가 필요하면 새 GatherContext(before_action=self)를 반환하여
  ReAct-style 루프를 형성한다.
  """
  # Resume state from previous GatherContext steps
  chosen_but_unexplored_apps: list[str] = []
  chosen_but_unexplored_apis: list[str] = []
  explored_apis: list[str] = []
  discard_unexplored: bool = False

  def _prev_gather(self):
    """Walk before_action chain to find the previous GatherContext."""
    action = self.before_action
    while action is not None:
      if isinstance(action, GatherContextNew):
        return action
      action = action.before_action
    return None

  def take(self, snapshot: Snapshot) -> list[Fn]:
    fn = snapshot.fn
    # Inherit resume state from previous GatherContext
    prev = self._prev_gather()
    assert (prev is None) == (self.rationale is None), (
      f"GatherContextNew: rationale is {'None' if self.rationale is None else 'set'} "
      f"but _prev_gather() returned {'None' if prev is None else prev}"
    )
    explored_apis = list(prev.explored_apis) if prev else []
    if self.discard_unexplored:
      chosen_but_unexplored_apps = []
      chosen_but_unexplored_apis = []
    else:
      chosen_but_unexplored_apps = list(prev.chosen_but_unexplored_apps) if prev else []
      chosen_but_unexplored_apis = list(prev.chosen_but_unexplored_apis) if prev else []

    max_retries = 3
    logger.info(
      "GatherContext.take: fn='%s', explored_apis=%s, unexplored_apis=%s, unexplored_apps=%s",
      fn.name, explored_apis, chosen_but_unexplored_apis, chosen_but_unexplored_apps
    )
    for retry in range(max_retries):
      # --- Step 1: Choose apps ---
      if chosen_but_unexplored_apis:
        apps = [chosen_but_unexplored_apis[0].split(".")[0]]
        assert apps[0] not in chosen_but_unexplored_apps, (
          f"GatherContext: app '{apps[0]}' from chosen_but_unexplored_apis "
          f"should not be in chosen_but_unexplored_apps={chosen_but_unexplored_apps}"
        )
        logger.info(
          "GatherContext: resuming from unexplored APIs %s → apps=%s",
          chosen_but_unexplored_apis, apps
        )
      elif chosen_but_unexplored_apps:
        apps = chosen_but_unexplored_apps
        logger.info(
          "GatherContext: resuming from unexplored apps %s",
          chosen_but_unexplored_apps
        )
      else:
        logger.info("GatherContext: fresh app selection (retry=%d)", retry)
        gen_msgs = self.agent.system_coder()
        gen_msgs.extend(
          render_messages_template(
            "templates/v11/gather_context_1.md",
            snapshot=snapshot,
            rationale=self.rationale,
          )
        )
        _, _, extra = self.generate_with_think(gen_msgs, reasoning={"effort": "none"}, max_completion_tokens=512, max_tokens=512)
        apps = extra["apps"]
        logger.info("GatherContext: LLM chose apps=%s", apps)

      # --- Step 2: Choose APIs from chosen apps ---
      apis_by_candidate_app = {}
      for app_name in apps:
        apis_by_candidate_app[app_name] = {}
        for api in self.agent.show_api_descriptions(app_name=app_name):
          qualified = f"{app_name}.{api['name']}"
          if qualified not in explored_apis:
            apis_by_candidate_app[app_name][api["name"]] = api["description"]

      # Build message thread on top of previous rounds
      msgs = self.agent.system_coder()
      msgs.extend(
        render_messages_template(
          "templates/v11/gather_context_1.md",
          snapshot=snapshot,
          rationale=self.rationale,
          include_response_format=False
        )
      )
      msgs.add(
        role="assistant",
        content=", ".join(f"`{app_name}`" for app_name in apps)
      )

      if chosen_but_unexplored_apis:
        logger.info("GatherContext: skipping steps 2-3, reusing qualified APIs %s", chosen_but_unexplored_apis)
        apis = chosen_but_unexplored_apis
        api_doc_by_api = {}
        for api in apis:
          a, n = api.split(".")
          api_doc_by_api[api] = self.agent.show_api_doc(a, n)
        qualified_apis = chosen_but_unexplored_apis
      else:
        gen_msgs = msgs.model_copy(deep=True)
        gen_msgs.extend(
          render_messages_template(
            "templates/v11/gather_context_2.md",
            snapshot=snapshot,
            apis_by_candidate_app=apis_by_candidate_app
          )
        )
        _, _, extra = self.generate_with_think(gen_msgs, reasoning={"effort": "none"}, max_completion_tokens=512, max_tokens=512)
        apis = extra["apis"]
        logger.info("GatherContext: LLM chose APIs to inspect: %s", apis)
        api_doc_by_api = {}
        for api in apis:
          app_name, api_name = api.split(".")
          api_doc_by_api[api] = self.agent.show_api_doc(app_name, api_name)

      msgs.extend(
        render_messages_template(
          "templates/v11/gather_context_2.md",
          snapshot=snapshot,
          apis_by_candidate_app=apis_by_candidate_app,
          include_response_format=False
        )
      )
      msgs.add(
        role="assistant",
        content=", ".join(f"`{api}`" for api in apis)
      )

      if not chosen_but_unexplored_apis:
        # --- Step 3: Qualify/inspect APIs ---
        gen_msgs = msgs.model_copy(deep=True)
        gen_msgs.extend(
          render_messages_template(
            "templates/v11/gather_context_3.md",
            snapshot=snapshot,
            api_doc_by_api=api_doc_by_api
          )
        )
        _, _, extra = self.generate_with_think(gen_msgs, reasoning={"effort": "none"}, max_completion_tokens=512, max_tokens=512)
        qualified_apis = extra["qualified_apis"]
        logger.info("GatherContext: qualified APIs: %s", qualified_apis)

      if not qualified_apis:
        if chosen_but_unexplored_apis:
          logger.warning(
            "GatherContext: no qualified APIs from unexplored_apis=%s → falling back to unexplored_apps=%s",
            chosen_but_unexplored_apis, chosen_but_unexplored_apps
          )
          chosen_but_unexplored_apis = []
        elif chosen_but_unexplored_apps:
          logger.warning(
            "GatherContext: no qualified APIs from unexplored_apps=%s → falling back to fresh app selection",
            chosen_but_unexplored_apps
          )
          chosen_but_unexplored_apps = []
        else:
          logger.warning("GatherContext: no qualified APIs from fresh selection → retrying (retry=%d)", retry)
        continue
      break
    else:
      raise AssertionError(
        f"GatherContext: no qualified APIs found after {max_retries} retries "
        f"(explored_apis={explored_apis})"
      )

    # --- Pick the best API and generate code ---
    logger.info("GatherContext: invoking %s (qualified=%s)", qualified_apis[0], qualified_apis)
    app_name, api_name = qualified_apis[0].split(".")
    observed_variables = self._observed_variables(snapshot, include_inner=False)
    invoke_msgs = render_messages_template(
      "templates/v11/invoke_api.md",
      global_variables=self.agent.globals(),
      snapshot=snapshot,
      app_name=app_name,
      api_name=api_name,
      api_doc=self.agent.show_api_doc(app_name=app_name, api_name=api_name),
      working_memory=self.agent.working_memory,
      observed_variables=observed_variables,
    )
    _, code = self.generate_fn(invoke_msgs, fn, reasoning={"effort": "none"})
    codes = lift_inner_functions(code, cleanup=True)
    code = codes[fn.name]
    code = self.agent.remove_print_statements(code, snapshot.ctx)
    code = remove_comments(code)
    code = self.ensure_no_void_calls(code, snapshot)
    code = remove_returns(code)
    code = truncate_execution_flow(code, f"{app_name}.{api_name}")
    code = self.rename_existing_helpers(code, snapshot)

    # --- Save resume state for next GatherContext ---
    used_api = f"{app_name}.{api_name}"
    self.explored_apis = explored_apis + [used_api]
    self.chosen_but_unexplored_apis = [a for a in qualified_apis if a != used_api]
    apps_with_qualified = {a.split(".")[0] for a in self.chosen_but_unexplored_apis}
    remaining_apps = [a for a in apps if a != app_name and a not in apps_with_qualified]
    carried_apps = [a for a in chosen_but_unexplored_apps if a not in apps and a not in apps_with_qualified]
    self.chosen_but_unexplored_apps = remaining_apps + carried_apps
    logger.info(
      "GatherContext: saved state → explored=%s, unexplored_apis=%s, unexplored_apps=%s",
      self.explored_apis, self.chosen_but_unexplored_apis, self.chosen_but_unexplored_apps
    )

    return [fn.update(body=parse_fn_body(code))]


class GatherContextAgain(GatherContext):
  ...


# ------------------------------------------------------------------
# 3. Fix 계열 (오류 수정 및 로직 개선)
# ------------------------------------------------------------------
class FixError(CodeGenAction):
  """
  실행 결과나 피드백을 바탕으로 기존 코드를 수정하는 Base Todo.
  수정에 필요한 구체적인 이유(feedback)를 필수로 가집니다.
  """

  def _snapshot_with_marker(self, snapshot: Snapshot) -> Snapshot:
    return snapshot
    """Return a snapshot copy whose fn body has a truncation marker at the error line."""
    ctx = snapshot.ctx
    if ctx is None or ctx.exc is None or ctx.exc.tb is None:
      return snapshot
    marked_code = insert_truncation_marker(
      snapshot.fn.dumps(), ctx
    )
    marked_fn = Fn.from_code(marked_code, ignore_docstring=True)
    return Snapshot(fn=marked_fn, solution=snapshot.solution, ctx=snapshot.ctx)


class HotFix(FixError):
  """
  단순 런타임 에러(예: Type Error, 오타 등)나 가벼운 로직 버그를
  기존 코드 구조를 유지한 채 빠르게 덧대어 고치는(Patch) Todo
  """
  feedback: str

  def take(self, snapshot: Snapshot) -> list[Fn]:
    fn, ctx = snapshot.fn, snapshot.ctx
    marked_snapshot = self._snapshot_with_marker(snapshot)
    template_path = "templates/v11/hotfix.md" if self._is_gathering() else "templates/v11/try_hotfix.md"
    msgs = self.agent.system_coder()
    msgs.extend(
      render_messages_template(
        template_path,
        global_variables=self.agent.globals(),
        globlas_accessed=self.agent.globals_accessed(snapshot.fn),
        snapshot=marked_snapshot,
        feedback=self.feedback
      )
    )
    max_retries = 3
    for _ in range(max_retries):
      try:
        _, code = self.generate_fn(msgs, snapshot.fn, reasoning={"effort": "none"})
        break
      except:
        pass
    else:
      raise
    code = truncate_at_marker(code, marked_snapshot.fn.dumps())
    code = self.agent.remove_print_statements(code, snapshot.ctx)
    return [
      fn.update(
        body=remove_comments(
          reindent(parse_fn_body(code), indent=Fn.indent)
        )
      )
    ]


class Diagnosis(BaseModel):

  cause: str
  fix: str
  category: str


class ExploreDiagnoses(MetaAction):

  def _consecutive_hotfix_depth(self) -> int:
    depth = 0
    cur = self.before_action
    while cur is not None:
      if isinstance(cur, HotFixOnDiagnosis):
        depth += 1
      else:
        break
      cur = cur.before_action
    return depth

  def take(self, snapshot: Snapshot) -> list[FixOnDiagnosis]:
    # msgs = self.agent.system_coder(include_global_variables=self.agent.globals_accessed(snapshot.fn))
    msgs = self.agent.system_coder()
    msgs.extend(
      render_messages_template(
        "templates/v11/critique.md",
        snapshot=snapshot,
        used_apis=self.agent.parse_active_calls(snapshot.fn, snapshot.solution),
      )
    )
    # response = self.generate(msgs, prefix="```\n[\n", retry_on=lambda response: False, use_prefix=False, max_tokens=2048, max_completion_tokens=2048)
    response = self.generate(msgs, prefix="```\n[\n", retry_on=lambda response: False, use_prefix=False)
    response.content = response.content.replace("```json", "```python")
    try:
      code, = extract_python_codes(response.content)
    except:
      try:
        code, = extract_fenced_chunks(response.content)
      except:
        code, = extract_fenced_chunks(f"```\n{response.content}```")

    max_hotfix_depth = 3
    hotfix_depth = self._consecutive_hotfix_depth()

    observed_variables = self._observed_variables(snapshot)

    next_actions = []
    for diagnosis in ast.literal_eval(code):
      diagnosis = Diagnosis(**diagnosis)
      category = diagnosis.category
      if category == "fixable_now":
        if hotfix_depth < max_hotfix_depth:
          next_actions.append(
            HotFixOnDiagnosis(scope=snapshot.fn.name, diagnosis=diagnosis, observed_variables=observed_variables, before_action=self),
          )
      elif category == "missing_information":
        next_actions.append(
          ObtainMissingInformation(scope=snapshot.fn.name, diagnosis=diagnosis, observed_variables=observed_variables, before_action=self),
        )
    return next_actions


class FixOnDiagnosis(FixError):
  diagnosis: Diagnosis
  observed_variables: dict[str, dict[str, dict[str, Any]]]


class HotFixOnDiagnosis(FixOnDiagnosis):

  def take(self, snapshot: Snapshot) -> list[Fn]:
    fn = snapshot.fn
    feedback = f"- Cause: {self.diagnosis.cause}\n- Fix: {self.diagnosis.fix}".strip()
    marked_snapshot = self._snapshot_with_marker(snapshot)
    msgs = self.agent.system_coder()
    msgs.extend(
      render_messages_template(
        "templates/v11/hotfix_on_hypothesis.md",
        global_variables=self.agent.globals(),
        globlas_accessed=self.agent.globals_accessed(snapshot.fn),
        snapshot=marked_snapshot,
        feedback=feedback
      )
    )
    _, code = self.generate_fn(msgs, fn)
    code = truncate_at_marker(code, marked_snapshot.fn.dumps())
    code = self.agent.remove_print_statements(code, snapshot.ctx)
    after_apis, before_apis = self.agent.new_unknown_calls(before=snapshot.fn.dumps(), after=code, scope=snapshot.fn.name, solution=snapshot.solution)
    new_unknown_calls = sorted(after_apis - before_apis)
    if not new_unknown_calls:
      return [
        fn.update(
          body=remove_comments(
            reindent(parse_fn_body(code), indent=Fn.indent)
          )
        )
      ]

    logger.error(
      "HotFixOnDiagnosis.take: new_unknown_calls=%s in `%s`",
      new_unknown_calls,
      snapshot.fn.name
    )
    action = ObtainMissingInformation(
      scope=self.scope,
      before_action=self.before_action,
      diagnosis=self.diagnosis,
      observed_variables=self.observed_variables
    )
    return action.take(snapshot)


class ObtainMissingInformation(FixOnDiagnosis):

  def take(self, snapshot: Snapshot) -> list[Fn]:
    fn, ctx = snapshot.fn, snapshot.ctx
    active_calls = self.agent.parse_active_calls(snapshot.fn, snapshot.solution)
    feedback = f"- Cause: {self.diagnosis.cause}\n- Fix: {self.diagnosis.fix}".strip()
    marked_snapshot = self._snapshot_with_marker(snapshot)

    obs = self._observed_variables(snapshot, include_inner=False)

    if not obs:
      classification = "never_seen"
    else:
      msgs = render_messages_template(
        "templates/v11/missing_info_classify.md",
        global_variables=self.agent.globals(),
        globlas_accessed=self.agent.globals_accessed(snapshot.fn),
        snapshot=marked_snapshot,
        diagnosis=feedback,
        app_descriptions=self.agent.show_app_descriptions(exclude=["api_docs"]),
        instruction=self.agent.world.task.instruction,
        used_apis=active_calls,
        observed_variables=obs
      )
      _, think, extra = self.generate_with_think(msgs)
      classification = extra["classification"].lower()

    if classification == "never_seen":
      msgs = self.agent.system_coder()
      msgs.extend(
        render_messages_template(
          "templates/v11/obtain.md",
          global_variables=self.agent.globals(),
          globlas_accessed=self.agent.globals_accessed(marked_snapshot.fn),
          snapshot=marked_snapshot,
          diagnosis=feedback,
          app_descriptions=self.agent.show_app_descriptions(exclude=["api_docs"]),
          instruction=self.agent.world.task.instruction,
          used_apis=active_calls,
        )
      )
      _, code = self.generate_fn(msgs, fn)
      code = truncate_at_marker(code, marked_snapshot.fn.dumps())
      code = self.agent.remove_print_statements(code, snapshot.ctx)
      code = self.ensure_no_void_calls(code, snapshot)
      code = self.rename_existing_helpers(code, snapshot)
      return [
        fn.update(
          body=(
            reindent(parse_fn_body(code), indent=Fn.indent)
          )
        )
      ]
    logger.error(
      "ObtainMissingInformation.take: classification='%s' for fn='%s' — "
      "only 'never_seen' is implemented, other classifications are not handled",
      classification, fn.name
    )
    raise NotImplementedError(
      f"ObtainMissingInformation.take: classification='{classification}' for fn='{fn.name}' — "
      f"only 'never_seen' classification is implemented. "
      f"Diagnosis: {feedback[:200]}"
    )