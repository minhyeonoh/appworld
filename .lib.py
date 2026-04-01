
@show_locals_on_exception(type_hints=False)
def get_account_password(account_name):
  password_list = supervisor.show_account_passwords()
  for account in password_list:
    if account["account_name"] == account_name:
      return account["password"]
  raise NeverHappen(
    f"The '{account_name}' account was not found in the password list."
  )

@show_locals_on_exception(type_hints=False)
def get_service_access_token(service_name, username):
  password = get_account_password(service_name)
  access_token = file_system.login(username=username, password=password)
  return access_token


try:
  main()
except (FunctionNotFound, NotImplementedError, ReturnAsException):
  pass