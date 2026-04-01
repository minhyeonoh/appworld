# 정보 제약하에서의 robust planning

from __future__ import annotations

import ast
import json
import json_repair
import os
import re
from collections import defaultdict
from contextlib import contextmanager
from typing import Any, cast
from jinja2 import Template
from rich import print as rprint
from munch import munchify, unmunchify

from anytree import NodeMixin
from appworld import AppWorld
from appworld.common.io import read_file
from appworld.common.my_code_parsing import *
import appworld.common.my_code_parsing as codeparse
from appworld_agents.code.my.agent import Agent
from appworld_agents.code.my.message import *
import appworld_agents.code.my.actions as actions
from appworld_agents.code.my.fn import *
from appworld_agents.code.my.json_parser import generate_json_dict, fn_info_schema, BUILTIN_TYPE_PATTERN
from appworld_agents.code.my.python_def_parser import generate_python_def

import logging
logger = logging.getLogger("peter")
_LOG_FMT = logging.Formatter("[%(asctime)s %(levelname)s] %(name)s | %(message)s", datefmt="%H:%M:%S")
if not logger.handlers:
    _stderr = logging.StreamHandler()
    _stderr.setFormatter(_LOG_FMT)
    logger.addHandler(_stderr)
    logger.setLevel(logging.DEBUG)


def pop_tagged_content(text: str, tag: str):
  # 정규식: <__debug_context__> 태그 안의 내용과, 나머지 부분을 분리
  # (?s)는 .이 줄바꿈 문자도 매칭하도록 하는 옵션
  pattern = rf"<{tag}>(?P<content>.*?)</{tag}>"
  if not (m := re.search(pattern, text, re.DOTALL)):
    return None, text
  else:
    content = m.group("content")
    return content.strip(), re.sub(pattern, "", text, 1, re.DOTALL).strip()

RaiseFunctionNotFound = "raise FunctionNotFound(inspect.currentframe().f_code.co_name)"
RaiseFunctionNotFeasible = "raise FunctionNotFeasible(inspect.currentframe().f_code.co_name)"

DONE = object()
PENDING = object()

class RefinementNode(NodeMixin):
  """Refinement tree node. Root holds the initial snapshot (action=None).
  Children are edges: action applied to parent's snapshot, result starts as PENDING."""

  def __init__(self, snapshot: Snapshot, action: actions.Action | None = None, parent=None):
    super().__init__()
    self.snapshot = snapshot
    self.action = action
    self.result = PENDING if action else snapshot
    self.parent = parent

  def add_child(self, action: actions.Action):
    return RefinementNode(snapshot=self.result, action=action, parent=self)

  def resolve(self, result_snapshot: Snapshot):
    self.result = result_snapshot

  def explore(self):
    """DFS for the first PENDING node."""
    if self.result is PENDING:
      return self
    for child in self.children:
      if (found := child.explore()) is not None:
        return found
    return None

_DIR = os.path.dirname(os.path.abspath(__file__))


# ------------------------------------------------------------------
# Standalone helpers (used by both PeTER and SubAgent)
# ------------------------------------------------------------------

_api_doc_cache: dict[int, dict] = {}  # keyed by id(world)

def _ensure_cache(world: AppWorld) -> dict:
  wid = id(world)
  if wid not in _api_doc_cache:
    _api_doc_cache[wid] = {"apps": None, "api_descs": {}, "api_docs": {}}
  return _api_doc_cache[wid]

def invalidate_api_doc_cache(world: AppWorld):
  _api_doc_cache.pop(id(world), None)

def show_app_descriptions(world: AppWorld, exclude: list = []):
  cache = _ensure_cache(world)
  if cache["apps"] is None:
    cache["apps"] = json.loads(
      world.execute(f"print(apis.api_docs.show_app_descriptions())", save_state=False)
    )
  return [app for app in cache["apps"] if app["name"] not in exclude]

def show_api_descriptions(world: AppWorld, app_name: str, exclude: list = []):
  cache = _ensure_cache(world)
  if app_name not in cache["api_descs"]:
    cache["api_descs"][app_name] = json.loads(
      world.execute(f"print(apis.api_docs.show_api_descriptions(app_name='{app_name}'))", save_state=False)
    )
  return [api for api in cache["api_descs"][app_name] if api["name"] not in exclude]

def show_api_doc(world: AppWorld, app_name: str, api_name: str):
  cache = _ensure_cache(world)
  key = (app_name, api_name)
  if key not in cache["api_docs"]:
    cache["api_docs"][key] = json.loads(
      world.execute(f"print(apis.api_docs.show_api_doc(app_name='{app_name}', api_name='{api_name}'))", save_state=False)
    )
  return cache["api_docs"][key]

def get_api_doc(world: AppWorld, app_name: str, api_name: str, default: Any = None):
  cache = _ensure_cache(world)
  key = (app_name, api_name)
  if key not in cache["api_docs"]:
    # Check app/api existence without fetching all docs
    apps = show_app_descriptions(world)
    if not any(app["name"] == app_name for app in apps):
      return default
    apis = show_api_descriptions(world, app_name)
    if not any(api["name"] == api_name for api in apis):
      return default
    cache["api_docs"][key] = json.loads(
      world.execute(f"print(apis.api_docs.show_api_doc(app_name='{app_name}', api_name='{api_name}'))", save_state=False)
    )
  return cache["api_docs"][key]


def make_globals(task) -> str:
  today = task.datetime
  supervisor = task.supervisor
  return (
f"""
# Global variables (available anywhere)
today: datetime = datetime.fromisoformat({json.dumps(today.isoformat())}) # today's date
my_name_first: str = {json.dumps(supervisor.first_name)} # my first name
my_name_last: str = {json.dumps(supervisor.last_name)} # my last name
my_email: str = {json.dumps(supervisor.email)} # my email address
my_phone_number: str = {json.dumps(supervisor.phone_number)} # my phone number
"""
  ).strip()


def globals_names() -> list[str]:
  return ["today", "my_name_first", "my_name_last", "my_email", "my_phone_number"]


# ------------------------------------------------------------------
# SubAgent: owns algorithm, LM, world
# ------------------------------------------------------------------

class SubAgent(NodeMixin):

  # Class-level shared infrastructure — set once via setup() before creating any instance
  language_models: dict = None
  world: AppWorld = None
  logger_: Any = None
  usage_tracker: Any = None
  working_memory: WorkingMemory = None
  on_extra_functions: str = "ignore"
  _dashboard_log: Any = None  # DashboardLog (optional)

  @classmethod
  def setup(cls, *, language_models, world, logger_, usage_tracker, working_memory, on_extra_functions="ignore", dashboard_log=None):
    cls.language_models = language_models
    cls.world = world
    cls.logger_ = logger_
    cls.usage_tracker = usage_tracker
    cls.working_memory = working_memory
    cls.on_extra_functions = on_extra_functions
    cls._dashboard_log = dashboard_log

  def __init__(
    self,
    fn: Fn,
    solution: Solution,
    lib: Library,
    parent: SubAgent | None = None,
  ):
    super().__init__()
    self.name = fn.name
    self.lib = lib
    self.parent = parent
    self.refinement_root: RefinementNode | None = None
    self.result: tuple[Solution, Library] | None = None
    self.trivially_solved: bool = False
    self.trivially_solved_helpers: set[str] = set()

    # Create initial snapshot
    f = fn.name
    solution = solution.update(fn)
    ctx = self.run(f, solution)
    assert ctx.scope == f, f"solve: initial run scope mismatch — expected '{f}', got '{ctx.scope}'"
    self.snapshot = Snapshot(fn=fn, solution=solution, ctx=ctx)
    if self._dashboard_log:
      self._dashboard_log.subagent_created(self)

  # ------------------------------------------------------------------
  # Context manager for Action binding
  # ------------------------------------------------------------------

  @contextmanager
  def as_active_agent(self):
    prev = actions.Action._agent
    actions.Action.setup_agent(self)
    try:
      yield
    finally:
      actions.Action._agent = prev

  # ------------------------------------------------------------------
  # Generation methods (moved from Agent)
  # ------------------------------------------------------------------

  def generate(self, messages, name="coder", prefix: str | None = None, retry_on=lambda response: False, max_retries: int = 3, use_prefix=True, **kwargs) -> Msg:
    messages = messages.copy()
    with open("my/messages.md", "w") as fout:
      for message in messages:
        fout.write(f"{message.role.upper()}:\n")
        fout.write(f"{message.content}\n\n")
    if prefix is not None and use_prefix:
      kwargs.update(dict(extra_body={"chat_template_kwargs": {"enable_thinking": False}}))
      kwargs.update(dict(
        add_generation_prompt=False,
        continue_final_message=True
      ))
      messages.add(role="assistant", content=prefix)
    for attempt in range(max_retries):
      response = self.language_models[name].generate(
        messages=messages.model_dump(), cache_control_at=None, **kwargs
      )
      response = Msg(**response)
      if not retry_on(response):
        break
    reasoning_content = getattr(response, "reasoning_content", None)
    self.logger_.show_message(
      role="agent",
      content=response.content,
      reasoning_content=reasoning_content,
    )
    if self._dashboard_log:
      self._dashboard_log.message("agent", response.content, reasoning_content)
    with open("my/agent-response.txt", "a") as fout:
      fout.write(
f"""
ASSISTANT:
{f'[reasoning_content]\n{reasoning_content}\n[/reasoning_content]\n' if reasoning_content else ''}{response.content}
"""
      )
    if prefix is not None and use_prefix:
      response.content = prefix + response.content
      return response
    return response

  def generate_defn(self, messages, defn, prefix=True, **kwargs):
    if prefix:
      response = self.generate(messages, prefix=f"```python", **kwargs)
    else:
      response = self.generate(messages, **kwargs)
    code = extract_python_function_defs(
      response.content, defn.name, reindent=defn.indent
    )
    code = remove_docstring(code)
    return response, code

  def generate_function_defs(
    self,
    messages,
    defn,
    hoist_inner_functions=True,
    remove_docstrings=True,
    remove_comments=True,
    prefix=True,
  ):
    def maybe_cleanup(code):
      if remove_docstrings:
        code = remove_docstring(code)
      if remove_comments:
        code = codeparse.remove_comments(code)
      return code

    if prefix:
      response = self.generate(messages, prefix=f"```python\n{defn.header()}:\n")
    else:
      response = self.generate(messages)
    function_defs = {}
    for name, code in (
      extract_python_function_defs(
        response.content, reindent=defn.indent
      ).items()
    ):
      function_defs[name] = maybe_cleanup(code)
      if hoist_inner_functions:
        for inner_name, inner_code in (
          lift_inner_functions(code, cleanup=True).items()
        ):
          function_defs[inner_name] = maybe_cleanup(inner_code)
    return function_defs

  def generate_with_think(self, messages, prefix=True, **kwargs):
    if prefix:
      response = self.generate(messages, prefix='```\n{\n  "reason": "', **kwargs)
    else:
      response = self.generate(messages, **kwargs)

    print(response.content)
    codes = []
    try:
      code, = extract_python_codes(response.content)
      codes.append(code)
    except Exception:
      pass
    try:
      code, = extract_fenced_chunks(response.content)
      codes.append(code)
    except:
      pass
    try:
      code, = extract_fenced_chunks(f"```\n{response.content}```")
      codes.append(code)
    except Exception:
      pass
    if not codes:
      raise AssertionError()
    print(codes)
    objs = []
    for code in codes:
      try:
        think_and_answer = json.loads(code)
        objs.append(think_and_answer)
      except Exception:
        # Try extracting "reason"/"think" field separately before json_repair,
        # because json_repair truncates values containing unescaped inner quotes.
        extracted = self._extract_think_then_parse(code)
        if extracted is not None:
          objs.append(extracted)
        else:
          try:
            think_and_answer = json_repair.loads(code)
            objs.append(think_and_answer)
          except Exception:
            pass
    if not objs:
      raise AssertionError()
    print(objs)
    for obj in objs:
      try:
        think = obj.pop("reason")
        break
      except Exception:
        try:
          think = obj.pop("think")
          break
        except:
          pass
    else:
      raise AssertionError()
    return response, think, obj

  @staticmethod
  def _extract_think_then_parse(code: str):
    """Extract the reason/think field as raw text, then JSON-parse the rest.

    LLMs often embed unescaped quotes inside the reason string, which breaks
    json.loads and causes json_repair to truncate.  We find the boundary
    between the reason value and the next JSON key, split there, and only
    ask json.loads to handle the well-structured remainder.
    """
    for key in ("reason", "think"):
      # Match: "reason": "...VALUE...",\n  "next_key"
      # We look for  ",\n followed by optional whitespace and a quote
      # that starts the next key — this is the split point.
      pattern = rf'"{key}"\s*:\s*"'
      m = re.search(pattern, code)
      if m is None:
        continue
      value_start = m.end()
      # Find the boundary: a quote-comma-newline-whitespace-quote sequence
      # that signals the end of this string value and start of the next key.
      boundary = re.search(r'",\s*\n\s*"', code[value_start:])
      if boundary is None:
        continue
      reason_text = code[value_start:value_start + boundary.start()]
      rest_json = "{" + code[value_start + boundary.start() + 1:]  # skip the closing quote
      rest_json = rest_json.strip().rstrip("}")  .strip().rstrip(",").strip()
      # rest_json now looks like: { "next_key": ... }  — but missing closing brace
      rest_json = rest_json + "}"
      try:
        obj = json.loads(rest_json)
      except Exception:
        try:
          obj = json_repair.loads(rest_json)
        except Exception:
          continue
      obj[key] = reason_text
      return obj
    return None

  def generate_dict(self, messages, prefix_key, prefix=True, **kwargs):
    if prefix:
      response = self.generate(messages, prefix=f'```python\n{{  "{prefix_key}": "', **kwargs)
    else:
      response = self.generate(messages, **kwargs)

    response.content = response.content.replace("```json", "```python")
    code, = extract_python_codes(response.content)
    return ast.literal_eval(code), response

  # ------------------------------------------------------------------
  # API doc methods (use self.world)
  # ------------------------------------------------------------------

  def show_app_descriptions(self, exclude: list = []):
    return show_app_descriptions(self.world, exclude)

  def show_api_descriptions(self, app_name: str, exclude: list = []):
    return show_api_descriptions(self.world, app_name, exclude)

  def show_api_doc(self, app_name: str, api_name: str):
    return show_api_doc(self.world, app_name, api_name)

  def get_api_doc(self, app_name: str, api_name: str, default: Any = None):
    return get_api_doc(self.world, app_name, api_name, default)

  def isapi(self, name: str):
    parts = name.split(".")
    if len(parts) != 2:
      return False
    app_name, api_name = parts
    return self.get_api_doc(app_name, api_name) is not None

  def _get_api_doc(self, name: str):
    parts = name.split(".")
    if len(parts) != 2:
      return None
    app_name, api_name = parts
    return self.get_api_doc(app_name, api_name)

  # ------------------------------------------------------------------
  # Globals helpers
  # ------------------------------------------------------------------

  def globals(self):
    return make_globals(self.world.task)

  def globals_names(self):
    return globals_names()

  def globals_accessed(self, fn, **dumps_kwargs):
    qualified_names = get_qualified_names(
      f"from __globals__ import {', '.join(self.globals_names())}\n"
      + fn.dumps(**dumps_kwargs)
    )
    return any(
      qualified_name.source == QualifiedNameSource.IMPORT and
      qualified_name.name.startswith("__globals__") for qualified_name in qualified_names.values()
    )

  # ------------------------------------------------------------------
  # Execution
  # ------------------------------------------------------------------

  def run(self, f: str, solution: Solution, pause_after: str | None = None, save_state: bool = False) -> Ctx:
    code = solution.dumps(current_scope=f, pause_after=pause_after)
    with open(".code.py", "w") as fout:
      fout.write(code)
    output = self.world.execute(code, save_state=save_state)
    stdout, raw_tb = pop_tagged_content(output, "stdout")
    if stdout is None:
      stdout, raw_tb = output, None
    ctx, _ = pop_tagged_content(stdout, "context")
    try:
      ctx = munchify(json.loads(ctx))
    except Exception:
      raise
    assert f == ctx.scope, (
      f"run: scope mismatch — expected f='{f}', got ctx.scope='{ctx.scope}', "
      f"exc.type='{ctx.exc.type}'"
    )
    assert (ctx.exc.type in ("FunctionNotFound", "NotImplementedError", "ReturnAsException", "HelperReturnAsException")) == (raw_tb is None), (
      f"run: traceback presence mismatch — exc.type='{ctx.exc.type}', raw_tb is {'None' if raw_tb is None else 'present'}"
    )
    ctx.exc = Exc(
      **unmunchify(ctx.exc), tb=(
        raw_tb and Traceback.from_str(raw_tb)
      )
    )
    return Ctx(**unmunchify(ctx))

  # ------------------------------------------------------------------
  # Algorithm
  # ------------------------------------------------------------------

  def solve(self):
    dl = self._dashboard_log
    if dl:
      dl.subagent_solving(self)
    with self.as_active_agent():
      result = self._solve()
    if dl:
      dl.subagent_solved(self)
    return result

  def _solve(self):
    snapshot = self.snapshot
    fn = snapshot.fn
    f = fn.name
    lib = self.lib
    dl = self._dashboard_log
    self.working_memory.solved_helpers[f] = {}

    # if f != "main" and not snapshot.fn.obtaining_missing_info:
    #   new_solution = self.trivial_implementation(snapshot)
    #   new_fn = new_solution[f]
    #   new_ctx = self.run(f, new_solution)
    #   if new_ctx.before_return():
    #     self.trivially_solved = True
    #     new_snapshot = Snapshot(fn=new_fn, solution=new_solution, ctx=new_ctx)
    #     self.result = (new_solution, self.generalize(new_snapshot, lib))
    #     return self.result
    #   if new_ctx.unexpected_error() and new_ctx.exc.type != "NeedMoreInformation":
    #     for _ in range(3):
    #       new_snapshot = Snapshot(fn=new_fn, solution=new_solution, ctx=new_ctx)
    #       hotfix = actions.HotFix(
    #         scope=fn.name,
    #         feedback=(
    #           f"`{f}` raised {new_ctx.exc.type}: {new_ctx.exc.arguments}. "
    #           f"Fix the implementation to match the expected functionality."
    #         ),
    #         before_action=None,
    #       )
    #       new_solution = self._update(new_snapshot, hotfix)
    #       new_fn = new_solution[f]
    #       new_ctx = self.run(f, new_solution)
    #       if new_ctx.before_return():
    #         self.trivially_solved = True
    #         new_snapshot = Snapshot(fn=new_fn, solution=new_solution, ctx=new_ctx)
    #         self.result = (new_solution, self.generalize(new_snapshot, lib))
    #         return self.result
    #       if not (new_ctx.unexpected_error() or new_ctx.exc.type == "NeedMoreInformation"):
    #         break

    self.refinement_root = root = RefinementNode(snapshot=snapshot)
    if snapshot.fn.obtaining_missing_info:
      root.add_child(actions.GatherContextNew(scope=fn.name, before_action=None))
    else:
      root.add_child(actions.Classify(scope=fn.name, before_action=None))
    if dl:
      dl.refinement_tree(self, root)

    while (node := root.explore()) is not None:
      if dl:
        dl.node_exploring(self, node)

      if isinstance(node.action, actions.MetaAction):
        node.resolve(node.snapshot)
        for new_action in node.action.take(node.snapshot):
          node.add_child(new_action)
        if dl:
          dl.refinement_tree(self, root)
        continue
      new_solution = self._update(node.snapshot, node.action)

      # if isinstance(node.action, actions.Complete):
      #   self.result = (
      #     new_solution.update(new_solution[f].update_from_code(save_before_return(new_solution[f].dumps(with_docstring=True)))),
      #     self.generalize(new_snapshot, lib),
      #   )
      #   return self.result

      if new_solution is None:
        node.result = None
      else:
        new_fn = new_solution[f]
        pause_after = None
        while True:
          new_ctx = self.run(f, new_solution, pause_after=pause_after)
          if (g := new_ctx.function_not_found()):
            child_fn, = self.low_level_fn(g, new_fn, new_ctx, action=node.action)
            child = SubAgent(child_fn, new_solution, lib, parent=self)
            new_solution, lib = child.solve()
            if child.trivially_solved:
              self.trivially_solved_helpers.add(g)
            pause_after = g
          else:
            if (result := new_ctx.helper_returned()):
              _, helper_name = result
              pause_after = None
              if helper_name in self.trivially_solved_helpers:
                continue
            new_snapshot = Snapshot(fn=new_fn, solution=new_solution, ctx=new_ctx)
            node.resolve(new_snapshot)
            critique = self.critique(new_snapshot, node.snapshot, node.action)
            if critique is DONE:
              # Save this function as a solved helper of its caller
              self.working_memory.solved_helpers[new_ctx.outer_scope][f] = new_solution[f]
              self.result = (
                new_solution.update(new_solution[f].update_from_code(save_before_return(new_fn.dumps(with_docstring=True)))),
                self.generalize(new_snapshot, lib),
              )
              return self.result
            for new_action in critique:
              node.add_child(new_action)
            if dl:
              dl.refinement_tree(self, root)
            break
    logger.warning("solve: all refinements exhausted for fn='%s' — marking as FunctionNotFeasible", f)
    self.result = (snapshot.solution.update(fn.update(body=RaiseFunctionNotFeasible)), lib)
    return self.result

  def trivial_implementation(self, snapshot):
    raise
    msgs = render_messages_template(
      "templates/v11/try_trivial.md",
      app_descriptions=self.show_app_descriptions(exclude=["api_docs"]),
      global_variables=self.globals(),
      globlas_accessed=self.globals_accessed(snapshot.fn),
      snapshot=snapshot,
    )
    _, code = self.generate_defn(msgs, snapshot.fn, reasoning={"effort": "none"})
    return snapshot.solution.update(snapshot.fn.update_from_code(code))

  def generalize(self, snapshot: Snapshot, lib: Library):
    return lib

  def explore(self):
    return self.refinement_root.explore() if self.refinement_root else None

  def system_coder(self, **kwargs):
    return render_messages_template(
      "templates/v12/system/coder.md",
      app_descriptions=self.show_app_descriptions(exclude=["api_docs"]),
      global_variables=self.globals(),
      instruction=self.world.task.instruction,
      **kwargs
    )

  def _compound_vs_atomic(self, snapshot: Snapshot):
    fn = snapshot.fn
    if fn.obtaining_missing_info:
      raise
      # return [
      #   actions.Explore(
      #     scope=fn.name,
      #     target=f"Find primary APIs that are CLOSEST to the expected functionality of `{snapshot.fn.name}`.",
      #     before_action=None
      #   )
      # ]
    include_implementation_first = (snapshot.fn.name != "main" and not snapshot.fn.obtaining_missing_info)
    msgs = self.system_coder()
    msgs.extend(
      render_messages_template(
        "templates/v12/compound_vs_atomic.md",
        snapshot=snapshot,
        app_descriptions=self.show_app_descriptions(exclude=["api_docs"]),
        instruction=self.world.task.instruction,
        include_implementation_first=include_implementation_first,
      )
    )
    parsed, response = generate_json_dict(
      self.generate, 
      msgs, 
      reasoning={"effort": "none"},
      max_retries=3,
      json_schema={
        "type": "object",
        "required": ["mode", "strategy"],
        "properties": {
          "mode": {
            "type": "string",
            "pattern": "(?i)^(plan-first|exploration-first" + ("|implementation-first" if include_implementation_first else "") + ")$"
          },
          "strategy": {"type": "string"}
        },
      }
    )
    mode = parsed["mode"].lower()
    if mode == "plan-first":
      return [actions.Plan(scope=fn.name, before_action=None)]
    elif mode == "exploration-first":
      return [actions.Explore(scope=fn.name, target=parsed["strategy"], before_action=None)]
    elif mode == "implementation-first":
      return [
        actions.Trivial(scope=fn.name, target=parsed["strategy"], before_action=None),
        actions.Explore(
          scope=fn.name,
          target=f"Find primary APIs that are CLOSEST to the expected functionality of `{snapshot.fn.name}`.",
          before_action=None
        )
      ]
    else:
      raise AssertionError(
        f"SubAgent._compound_vs_atomic: cannot happen (mode={mode})"
      )

  def _update(
    self,
    snapshot: Snapshot,
    action: actions.Action,
  ):
    f = snapshot.fn.name
    result = action.take(snapshot)
    if result is None:
      return result
    fn, *extra = result
    solution = snapshot.solution.update(*extra)
    for call in parse_code_function_calls(fn.dumps()):
      g = call.name
      if self.is_helper_function(g, scope=f, solution=solution):
        solution = solution.update(
          Fn(
            name=g,
            body=RaiseFunctionNotFound,
            parameters=[
              Parameter(name="*args"),
              Parameter(name="**kwargs")
            ],
          )
        )
    return solution.update(fn)

  def remove_print_statements(self, code: str, ctx: Ctx):
    if ctx is None:
      return code
    local_print_stmts = [
      f'print(f"{var.id} = {{{var.id}}}")' for var in ctx.locals
    ]
    def remove_or_not(s):
      for target_print_stmt in local_print_stmts:
        if is_same_syntax(s, target_print_stmt):
          return True
      return False
    return remove_statements(code, remove_or_not)

  def remove_print_statements_eager(self, code: str):
    def remove_or_not(s):
      return s.startswith("print(")
    return remove_statements(code, remove_or_not)

  def generate_function_defs_with_compound_flow(
    self,
    msgs,
    fn: Fn,
    ctx: Ctx,
    **kwargs
  ):
    function_defs = {}
    for name, code in (
      self.generate_function_defs(msgs, fn, **kwargs).items()
    ):
      code = remove_function_call_arguments(code, targets=self.globals_names())
      code = self.remove_print_statements(code, ctx)
      body = parse_fn_body(code)
      if name == fn.name:
        function_defs[name] = fn.update(body=body)
      else:
        if self.on_extra_functions == "ignore":
          continue
        if self.on_extra_functions == "ignore-body":
          body = RaiseFunctionNotFound
        if self.on_extra_functions == "eager":
          if "NotImplementedError" in body or "pass" in body:
            body = RaiseFunctionNotFound
          else:
            tree = cst.parse_module(body)
            body = tree.with_changes(
              default_indent="  ",
              body=[
                cst.parse_statement((
                  "try:\n"
                  "  ...\n"
                  "except:\n"
                  "  raise FunctionNotFound(inspect.currentframe().f_code.co_name)"
                )).with_changes(
                  body=cst.IndentedBlock(body=tree.body)
                )
              ]
            ).code
        function_defs[name] = Fn(
          name=name, body=body, parameters=tuple(parse_fn_params(code))
        )
    return [function_defs.pop(fn.name), *function_defs.values()]

  def is_helper_function(self, f: str, scope: str, solution: Solution):
    qualified_names = get_qualified_names(solution[scope].dumps())
    return (
      (f not in ("NeverHappen", "NeedMoreInformation")) and
      (f not in solution) and
      (not self.isapi(f)) and
      ("." not in f) and
      (f not in set(dir(builtins))) and
      not (f in qualified_names and qualified_names[f].source == QualifiedNameSource.IMPORT)
    )

  def existing_helpers(self, code: str, solution: Solution, before: str | None = None):
    print(before)
    print(code)
    before_calls = {call.name for call in parse_code_function_calls(before)} if before else set()
    helpers = []
    for call in parse_code_function_calls(code):
      g = call.name
      if g in solution and g not in before_calls:
        helpers.append(g)
    print(helpers)
    return helpers

  def new_unknown_calls(self, before: str, after: str, scope: str, solution: Solution) -> list[str]:
    """Return API names (e.g. 'app.api') present in after_fns but not in before_snapshot.fn."""

    before_apis = set()
    for call in parse_code_function_calls(before):
      if self._get_api_doc(call.name) is not None:
        before_apis.add(call.name)
      else:
        is_known_call = (not self.is_helper_function(call.name, scope=scope, solution=solution))
        if is_known_call:
          before_apis.add(call.name)

    app_names = {app["name"] for app in self.show_app_descriptions()}
    after_apis = set()
    for call in parse_code_function_calls(after):
      parts = call.name.split(".")
      if len(parts) >= 2 and parts[0] in app_names:
        after_apis.add(call.name)
      elif len(parts) < 2 and call.name not in set(dir(builtins)):
        after_apis.add(call.name)
    return after_apis, before_apis

  def low_level_fn(self, name: str, scope: Fn, ctx: Ctx, action: actions.Action | None = None):
    self.working_memory.ctx_by_scope[scope.name] = ctx
    obtaining_missing_info = isinstance(action, actions.ObtainMissingInformation)
    diagnosis = None
    if obtaining_missing_info:
      diagnosis = action.diagnosis
    print(obtaining_missing_info)
    for flow in return_to_pass_flow(scope.dumps()):
      if flow.producer.function_name != name:
        continue
      parts = flow.consumer.function_name.split(".")
      if len(parts) != 2:
        continue
      app_name, api_name = parts
      if (api_doc := self.get_api_doc(app_name, api_name)):
        for param in api_doc["parameters"]:
          if flow.consumer.parameter == param["name"]:
            [function_call] = find_function_call(scope.dumps(), name)
            msgs = self.system_coder()
            msgs.extend(
              render_messages_template(
                "templates/v12/low_level_fn.md",
                name=name,
                scope=scope,
                ctx=ctx,
                app_descriptions=self.show_app_descriptions(exclude=["api_docs"]),
                instruction=self.world.task.instruction,
                parameters=(
                  function_call.positional_arguments or
                  function_call.keyword_arguments
                )
              )
            )
            info, response = generate_json_dict(
              self.generate,
              msgs,
              reasoning={"effort": "none"},
              max_retries=3,
              json_schema=fn_info_schema(
                has_parameters=bool(function_call.positional_arguments or function_call.keyword_arguments)
              ),
            )
            info["description"] += f""" Obtain and return the value of an `{param["name"]}`, which is passed to `{app_name}.{api_name}` API call."""
            info["returns"][0]["name"] = f"""{param["name"]}"""
            info["returns"][0]["description"] += f""" {param["description"]}"""
            info["returns"][0]["type"] = f"""{param["type"]}"""
            msgs.add(
              role="assistant",
              content=f"```python\n{json.dumps(info, indent=2)}\n```"
            )
            return FnApiParam(
              name=name, 
              **info, 
              assure_return_value_type=True, 
              return_passed_to={
                "var_name": flow.producer.variable, 
                "app_name": app_name, 
                "api_name": api_name, 
                "param_name": param["name"]
              },
              obtaining_missing_info=obtaining_missing_info,
              diagnosis=diagnosis
            ),

    [function_call] = find_function_call(scope.dumps(), name)
    msgs = self.system_coder()
    msgs.extend(
      render_messages_template(
        "templates/v12/low_level_fn.md",
        name=name,
        scope=scope,
        ctx=ctx,
        app_descriptions=self.show_app_descriptions(exclude=["api_docs"]),
        instruction=self.world.task.instruction,
        parameters=(
          function_call.positional_arguments or
          function_call.keyword_arguments
        )
      )
    )
    info, response = generate_json_dict(
      self.generate,
      msgs,
      reasoning={"effort": "none"},
      max_retries=3,
      json_schema=fn_info_schema(
        has_parameters=bool(function_call.positional_arguments or function_call.keyword_arguments)
      ),
    )
    if "parameters" not in info:
      info["parameters"] = []
    elif info["parameters"]:
      first_param = info["parameters"][0]
      if not first_param or first_param["name"] in (None, "None", "none", ""):
        info["parameters"] = []
    msgs.add(
      role="assistant",
      content=f"```python\n{json.dumps(info, indent=2)}\n```"
    )
    return Fn(name=name, **info, obtaining_missing_info=obtaining_missing_info, diagnosis=diagnosis),

  def critique(self, snapshot: Snapshot, before_snapshot: Snapshot, action: actions.Action):
    fn, solution, ctx = snapshot.fn, snapshot.solution, snapshot.ctx

    _action = action
    if isinstance(_action, actions.Adapt):
      _action = action.before_action

    if isinstance(_action, actions.Trivial):
      if ctx.exc.type == "NeedMoreInformation":
        return []
      elif ctx.exc.type == "ReturnAsException":
        return [
          actions.Certification(
            scope=fn.name, before_action=action
          )
        ]
      else:
        # Trivial - HotFix xN - Trivial - HotFix xN - ... 이렇게 띄엄띄엄이면 maximum count 0부터 다시 셈
        raise NotImplementedError(
          "hot fix를 maximum N번만 가능하도록 하고 그 뒤에는 [] 리턴"
        )

    if isinstance(_action, actions.Explore):
      if ctx.exc.type == "ReturnAsException":
        return [actions.Classify(scope=fn.name, before_action=action)]
      elif ctx.exc.type == "HelperReturnAsException":
        return_value, helper_name = ctx.helper_returned()
        return [
          actions.Adapt(scope=fn.name, helper=helper_name, return_value=return_value, before_action=action)
        ]
      elif ctx.exc.type not in ("FunctionNotFound", "NotImplementedError"):
        return [
          actions.Diagnose(
            scope=fn.name,
            target=_action.target,
            invoked_app_apis=_action.invoked_app_apis,
            # app_name=_action.invoked_api.split(".")[0],
            # api_name=_action.invoked_api.split(".")[1],
            before_action=action
          )
        ]
      else:
        rprint(ctx)
        raise NotImplementedError(
          "?"
        )

    if isinstance(_action, actions.LocalFix):
      if ctx.exc.type == "ReturnAsException":
        return [actions.Classify(scope=fn.name, before_action=action)]
      else:
        raise

    if isinstance(_action, (actions.LocalFix, actions.Restructure)):
      raise
      explore = action._find_ancestor(actions.Explore)
      if ctx.exc.type == "ReturnAsException":
        return [actions.Classify(scope=fn.name, before_action=action)]
      elif ctx.exc.type == "HelperReturnAsException":
        return_value, helper_name = ctx.helper_returned()
        return [
          actions.Adapt(scope=fn.name, helper=helper_name, return_value=return_value, before_action=action)
        ]
      else:
        return [
          actions.Diagnose(
            scope=fn.name,
            target=explore.target,
            app_name=explore.invoked_api.split(".")[0],
            api_name=explore.invoked_api.split(".")[1],
            before_action=action,
          )
        ]

    if isinstance(_action, actions.Certification):
      if ctx.exc.type == "ReturnAsException":
        return DONE
      else:
        rprint(ctx)
        raise NotImplementedError(
          "??"
        )

    raise
    if ctx.exc.type == "ReturnAsException":
      # if isinstance(action, actions.GatherContext):
      if action._is_gathering():
        # GatherContext loop: ask if more API calls are needed
        observed_variables = action._observed_variables(snapshot, include_inner=False)
        msgs = self.system_coder()
        msgs.extend(
          render_messages_template(
            "templates/v11/gather_context_check.md",
            global_variables=self.globals(),
            globals_accessed=self.globals_accessed(snapshot.fn),
            snapshot=snapshot,
            observed_variables=observed_variables,
          )
        )
        _, think, extra = self.generate_with_think(
          msgs,
          prefix=False,
          # max_tokens=1024, max_completion_tokens=1024
        )
        evaluation = extra["evaluation"]
        if evaluation == "done":
          return [
            actions.HotFix(
              scope=fn.name,
              feedback=(
                f"The current implementation of `{fn.name}` does not exactly meet "
                f"the expected functionality. You need implement the remaining body of `{fn.name}` "
                f"to match what `{fn.name}` is expected to return."
              ),
              before_action=action,
            ),
          ]
        elif evaluation == "unhelpful":
          return [
            actions.GatherContextNew(scope=fn.name, rationale=think, before_action=action, discard_unexplored=False)
          ]
        elif evaluation == "helpful-but-retry":
          return [
            actions.GatherContextAgain(scope=fn.name, rationale=think, before_action=action)
          ]
        elif evaluation == "helpful-but-more":
          return [
            actions.GatherContextNew(scope=fn.name, rationale=think, before_action=action, discard_unexplored=True)
          ]
        else:
          raise
      print(action)
      msgs = self.system_coder()
      msgs.extend(
        render_messages_template(
          "templates/v11/check_before_return.md",
          global_variables=self.globals(),
          globals_accessed=self.globals_accessed(snapshot.fn),
          snapshot=snapshot,
        )
      )
      _, think, extra = self.generate_with_think(
        msgs,
        prefix=False,
        # max_tokens=1024, max_completion_tokens=1024
      )
      evaluation = extra["evaluation"]
      if evaluation == "yes":
        return [
          actions.Complete(scope=fn.name, before_action=action)
        ]
      else:
        return [
          actions.HotFix(
            scope=fn.name,
            feedback=(
              f"The current implementation of `{fn.name}` does not exactly meet "
              f"the desired functionality. {think}"
            ),
            before_action=action,
          ),
        ]
    elif (result := ctx.helper_returned()):
      return_value, helper_name = result
      return [
        actions.Adapt(scope=fn.name, helper=helper_name, return_value=return_value, before_action=action)
      ]
    elif ctx.exc.type in ("FunctionNotFound", "NotImplementedError"):
      logger.error(
        "critique: unexpected exc.type='%s' for fn='%s' — should have been resolved before reaching critique",
        ctx.exc.type, fn.name
      )
      raise NotImplementedError(
        f"critique: exc.type='{ctx.exc.type}' reached critique for fn='{fn.name}' — "
        f"this should have been handled by the solve loop (FunctionNotFound → solve child, "
        f"NotImplementedError → initial implementation). args={ctx.exc.arguments}"
      )
    else: # Unexpected Error
      if isinstance(action, actions.FixOnDiagnosis):
        if not self.has_progress(before_snapshot, action, snapshot):
          return []
      return [
        actions.ExploreDiagnoses(scope=fn.name, before_action=action)
      ]

  def after_helper(self, snapshot: Snapshot):
    fn, ctx = snapshot.fn, snapshot.ctx
    helper_return_value, helper_name = ctx.helper_returned()
    helper_return_value_type = ctx.exc.arguments[1]
    response, think, extra = self.generate_with_think(
      render_messages_template(
        "templates/v10/after_helper.md",
        global_variables=self.globals(),
        globals_accessed=self.globals_accessed(fn),
        snapshot=snapshot,
        helper_name=helper_name,
        helper_return_value=helper_return_value,
        helper_return_value_type=helper_return_value_type,
      ),
      prefix=False,
      max_tokens=2048, max_completion_tokens=2048,
    )
    if extra["update"] == "no":
      return None
    codes = extract_python_codes(response.content)
    if len(codes) < 2:
      return None
    body = parse_fn_body(codes[1])
    return fn.update(body=body)

  def parse_active_calls(self, fn: Fn, solution: Solution):
    used = []
    for function_call in parse_code_function_calls(fn.dumps()):
      name = function_call.name
      if (api_doc := self._get_api_doc(name)) is not None:
        used.append(
          dict(
            name=name,
            description=api_doc["description"],
            parameters=api_doc["parameters"],
          )
        )
      else:
        if (defn := solution.get(name)) is not None:
          if "FunctionNotFound" not in defn.body:
            used.append(
              dict(
                name=name,
                description=defn.description,
                parameters=defn.parameters,
              )
            )
    return used

  def consecutive_hotfix_depth(self, action: actions.Action | None) -> int:
    depth = 0
    cur = action
    while cur is not None:
        if isinstance(cur, actions.HotFixOnDiagnosis):
            depth += 1
        else:
            break
        cur = cur.before_action
    return depth

  def has_progress(self, before_snapshot, action, after_snapshot):
    # 1. 더 좋은 종료 상태
    if after_snapshot.ctx.before_return() and not before_snapshot.ctx.before_return():
      return True
    # 2. helper missing 해결
    if before_snapshot.ctx.function_not_found() and not after_snapshot.ctx.function_not_found():
      return True
    # 3. surface error 동일하면 우선 no-progress 의심
    before_msg = (before_snapshot.ctx.exc.tb.message if before_snapshot.ctx.exc.tb else "")
    after_msg = (after_snapshot.ctx.exc.tb.message if after_snapshot.ctx.exc.tb else "")
    if (
        before_snapshot.ctx.exc.type == after_snapshot.ctx.exc.type and
        before_msg == after_msg
    ):
      return False

    msgs = self.system_coder()
    msgs.extend(
      render_messages_template(
        "templates/v11/progress.md",
        before_snapshot=before_snapshot,
        after_snapshot=after_snapshot,
        action=action,
        instruction=self.world.task.instruction,
      )
    )
    _, think, extra = self.generate_with_think(msgs, prefix=False)
    return extra["progress"].lower() == "yes"


# ------------------------------------------------------------------
# PeTER: thin AppWorld lifecycle shell
# ------------------------------------------------------------------

@Agent.register("peter")
class PeTER(Agent):

  def __init__(self, *args, **kwargs):
    super().__init__(*args, **kwargs)
    self.on_extra_functions = "ignore"
    self.working_memory = WorkingMemory()
    self._dashboard_log = None  # set externally for dashboard mode

  def initialize(self, world: AppWorld) -> None:
    super().initialize(world)
    # Attach a per-task file handler to the peter logger
    for h in logger.handlers[:]:
      if isinstance(h, logging.FileHandler):
        h.close()
        logger.removeHandler(h)
    fh = logging.FileHandler(
      os.path.join(world.output_logs_directory, "peter.log"),
      mode="w", encoding="utf-8"
    )
    fh.setFormatter(_LOG_FMT)
    logger.addHandler(fh)

    template = Template(cast(str, read_file(os.path.join(_DIR, "templates", "1.txt"))).lstrip())
    template_params = {
      "instruction": world.task.instruction,
      "main_user": world.task.supervisor,
      "date": world.task.datetime.isoformat(timespec="seconds"),
    }
    output_str = template.render(template_params)
    self.messages = self.text_to_messages(output_str)
    system = self.messages[0]
    assert system["role"] == "system", f"initialize: expected first message role='system', got '{system['role']}'"
    system["today_date"] = world.task.datetime.date().strftime("%Y-%m-%d")

    msgs = render_messages_template(
      "templates/v11/system/coder.md",
      app_descriptions=show_app_descriptions(world, exclude=["api_docs"]),
      global_variables=make_globals(world.task),
      instruction=self.world.task.instruction,
    )
    lines: list[str] = []
    for i, msg in enumerate(msgs):
      role = msg.role
      content = msg.content
      lines.append("=" * 80)
      header = f"MESSAGE {i} | role: {role}"
      lines.append(header)
      lines.append("=" * 80)
      if content:
        lines.append(str(content))
      lines.append("")
    dump_path = os.path.join("test_output.md")
    with open(dump_path, "w") as f:
      f.write("\n".join(lines))

  INITIAL_CHECKPOINT = "__initial__"

  def solve_task(self, task_id: str) -> None:
    self.usage_tracker.reset(task_id)
    try:
      with AppWorld(task_id=task_id) as world:
        self.initialize(world)
        self.world = world
        self.run_setup()
        world.save_state(self.INITIAL_CHECKPOINT)
        fn = Fn("main", description=f"Process the user request. {world.task.instruction}")
        SubAgent.setup(
          language_models=self.language_models,
          world=self.world,
          logger_=self.logger,
          usage_tracker=self.usage_tracker,
          working_memory=self.working_memory,
          on_extra_functions=self.on_extra_functions,
          dashboard_log=self._dashboard_log,
        )
        self.root_agent = SubAgent(fn, Solution(), Library())
        solution, lib = self.root_agent.solve()
        self.replay(solution)
    except NotImplementedError as e:
      raise e
      logger.error("solve_task: task_id='%s' hit unimplemented code path: %s", task_id, e)
      self.logger.show_message(
        role="termination",
        content=f"[NotImplementedError] {e}"
      )
    except Exception as e:
      raise e
      logger.error("solve_task: task_id='%s' failed with unexpected error: %s: %s", task_id, type(e).__name__, e)
      self.logger.show_message(
        role="termination",
        content=f"[{type(e).__name__}] {e}"
      )
    self.logger.complete_task()

  def replay(self, solution: Solution) -> None:
    """Reset to initial state and re-run the final solution cleanly."""
    logger.info("replay: resetting to initial checkpoint and re-running final solution")
    self.world.load_state(self.INITIAL_CHECKPOINT)
    self.run_setup()
    code = solution.dumps()
    output = self.world.execute(code, save_state=False)
    logger.info("replay: done — output: %s", output[:200])

  def run_setup(self):
    code = render_template(
      "templates/v11/setup.py",
      app_descriptions=show_app_descriptions(self.world, exclude=["api_docs"]),
      globals=make_globals(self.world.task),
    )
    output = self.world.execute(code, save_state=False)
    try:
      assert output.startswith("Execution successful."), f"run_setup: execution failed — output: {output[:500]}"
    except Exception:
      print(output)
      raise
