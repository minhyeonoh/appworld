"""Robust Python function definition extractor for LLM responses.

Extracts function definitions from LLM output that may contain markdown
fences, prose, multiple code blocks, or malformed formatting. Supports
retry-based generation with configurable cleanup and validation.
"""

from __future__ import annotations

from typing import Any, Callable, TypeVar

import builtins
import libcst as cst

from appworld.common.my_code_parsing import (
    extract_python_function_defs,
    lift_inner_functions,
    parse_code_function_calls,
    remove_docstring,
)
from appworld.common import my_code_parsing as codeparse


T = TypeVar("T")


class PythonParseError(ValueError):
    """Raised when a Python function definition cannot be extracted."""

    def __init__(self, message: str, original_text: str):
        self.original_text = original_text
        super().__init__(f"{message}\n--- Original text (first 500 chars) ---\n{original_text[:500]}")


def generate_python_def(
    generate_fn: Callable[..., T],
    *args,
    target: str | list[str] | None = None,
    reindent: str | None = None,
    remove_docstrings: bool = True,
    remove_comments: bool = False,
    hoist_inner_functions: bool = False,
    max_retries: int = 3,
    get_text: Callable[[T], str] | None = None,
    **kwargs,
) -> tuple[str | dict[str, str], T]:
    """Generate and extract Python function definition(s) from LLM response, with retry.

    Parameters
    ----------
    generate_fn : callable
        The generation function. Called as generate_fn(*args, **kwargs).
    target : str | list[str] | None
        - str: extract a single function by name, return its code as str.
        - list[str]: extract these functions, return dict[name, code].
        - None: extract all functions found, return dict[name, code].
    reindent : str | None
        Re-indent function body to this string (e.g. "  ").
    remove_docstrings : bool
        Strip docstrings from extracted functions (default True).
    remove_comments : bool
        Strip comments from extracted functions (default False).
    hoist_inner_functions : bool
        Also extract inner (nested) function definitions as top-level entries.
    max_retries : int
        Maximum generation attempts (default 3).
    get_text : callable or None
        Extracts text from generate_fn's return value. Defaults to .content.

    Returns
    -------
    (code, response) : tuple
        - If target is str: (code_string, response)
        - If target is list or None: (dict[name, code], response)
    """
    if get_text is None:
        get_text = lambda r: r.content

    def _cleanup(code: str) -> str:
        if remove_docstrings:
            code = remove_docstring(code)
        if remove_comments:
            code = codeparse.remove_comments(code)
        return code

    last_error = None
    text = ""
    for _ in range(max_retries):
        response = generate_fn(*args, **kwargs)
        text = get_text(response)
        try:
            result = extract_python_function_defs(text, target=target, reindent=reindent)

            if result is None:
                raise PythonParseError("No function definitions found", text)

            # Single target: result is a string
            if isinstance(target, str):
                return _cleanup(result), response

            # Multiple/all targets: result is a dict
            if not isinstance(result, dict) or not result:
                raise PythonParseError("No function definitions found", text)

            function_defs = {}
            for name, code in result.items():
                function_defs[name] = _cleanup(code)
                if hoist_inner_functions:
                    for inner_name, inner_code in lift_inner_functions(code, cleanup=True).items():
                        function_defs[inner_name] = _cleanup(inner_code)

            # If specific targets requested, verify all found
            if isinstance(target, list):
                missing = [t for t in target if t not in function_defs]
                if missing:
                    raise PythonParseError(f"Missing function(s): {missing}", text)

            return function_defs, response

        except PythonParseError as e:
            last_error = e
        except Exception as e:
            last_error = PythonParseError(str(e), text)

    raise PythonParseError(
        f"Failed to extract Python def after {max_retries} attempts. Last error: {last_error}",
        text,
    )


# ---------------------------------------------------------------------------
# Dual-format response parsing (Python def OR JSON)
# ---------------------------------------------------------------------------

from appworld_agents.code.my.json_parser import parse_json_dict, JSONParseError


def parse_code_or_json(
    text: str,
    target: str,
    reindent: str | None = None,
    remove_docstrings: bool = True,
    remove_comments: bool = False,
) -> tuple[str, str | None] | tuple[None, dict]:
    """Parse an LLM response that is either a Python function def or a JSON dict.

    Strategy:
    1. Try extracting a Python function def with the given target name.
       If found → return (code, None) meaning "yes" evaluation.
    2. Try parsing as JSON dict.
       If found → return (None, json_dict) meaning "no" evaluation.
    3. Both fail → raise PythonParseError with diagnostic info.

    Returns
    -------
    (code, None) — evaluation is "yes", code is the extracted function def.
    (None, json_dict) — evaluation is "no", json_dict has rationale/evaluation.
    """
    # 1. Try Python function def
    try:
        result = extract_python_function_defs(text, target=target, reindent=reindent)
        if result is not None:
            code = result
            if remove_docstrings:
                code = remove_docstring(code)
            if remove_comments:
                code = codeparse.remove_comments(code)
            return code, None
    except Exception:
        pass

    # 2. Try JSON dict
    try:
        d = parse_json_dict(text)
        if "evaluation" in d:
            return None, d
    except JSONParseError:
        pass

    # 3. Both failed — build diagnostic
    has_python = "def " in text and target in text
    has_json = "{" in text and "evaluation" in text
    if has_python and has_json:
        hint = "Response contains both Python code and JSON. Return ONLY one format."
    elif has_python:
        hint = f"Python code found but function `{target}` could not be extracted. Check syntax."
    elif has_json:
        hint = "JSON found but could not be parsed. Check for syntax errors in the JSON block."
    else:
        hint = f"Expected either a Python function `{target}` or a JSON dict with 'evaluation' key."
    raise PythonParseError(hint, text)


def generate_code_or_json(
    generate_fn: Callable[..., T],
    *args,
    target: str,
    reindent: str | None = None,
    remove_docstrings: bool = True,
    remove_comments: bool = False,
    max_retries: int = 3,
    get_text: Callable[[T], str] | None = None,
    **kwargs,
) -> tuple[tuple[str, None] | tuple[None, dict], T]:
    """Generate and parse a dual-format response (Python def or JSON), with retry.

    On parse failure, appends the diagnostic to the message thread and reprompts
    the LLM to strictly follow the response format.

    Returns
    -------
    ((code, None), response) — "yes" evaluation with transformed code.
    ((None, json_dict), response) — "no" evaluation with rationale.
    """
    if get_text is None:
        get_text = lambda r: r.content

    last_error = None
    for attempt in range(max_retries):
        response = generate_fn(*args, **kwargs)
        text = get_text(response)
        try:
            result = parse_code_or_json(
                text, target=target, reindent=reindent,
                remove_docstrings=remove_docstrings, remove_comments=remove_comments,
            )
            return result, response
        except PythonParseError as e:
            last_error = e
            # Inject feedback into the message thread for next retry
            # The caller's *args should include msgs — we append to it
            # Find the msgs object (first positional arg by convention)
            if args and hasattr(args[0], 'add'):
                msgs = args[0]
                msgs.add(role="assistant", content=text)
                msgs.add(role="user", content=(
                    f"Your response could not be parsed. {e.args[0].splitlines()[0]}\n\n"
                    f"You MUST follow the response format strictly:\n"
                    f"- If evaluation is 'no': output ONLY a JSON block.\n"
                    f"- If evaluation is 'yes': output ONLY a Python function `{target}`.\n"
                    f"Do NOT mix both formats."
                ))

    raise PythonParseError(
        f"Failed to parse code-or-json after {max_retries} attempts. Last error: {last_error}",
        text,
    )


# ---------------------------------------------------------------------------
# Hallucinated API call sanitization
# ---------------------------------------------------------------------------

_BUILTIN_DOTTED_PREFIXES = {
    name for name in dir(builtins)
} | {
    # Common Python method-chain prefixes that look like dotted calls
    # but are actually method calls on objects
    "self", "cls", "super",
}


class _RenameDottedCalls(cst.CSTTransformer):
    """CST transformer that replaces `app_name.api_name(...)` with `app_name_api_name(...)`."""

    def __init__(self, renames: dict[str, str]):
        super().__init__()
        self.renames = renames  # {"spotify.get_playlist": "spotify_get_playlist", ...}

    def leave_Call(self, original: cst.Call, updated: cst.Call) -> cst.Call:
        func = updated.func
        if isinstance(func, cst.Attribute) and isinstance(func.value, cst.Name):
            dotted = f"{func.value.value}.{func.attr.value}"
            if dotted in self.renames:
                return updated.with_changes(
                    func=cst.Name(self.renames[dotted])
                )
        return updated


def sanitize_api_calls(
    code: str,
    expected_api: str,
    app_names: set[str],
    is_valid_api: Callable[[str], bool] | None = None,
) -> tuple[str, list[str]]:
    """Sanitize hallucinated API calls in LLM-generated code.

    Rules:
    1. `app_name.api_name(...)` where app_name is a valid app but the call
       is NOT the expected API → rename to `app_name_api_name(...)` (turns
       into a helper function call that can be implemented later).
    2. Dotted calls on builtins/methods (e.g. `dict.get(...)`, `result.append(...)`)
       → leave untouched.
    3. Other unknown dotted calls → flagged for the caller to decide
       (returned in the `unknown` list).

    Parameters
    ----------
    code : str
        The generated Python code (full function def).
    expected_api : str
        The API that was requested, e.g. "spotify.search_tracks".
    app_names : set[str]
        Valid app names in the system.
    is_valid_api : callable or None
        Optional check `(dotted_name) -> bool` for whether a dotted call
        is actually a known API. If None, any `app_name.x` is treated as an API.

    Returns
    -------
    (sanitized_code, unknown_calls) : tuple
        sanitized_code: code with hallucinated app API calls renamed.
        unknown_calls: list of dotted calls that are neither app APIs
                       nor recognized builtins (case 3).
    """
    calls = parse_code_function_calls(code)

    renames = {}
    unknown = []

    for call in calls:
        parts = call.name.split(".")
        if len(parts) != 2:
            continue

        prefix, suffix = parts
        dotted = call.name

        # Skip the expected API
        if dotted == expected_api:
            continue

        # Case 1: prefix is a valid app name → hallucinated API call
        if prefix in app_names:
            new_name = f"{prefix}_{suffix}"
            renames[dotted] = new_name
            continue

        # Case 2: builtin or method call on a variable → leave alone
        if prefix in _BUILTIN_DOTTED_PREFIXES:
            continue

        # The prefix could be a local variable (result.append, response.json, etc.)
        # These are method calls, not API calls — leave them alone.
        # We can't fully resolve types, so we use a heuristic:
        # if the prefix is lowercase and not an app name, it's likely a variable.
        if prefix[0].islower() and prefix not in app_names:
            continue

        # Case 3: truly unknown
        unknown.append(dotted)

    # Apply renames via CST
    if renames:
        tree = cst.parse_module(code)
        transformer = _RenameDottedCalls(renames)
        tree = tree.visit(transformer)
        code = tree.code

    return code, unknown


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    passed = 0
    failed = 0

    class FakeMsg:
        def __init__(self, content: str):
            self.content = content

    # =======================================================================
    # 1. Single target extraction
    # =======================================================================
    print("\n--- Single target ---")

    try:
        def gen_single():
            return FakeMsg('```python\ndef solve(x):\n  return x + 1\n```')
        code, resp = generate_python_def(gen_single, target="solve")
        assert "def solve(x):" in code
        assert "return x + 1" in code
        passed += 1
        print("  PASS: extract single function")
    except Exception as e:
        failed += 1
        print(f"  FAIL: extract single function — {e}")

    # With prose around it
    try:
        def gen_with_prose():
            return FakeMsg('Here is the solution:\n```python\ndef solve(x):\n  return x * 2\n```\nDone!')
        code, resp = generate_python_def(gen_with_prose, target="solve")
        assert "return x * 2" in code
        passed += 1
        print("  PASS: extract from prose + fence")
    except Exception as e:
        failed += 1
        print(f"  FAIL: extract from prose + fence — {e}")

    # =======================================================================
    # 2. Multiple targets
    # =======================================================================
    print("\n--- Multiple targets ---")

    try:
        def gen_multi():
            return FakeMsg('```python\ndef foo():\n  return 1\n\ndef bar():\n  return 2\n```')
        defs, resp = generate_python_def(gen_multi, target=["foo", "bar"])
        assert "foo" in defs and "bar" in defs
        assert "return 1" in defs["foo"]
        assert "return 2" in defs["bar"]
        passed += 1
        print("  PASS: extract multiple targets")
    except Exception as e:
        failed += 1
        print(f"  FAIL: extract multiple targets — {e}")

    # =======================================================================
    # 3. All functions (target=None)
    # =======================================================================
    print("\n--- All functions ---")

    try:
        def gen_all():
            return FakeMsg('```python\ndef a():\n  pass\n\ndef b():\n  pass\n\ndef c():\n  pass\n```')
        defs, resp = generate_python_def(gen_all, target=None)
        assert set(defs.keys()) == {"a", "b", "c"}
        passed += 1
        print("  PASS: extract all functions")
    except Exception as e:
        failed += 1
        print(f"  FAIL: extract all functions — {e}")

    # =======================================================================
    # 4. Retry on failure
    # =======================================================================
    print("\n--- Retry ---")

    try:
        c = [0]
        def gen_flaky_code():
            c[0] += 1
            if c[0] < 3:
                return FakeMsg("no code here at all")
            return FakeMsg('```python\ndef solve(x):\n  return x\n```')
        code, resp = generate_python_def(gen_flaky_code, target="solve", max_retries=5)
        assert "return x" in code
        assert c[0] == 3
        passed += 1
        print("  PASS: retries on missing code")
    except Exception as e:
        failed += 1
        print(f"  FAIL: retries on missing code — {e}")

    # Exhausts retries
    try:
        c = [0]
        def gen_always_bad():
            c[0] += 1
            return FakeMsg("just text, no code")
        generate_python_def(gen_always_bad, target="solve", max_retries=2)
        failed += 1
        print("  FAIL: exhausts retries — expected error")
    except PythonParseError:
        assert c[0] == 2
        passed += 1
        print("  PASS: exhausts retries and raises")
    except Exception as e:
        failed += 1
        print(f"  FAIL: exhausts retries — {e}")

    # max_retries=1
    try:
        c = [0]
        def gen_once_bad():
            c[0] += 1
            return FakeMsg("nope")
        generate_python_def(gen_once_bad, target="solve", max_retries=1)
        failed += 1
        print("  FAIL: max_retries=1 — expected error")
    except PythonParseError:
        assert c[0] == 1
        passed += 1
        print("  PASS: max_retries=1 only calls once")
    except Exception as e:
        failed += 1
        print(f"  FAIL: max_retries=1 — {e}")

    # =======================================================================
    # 5. Retry on wrong target
    # =======================================================================
    print("\n--- Wrong target retry ---")

    try:
        c = [0]
        def gen_wrong_then_right():
            c[0] += 1
            if c[0] == 1:
                return FakeMsg('```python\ndef wrong_name():\n  pass\n```')
            return FakeMsg('```python\ndef solve(x):\n  return x + 1\n```')
        code, resp = generate_python_def(gen_wrong_then_right, target="solve", max_retries=3)
        assert "return x + 1" in code
        assert c[0] == 2
        passed += 1
        print("  PASS: retries when target function not found")
    except Exception as e:
        failed += 1
        print(f"  FAIL: retries when target function not found — {e}")

    # Missing one of multiple targets
    try:
        c = [0]
        def gen_missing_one():
            c[0] += 1
            if c[0] == 1:
                return FakeMsg('```python\ndef foo():\n  return 1\n```')
            return FakeMsg('```python\ndef foo():\n  return 1\n\ndef bar():\n  return 2\n```')
        defs, resp = generate_python_def(gen_missing_one, target=["foo", "bar"], max_retries=3)
        assert "foo" in defs and "bar" in defs
        assert c[0] == 2
        passed += 1
        print("  PASS: retries when one target missing from multi")
    except Exception as e:
        failed += 1
        print(f"  FAIL: retries when one target missing from multi — {e}")

    # =======================================================================
    # 6. Docstring removal
    # =======================================================================
    print("\n--- Cleanup options ---")

    try:
        def gen_with_docstring():
            return FakeMsg('```python\ndef solve(x):\n  """Solve it."""\n  return x\n```')
        code, resp = generate_python_def(gen_with_docstring, target="solve", remove_docstrings=True)
        assert '"""' not in code
        assert "return x" in code
        passed += 1
        print("  PASS: remove_docstrings=True strips docstring")
    except Exception as e:
        failed += 1
        print(f"  FAIL: remove_docstrings=True strips docstring — {e}")

    try:
        def gen_with_docstring2():
            return FakeMsg('```python\ndef solve(x):\n  """Solve it."""\n  return x\n```')
        code, resp = generate_python_def(gen_with_docstring2, target="solve", remove_docstrings=False)
        assert '"""' in code
        passed += 1
        print("  PASS: remove_docstrings=False keeps docstring")
    except Exception as e:
        failed += 1
        print(f"  FAIL: remove_docstrings=False keeps docstring — {e}")

    # =======================================================================
    # 7. Custom get_text
    # =======================================================================
    print("\n--- Custom get_text ---")

    try:
        class WeirdResp:
            def __init__(self, data):
                self.data = data
        def gen_weird():
            return WeirdResp({"output": '```python\ndef solve():\n  return 42\n```'})
        code, resp = generate_python_def(gen_weird, target="solve", get_text=lambda r: r.data["output"])
        assert "return 42" in code
        passed += 1
        print("  PASS: custom get_text")
    except Exception as e:
        failed += 1
        print(f"  FAIL: custom get_text — {e}")

    # =======================================================================
    # 8. Args/kwargs forwarded
    # =======================================================================
    print("\n--- Args/kwargs forwarding ---")

    try:
        def gen_with_args(msgs, prefix=None):
            code = '```python\ndef solve():\n  return 1\n```'
            if prefix:
                code = prefix + code
            return FakeMsg(code)
        code, resp = generate_python_def(gen_with_args, "hello", target="solve", prefix="# ")
        assert "return 1" in code
        passed += 1
        print("  PASS: args and kwargs forwarded")
    except Exception as e:
        failed += 1
        print(f"  FAIL: args and kwargs forwarded — {e}")

    # =======================================================================
    # 9. Multiple code blocks in response
    # =======================================================================
    print("\n--- Multiple code blocks ---")

    try:
        def gen_multi_blocks():
            return FakeMsg(
                'First block:\n```python\ndef helper():\n  return 0\n```\n'
                'Main:\n```python\ndef solve(x):\n  return helper() + x\n```'
            )
        defs, resp = generate_python_def(gen_multi_blocks, target=None)
        assert "helper" in defs
        assert "solve" in defs
        passed += 1
        print("  PASS: functions from multiple code blocks")
    except Exception as e:
        failed += 1
        print(f"  FAIL: functions from multiple code blocks — {e}")

    # =======================================================================
    # 10. Hoist inner functions
    # =======================================================================
    print("\n--- Hoist inner functions ---")

    try:
        def gen_with_inner():
            return FakeMsg('```python\ndef outer():\n  def inner():\n    return 1\n  return inner()\n```')
        defs, resp = generate_python_def(gen_with_inner, target=None, hoist_inner_functions=True)
        assert "outer" in defs
        assert "inner" in defs
        passed += 1
        print("  PASS: hoist_inner_functions=True")
    except Exception as e:
        failed += 1
        print(f"  FAIL: hoist_inner_functions=True — {e}")

    # Note: extract_python_function_defs always picks up inner defs too.
    # hoist_inner_functions controls the *additional* lift_inner_functions pass
    # which restructures them (removes from parent, adds as top-level).
    # With target="outer", inner is NOT returned when hoist is off.
    try:
        def gen_with_inner2():
            return FakeMsg('```python\ndef outer():\n  def inner():\n    return 1\n  return inner()\n```')
        code, resp = generate_python_def(gen_with_inner2, target="outer", hoist_inner_functions=False)
        assert "def outer" in code
        passed += 1
        print("  PASS: hoist_inner_functions=False with single target")
    except Exception as e:
        failed += 1
        print(f"  FAIL: hoist_inner_functions=False with single target — {e}")

    # =======================================================================
    # 11. sanitize_api_calls
    # =======================================================================
    print("\n--- sanitize_api_calls ---")

    apps = {"spotify", "file_system", "phone", "supervisor"}

    # Expected API is kept
    try:
        code = "def main():\n  result = spotify.search_tracks(query='test')\n  return result"
        sanitized, unknown = sanitize_api_calls(code, "spotify.search_tracks", apps)
        assert "spotify.search_tracks" in sanitized
        assert not unknown
        passed += 1
        print("  PASS: expected API kept unchanged")
    except Exception as e:
        failed += 1
        print(f"  FAIL: expected API kept unchanged — {e}")

    # Hallucinated API (valid app, wrong API) → renamed to underscore
    try:
        code = "def main():\n  x = spotify.search_tracks(q='a')\n  y = spotify.get_playlist(id=1)\n  return y"
        sanitized, unknown = sanitize_api_calls(code, "spotify.search_tracks", apps)
        assert "spotify.search_tracks" in sanitized
        assert "spotify_get_playlist" in sanitized
        assert "spotify.get_playlist" not in sanitized
        assert not unknown
        passed += 1
        print("  PASS: hallucinated app API renamed to underscore")
    except Exception as e:
        failed += 1
        print(f"  FAIL: hallucinated app API renamed to underscore — {e}")

    # Multiple hallucinated APIs from different apps
    try:
        code = (
            "def main():\n"
            "  a = spotify.search_tracks(q='x')\n"
            "  b = file_system.read_file(path='y')\n"
            "  c = phone.send_sms(to='z')\n"
            "  return a, b, c"
        )
        sanitized, unknown = sanitize_api_calls(code, "spotify.search_tracks", apps)
        assert "spotify.search_tracks" in sanitized
        assert "file_system_read_file" in sanitized
        assert "phone_send_sms" in sanitized
        assert not unknown
        passed += 1
        print("  PASS: multiple hallucinated APIs from different apps")
    except Exception as e:
        failed += 1
        print(f"  FAIL: multiple hallucinated APIs from different apps — {e}")

    # Builtin method calls left alone
    try:
        code = (
            "def main():\n"
            "  d = {}\n"
            "  result = spotify.search_tracks(q='x')\n"
            "  items = result.get('items', [])\n"
            "  name = items[0].get('name')\n"
            "  return name"
        )
        sanitized, unknown = sanitize_api_calls(code, "spotify.search_tracks", apps)
        assert "result.get" in sanitized
        assert "items[0].get" in sanitized
        assert not unknown
        passed += 1
        print("  PASS: builtin method calls left alone")
    except Exception as e:
        failed += 1
        print(f"  FAIL: builtin method calls left alone — {e}")

    # Variable method calls left alone (response.json, data.append, etc.)
    try:
        code = (
            "def main():\n"
            "  response = spotify.search_tracks(q='x')\n"
            "  data = response.json()\n"
            "  items = data.get('items')\n"
            "  names = []\n"
            "  names.append(items[0])\n"
            "  return names"
        )
        sanitized, unknown = sanitize_api_calls(code, "spotify.search_tracks", apps)
        assert "response.json" in sanitized
        assert "data.get" in sanitized
        assert "names.append" in sanitized
        assert not unknown
        passed += 1
        print("  PASS: variable method calls left alone")
    except Exception as e:
        failed += 1
        print(f"  FAIL: variable method calls left alone — {e}")

    # No dotted calls at all
    try:
        code = "def main():\n  x = helper()\n  return x"
        sanitized, unknown = sanitize_api_calls(code, "spotify.search_tracks", apps)
        assert sanitized.strip() == code.strip()
        assert not unknown
        passed += 1
        print("  PASS: no dotted calls unchanged")
    except Exception as e:
        failed += 1
        print(f"  FAIL: no dotted calls unchanged — {e}")

    # Only expected API, nothing else
    try:
        code = "def main():\n  return spotify.search_tracks(q='test')"
        sanitized, unknown = sanitize_api_calls(code, "spotify.search_tracks", apps)
        assert "spotify.search_tracks" in sanitized
        assert not unknown
        passed += 1
        print("  PASS: only expected API present")
    except Exception as e:
        failed += 1
        print(f"  FAIL: only expected API present — {e}")

    # Unknown dotted call (prefix not an app, not a lowercase variable)
    try:
        code = "def main():\n  x = ExternalService.fetch(url='http://example.com')\n  return x"
        sanitized, unknown = sanitize_api_calls(code, "spotify.search_tracks", apps)
        assert "ExternalService.fetch" in sanitized  # not renamed
        assert "ExternalService.fetch" in unknown
        passed += 1
        print("  PASS: unknown uppercase dotted call flagged")
    except Exception as e:
        failed += 1
        print(f"  FAIL: unknown uppercase dotted call flagged — {e}")

    # Mixed: expected + hallucinated + builtin method + unknown
    try:
        code = (
            "def main():\n"
            "  result = spotify.search_tracks(q='x')\n"
            "  extra = spotify.get_album(id=1)\n"
            "  items = result.get('items')\n"
            "  wtf = UnknownThing.do_stuff()\n"
            "  return items"
        )
        sanitized, unknown = sanitize_api_calls(code, "spotify.search_tracks", apps)
        assert "spotify.search_tracks" in sanitized
        assert "spotify_get_album" in sanitized
        assert "spotify.get_album" not in sanitized
        assert "result.get" in sanitized
        assert "UnknownThing.do_stuff" in sanitized
        assert "UnknownThing.do_stuff" in unknown
        passed += 1
        print("  PASS: mixed scenario")
    except Exception as e:
        failed += 1
        print(f"  FAIL: mixed scenario — {e}")

    # =======================================================================
    # 12. parse_code_or_json
    # =======================================================================
    print("\n--- parse_code_or_json ---")

    # --- "yes" cases: Python function returned ---

    try:
        text = '```python\ndef solve(x):\n  return {"primary": x, "extras": {}}\n```'
        code, json_result = parse_code_or_json(text, target="solve")
        assert code is not None
        assert json_result is None
        assert "primary" in code
        passed += 1
        print("  PASS: yes — clean python in fence")
    except Exception as e:
        failed += 1
        print(f"  FAIL: yes — clean python in fence — {e}")

    try:
        text = 'Here is the transformed code:\n```python\ndef solve(x):\n  return {"primary": x + 1, "extras": {"raw": x}}\n```\nDone!'
        code, json_result = parse_code_or_json(text, target="solve")
        assert code is not None and json_result is None
        passed += 1
        print("  PASS: yes — python with prose around")
    except Exception as e:
        failed += 1
        print(f"  FAIL: yes — python with prose around — {e}")

    try:
        text = 'def solve(x):\n  return {"primary": x, "extras": {}}'
        code, json_result = parse_code_or_json(text, target="solve")
        assert code is not None and json_result is None
        passed += 1
        print("  PASS: yes — bare python without fence")
    except Exception as e:
        failed += 1
        print(f"  FAIL: yes — bare python without fence — {e}")

    try:
        text = '```python\ndef get_token():\n  """Get token."""\n  pwd = get_password()\n  return {"primary": pwd, "extras": {}}\n```'
        code, json_result = parse_code_or_json(text, target="get_token", remove_docstrings=True)
        assert code is not None and json_result is None
        assert '"""' not in code
        passed += 1
        print("  PASS: yes — docstring removed")
    except Exception as e:
        failed += 1
        print(f"  FAIL: yes — docstring removed — {e}")

    # --- "no" cases: JSON returned ---

    try:
        text = '```json\n{"rationale": "missing auth token", "evaluation": "no"}\n```'
        code, json_result = parse_code_or_json(text, target="solve")
        assert code is None
        assert json_result is not None
        assert json_result["evaluation"] == "no"
        assert "missing auth token" in json_result["rationale"]
        passed += 1
        print("  PASS: no — json in fence")
    except Exception as e:
        failed += 1
        print(f"  FAIL: no — json in fence — {e}")

    try:
        text = '{"rationale": "not enough data", "evaluation": "no"}'
        code, json_result = parse_code_or_json(text, target="solve")
        assert code is None and json_result is not None
        assert json_result["evaluation"] == "no"
        passed += 1
        print("  PASS: no — bare json")
    except Exception as e:
        failed += 1
        print(f"  FAIL: no — bare json — {e}")

    try:
        text = 'Based on my analysis:\n```json\n{"rationale": "return type mismatch", "evaluation": "no"}\n```'
        code, json_result = parse_code_or_json(text, target="solve")
        assert code is None and json_result is not None
        passed += 1
        print("  PASS: no — json with prose before")
    except Exception as e:
        failed += 1
        print(f"  FAIL: no — json with prose before — {e}")

    try:
        text = '{"rationale": "incomplete", "evaluation": "no",}'
        code, json_result = parse_code_or_json(text, target="solve")
        assert code is None and json_result is not None
        passed += 1
        print("  PASS: no — json with trailing comma")
    except Exception as e:
        failed += 1
        print(f"  FAIL: no — json with trailing comma — {e}")

    # --- Python takes priority over JSON ---

    try:
        text = '```python\ndef solve():\n  return {"primary": 1, "extras": {}}\n```\n\nNote: evaluation is yes.'
        code, json_result = parse_code_or_json(text, target="solve")
        assert code is not None and json_result is None
        passed += 1
        print("  PASS: python prioritized over trailing text")
    except Exception as e:
        failed += 1
        print(f"  FAIL: python prioritized over trailing text — {e}")

    # --- Failure cases ---

    try:
        text = "I'm not sure what to do here."
        parse_code_or_json(text, target="solve")
        failed += 1
        print("  FAIL: garbage text — expected error")
    except PythonParseError as e:
        assert "Expected either" in str(e)
        passed += 1
        print("  PASS: garbage text raises PythonParseError")
    except Exception as e:
        failed += 1
        print(f"  FAIL: garbage text — {type(e).__name__}: {e}")

    try:
        text = '{"rationale": "broken json'
        parse_code_or_json(text, target="solve")
        failed += 1
        print("  FAIL: broken json — expected error")
    except PythonParseError:
        passed += 1
        print("  PASS: broken json raises PythonParseError")
    except Exception as e:
        failed += 1
        print(f"  FAIL: broken json — {type(e).__name__}: {e}")

    try:
        text = '```python\ndef wrong_name():\n  return 1\n```'
        parse_code_or_json(text, target="solve")
        failed += 1
        print("  FAIL: wrong function name — expected error")
    except PythonParseError as e:
        assert "solve" in str(e)
        passed += 1
        print("  PASS: wrong function name raises PythonParseError")
    except Exception as e:
        failed += 1
        print(f"  FAIL: wrong function name — {type(e).__name__}: {e}")

    try:
        text = '{"some_key": "no evaluation field"}'
        parse_code_or_json(text, target="solve")
        failed += 1
        print("  FAIL: json without evaluation key — expected error")
    except PythonParseError:
        passed += 1
        print("  PASS: json without evaluation key raises PythonParseError")
    except Exception as e:
        failed += 1
        print(f"  FAIL: json without evaluation key — {type(e).__name__}: {e}")

    # --- Edge cases ---

    try:
        text = '```python\ndef solve():\n  # evaluation is yes\n  return {"primary": 42, "extras": {}}\n```'
        code, json_result = parse_code_or_json(text, target="solve", remove_comments=True)
        assert code is not None and json_result is None
        assert "evaluation" not in code
        passed += 1
        print("  PASS: comment containing 'evaluation' removed")
    except Exception as e:
        failed += 1
        print(f"  FAIL: comment containing 'evaluation' removed — {e}")

    try:
        text = '```json\n{"rationale": "def solve() is wrong", "evaluation": "no"}\n```'
        code, json_result = parse_code_or_json(text, target="solve")
        assert code is None and json_result is not None
        passed += 1
        print("  PASS: json containing 'def solve' in string value")
    except Exception as e:
        failed += 1
        print(f"  FAIL: json containing 'def solve' in string value — {e}")

    try:
        text = '```python\ndef solve(data):\n  results = []\n  for item in data:\n    results.append({"name": item["name"], "id": item["id"]})\n  return {"primary": results, "extras": {"count": len(data)}}\n```'
        code, json_result = parse_code_or_json(text, target="solve")
        assert code is not None and json_result is None
        assert "results" in code
        passed += 1
        print("  PASS: yes — complex multi-line function")
    except Exception as e:
        failed += 1
        print(f"  FAIL: yes — complex multi-line function — {e}")

    # =======================================================================
    # Summary
    # =======================================================================
    print(f"\n{'='*60}")
    print(f"Results: {passed} passed, {failed} failed, {passed + failed} total")
    if failed == 0:
        print("All tests passed!")
    else:
        print(f"WARNING: {failed} test(s) failed!")
    print(f"{'='*60}")
