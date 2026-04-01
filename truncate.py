import random
import ast
import executing
import re
import json
import inspect
import textwrap
from traceback import walk_tb
from functools import wraps
from datetime import datetime
from typing import Any

# --- 제공해주신 코드 ---
class FunctionNotFound(Exception):
  def __init__(self, name: str):
    super().__init__(name)
    self.name = name
  def __str__(self):
    return f"{self.name}"

class ReturnAsException(Exception):
  def __init__(self, *return_value):
    super().__init__(*return_value)
    self.return_value = return_value

class NeverHappen(AssertionError): ...
class CannotImplement(Exception): ...

def show_locals_on_exception(type_hints: bool = False):
  def decorator(func):
    @wraps(func)
    def __show_locals_on_exception_wrap(*args, **kwargs):
      try:
        return func(*args, **kwargs)
      except Exception as e:
        if getattr(e, "_locals_shown", False):
          raise e
        def find_tb():
          for frame, lineno in reversed(list(walk_tb(e.__traceback__))):
            if frame.f_code is func.__code__:
              return frame, lineno
          raise AssertionError()
        frame, lineno = find_tb()
        locals = []
        for id, value in frame.f_locals.copy().items():
          if not (
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
          line=lineno,
          firstline=frame.f_code.co_firstlineno + 1, # skip this decorator `@show_locals_on_exception`
          exc=dict(
            type=type(e).__name__,
            arguments=e.args,
          ),
        )
        print(f"<context>\n{json.dumps(ctx, indent=2, default=str)}\n</context>")
        e._locals_shown = True
        raise e 
    return __show_locals_on_exception_wrap
  return decorator


# --- 예외 발생 테스트용 함수 ---
def helper_function_raises(*args, **kwargs):
  raise FunctionNotFound(inspect.currentframe().f_code.co_name)

@show_locals_on_exception()
def test_multi_line_list_exception():
    # firstline은 함수가 정의된 'def' 다음 줄부터 계산되므로 
    # 이 아래 'a = 10'이 있는 위치가 됩니다.
    a = 10
    b = 20
    
    # 여러 줄에 걸친 리스트 정의 내에서 예외 발생
    if False:
      print()
    else:
      my_list = [
          "첫 번째 요소",
          "두 번째 요소",
          1 / 0,  # <-- line: 여기가 예외가 실제로 발생한 라인
          "네 번째 요소",
      ]
    sum([])
    return my_list

@show_locals_on_exception()
def test_multi_line_function_call_exception():
    x = "안전한 변수"
    
    # 여러 줄에 걸친 함수 호출(딕셔너리 생성) 내에서 예외 발생
    if False:
      print()
    else:
      
      my_dict = dict(
          key1="value1",
          key2="value2",
          key3=helper_function_raises(
            1,
            2,
            4,
            5,
            2
          ), # <-- line: 헬퍼 함수로 인해 여기서 예외 발생
          key4="value4"
      )
    sum([])
    return my_dict


# --- 테스트 실행부 ---
# if __name__ == "__main__":
print("="*60)
print("테스트 1: 여러 줄로 구성된 리스트(List) 내부에서 예외 발생")
print("="*60)
try:
    test_multi_line_list_exception()
except ZeroDivisionError:
    print("[Info] 테스트 1 예외가 정상적으로 캐치되었습니다.\n")
    
print("="*60)
print("테스트 2: 여러 줄로 구성된 함수 호출 구문에서 예외 발생")
print("="*60)
try:
    test_multi_line_function_call_exception()
except FunctionNotFound:
    print("[Info] 테스트 2 예외가 정상적으로 캐치되었습니다.\n")










# exit(0)
import libcst as cst
from libcst.metadata import PositionProvider
from typing import Sequence

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
      raise
      return updated_suite.with_changes(
        body=self._slice_small_statements(
          original_suite.body, updated_suite.body
        )
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
    raise

  def leave_Match(self, original: cst.Match, updated: cst.Match) -> cst.Match:
    raise


def truncate_execution_flow_by_line(text: str, after: int) -> str:
  tree = cst.parse_module(text)
  tree = cst.MetadataWrapper(tree)
  transformer = TruncateExecutionFlowByLineTransformer(after)
  tree = tree.visit(transformer)
  return tree.code


code = """
def test_multi_line_function_call_exception():
    x = "안전한 변수"
    
    # 여러 줄에 걸친 함수 호출(딕셔너리 생성) 내에서 예외 발생
    if False:
      print()
    else:
      
      my_dict = dict(
          key1="value1",
          key2="value2",
          key3=helper_function_raises(
            1,
            2,
            4,
            5,
            2
          ), # <-- line: 헬퍼 함수로 인해 여기서 예외 발생
          key4="value4"
      )
    sum([])
    return my_dict
""".strip()

print(truncate_execution_flow_by_line(code, after=117 - 106 + 1))