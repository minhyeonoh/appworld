import ast
import executing
import re
import json
import inspect
import textwrap
from collections import defaultdict
from traceback import walk_tb
from functools import wraps
from datetime import datetime
from typing import Any


class FunctionNotFound(Exception):

  def __init__(self, name: str):
    super().__init__(name)
    self.name = name

  def __str__(self):
    return f"{self.name}"


class ReturnAsException(Exception):
  def __init__(self, return_value, return_value_type):
    super().__init__(return_value, return_value_type)
    self.return_value = return_value
    self.return_value_type = return_value_type


class HelperReturnAsException(Exception):
  def __init__(self, return_value, return_value_type, helper_name=None):
    super().__init__(return_value, return_value_type, helper_name)
    self.return_value = return_value
    self.return_value_type = return_value_type
    self.helper_name = helper_name


class NeverHappen(AssertionError): ...


class CannotImplement(Exception):
  ...


class NeedMoreInformation(AssertionError): ...


import inspect
import libcst as cst
from libcst.metadata import ParentNodeProvider, PositionProvider, MetadataWrapper

class RuntimeBlockScopeChecker(cst.CSTVisitor):
    # 💡 PositionProvider 추가: 라인 번호 추적용
    METADATA_DEPENDENCIES = (ParentNodeProvider, PositionProvider)

    def __init__(self, target_vars, target_line):
        super().__init__()
        self.target_vars = target_vars
        self.target_line = target_line
        self.target_block = None
        self.assignment_blocks = {var: [] for var in target_vars}
        self.leaked_variables = set()

    def _get_innermost_block(self, node: cst.CSTNode):
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

    # 💡 핵심: 하드코딩된 print 대신, 현재 실행 중인 타겟 라인 번호의 블록을 찾음
    def on_visit(self, node: cst.CSTNode) -> bool:
        if self.target_block is None:
            pos = self.get_metadata(PositionProvider, node, None)
            # 노드의 시작 라인이 우리가 찾던 호출 라인과 일치하면 거기가 현재 스코프!
            if pos and pos.start.line == self.target_line:
                self.target_block = self._get_innermost_block(node)
        return super().on_visit(node)

    def visit_AssignTarget(self, node: cst.AssignTarget):
        self._record_assignment(node.target)

    def visit_For(self, node: cst.For):
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

    def leave_Module(self, original_node: cst.Module):
        if not self.target_block:
            return

        for var, blocks in self.assignment_blocks.items():
            if not blocks:
                continue
            
            is_valid = False
            for block in blocks:
                if self._is_ancestor(block, self.target_block):
                    is_valid = True
                    break
            
            if not is_valid:
                self.leaked_variables.add(var)


def get_strictly_observed_variables() -> dict[str, dict]:
  observed = {}

  # 데코레이터 래퍼 함수 이름 등 무시할 함수 목록
  IGNORED_FUNCTIONS = {'<module>', '__show_locals_on_exception_wrap'}

  # 수집하지 않을 변수 이름들 (우리가 주입한 특수 변수 등)
  IGNORED_VARS = {'_caller_contexts_', '__caller_contexts__'}

  # [2:] 를 사용하여 현재 유틸함수와 호출한 헬퍼함수(Callee)의 프레임은 건너뜀
  for frame_info in inspect.stack()[2:]:
    func_name = frame_info.function
    if func_name == '<module>': 
      break
    if func_name in IGNORED_FUNCTIONS:
      continue
        
    frame = frame_info.frame
    raw_locals = frame.f_locals.copy()
    
    # 1. 호출된 Caller의 파일 절대 경로와 실제 실행 라인 번호 획득
    target_line = frame.f_lineno 
    
    try:
      # 절대 라인 매칭을 위해 파일 전체의 소스를 읽어옴
      source_file = inspect.getsourcefile(frame)
      with open(source_file, 'r', encoding='utf-8') as f:
        source_code = f.read()
          
      # 2. 정적 분석기 가동
      module = cst.parse_module(source_code)
      wrapper = MetadataWrapper(module)
      
      checker = RuntimeBlockScopeChecker(list(raw_locals.keys()), target_line)
      wrapper.visit(checker)
      
      # 3. Leaked 변수를 제외한 '진짜 안전한' 로컬 변수만 필터링
      filtered_locals = {
        k: v for k, v in raw_locals.items()
        if k not in checker.leaked_variables
        and not (inspect.ismodule(v) or inspect.isfunction(v) or inspect.isclass(v))
      }
      observed[func_name] = filtered_locals

    except Exception as e:
      # 주피터 노트북 등 소스 파일 접근이 불가능한 샌드박스 환경에선 원본 locals 반환
      observed[func_name] = {
        k: v for k, v in raw_locals.items()
        if not (inspect.ismodule(v) or inspect.isfunction(v) or inspect.isclass(v))
      }
          
  return observed






def get_observed_variables() -> dict[str, dict]:
  """콜스택을 추적하여 상위 함수들의 로컬 변수들을 딕셔너리로 반환합니다."""
  observed = {}
  # 현재 프레임(0)과 이 유틸함수 프레임(1)을 제외한 상위 프레임들 탐색
  for frame_info in inspect.stack()[2:]:
    func_name = frame_info.function
    if func_name == '<module>': # 최상단 도달 시 종료
      break
    # 상위 함수의 locals() 복사본 저장
    observed[func_name] = frame_info.frame.f_locals.copy()
  return observed




def save_strictly_observed_variables():
  """호출한 함수의 현재 로컬 변수를 Leaked 필터링 후 전역 저장소에 기록합니다."""
  #은 이 함수를 호출한 바로 그 함수(타겟 Callee)의 프레임입니다.
  frame = inspect.currentframe().f_back
  if frame is None:
    raise AssertionError("save_strictly_observed_variables: caller frame is None")

  func_name = frame.f_code.co_name
  target_line = frame.f_lineno 
  raw_locals = frame.f_locals.copy()
  
  try:
    source_file = inspect.getsourcefile(frame)
    with open(source_file, 'r', encoding='utf-8') as f:
      source_code = f.read()
        
    module = cst.parse_module(source_code)
    wrapper = MetadataWrapper(module)
    
    # 앞서 작성하신 Checker 재활용
    checker = RuntimeBlockScopeChecker(list(raw_locals.keys()), target_line)
    wrapper.visit(checker)
    
    filtered_locals = {
      k: v for k, v in raw_locals.items()
      if k not in checker.leaked_variables
      and not (inspect.ismodule(v) or inspect.isfunction(v) or inspect.isclass(v))
    }

    # 히스토리에 추가 (동일 함수가 여러 번 호출될 수 있으므로 list에 append)
    observed_callee_history[func_name].append(filtered_locals)

  except Exception as e:
    # 파일 읽기 실패 등 예외 발생 시 원본 locals 그대로 저장
    observed_callee_history[func_name].append({
      k: v for k, v in raw_locals.items()
      if not (inspect.ismodule(v) or inspect.isfunction(v) or inspect.isclass(v))
    })


def show_locals_on_exception(type_hints: bool = False):
  def decorator(func):
    @wraps(func)
    def __show_locals_on_exception_wrap(*args, **kwargs):
      try:
        return func(*args, **kwargs)
      except Exception as e:
        if isinstance(e, HelperReturnAsException):
          # Skip if this function raised it (g's decorator); capture if caller (f's decorator)
          frames = list(walk_tb(e.__traceback__))
          if frames[-1][0].f_code is func.__code__:
            raise
        if getattr(e, "_locals_shown", False):
          raise e
        def find_tb():
          for frame, lineno in reversed(list(walk_tb(e.__traceback__))):
            if frame.f_code is func.__code__:
              return frame, lineno
          raise AssertionError(f"find_tb: no traceback frame found matching func.__code__ for {func.__name__}")
        frame, lineno = find_tb()
        locals = []
        locals_in_outer_scopes = None
        for id, value in frame.f_locals.copy().items():
          if id == "_caller_contexts_":
            locals_in_outer_scopes = value
          elif not (
            id.startswith("__") or
            inspect.ismodule(value) or
            inspect.isfunction(value) or
            inspect.isclass(value)
          ):
            locals.append(
              dict(id=id, value=value, type=(
                type(value).__name__ if type_hints else None
              ))
            )
        outer_frame = frame.f_back
        while outer_frame.f_code.co_name == inspect.currentframe().f_code.co_name:
          outer_frame = outer_frame.f_back
        ex = executing.Source.executing(outer_frame)
        assert ex.node is not None
        ctx = dict(
          scope=frame.f_code.co_name,
          outer_scope=outer_frame.f_code.co_name,
          outer_scope_call_site=ex.text(),
          locals=locals,
          locals_in_outer_scopes=locals_in_outer_scopes,
          line=lineno,
          firstline=frame.f_code.co_firstlineno + 1, # skip this decorator `@show_locals_on_exception`
          exc=dict(
            type=type(e).__name__,
            arguments=e.args,
          ),
        )
        print(f"<context>\n{json.dumps(ctx, indent=2, default=str)}\n</context>")
        e._locals_shown = True
        raise e #???
    return __show_locals_on_exception_wrap
  return decorator


class Decorator:

  def __init__(self, api, app_name, api_name):
    self.api = api
    self.api_name = api_name
    self.api_doc = apis.api_docs.show_api_doc(app_name=app_name, api_name=api_name)

  def __call__(self, **kwargs):
    for param in self.api_doc["parameters"]:
      if not param["required"] and param["name"] in kwargs and kwargs[param["name"]] is None:
        kwargs.pop(param["name"])
    return self.api(**kwargs)


class ApiWrap:

  def __init__(self, app, app_name):
    self.app = app
    self.app_name = app_name
    self.api_names = [
      api["name"] for api in apis.api_docs.show_api_descriptions(app_name=self.app_name)
    ]

  def __getattr__(self, api_name):
    attr = getattr(self.app, api_name)
    if api_name in self.api_names:
      return Decorator(attr, self.app_name, api_name)
    return attr


class AppWrap:
  def __init__(self, apis):
    self.apis = apis
    self.app_names = [
      app["name"] for app in apis.api_docs.show_app_descriptions()
    ]

  def __getattr__(self, app_name):
    attr = getattr(self.apis, app_name)
    if app_name in self.app_names:
      return ApiWrap(attr, app_name)
    return attr


_apis = AppWrap(apis)
{% for info in app_descriptions %}
{{ info["name"] }} = _apis.{{ info["name"] }}
{%- endfor %}


{{ globals }}