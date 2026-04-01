
# 8
`supervisor.show_account_passwords` 같이 파라메터 없는 API는 그냥 내가 호출해주면 될 듯.

# 1

```python
def read_owe_list_from_csv():
  file_path = '/home/lindsey/owe_list.csv'
  access_token = get_access_token()

  file_exists_response = file_system.file_exists(
    file_path=file_path, access_token=access_token
  )
  if not file_exists_response.get("exists", False):
    file_path = find_correct_file_path(access_token)

  file_content = file_system.show_file(
    file_path=file_path, access_token=access_token
  )

  owe_list = parse_csv_content(file_content)

  raise owe_list
```
- file_exists_response.get("exists", False) 이런 거 못 하게 해야함.
- 아래 코드에서 "." not in g 지워도 돌아가게 해야함.
  if g not in solution and not self.isapi(g) and "." not in g:

# 2
에러 수정하고나서 specify 단계가 지금 너무 더럽게 되어있음.
예를 들면, `find_correct_file_path`에 대한 명세 작성할 때.

# 3
특정 api (A) 호출에 필요한 파라메터를 얻기 위한 함수 (B)에서 atomic 전략으로 api를 찾을 경우에는 A를 리스트에서 지우고 프롬프팅.
예를 들면, `file_system.show_file`에 필요한 `file_path`를 얻기 위한 `find_file_in_home_directory` 함수를 구현할 때 api 리스트업에서 `file_system.show_file`는 빼고 보여주기.

# 4
코드에 import 같은 게 있으면 `extract_python_function_defs` 함수에서 def 안으로 보내버리기(의존성 있는 거만?)

# 5
helper function 호출할 때, llm이 명시적으로 전달하지 않은 locals를 extra로 추가 전달해버리기.

# 6
raise 있으면 NotReached로 바꿔버리기.

# 7
`compound_vs_atomic_on_feedback.md` 프롬프팅 하고 나서 한 번 더 validate하기. 아래 룰들을 잘 지켰는지.
Critical rules that you MUST follow:
- Adhere to the axiom: "The user is correct; all the premises (e.g., existence of resources) explicit in the instruction are true."
- Do NOT raise exceptions as the user is correct; propose a concrete recovery that can make progress without additional user input.
- Do NOT introduce new facts. Use ONLY the evidence in the user instruction, exception message and annotated locals.
- Do NOT ask the user to take any action. You must propose an in-environment recovery that makes progress using available apps/APIs only.
- Do NOT perform "write" actions unless explicitly requested by the user.

# 9
`assure_dotted_call`에서 code 전체를 업데이트하지 말고, 타겟 콜 부분만 업데이트 하도록 바꾸기.

# 10
`venmo.login` 같이 호출하고 리스폰스 살짝 처리만하면 끝나는 경우는 처리하도록. API 호출 뒤에 아무것도 쓰지말라는 프롬프트 수정?

# 11
'This function is about to return None.' 인 상태에서 'Decide whether the feedback provides enough information to produce a correct patch *now*, without asking for any additional information or making unstated assumptions.'에 대해 no라고 답변하면 `feedback != None`이기 때문에 'What should you do to prevent the observed exception and fulfill the user’s intent?' 프롬프트로 연결됨(exception이 아님에도 불구하고).

# 12
리턴이 여러 곳에서 되면 어떻게? ReturnAsException은 한 번만 하는데 지금은.

# 13
inner 함수 lift 하고 나서 'Evaluate whether the current implementation of `check_if_person_has_venmo_account` exactly satisfies its docstring' 같은 프롬프트를 보게됨. inner 함수 lfit했으면 이 phase를 패스할지 또는 inner 함수도 같이 보여줄지 고민해봐야됨.
