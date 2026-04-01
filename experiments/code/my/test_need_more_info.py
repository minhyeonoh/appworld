"""Tests for has_mixed_need_more_info detection."""

from appworld_agents.code.my.actions import has_mixed_need_more_info

passed = 0
failed = 0

def test(name, code, expected):
    global passed, failed
    result = has_mixed_need_more_info(code)
    if result == expected:
        passed += 1
        print(f"  PASS: {name}")
    else:
        failed += 1
        print(f"  FAIL: {name} — expected {expected}, got {result}")


# =========================================================================
# 1. No NeedMoreInformation at all (clean implementation) → False
# =========================================================================
print("\n--- No NeedMoreInformation (clean impl) ---")

test("simple return",
     "def solve(x):\n  return x + 1",
     False)

test("multi-line implementation",
     "def solve(x):\n  y = x * 2\n  z = y + 1\n  return z",
     False)

test("with AssertionError",
     "def solve(x):\n  if x < 0:\n    raise AssertionError('negative')\n  return x",
     False)

test("empty body pass",
     "def solve():\n  pass",
     False)

test("raise NotImplementedError",
     "def solve():\n  raise NotImplementedError()",
     False)

test("complex implementation no NMI",
     """def get_token():
  password = get_password()
  result = auth.login(username=email, password=password)
  token = result['access_token']
  return token""",
     False)

test("string containing NeedMoreInformation text but not a raise",
     'def solve():\n  return "NeedMoreInformation is just a string"',
     False)

# =========================================================================
# 2. Single raise NeedMoreInformation only (clean give-up) → False
# =========================================================================
print("\n--- Single NeedMoreInformation only (clean give-up) ---")

test("bare NeedMoreInformation",
     "def solve():\n  raise NeedMoreInformation('not enough context')",
     False)

test("NeedMoreInformation with long message",
     "def solve():\n  raise NeedMoreInformation('I need to know the user ID and auth token to proceed')",
     False)

test("NeedMoreInformation no message",
     "def solve():\n  raise NeedMoreInformation()",
     False)

test("NeedMoreInformation with f-string",
     "def solve(x):\n  raise NeedMoreInformation(f'cannot solve for {x}')",
     False)

test("NeedMoreInformation with extra whitespace/indentation",
     "def solve():\n    raise NeedMoreInformation('nope')",
     False)

test("NeedMoreInformation with blank lines around",
     "def solve():\n\n  raise NeedMoreInformation('nope')\n\n",
     False)

# =========================================================================
# 3. Mixed: NeedMoreInformation + other statements → True
# =========================================================================
print("\n--- Mixed NeedMoreInformation (should flag) ---")

test("NMI after assignment",
     "def solve():\n  x = get_data()\n  raise NeedMoreInformation('missing info')",
     True)

test("NMI before return",
     "def solve():\n  raise NeedMoreInformation('hmm')\n  return 42",
     True)

test("NMI in if branch with other code",
     "def solve(x):\n  if x is None:\n    raise NeedMoreInformation('x is None')\n  return x + 1",
     True)

test("NMI in else branch",
     "def solve(x):\n  if x > 0:\n    return x\n  else:\n    raise NeedMoreInformation('negative')",
     True)

test("NMI after multiple setup lines",
     """def get_token():
  password = get_password()
  if password is None:
    raise NeedMoreInformation('password not available')
  result = auth.login(password=password)
  return result['token']""",
     True)

test("NMI in try/except",
     """def solve():
  try:
    result = do_something()
    return result
  except Exception:
    raise NeedMoreInformation('failed')""",
     True)

test("NMI with preceding comment only (comment is not a statement)",
     "def solve():\n  # We don't have enough info\n  raise NeedMoreInformation('nope')",
     False)

test("multiple NMI raises",
     """def solve(x):
  if x == 'a':
    raise NeedMoreInformation('case a')
  elif x == 'b':
    raise NeedMoreInformation('case b')""",
     True)

test("NMI after API call",
     """def get_data():
  token = get_access_token()
  data = api.fetch(token=token)
  raise NeedMoreInformation('need to check format')""",
     True)

test("NMI sandwiched between code",
     """def solve():
  x = 1
  raise NeedMoreInformation('missing')
  y = 2
  return y""",
     True)

test("partial impl with NMI as fallback default",
     """def solve(x):
  result = lookup(x)
  if result is None:
    raise NeedMoreInformation('lookup returned None')
  return result['value']""",
     True)

test("NMI inside for loop",
     """def solve(items):
  for item in items:
    if item.get('key') is None:
      raise NeedMoreInformation('missing key')
  return [i['key'] for i in items]""",
     True)

test("NMI with variable assignment on same thought",
     """def solve():
  info = "not enough"
  raise NeedMoreInformation(info)""",
     True)

test("real-world: partial impl with NMI guard",
     """def get_file_system_access_token():
  my_password = get_my_password()
  if my_password is None:
    raise NeedMoreInformation("Cannot determine user's password")
  login_result = file_system.login(username=my_email, password=my_password)
  return login_result['access_token']""",
     True)

test("NMI after helper calls and data processing",
     """def calculate_total():
  items = get_items()
  prices = [item['price'] for item in items]
  tax_rate = get_tax_rate()
  if tax_rate is None:
    raise NeedMoreInformation('tax rate not available')
  return sum(prices) * (1 + tax_rate)""",
     True)

# =========================================================================
# 4. Edge cases
# =========================================================================
print("\n--- Edge cases ---")

test("NeedMoreInformation in a string literal only",
     'def solve():\n  msg = "raise NeedMoreInformation(oops)"\n  return msg',
     False)

test("NeedMoreInformation as variable name (unusual but possible)",
     "def solve():\n  NeedMoreInformation = Exception\n  raise NeedMoreInformation('x')",
     True)

test("deeply indented single NMI",
     "def solve():\n        raise NeedMoreInformation('deep indent')",
     False)

test("function with decorator-like syntax",
     "def solve():\n  raise NeedMoreInformation(\n    'multi-line\\n'\n    'message'\n  )",
     False)

# =========================================================================
# Summary
# =========================================================================
print(f"\n{'='*60}")
print(f"Results: {passed} passed, {failed} failed, {passed + failed} total")
if failed == 0:
    print("All tests passed!")
else:
    print(f"WARNING: {failed} test(s) failed!")
print(f"{'='*60}")
