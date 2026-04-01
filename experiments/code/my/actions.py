from __future__ import annotations
import json
import logging

from copy import deepcopy
from collections import defaultdict
from typing import ClassVar, TYPE_CHECKING
from pydantic import BaseModel, ConfigDict

from appworld_agents.code.my.fn import Diagnosis, Fn, FnApiParam, Snapshot
from appworld.common.my_code_parsing import *
from appworld_agents.code.my.hashable import UidAsHash
from appworld_agents.code.my.message import *
from appworld_agents.code.my.json_parser import *
from appworld_agents.code.my.python_def_parser import *

logger = logging.getLogger("peter.actions")

if TYPE_CHECKING:
  from appworld_agents.code.my.v11 import SubAgent as MyAgent


# ------------------------------------------------------------------
# NeedMoreInformation detection
# ------------------------------------------------------------------

def has_mixed_need_more_info(code: str) -> bool:
    """Check if code contains NeedMoreInformation mixed with other statements.

    Returns True if NeedMoreInformation is present but NOT the sole body statement.
    Returns False if:
      - No `raise NeedMoreInformation` statement in the body (clean implementation,
        or NeedMoreInformation only appears inside a string literal)
      - `raise NeedMoreInformation(...)` is the only statement in the body (clean give-up,
        even if the raise spans multiple lines)
    """
    body = parse_fn_body(code).strip()
    import ast
    try:
        tree = ast.parse(body)
    except SyntaxError:
        return "raise NeedMoreInformation" in body

    # Walk AST to find any raise NeedMoreInformation(...) node
    has_nmi = False
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Raise)
            and isinstance(node.exc, ast.Call)
            and isinstance(node.exc.func, ast.Name)
            and node.exc.func.id == "NeedMoreInformation"
        ):
            has_nmi = True
            break
    if not has_nmi:
        return False

    # Single statement: raise NeedMoreInformation(...) alone → clean give-up
    if len(tree.body) == 1 and isinstance(tree.body[0], ast.Raise):
        return False

    return True


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

  def sanitize_and_fix_api_calls(
    self,
    code: str,
    snapshot: Snapshot,
    app_name: str,
    api_name: str,
    max_retries: int = 3,
  ) -> str:
    """Sanitize hallucinated API calls, then ask LLM to fix any unknown dotted calls.

    1. Rename hallucinated app API calls (valid app, wrong API) to underscored helpers.
    2. If unknown dotted calls remain, prompt LLM to rewrite just those calls.
    """
    app_names = {app["name"] for app in self.agent.show_app_descriptions()}
    expected_api = f"{app_name}.{api_name}"

    for _ in range(max_retries):
      code, unknown_calls = sanitize_api_calls(
        code,
        expected_api=expected_api,
        app_names=app_names,
      )
      if not unknown_calls:
        return code

      raise NotImplementedError(
        f"Action.sanitize_and_fix_api_calls: can occur? unknown_calls={unknown_calls}"
      )
      msgs = Msgs()
      msgs.add(
        role="user",
        content=(
          f"The following calls are not recognized: {unknown_calls}.\n"
          f"You were asked to call ONLY `{expected_api}`.\n"
          f"Rewrite the function so that unknown calls are replaced with "
          f"helper function calls (no dots) or removed.\n\n"
          f"```python\n{code}\n```"
        ),
      )
      _, code = self.generate_fn(msgs, snapshot.fn, reasoning={"effort": "none"})
      code = remove_comments(code)

    # Final pass
    code, unknown_calls = sanitize_api_calls(code, expected_api=expected_api, app_names=app_names)
    if unknown_calls:
      logger.warning(
        "sanitize_and_fix_api_calls: unknown calls %s remain after %d retries",
        unknown_calls, max_retries,
      )
    return code

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


class Classify(MetaAction):
  """Decide how to implement a function: plan-first, exploration-first, or implementation-first.

  Reused both at initial decomposition and after Explore reaches before-return,
  so the same decision logic applies with updated context each time.
  """

  def take(self, snapshot: Snapshot) -> list[CodeGenAction | MetaAction]:
    fn = snapshot.fn
    is_reclassify = self.before_action is not None
    assert not is_reclassify or snapshot.ctx.locals, (
      f"Classify: re-classify but no local variables in context for '{fn.name}'"
    )
    rprint(fn)
    not_include_implementation_first = (fn.name == "main" and not snapshot.ctx.locals) or fn.obtaining_missing_info
    msgs = self.agent.system_coder()
    msgs.extend(
      render_messages_template(
        "templates/v12/compound_vs_atomic.md",
        snapshot=snapshot,
        app_descriptions=self.agent.show_app_descriptions(exclude=["api_docs"]),
        instruction=self.agent.world.task.instruction,
        include_implementation_first=not not_include_implementation_first,
      )
    )
    parsed, response = generate_json_dict(
      self.agent.generate,
      msgs,
      reasoning={"effort": "none"},
      max_retries=3,
      json_schema={
        "type": "object",
        "required": ["mode", "strategy"],
        "properties": {
          "mode": {
            "type": "string",
            "pattern": "(?i)^(plan-first|exploration-first"
              + ("|implementation-first" if not not_include_implementation_first else "")
              + ")$"
          },
          "strategy": {"type": "string"}
        },
      }
    )
    mode = parsed["mode"].lower()
    if mode == "plan-first":
      return [Plan(scope=fn.name, before_action=self)]
    elif mode == "exploration-first":
      return [Explore(scope=fn.name, target=parsed["strategy"], before_action=self)]
    elif mode == "implementation-first":
      return [
        Trivial(scope=fn.name, target=parsed["strategy"], before_action=self),
        Explore(
          scope=fn.name,
          target=f"Find primary APIs that are CLOSEST to the expected functionality of `{fn.name}`.",
          before_action=self,
        ),
      ]
    else:
      raise ValueError(f"Classify: unexpected mode={mode!r}")


class Plan(CodeGenAction):

  def take(self, snapshot: Snapshot) -> list[Fn]:
    raise NotImplementedError(self.__class__)


class Explore(CodeGenAction):

  # Resume state from previous GatherContext steps
  target: str
  chosen_but_unexplored_apps: list[str] = []
  chosen_but_unexplored_apis: list[str] = []
  explored_apis: list[str] = []
  discard_unexplored: bool = False

  # Saved after take() so the evaluation can resume the same thread
  # invoke_msgs: Msgs | None = None
  invoked_app_apis: str | None = None

  def _prev_gather(self):
    """Walk before_action chain to find the previous Explore or GatherContextNew."""
    action = self.before_action
    while action is not None:
      if isinstance(action, Explore):
        return action
      action = action.before_action
    return None

  def take(self, snapshot: Snapshot) -> list[Fn]:
    fn = snapshot.fn
    # Inherit resume state from previous GatherContext
    prev = self._prev_gather()
    explored_apis = list(prev.explored_apis) if prev else []
    explored_docs = {}
    for api in explored_apis:
      a, n = api.split(".")
      explored_docs[api] = self.agent.show_api_doc(a, n)

    if self.discard_unexplored:
      chosen_but_unexplored_apps = []
      chosen_but_unexplored_apis = []
    else:
      chosen_but_unexplored_apps = list(prev.chosen_but_unexplored_apps) if prev else []
      chosen_but_unexplored_apis = list(prev.chosen_but_unexplored_apis) if prev else []

    # --- Step 0: If past Explores exist, ask whether to re-invoke ---
    reinvoke_app_apis = {}
    if explored_docs:
      reinvoke_app_apis = self._should_reinvoke(snapshot, explored_docs)
      if len(reinvoke_app_apis["re-invoke"]) > 0:
        logger.info("Explore.take: re-invoking %s (skipping discovery)", reinvoke_app_apis)

    if reinvoke_app_apis:
      qualified_apis = reinvoke_app_apis
      invoke_msgs = self.agent.system_coder()
      invoke_msgs.extend(
        render_messages_template(
          "templates/v12/should_reinvoke.md",
          snapshot=snapshot,
          explored_apis=explored_docs,
          rationale=self.target,
          include_response_format=False,
        )
      )
      invoke_msgs.add(
        role="assistant",
        content=(
          f"Decided. {reinvoke_app_apis["rationale"]}\n\n"
          f"# API{'s' if len(reinvoke_app_apis['re-invoke']) > 1 else ''} TO RE-INVOKE\n"
          f"{'.'.join(f"- {app_api}" for app_api in reinvoke_app_apis['re-invoke'])}"
        )
      )
      observed_variables = self._observed_variables(snapshot, include_inner=False)
      invoke_msgs.extend(
        render_messages_template(
          "templates/v12/reinvoke_apis.md",
          global_variables=self.agent.globals(),
          snapshot=snapshot,
          working_memory=self.agent.working_memory,
          observed_variables=observed_variables,
          include_why=True,
          rationale=self.target,
          reinvoke_app_apis=reinvoke_app_apis['re-invoke'],
          include_response_format=False,
        )
      )
      code, response = generate_python_def(
        self.generate,
        invoke_msgs,
        reasoning={"effort": "none"},
        max_retries=3,
        target=snapshot.fn.name,
        remove_docstrings=True,
        remove_comments=True,
        hoist_inner_functions=True,
      )
      raise
    else:
      qualified_apis, apps = self._discover_app_apis(
        snapshot,
        explored_apis,
        chosen_but_unexplored_apis,
        chosen_but_unexplored_apps
      )
      self.invoked_app_apis = qualified_apis
      logger.info("Explore.take: invoking %s", qualified_apis)
      app_name, api_name = qualified_apis[0].split(".")
      observed_variables = self._observed_variables(snapshot, include_inner=False)
      invoke_msgs = render_messages_template(
        "templates/v12/invoke_api.md",
        global_variables=self.agent.globals(),
        snapshot=snapshot,
        app_name=app_name,
        api_name=api_name,
        api_doc=self.agent.show_api_doc(app_name=app_name, api_name=api_name),
        working_memory=self.agent.working_memory,
        observed_variables=observed_variables,
        include_why=True,
        rationale=self.target
      )
      code, response = generate_python_def(
        self.generate,
        invoke_msgs,
        reasoning={"effort": "none"},
        max_retries=3,
        target=snapshot.fn.name,
        remove_docstrings=True,
        remove_comments=True,
        hoist_inner_functions=True,
      )
      code = self.agent.remove_print_statements(code, snapshot.ctx)
      code = self.ensure_no_void_calls(code, snapshot)
      code = self.sanitize_and_fix_api_calls(code, snapshot, app_name, api_name)
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
        "Explore.take: saved state → explored=%s, unexplored_apis=%s, unexplored_apps=%s",
        self.explored_apis,
        self.chosen_but_unexplored_apis,
        self.chosen_but_unexplored_apps
      )
      return [fn.update(body=parse_fn_body(code))]

    raise
    primary_app_name, primary_api_name = qualified_apis[0]
    target_apis = [
      {"app_name": a, "api_name": n, "doc": self.agent.show_api_doc(a, n)}
      for a, n in target_apis
    ]

    # --- Pick the best API and generate code ---
    logger.info("GatherContext: invoking %s", target_apis)
    observed_variables = self._observed_variables(snapshot, include_inner=False)
    invoke_msgs = render_messages_template(
      "templates/v12/invoke_api.md",
      global_variables=self.agent.globals(),
      snapshot=snapshot,
      apis=target_apis,
      working_memory=self.agent.working_memory,
      observed_variables=observed_variables,
      include_why=True,
      rationale=self.target
    )
    code, response = generate_python_def(
      self.generate,
      invoke_msgs,
      reasoning={"effort": "none"},
      max_retries=3,
      target=snapshot.fn.name,
      remove_docstrings=True,
      remove_comments=True,
      hoist_inner_functions=True,
    )
    code = self.agent.remove_print_statements(code, snapshot.ctx)
    code = self.ensure_no_void_calls(code, snapshot)
    if not reinvoke_apis:
      code = self.sanitize_and_fix_api_calls(code, snapshot, primary_app_name, primary_api_name)
    code = remove_returns(code)
    if not reinvoke_apis:
      code = truncate_execution_flow(code, f"{primary_app_name}.{primary_api_name}")
    code = self.rename_existing_helpers(code, snapshot)

    # --- Save resume state for next GatherContext ---
    if not reinvoke_apis:
      qualified_apis = [f"{info['app_name']}.{info['api_name']}" for info in target_apis]
      used_api = f"{primary_app_name}.{primary_api_name}"
      self.explored_apis = explored_apis + [used_api]
      self.chosen_but_unexplored_apis = [a for a in qualified_apis if a != used_api]
      apps_with_qualified = {a.split(".")[0] for a in self.chosen_but_unexplored_apis}
      remaining_apps = [a for a in apps if a != primary_app_name and a not in apps_with_qualified]
      carried_apps = [a for a in chosen_but_unexplored_apps if a not in apps and a not in apps_with_qualified]
      self.chosen_but_unexplored_apps = remaining_apps + carried_apps
    logger.info(
      "GatherContext: saved state → explored=%s, unexplored_apis=%s, unexplored_apps=%s",
      self.explored_apis, self.chosen_but_unexplored_apis, self.chosen_but_unexplored_apps
    )
    return [fn.update(body=parse_fn_body(code))]

  def _discover_app_apis(
    self,
    snapshot,
    explored_apis,
    chosen_but_unexplored_apis,
    chosen_but_unexplored_apps
  ):

    logger.info(
      "Explore._discover_app_apis: fn='%s', explored_apis=%s, unexplored_apis=%s, unexplored_apps=%s",
      snapshot.fn.name, explored_apis, chosen_but_unexplored_apis, chosen_but_unexplored_apps
    )
    max_retries = 3
    for retry in range(max_retries):
      # --- Step 1: Choose apps ---
      if chosen_but_unexplored_apis:
        apps = [chosen_but_unexplored_apis[0].split(".")[0]]
        assert apps[0] not in chosen_but_unexplored_apps, (
          f"Explore._discover_app_apis: app '{apps[0]}' from chosen_but_unexplored_apis "
          f"should not be in chosen_but_unexplored_apps={chosen_but_unexplored_apps}"
        )
        logger.info(
          "Explore._discover_app_apis: resuming from unexplored APIs %s → apps=%s",
          chosen_but_unexplored_apis, apps
        )
      elif chosen_but_unexplored_apps:
        apps = chosen_but_unexplored_apps
        logger.info(
          "GatherContext: resuming from unexplored apps %s",
          chosen_but_unexplored_apps
        )
      else:
        logger.info("Explore._discover_app_apis: fresh app selection (retry=%d)", retry)
        gen_msgs = self.agent.system_coder()
        gen_msgs.extend(
          render_messages_template(
            "templates/v12/gather_context_1.md",
            snapshot=snapshot,
            rationale=self.target,
          )
        )
        parsed, response = generate_json_dict(
          self.agent.generate, 
          gen_msgs, 
          reasoning={"effort": "none"},
          max_retries=3,
          json_schema={
            "type": "object",
            "required": ["rationale", "apps"],
            "properties": {
              "rationale": {"type": "string"},
              "apps": {
                "type": "array",
                "items": {
                    "type": "string"
                  }
              }
            },
          }
        )
        apps = parsed["apps"]
        logger.info("Explore._discover_app_apis: LLM chose apps=%s", apps)

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
          "templates/v12/gather_context_1.md",
          snapshot=snapshot,
          rationale=self.target,
          include_response_format=False
        )
      )
      msgs.add(
        role="assistant",
        content=", ".join(f"`{app_name}`" for app_name in apps)
      )

      if chosen_but_unexplored_apis:
        logger.info("Explore._discover_app_apis: skipping steps 2-3, reusing qualified APIs %s", chosen_but_unexplored_apis)
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
            "templates/v12/gather_context_2.md",
            snapshot=snapshot,
            apis_by_candidate_app=apis_by_candidate_app
          )
        )
        parsed, response = generate_json_dict(
          self.generate, 
          gen_msgs, 
          reasoning={"effort": "none"},
          max_retries=3,
          json_schema={
            "type": "object",
            "required": ["rationale", "apis"],
            "properties": {
              "rationale": {"type": "string"},
              "apis": {
                "type": "array",
                "items": {
                    "type": "string"
                  }
              }
            },
          }
        )
        apis = parsed["apis"]
        logger.info("Explore._discover_app_apis: LLM chose APIs to inspect: %s", apis)
        api_doc_by_api = {}
        for api in apis:
          app_name, api_name = api.split(".")
          api_doc_by_api[api] = self.agent.show_api_doc(app_name, api_name)

      msgs.extend(
        render_messages_template(
          "templates/v12/gather_context_2.md",
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
            "templates/v12/gather_context_3.md",
            snapshot=snapshot,
            api_doc_by_api=api_doc_by_api
          )
        )
        parsed, response = generate_json_dict(
          self.generate, 
          gen_msgs, 
          reasoning={"effort": "none"},
          max_retries=3,
          json_schema={
            "type": "object",
            "required": ["rationale", "qualified_apis"],
            "properties": {
              "rationale": {"type": "string"},
              "apis": {
                "type": "array",
                "items": {
                    "type": "string"
                  }
              }
            },
          }
        )
        qualified_apis = parsed["qualified_apis"]
        logger.info("Explore._discover_app_apis: qualified APIs: %s", qualified_apis)

      if not qualified_apis:
        if chosen_but_unexplored_apis:
          logger.warning(
            "Explore._discover_app_apis: no qualified APIs from unexplored_apis=%s → falling back to unexplored_apps=%s",
            chosen_but_unexplored_apis, chosen_but_unexplored_apps
          )
          chosen_but_unexplored_apis = []
        elif chosen_but_unexplored_apps:
          logger.warning(
            "Explore._discover_app_apis: no qualified APIs from unexplored_apps=%s → falling back to fresh app selection",
            chosen_but_unexplored_apps
          )
          chosen_but_unexplored_apps = []
        else:
          logger.warning("Explore._discover_app_apis: no qualified APIs from fresh selection → retrying (retry=%d)", retry)
        continue
      break
    else:
      raise NotImplementedError(
        f"Explore._discover_app_apis: no qualified APIs found after {max_retries} retries "
        f"(explored_apis={explored_apis})"
      )

    return qualified_apis, apps

  def _should_reinvoke(self, snapshot: Snapshot, explored_docs: dict[str, dict[str, Any]]) -> str | None:
    """Ask LLM whether to re-invoke a previously explored API or explore new ones."""

    max_retries = 3
    for _ in range(max_retries):
      try:
        msgs = self.agent.system_coder()
        msgs.extend(
          render_messages_template(
            "templates/v12/should_reinvoke.md",
            snapshot=snapshot,
            explored_apis=explored_docs,
            rationale=self.target,
          )
        )
        parsed, response = generate_json_dict(
          self.generate,
          msgs,
          reasoning={"effort": "none"},
          max_retries=3,
          json_schema={
            "type": "object",
            "required": ["rationale", "re-invoke"],
            "properties": {
              "rationale": {"type": "string"},
              "re-invoke": {
                "type": "array",
                "items": {"type": "string"}
              },
            },
          }
        )
        for app_api in parsed["re-invoke"]:
          if app_api not in explored_docs:
            logger.warning("Explore._should_reinvoke: LLM chose '%s' but not in explored_apis=%s", app_api, list(explored_docs.keys()))
            raise
        break
      except Exception as e:
        pass
    else:
      raise
      
    return parsed


class Trivial(CodeGenAction):
  """Try to implement the function directly without API exploration.

  If the LLM determines all required information is available, it returns
  a full implementation. If it raises NeedMoreInformation, the function body
  is kept as-is (containing the raise), so the execution engine detects it
  and the refinement tree falls back to exploration.
  """
  target: str  # strategy description from _compound_vs_atomic

  def take(self, snapshot: Snapshot) -> list[Fn]:
    fn = snapshot.fn
    observed_variables = self._observed_variables(snapshot, include_inner=False)
    msgs = self.agent.system_coder()
    msgs.extend(
      render_messages_template(
        "templates/v12/try_trivial.md",
        global_variables=self.agent.globals(),
        snapshot=snapshot,
        observed_variables=observed_variables,
      )
    )
    code, response = generate_python_def(
      self.generate,
      msgs,
      target=fn.name,
      reasoning={"effort": "none"},
      max_retries=3,
      remove_docstrings=True,
      remove_comments=True,
    )
    code = self.agent.remove_print_statements(code, snapshot.ctx)
    code = self._check_need_more_info(code, msgs, fn)
    return [fn.update(body=reindent(parse_fn_body(code), indent=Fn.indent))]

  def _check_need_more_info(self, code: str, msgs: Msgs, fn: Fn, max_retries: int = 2) -> str:
    """If NeedMoreInformation is mixed with other statements, reprompt to use AssertionError instead."""
    for _ in range(max_retries):
      if not has_mixed_need_more_info(code):
        return code
      fix_msgs = Msgs()
      fix_msgs.add(
        role="user",
        content=(
          "The function below mixes real implementation with `raise NeedMoreInformation(...)`. "
          "This is not allowed. Either:\n"
          "1. Implement fully WITHOUT any `NeedMoreInformation`, using `raise AssertionError(...)` "
          "for unexpected execution paths, OR\n"
          "2. Give up entirely with ONLY `raise NeedMoreInformation(...)` as the sole body statement.\n\n"
          f"```python\n{code}\n```"
        ),
      )
      _, code = self.generate_fn(fix_msgs, fn, reasoning={"effort": "none"})
      code = remove_comments(code)
    return code


class Diagnose(MetaAction):
  """Diagnose runtime errors after Explore.

  Classifies each cause as 'sufficient' (fixable with available info)
  or 'insufficient' (needs data from another API call).
  """

  target: str
  invoked_app_apis: list[str]

  def take(self, snapshot: Snapshot) -> list[CodeGenAction | MetaAction]:
    overarching_action = self._find_ancestor(Explore)
    assert overarching_action is not None
    logger.info(
      f"Diagnose.take: during {overarching_action} (target='{overarching_action.target}')"
    )
    fn = snapshot.fn
    observed_variables = self._observed_variables(snapshot, include_inner=False)
    assert len(self.invoked_app_apis) == 1
    app_name, api_name = self.invoked_app_apis[0].split(".")
    msgs = self.agent.system_coder()
    msgs.extend(
      render_messages_template(
        "templates/v12/diagnose.md",
        snapshot=snapshot,
        app_descriptions=self.agent.show_app_descriptions(exclude=["api_docs"]),
        instruction=self.agent.world.task.instruction,
        observed_variables=observed_variables,
        rationale=self.target,
        app_name=app_name,
        api_name=api_name,
        api_doc=self.agent.show_api_doc(app_name=app_name, api_name=api_name),
        solved_helpers=self.agent.working_memory.solved_helpers,
      )
    )
    parsed, response = generate_json_dict(
      self.agent.generate,
      msgs,
      reasoning={"effort": "low"},
      max_retries=3,
      json_schema={
        "type": "object",
        "required": ["sufficient", "insufficient"],
        "properties": {
          "sufficient": {
            "type": "array",
            "items": {"type": "string"}
          },
          "insufficient": {
            "type": "array",
            "items": {"type": "string"}
          }
        },
      }
    )
    next_actions = []
    for diagnosis in parsed.get("sufficient", []):
      next_actions.append(
        LocalFix(
          scope=fn.name,
          diagnosis=diagnosis,
          app_name=app_name,
          api_name=api_name,
          before_action=self,
        )
      )
    for diagnosis in parsed.get("insufficient", []):
      next_actions.append(
        Restructure(
          scope=fn.name,
          diagnosis=diagnosis,
          app_name=app_name,
          api_name=api_name,
          before_action=self,
        )
      )
    return next_actions


class LocalFix(CodeGenAction):
  """Fix a runtime error using only information already available in scope."""

  diagnosis: str
  app_name: str
  api_name: str

  def take(self, snapshot: Snapshot) -> list[Fn]:
    overarching_action = self._find_ancestor(Explore)
    assert overarching_action is not None
    logger.info(
      f"LocalFix.take: during {overarching_action} (target='{overarching_action.target}')"
    )
    app_name, api_name = self.app_name, self.api_name
    fn = snapshot.fn
    observed_variables = self._observed_variables(snapshot, include_inner=False)
    msgs = self.agent.system_coder()
    msgs.extend(
      render_messages_template(
        "templates/v12/local_fix.md",
        snapshot=snapshot,
        app_descriptions=self.agent.show_app_descriptions(exclude=["api_docs"]),
        instruction=self.agent.world.task.instruction,
        observed_variables=observed_variables,
        rationale=overarching_action.target,
        app_name=app_name,
        api_name=api_name,
        api_doc=self.agent.show_api_doc(app_name=app_name, api_name=api_name),
        solved_helpers=self.agent.working_memory.solved_helpers,
        diagnosis=self.diagnosis
      )
    )
    code, response = generate_python_def(
      self.generate,
      msgs,
      reasoning={"effort": "none"},
      max_retries=3,
      target=snapshot.fn.name,
      remove_docstrings=True,
      remove_comments=True,
      hoist_inner_functions=True,
    )
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
    raise NotImplementedError(
      f"LocalFix.take: new_unknown_calls={new_unknown_calls}"
    )


class Restructure(CodeGenAction):
  """Replace a problematic parameter with a helper function call.

  The helper will be resolved by the existing FunctionNotFound → child SubAgent
  mechanism in the solve loop.
  """

  diagnosis: str
  app_name: str
  api_name: str

  def take(self, snapshot: Snapshot) -> list[Fn]:
    fn = snapshot.fn
    msgs = self.agent.system_coder()
    msgs.extend(
      render_messages_template(
        "templates/v12/restructure.md",
        global_variables=self.agent.globals(),
        globals_accessed=self.agent.globals_accessed(snapshot.fn),
        snapshot=snapshot,
        feedback=self.feedback,
        app_name=self.app_name,
        api_name=self.api_name,
        api_doc=self.agent.show_api_doc(app_name=self.app_name, api_name=self.api_name),
        solved_helpers=self.agent.working_memory.solved_helpers.get(fn.name, {}),
      )
    )
    _, code = self.generate_fn(msgs, fn, reasoning={"effort": "none"})
    code = self.agent.remove_print_statements(code, snapshot.ctx)
    code = self.ensure_no_void_calls(code, snapshot)
    code = self.rename_existing_helpers(code, snapshot)
    return [
      fn.update(
        body=reindent(parse_fn_body(code), indent=Fn.indent)
      )
    ]



























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


class Certification(CodeGenAction):

  def take(self, snapshot: Snapshot) -> list[Fn]:
    fn = snapshot.fn
    msgs = self.agent.system_coder()
    msgs.extend(
      render_messages_template(
        "templates/v12/check_and_summarize_before_return.md",
        snapshot=snapshot,
      )
    )
    (code, evaluation), response = generate_code_or_json(
      self.generate,
      msgs,
      target=fn.name,
      remove_docstrings=True,
      remove_comments=True,
      max_retries=3,
    )
    if code is not None:
      # "yes" — LLM returned transformed code
      return [fn.update(body=reindent(parse_fn_body(code), indent=Fn.indent))]
    else:
      # "no" — LLM returned JSON with rationale
      logger.info(
        "Certification: evaluation='no' for '%s', rationale: %s",
        fn.name, evaluation.get("rationale", ""),
      )
      return None


class NOP(CodeGenAction):

  def take(self, snapshot: Snapshot) -> list[Fn]:
    logger.info(
      "NOP: passing through '%s' unchanged (before_action=%s)",
      snapshot.fn.name,
      type(self.before_action).__name__ if self.before_action else None,
    )
    return [snapshot.fn.update()]


class Adapt(CodeGenAction):

  helper: str
  return_value: dict[str, Any]

  def take(self, snapshot: Snapshot) -> list[Fn]:
    helper_fn = snapshot.solution[self.helper]
    if isinstance(helper_fn, FnApiParam):
      # FnApiParam → originated from Atomic/GatherContext/GoAheadWithApi branch
      assert self._find_ancestor(Explore) is not None, (
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
    raise
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