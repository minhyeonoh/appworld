from rich import print as rprint
from appworld import AppWorld  # , load_task_ids

# api doc 보는 거는 다른 ipynb에서 하자.
# 괜히 context 길어지는 듯.

# reponse 기준으로 성공/실패 구분

# 트리 형태로 이전 context가 열렸다 닫혔다 하면서 필요한 것만 냅두기 (context window 절약)

# rollback은 어떻게?



class DisableApiExecution:

  def __init__(self, apis):
    self.apis = apis

  def __enter__(self):
    return self

  def __exit__(self, exc_type, exc_val, exc_tb):
    # 이 부분에서 API 실행을 다시 활성화하는 로직을 수행할 수 있습니다.
    if exc_type is not None:
      # 예외가 발생했음을 출력 (선택 사항)
      print(f"\n🚫 **예외 무시:** {exc_type.__name__} - {exc_val}")
      # True를 반환하여 예외를 무시하도록 지시
      return True
    return False

class ApiParameterPlaceholder:
  ...

# change to any task_id in train, dev (not test to preserve test data sanctity).
# e.g., choose one from load_task_ids("train"), load_task_ids("dev")
task_id = "6b6ca61_1"
world = AppWorld(task_id, raise_on_failure=False)
apis = world.apis

# Let's translate the instruction to pseudocode.
# pseudocode start:
"""
# translation of the intruction into pseudocode
rows = list_of_people_I_owe_money_to() # in owe_list.csv
for row in rows:
  if has_venmo_account(person(row)):
    send_money_privately_to(person=person(row), amount=amount(row), description=description(row))
  else:
    create_individual_non_grouped_splitwise_expense(amount=amount(row), description=description(row))
    attach_pdf_receipt() # They are in the same folder as the CSV file.
"""
# pseudocode ends

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


query = "owe_list.csv"
access_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJmaWxlX3N5c3RlbStsaW5kc2V5c2ltcHNvbkBnbWFpbC5jb20iLCJleHAiOjE2ODQ0MTI3OTl9.RfTqsMQzrPMMFjRPVV7wG65-iCKePseNUwoD63Y4WDA"
directory_path = None
substring = query
entry_type = "files"
recursive = True

_apis = AppWrap(apis)
result = _apis.file_system.show_directory(
  access_token=access_token,
  directory_path=None,
  substring="owe_list.csv",
  entry_type="files",
  recursive=True,
)
print(result)


world.close()