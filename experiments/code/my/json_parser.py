"""Robust JSON parser for LLM responses.

Validates and repairs malformed JSON that LLMs commonly produce:
- Markdown fenced code blocks (```json ... ```)
- Trailing commas before closing brackets
- Missing outer brackets/braces
- Unescaped control characters in strings
- Single-quoted strings
- Comments (// and /* */)
- Truncated/incomplete JSON
- Mixed text around JSON content
- Unescaped inner quotes in string values
"""

from __future__ import annotations

import json
import re
from typing import Any, Callable, TypeVar


# JSON Schema pattern string for Python builtin type annotations.
# Allows arbitrarily nested parameterized types: dict[str, list[tuple[int, bool]]]
# Only permits: str, int, float, bool, list, dict, tuple, set, bytes, None, Optional, Union, Any
BUILTIN_TYPE_PATTERN = (
    r"^(str|int|float|bool|list|dict|tuple|set|bytes|None|Optional|Union|Any)"
    r"(\[(str|int|float|bool|list|dict|tuple|set|bytes|None|Optional|Union|Any|,|\s|\[|\])*\])?$"
)


def fn_info_schema(has_parameters: bool = True) -> dict:
    """JSON Schema for a function info dict (description, parameters, returns).

    Parameters
    ----------
    has_parameters : bool
        Whether "parameters" is required (True when the function has arguments).
    """
    required = ["description", "concise_description", "returns"]
    if has_parameters:
        required.insert(2, "parameters")
    return {
        "type": "object",
        "required": required,
        "properties": {
            "description": {"type": "string"},
            "concise_description": {"type": "string"},
            "parameters": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["name", "description"],
                    "properties": {
                        "name": {"type": "string"},
                        "description": {"type": "string"},
                        "type": {"type": "string", "pattern": BUILTIN_TYPE_PATTERN},
                    },
                },
            },
            "returns": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["description"],
                    "properties": {
                        "description": {"type": "string"},
                        "type": {"type": "string", "pattern": BUILTIN_TYPE_PATTERN},
                    },
                },
            },
        },
    }


def parse_json(text: str, *, strict: bool = False) -> Any:
    """Parse JSON from an LLM response, applying repairs as needed.

    Tries the following strategies in order:
    1. Direct json.loads (fast path for well-formed JSON)
    2. Extract from markdown code fences
    3. Find JSON-like substring ({...} or [...])
    4. Apply text-level repairs and retry

    Parameters
    ----------
    text : str
        Raw LLM response text, potentially containing markdown, prose, etc.
    strict : bool
        If True, skip repair strategies and only try direct parse + extraction.

    Returns
    -------
    Parsed JSON value (dict, list, str, int, float, bool, or None).

    Raises
    ------
    JSONParseError
        If all strategies fail.
    """
    text = text.strip()
    if not text:
        raise JSONParseError("Empty input", text)

    # Strategy 1: direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Strategy 2: extract from markdown fences
    extracted = _extract_from_fences(text)
    if extracted is not None:
        try:
            return json.loads(extracted)
        except json.JSONDecodeError:
            if not strict:
                repaired = _repair(extracted)
                try:
                    return json.loads(repaired)
                except json.JSONDecodeError:
                    pass

    # Strategy 3: find JSON-like substring
    found = _find_json_substring(text)
    if found is not None:
        try:
            return json.loads(found)
        except json.JSONDecodeError:
            if not strict:
                repaired = _repair(found)
                try:
                    return json.loads(repaired)
                except json.JSONDecodeError:
                    pass

    if strict:
        raise JSONParseError("No valid JSON found (strict mode)", text)

    # Strategy 4: full repair on original text
    repaired = _repair(text)
    try:
        return json.loads(repaired)
    except json.JSONDecodeError:
        pass

    # Strategy 5: try json_repair as last resort (only if text looks JSON-ish)
    if any(c in text for c in '{}[]'):
        try:
            import json_repair
            result = json_repair.loads(text)
            # json_repair can return plain strings for non-JSON input; reject those
            if isinstance(result, (dict, list)):
                return result
        except Exception:
            pass

    raise JSONParseError("All parse strategies failed", text)


def parse_json_dict(text: str, **kwargs) -> dict:
    """Parse JSON and assert the result is a dict."""
    result = parse_json(text, **kwargs)
    if not isinstance(result, dict):
        raise JSONParseError(f"Expected dict, got {type(result).__name__}", text)
    return result


def parse_json_list(text: str, **kwargs) -> list:
    """Parse JSON and assert the result is a list."""
    result = parse_json(text, **kwargs)
    if not isinstance(result, list):
        raise JSONParseError(f"Expected list, got {type(result).__name__}", text)
    return result


T = TypeVar("T")


def generate_json(
    generate_fn: Callable[..., T],
    *args,
    parse: Callable[[str], Any] = parse_json,
    max_retries: int = 3,
    get_text: Callable[[T], str] | None = None,
    **kwargs,
) -> tuple[Any, T]:
    """Call a generation function and parse JSON from its output, retrying on failure.

    Parameters
    ----------
    generate_fn : callable
        The function to call for generation. Called as generate_fn(*args, **kwargs).
    *args, **kwargs
        Forwarded to generate_fn.
    parse : callable
        Parser function applied to the response text. Defaults to parse_json.
        Use parse_json_dict or parse_json_list to enforce a specific type.
    max_retries : int
        Maximum number of generation attempts (default 3).
    get_text : callable or None
        Extracts the text to parse from generate_fn's return value.
        If None, assumes the return value has a `.content` attribute (Msg-like).

    Returns
    -------
    (parsed, response) : tuple
        The parsed JSON value and the raw response from the last generation call.

    Raises
    ------
    JSONParseError
        If all retries fail to produce parseable JSON.
    """
    if get_text is None:
        get_text = lambda r: r.content

    last_error = None
    for attempt in range(max_retries):
        response = generate_fn(*args, **kwargs)
        text = get_text(response)
        try:
            return parse(text), response
        except (JSONParseError, json.JSONDecodeError, ValueError) as e:
            last_error = e

    raise JSONParseError(
        f"Failed to parse JSON after {max_retries} attempts. Last error: {last_error}",
        text,
    )


# ---------------------------------------------------------------------------
# Structure / schema validation
# ---------------------------------------------------------------------------

# Type DSL: Python types describe expected shape
#   str, int, float, bool  — leaf type checks
#   {"k": str, "nested": {"x": int}}  — dict with required typed keys
#   [str]  — list where every element is str
#   [{"name": str}]  — list of dicts
#   (str, int)  — union: value must match at least one
Structure = type | dict | list | tuple


def validate_structure(value: Any, structure: Structure, path: str = "$") -> list[str]:
    """Validate a value against a Python-type structure DSL.

    Returns a list of error strings (empty = valid).
    """
    errors = []

    if isinstance(structure, tuple):
        # Union: (str, int) means value can be str OR int
        if not any(_check_type(value, t) for t in structure):
            names = ", ".join(t.__name__ if isinstance(t, type) else str(t) for t in structure)
            errors.append(f"{path}: expected one of ({names}), got {type(value).__name__}")
        return errors

    if isinstance(structure, type):
        if not _check_type(value, structure):
            errors.append(f"{path}: expected {structure.__name__}, got {type(value).__name__}")
        return errors

    if isinstance(structure, dict):
        if not isinstance(value, dict):
            errors.append(f"{path}: expected dict, got {type(value).__name__}")
            return errors
        for k, v_structure in structure.items():
            if k not in value:
                errors.append(f"{path}: missing required key {k!r}")
            else:
                errors.extend(validate_structure(value[k], v_structure, f"{path}.{k}"))
        return errors

    if isinstance(structure, list):
        if not isinstance(value, list):
            errors.append(f"{path}: expected list, got {type(value).__name__}")
            return errors
        if structure:  # [element_structure]
            elem_structure = structure[0]
            for i, item in enumerate(value):
                errors.extend(validate_structure(item, elem_structure, f"{path}[{i}]"))
        return errors

    errors.append(f"{path}: unknown structure type {type(structure)}")
    return errors


def _check_type(value: Any, expected: type) -> bool:
    """Check type, treating bool as distinct from int."""
    if expected is int:
        return isinstance(value, int) and not isinstance(value, bool)
    if expected is float:
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    return isinstance(value, expected)


def _make_structure_parser(
    structure: Structure | None = None,
    json_schema: dict | None = None,
) -> Callable[[str], dict]:
    """Build a parse function that validates against structure DSL or JSON Schema."""

    if structure is not None and json_schema is not None:
        raise ValueError("Specify structure or json_schema, not both")

    if structure is None and json_schema is None:
        return parse_json_dict

    if structure is not None:
        def _parse_structure(text: str) -> dict:
            d = parse_json_dict(text)
            errors = validate_structure(d, structure)
            if errors:
                raise JSONParseError(
                    f"Structure validation failed:\n" + "\n".join(f"  - {e}" for e in errors),
                    text,
                )
            return d
        return _parse_structure

    # json_schema
    def _parse_json_schema(text: str) -> dict:
        import jsonschema
        d = parse_json_dict(text)
        try:
            jsonschema.validate(d, json_schema)
        except jsonschema.ValidationError as e:
            raise JSONParseError(f"JSON Schema validation failed: {e.message}", text) from e
        return d
    return _parse_json_schema


def generate_json_dict(
    generate_fn: Callable[..., T],
    *args,
    structure: Structure | None = None,
    json_schema: dict | None = None,
    max_retries: int = 3,
    get_text: Callable[[T], str] | None = None,
    **kwargs,
) -> tuple[dict, T]:
    """Like generate_json but enforces dict result with optional structure validation.

    Parameters
    ----------
    structure : Structure | None
        Python-type DSL for validation:
          {"type": str, "items": [{"name": str, "score": float}]}
        Keys in the dict are required. Types are checked recursively.
        Use tuple for unions: (str, int).
    json_schema : dict | None
        Full JSON Schema dict. Requires `jsonschema` package.
    """
    return generate_json(
        generate_fn, *args,
        parse=_make_structure_parser(structure, json_schema),
        max_retries=max_retries, get_text=get_text,
        **kwargs,
    )


def generate_json_list(
    generate_fn: Callable[..., T],
    *args,
    max_retries: int = 3,
    get_text: Callable[[T], str] | None = None,
    **kwargs,
) -> tuple[list, T]:
    """Like generate_json but enforces list result."""
    return generate_json(
        generate_fn, *args,
        parse=parse_json_list, max_retries=max_retries, get_text=get_text,
        **kwargs,
    )


class JSONParseError(ValueError):
    """Raised when JSON cannot be parsed from the input."""

    def __init__(self, message: str, original_text: str):
        self.original_text = original_text
        super().__init__(f"{message}\n--- Original text (first 500 chars) ---\n{original_text[:500]}")


# ---------------------------------------------------------------------------
# Internal strategies
# ---------------------------------------------------------------------------

def _extract_from_fences(text: str) -> str | None:
    """Extract content from markdown fenced code blocks."""
    # Try ```json, ```python, ```py, or bare ``` blocks
    pattern = r"```(?:json|python|py)?[ \t]*\r?\n(.*?)```"
    matches = re.findall(pattern, text, re.DOTALL | re.IGNORECASE)
    if not matches:
        return None
    # Return the longest match (most likely to be the complete JSON)
    return max(matches, key=len).strip()


def _find_json_substring(text: str) -> str | None:
    """Find the outermost JSON object or array in text.

    Uses bracket counting to handle nested structures correctly.
    Prefers whichever bracket type appears first in the text.
    """
    first_brace = text.find('{')
    first_bracket = text.find('[')

    # Try whichever appears first; if only one exists, try that one
    candidates = []
    if first_brace != -1:
        candidates.append((first_brace, '{', '}'))
    if first_bracket != -1:
        candidates.append((first_bracket, '[', ']'))
    candidates.sort(key=lambda x: x[0])

    for _, open_char, close_char in candidates:
        result = _extract_balanced(text, open_char, close_char)
        if result is not None:
            return result
    return None


def _extract_balanced(text: str, open_char: str, close_char: str) -> str | None:
    """Extract the first balanced bracket expression from text."""
    start = text.find(open_char)
    if start == -1:
        return None

    depth = 0
    in_string = False
    escape = False
    best_end = -1

    for i in range(start, len(text)):
        c = text[i]

        if escape:
            escape = False
            continue

        if c == '\\' and in_string:
            escape = True
            continue

        if c == '"' and not escape:
            in_string = not in_string
            continue

        if in_string:
            continue

        if c == open_char:
            depth += 1
        elif c == close_char:
            depth -= 1
            if depth == 0:
                best_end = i
                break

    if best_end != -1:
        return text[start:best_end + 1]

    # Truncated JSON: close remaining brackets
    if depth > 0:
        fragment = text[start:]
        fragment = fragment.rstrip().rstrip(',')
        fragment += close_char * depth
        return fragment

    return None


def _repair(text: str) -> str:
    """Apply a chain of text-level repairs to make JSON parseable."""
    s = text.strip()

    # Remove markdown fences if any remain
    s = re.sub(r'^```(?:json|python|py)?\s*', '', s, flags=re.IGNORECASE)
    s = re.sub(r'\s*```$', '', s)

    # Remove single-line comments (// ...)
    # Only outside strings — approximate by removing lines starting with //
    s = re.sub(r'(?m)^\s*//.*$', '', s)

    # Remove block comments (/* ... */) — simple non-nested version
    s = re.sub(r'/\*.*?\*/', '', s, flags=re.DOTALL)

    # Replace single quotes with double quotes (for keys/values)
    # This is approximate but handles the common case
    s = _replace_single_quotes(s)

    # Fix trailing commas: ,] or ,}
    s = re.sub(r',\s*([\]}])', r'\1', s)

    # Fix missing commas between elements: }\s*{ or ]\s*[
    # (common when LLM outputs array items without commas)
    s = re.sub(r'(\})\s*(\{)', r'\1,\2', s)
    s = re.sub(r'(\])\s*(\[)', r'\1,\2', s)

    # Escape unescaped newlines/tabs inside strings
    s = _escape_control_chars_in_strings(s)

    # Handle Python-style True/False/None
    s = _fix_python_literals(s)

    # Add missing outer braces if the content looks like object properties
    s = s.strip()
    if s and s[0] not in ('{', '[', '"') and ':' in s.split('\n')[0]:
        s = '{' + s + '}'

    # Balance brackets
    s = _balance_brackets(s)

    return s


def _replace_single_quotes(s: str) -> str:
    """Replace single-quoted strings with double-quoted, avoiding apostrophes in words."""
    result = []
    i = 0
    in_double = False

    while i < len(s):
        c = s[i]

        # Track double-quoted strings — don't touch anything inside
        if c == '"' and (i == 0 or s[i - 1] != '\\'):
            in_double = not in_double
            result.append(c)
            i += 1
            continue

        if in_double:
            result.append(c)
            i += 1
            continue

        # Outside double quotes: replace single-quoted strings
        if c == "'":
            # Look ahead for the closing single quote
            j = i + 1
            while j < len(s):
                if s[j] == '\\':
                    j += 2
                    continue
                if s[j] == "'":
                    break
                j += 1

            if j < len(s):
                inner = s[i + 1:j]
                # Escape any double quotes inside
                inner = inner.replace('"', '\\"')
                result.append('"')
                result.append(inner)
                result.append('"')
                i = j + 1
                continue

        result.append(c)
        i += 1

    return ''.join(result)


def _escape_control_chars_in_strings(s: str) -> str:
    """Escape literal newlines/tabs inside JSON string values."""
    result = []
    in_string = False
    escape = False

    for c in s:
        if escape:
            result.append(c)
            escape = False
            continue

        if c == '\\' and in_string:
            result.append(c)
            escape = True
            continue

        if c == '"':
            in_string = not in_string
            result.append(c)
            continue

        if in_string:
            if c == '\n':
                result.append('\\n')
                continue
            if c == '\r':
                result.append('\\r')
                continue
            if c == '\t':
                result.append('\\t')
                continue

        result.append(c)

    return ''.join(result)


def _fix_python_literals(s: str) -> str:
    """Replace Python True/False/None with JSON true/false/null outside strings."""
    # Use word boundary replacement, but only outside quoted strings
    parts = []
    in_string = False
    escape = False
    buf = []

    for c in s:
        if escape:
            buf.append(c)
            escape = False
            continue
        if c == '\\' and in_string:
            buf.append(c)
            escape = True
            continue
        if c == '"':
            if in_string:
                buf.append(c)
                in_string = False
                continue
            else:
                # Flush buffer, apply replacements
                chunk = ''.join(buf)
                chunk = re.sub(r'\bTrue\b', 'true', chunk)
                chunk = re.sub(r'\bFalse\b', 'false', chunk)
                chunk = re.sub(r'\bNone\b', 'null', chunk)
                parts.append(chunk)
                buf = [c]
                in_string = True
                continue
        buf.append(c)

    # Flush remaining buffer
    chunk = ''.join(buf)
    if not in_string:
        chunk = re.sub(r'\bTrue\b', 'true', chunk)
        chunk = re.sub(r'\bFalse\b', 'false', chunk)
        chunk = re.sub(r'\bNone\b', 'null', chunk)
    parts.append(chunk)

    return ''.join(parts)


def _balance_brackets(s: str) -> str:
    """Close any unclosed brackets/braces at the end."""
    stack = []
    in_string = False
    escape = False

    for c in s:
        if escape:
            escape = False
            continue
        if c == '\\' and in_string:
            escape = True
            continue
        if c == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if c in ('{', '['):
            stack.append('}' if c == '{' else ']')
        elif c in ('}', ']'):
            if stack and stack[-1] == c:
                stack.pop()

    # Close unclosed brackets in reverse order
    if stack:
        s = s.rstrip().rstrip(',')
        s += ''.join(reversed(stack))

    return s


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    passed = 0
    failed = 0

    def test(name, input_text, expected):
        global passed, failed
        try:
            result = parse_json(input_text)
            assert result == expected, f"got {result!r}"
            passed += 1
            print(f"  PASS: {name}")
        except Exception as e:
            failed += 1
            print(f"  FAIL: {name} — {e}")

    def test_error(name, input_text, error_type=JSONParseError):
        global passed, failed
        try:
            parse_json(input_text)
            failed += 1
            print(f"  FAIL: {name} — expected error, got success")
        except error_type:
            passed += 1
            print(f"  PASS: {name}")
        except Exception as e:
            failed += 1
            print(f"  FAIL: {name} — expected {error_type.__name__}, got {type(e).__name__}: {e}")

    # =======================================================================
    # 1. Well-formed JSON (fast path)
    # =======================================================================
    print("\n--- Well-formed JSON ---")
    test("empty object", "{}", {})
    test("empty array", "[]", [])
    test("simple object", '{"a": 1, "b": 2}', {"a": 1, "b": 2})
    test("simple array", '[1, 2, 3]', [1, 2, 3])
    test("nested object", '{"a": {"b": {"c": 1}}}', {"a": {"b": {"c": 1}}})
    test("nested array", '[[1, 2], [3, 4]]', [[1, 2], [3, 4]])
    test("mixed nesting", '{"a": [1, {"b": 2}], "c": null}', {"a": [1, {"b": 2}], "c": None})
    test("string value", '"hello"', "hello")
    test("number value", '42', 42)
    test("float value", '3.14', 3.14)
    test("negative number", '-7', -7)
    test("boolean true", 'true', True)
    test("boolean false", 'false', False)
    test("null", 'null', None)
    test("unicode", '{"emoji": "\\u2603"}', {"emoji": "\u2603"})
    test("escaped chars", '{"a": "line1\\nline2\\ttab"}', {"a": "line1\nline2\ttab"})

    # =======================================================================
    # 2. Whitespace / padding
    # =======================================================================
    print("\n--- Whitespace / padding ---")
    test("leading whitespace", '   {"a": 1}', {"a": 1})
    test("trailing whitespace", '{"a": 1}   ', {"a": 1})
    test("leading newlines", '\n\n\n{"a": 1}', {"a": 1})
    test("trailing newlines", '{"a": 1}\n\n\n', {"a": 1})
    test("CRLF line endings", '{\r\n  "a": 1\r\n}', {"a": 1})

    # =======================================================================
    # 3. Markdown fenced code blocks
    # =======================================================================
    print("\n--- Markdown fenced code blocks ---")
    test("```json fence", '```json\n{"a": 1}\n```', {"a": 1})
    test("```python fence", '```python\n{"a": 1}\n```', {"a": 1})
    test("```py fence", '```py\n{"a": 1}\n```', {"a": 1})
    test("bare ``` fence", '```\n{"a": 1}\n```', {"a": 1})
    test("```JSON uppercase", '```JSON\n{"a": 1}\n```', {"a": 1})
    test("fence with trailing space", '```json \n{"a": 1}\n```', {"a": 1})
    test("fence with prose before", 'Here is the JSON:\n```json\n{"a": 1}\n```', {"a": 1})
    test("fence with prose after", '```json\n{"a": 1}\n```\nThat is the result.', {"a": 1})
    test("fence with prose both sides",
         'Sure! Here you go:\n```json\n{"key": "value"}\n```\nHope that helps!',
         {"key": "value"})
    test("multiple fences picks longest",
         '```json\n{"a": 1}\n```\n\n```json\n{"a": 1, "b": 2, "c": 3}\n```',
         {"a": 1, "b": 2, "c": 3})
    test("fence with array", '```json\n[1, 2, 3]\n```', [1, 2, 3])
    test("fence with malformed JSON inside",
         '```json\n{"a": 1, "b": 2,}\n```', {"a": 1, "b": 2})

    # =======================================================================
    # 4. Trailing commas
    # =======================================================================
    print("\n--- Trailing commas ---")
    test("trailing comma in object", '{"a": 1,}', {"a": 1})
    test("trailing comma in array", '[1, 2, 3,]', [1, 2, 3])
    test("trailing comma with whitespace", '{"a": 1 , }', {"a": 1})
    test("trailing comma with newline", '{"a": 1,\n}', {"a": 1})
    test("trailing comma nested", '{"a": [1, 2,], "b": {"c": 3,},}',
         {"a": [1, 2], "b": {"c": 3}})
    test("multiple trailing commas in array", '[1, 2, 3, , ]', [1, 2, 3])

    # =======================================================================
    # 5. Single quotes
    # =======================================================================
    print("\n--- Single quotes ---")
    test("single-quoted keys", "{'a': 1}", {"a": 1})
    test("single-quoted values", "{'a': 'hello'}", {"a": "hello"})
    test("mixed quotes", '{\'a\': "hello"}', {"a": "hello"})
    test("single quotes with inner double",
         "{'a': 'he said \"hi\"'}",
         {"a": 'he said "hi"'})
    test("single quotes nested", "{'a': {'b': 'c'}}", {"a": {"b": "c"}})

    # =======================================================================
    # 6. Python literals (True, False, None)
    # =======================================================================
    print("\n--- Python literals ---")
    test("True", '{"a": True}', {"a": True})
    test("False", '{"a": False}', {"a": False})
    test("None", '{"a": None}', {"a": None})
    test("all three", '{"a": True, "b": False, "c": None}',
         {"a": True, "b": False, "c": None})
    test("True inside string preserved",
         '{"a": "True is not False"}',
         {"a": "True is not False"})
    test("None inside string preserved",
         '{"val": "None of the above"}',
         {"val": "None of the above"})
    test("Python literal in array", '[True, False, None, 1]',
         [True, False, None, 1])

    # =======================================================================
    # 7. Comments
    # =======================================================================
    print("\n--- Comments ---")
    test("single-line comment at start",
         '// This is a comment\n{"a": 1}', {"a": 1})
    test("single-line comment between keys",
         '{\n// comment\n"a": 1\n}', {"a": 1})
    test("block comment inline",
         '{"a": /* a number */ 1}', {"a": 1})
    test("block comment multiline",
         '{"a": /* a\nnumber */ 1}', {"a": 1})
    test("multiple single-line comments",
         '{\n// first\n"a": 1,\n// second\n"b": 2\n}',
         {"a": 1, "b": 2})

    # =======================================================================
    # 8. Truncated / incomplete JSON
    # =======================================================================
    print("\n--- Truncated / incomplete JSON ---")
    test("missing closing brace", '{"a": 1', {"a": 1})
    test("missing closing bracket", '[1, 2, 3', [1, 2, 3])
    test("missing nested closing", '{"a": [1, 2', {"a": [1, 2]})
    test("missing deeply nested closing",
         '{"a": {"b": [1, {"c": 2',
         {"a": {"b": [1, {"c": 2}]}})
    test("trailing comma then truncated", '{"a": 1, "b": 2,', {"a": 1, "b": 2})
    test("truncated array with trailing comma", '[1, 2,', [1, 2])

    # =======================================================================
    # 9. Mixed text / prose around JSON
    # =======================================================================
    print("\n--- Mixed text / prose around JSON ---")
    test("prose before object",
         'The answer is: {"result": 42}',
         {"result": 42})
    test("prose after object",
         '{"result": 42} That\'s the answer.',
         {"result": 42})
    test("prose both sides",
         'Here is the data:\n{"x": 1, "y": 2}\nEnd of data.',
         {"x": 1, "y": 2})
    test("prose before array",
         'Results: [1, 2, 3]',
         [1, 2, 3])
    test("multiline prose before",
         'I analyzed the data.\nThe result is:\n{"score": 95}',
         {"score": 95})
    test("JSON buried in paragraph",
         'The configuration should be {"mode": "fast", "retries": 3} for best results.',
         {"mode": "fast", "retries": 3})

    # =======================================================================
    # 10. Unescaped control characters in strings
    # =======================================================================
    print("\n--- Unescaped control chars in strings ---")
    test("literal newline in value",
         '{"text": "line1\nline2"}',
         {"text": "line1\nline2"})
    test("literal tab in value",
         '{"text": "col1\tcol2"}',
         {"text": "col1\tcol2"})
    test("literal CR+LF in value",
         '{"text": "a\r\nb"}',
         {"text": "a\r\nb"})
    test("multiple newlines in value",
         '{"poem": "roses are red\nviolets are blue\nJSON is hard\nLLMs break it too"}',
         {"poem": "roses are red\nviolets are blue\nJSON is hard\nLLMs break it too"})

    # =======================================================================
    # 11. Missing commas between elements
    # =======================================================================
    print("\n--- Missing commas ---")
    test("missing comma between objects in array",
         '[{"a": 1} {"b": 2}]',
         [{"a": 1}, {"b": 2}])

    # =======================================================================
    # 12. Multiple combined issues
    # =======================================================================
    print("\n--- Multiple combined issues ---")
    test("fence + trailing comma",
         '```json\n{"a": 1, "b": 2,}\n```',
         {"a": 1, "b": 2})
    test("fence + Python literals",
         '```json\n{"flag": True, "val": None}\n```',
         {"flag": True, "val": None})
    test("prose + trailing comma + Python literal",
         'Result:\n{"ok": True, "items": [1, 2,],}',
         {"ok": True, "items": [1, 2]})
    test("single quotes + trailing comma",
         "{'a': 1, 'b': 2,}",
         {"a": 1, "b": 2})
    test("fence + single quotes + Python literal",
         "```json\n{'active': True, 'name': 'test'}\n```",
         {"active": True, "name": "test"})
    test("prose + truncated + trailing comma",
         'Here: {"a": 1, "b": [2, 3,',
         {"a": 1, "b": [2, 3]})
    test("comment + trailing comma + Python literal",
         '{\n// config\n"debug": True,\n"level": 5,\n}',
         {"debug": True, "level": 5})
    test("fence + comment + truncated",
         '```json\n{\n// settings\n"x": 1, "y": [2\n```',
         {"x": 1, "y": [2]})

    # =======================================================================
    # 13. Large / realistic LLM responses
    # =======================================================================
    print("\n--- Realistic LLM responses ---")
    test("ChatGPT-style response",
         """Sure! Here's the JSON you requested:

```json
{
  "name": "John Doe",
  "age": 30,
  "hobbies": ["reading", "coding", "hiking"],
  "address": {
    "street": "123 Main St",
    "city": "Springfield"
  }
}
```

Let me know if you need anything else!""",
         {
             "name": "John Doe",
             "age": 30,
             "hobbies": ["reading", "coding", "hiking"],
             "address": {"street": "123 Main St", "city": "Springfield"},
         })

    test("LLM with reasoning then JSON",
         """I'll analyze the data and provide the results.

Based on my analysis:
{"classification": "positive", "confidence": 0.95, "labels": ["happy", "excited"]}""",
         {"classification": "positive", "confidence": 0.95, "labels": ["happy", "excited"]})

    test("LLM with Python dict style",
         """Here are the results:
```python
{'status': 'success', 'count': 42, 'items': [{'id': 1, 'active': True}, {'id': 2, 'active': False}]}
```""",
         {"status": "success", "count": 42, "items": [{"id": 1, "active": True}, {"id": 2, "active": False}]})

    test("LLM messy multiline with comments",
         """{
  // The main config
  "model": "gpt-4",
  "temperature": 0.7,
  "max_tokens": 1000,
  /* These are optional */
  "stop": ["\\n\\n"],
  "stream": True,
}""",
         {"model": "gpt-4", "temperature": 0.7, "max_tokens": 1000,
          "stop": ["\n\n"], "stream": True})

    test("deeply nested truncated",
         '{"users": [{"name": "Alice", "prefs": {"theme": "dark", "lang": "en", "notifications": {"email": true, "sms": false',
         {"users": [{"name": "Alice", "prefs": {"theme": "dark", "lang": "en",
          "notifications": {"email": True, "sms": False}}}]})

    test("array of objects with trailing commas",
         """[
  {"id": 1, "name": "foo",},
  {"id": 2, "name": "bar",},
  {"id": 3, "name": "baz",},
]""",
         [{"id": 1, "name": "foo"}, {"id": 2, "name": "bar"}, {"id": 3, "name": "baz"}])

    # =======================================================================
    # 14. Edge cases — values
    # =======================================================================
    print("\n--- Edge case values ---")
    test("empty string value", '{"a": ""}', {"a": ""})
    test("string with only spaces", '{"a": "   "}', {"a": "   "})
    test("zero", '{"a": 0}', {"a": 0})
    test("negative float", '{"a": -3.14}', {"a": -3.14})
    test("scientific notation", '{"a": 1.5e10}', {"a": 1.5e10})
    test("very long string",
         '{"a": "' + "x" * 5000 + '"}',
         {"a": "x" * 5000})
    test("deeply nested empty objects",
         '{"a": {"b": {"c": {"d": {}}}}}',
         {"a": {"b": {"c": {"d": {}}}}})
    test("array of nulls", '[null, null, null]', [None, None, None])
    test("mixed type array", '[1, "two", true, null, 3.14, []]',
         [1, "two", True, None, 3.14, []])

    # =======================================================================
    # 15. Error cases
    # =======================================================================
    print("\n--- Error cases ---")
    test_error("empty string", "")
    test_error("only whitespace", "   \n\t  ")
    test_error("plain text no JSON", "This is just a sentence with no JSON at all.")

    # Test strict mode specifically
    try:
        parse_json('{"a": True}', strict=True)
        failed += 1
        print("  FAIL: strict mode rejects Python True — expected error, got success")
    except (JSONParseError, Exception):
        passed += 1
        print("  PASS: strict mode rejects Python True")

    # =======================================================================
    # 16. parse_json_dict / parse_json_list type checks
    # =======================================================================
    print("\n--- Typed parsers ---")
    try:
        parse_json_dict('[1, 2, 3]')
        failed += 1
        print("  FAIL: parse_json_dict rejects array — expected error")
    except JSONParseError:
        passed += 1
        print("  PASS: parse_json_dict rejects array")

    try:
        parse_json_list('{"a": 1}')
        failed += 1
        print("  FAIL: parse_json_list rejects object — expected error")
    except JSONParseError:
        passed += 1
        print("  PASS: parse_json_list rejects object")

    try:
        result = parse_json_dict('```json\n{"key": "value",}\n```')
        assert result == {"key": "value"}
        passed += 1
        print("  PASS: parse_json_dict with fence + trailing comma")
    except Exception as e:
        failed += 1
        print(f"  FAIL: parse_json_dict with fence + trailing comma — {e}")

    try:
        result = parse_json_list('Here: [1, 2, 3,]')
        assert result == [1, 2, 3]
        passed += 1
        print("  PASS: parse_json_list with prose + trailing comma")
    except Exception as e:
        failed += 1
        print(f"  FAIL: parse_json_list with prose + trailing comma — {e}")

    # =======================================================================
    # 17. Strings with special characters
    # =======================================================================
    print("\n--- Special characters in strings ---")
    test("backslash in value", '{"path": "C:\\\\Users\\\\test"}',
         {"path": "C:\\Users\\test"})
    test("url in value",
         '{"url": "https://example.com/api?q=1&b=2"}',
         {"url": "https://example.com/api?q=1&b=2"})
    test("json-like content inside string",
         '{"data": "the object {\\\"a\\\": 1} is here"}',
         {"data": 'the object {"a": 1} is here'})

    # =======================================================================
    # 18. Unusual but valid JSON
    # =======================================================================
    print("\n--- Unusual but valid JSON ---")
    test("top-level string", '"just a string"', "just a string")
    test("top-level number", '42', 42)
    test("top-level true", 'true', True)
    test("top-level null", 'null', None)
    test("empty nested arrays", '[[[], []], []]', [[[], []], []])
    test("keys with spaces", '{"a key": "a value"}', {"a key": "a value"})
    test("numeric string keys", '{"123": "abc"}', {"123": "abc"})

    # =======================================================================
    # 19. generate_json with retry
    # =======================================================================
    print("\n--- generate_json with retry ---")

    # Simple Msg-like object for testing
    class FakeMsg:
        def __init__(self, content: str):
            self.content = content

    # Test: succeeds on first try
    try:
        c = [0]
        def gen_ok():
            c[0] += 1
            return FakeMsg('{"status": "ok"}')
        parsed, resp = generate_json(gen_ok)
        assert parsed == {"status": "ok"}
        assert c[0] == 1
        passed += 1
        print("  PASS: generate_json succeeds on first try")
    except Exception as e:
        failed += 1
        print(f"  FAIL: generate_json succeeds on first try — {e}")

    # Test: fails twice then succeeds
    try:
        c = [0]
        def gen_flaky():
            c[0] += 1
            if c[0] < 3:
                return FakeMsg("not json at all")
            return FakeMsg('{"attempt": 3}')
        parsed, resp = generate_json(gen_flaky, max_retries=5)
        assert parsed == {"attempt": 3}
        assert c[0] == 3
        passed += 1
        print("  PASS: generate_json retries on parse failure")
    except Exception as e:
        failed += 1
        print(f"  FAIL: generate_json retries on parse failure — {e}")

    # Test: exhausts all retries
    try:
        c = [0]
        def gen_bad():
            c[0] += 1
            return FakeMsg("garbage")
        generate_json(gen_bad, max_retries=3)
        failed += 1
        print("  FAIL: generate_json exhausts retries — expected error")
    except JSONParseError:
        assert c[0] == 3
        passed += 1
        print("  PASS: generate_json exhausts retries and raises")
    except Exception as e:
        failed += 1
        print(f"  FAIL: generate_json exhausts retries — {type(e).__name__}: {e}")

    # Test: max_retries=1 means single attempt
    try:
        c = [0]
        def gen_once():
            c[0] += 1
            return FakeMsg("bad")
        generate_json(gen_once, max_retries=1)
        failed += 1
        print("  FAIL: max_retries=1 — expected error")
    except JSONParseError:
        assert c[0] == 1
        passed += 1
        print("  PASS: max_retries=1 only calls once")
    except Exception as e:
        failed += 1
        print(f"  FAIL: max_retries=1 — {e}")

    # Test: generate_json_dict enforces dict type with retry
    try:
        c = [0]
        def gen_array_then_dict():
            c[0] += 1
            if c[0] == 1:
                return FakeMsg("[1, 2, 3]")  # valid JSON but wrong type
            return FakeMsg('{"key": "value"}')
        parsed, resp = generate_json_dict(gen_array_then_dict, max_retries=3)
        assert parsed == {"key": "value"}
        assert c[0] == 2
        passed += 1
        print("  PASS: generate_json_dict retries on wrong type")
    except Exception as e:
        failed += 1
        print(f"  FAIL: generate_json_dict retries on wrong type — {e}")

    # Test: generate_json_list enforces list type with retry
    try:
        c = [0]
        def gen_dict_then_list():
            c[0] += 1
            if c[0] == 1:
                return FakeMsg('{"a": 1}')  # valid JSON but wrong type
            return FakeMsg('[1, 2, 3]')
        parsed, resp = generate_json_list(gen_dict_then_list, max_retries=3)
        assert parsed == [1, 2, 3]
        assert c[0] == 2
        passed += 1
        print("  PASS: generate_json_list retries on wrong type")
    except Exception as e:
        failed += 1
        print(f"  FAIL: generate_json_list retries on wrong type — {e}")

    # Test: custom get_text extractor
    try:
        class WeirdResponse:
            def __init__(self, data):
                self.data = data
        def gen_weird():
            return WeirdResponse({"output": '{"x": 1}'})
        parsed, resp = generate_json(gen_weird, get_text=lambda r: r.data["output"])
        assert parsed == {"x": 1}
        passed += 1
        print("  PASS: generate_json with custom get_text")
    except Exception as e:
        failed += 1
        print(f"  FAIL: generate_json with custom get_text — {e}")

    # Test: args and kwargs forwarded to generate_fn
    try:
        def gen_with_args(a, b, key=None):
            return FakeMsg(json.dumps({"a": a, "b": b, "key": key}))
        parsed, resp = generate_json(gen_with_args, 1, 2, key="val")
        assert parsed == {"a": 1, "b": 2, "key": "val"}
        passed += 1
        print("  PASS: generate_json forwards args/kwargs")
    except Exception as e:
        failed += 1
        print(f"  FAIL: generate_json forwards args/kwargs — {e}")

    # Test: repair kicks in during retry (malformed on first, still malformed but repairable)
    try:
        c = [0]
        def gen_malformed():
            c[0] += 1
            if c[0] == 1:
                return FakeMsg("completely not json")
            return FakeMsg('{"fixed": True,}')  # repairable
        parsed, resp = generate_json(gen_malformed, max_retries=3)
        assert parsed == {"fixed": True}
        assert c[0] == 2
        passed += 1
        print("  PASS: generate_json repair works during retry")
    except Exception as e:
        failed += 1
        print(f"  FAIL: generate_json repair works during retry — {e}")

    # Test: generate_json_dict fails all retries when only lists returned
    try:
        c = [0]
        def gen_always_list():
            c[0] += 1
            return FakeMsg("[1, 2, 3]")
        generate_json_dict(gen_always_list, max_retries=2)
        failed += 1
        print("  FAIL: generate_json_dict all retries wrong type — expected error")
    except JSONParseError:
        assert c[0] == 2
        passed += 1
        print("  PASS: generate_json_dict all retries wrong type raises")
    except Exception as e:
        failed += 1
        print(f"  FAIL: generate_json_dict all retries wrong type — {e}")

    # Test: custom parse function
    try:
        def must_have_name(text):
            result = parse_json_dict(text)
            if "name" not in result:
                raise JSONParseError("Missing 'name' key", text)
            return result
        c = [0]
        def gen_missing_then_complete():
            c[0] += 1
            if c[0] == 1:
                return FakeMsg('{"age": 30}')
            return FakeMsg('{"name": "Alice", "age": 30}')
        parsed, resp = generate_json(gen_missing_then_complete, parse=must_have_name, max_retries=3)
        assert parsed == {"name": "Alice", "age": 30}
        assert c[0] == 2
        passed += 1
        print("  PASS: generate_json with custom parse validator")
    except Exception as e:
        failed += 1
        print(f"  FAIL: generate_json with custom parse validator — {e}")

    # Test: response from last attempt is returned
    try:
        c = [0]
        def gen_track_responses():
            c[0] += 1
            return FakeMsg(f'{{"attempt": {c[0]}}}')
        parsed, resp = generate_json(gen_track_responses)
        assert resp.content == '{"attempt": 1}'
        passed += 1
        print("  PASS: generate_json returns response from successful attempt")
    except Exception as e:
        failed += 1
        print(f"  FAIL: generate_json returns response from successful attempt — {e}")

    # =======================================================================
    # 20. validate_structure — Python-type DSL
    # =======================================================================
    print("\n--- validate_structure DSL ---")

    def test_valid(name, value, structure):
        global passed, failed
        errors = validate_structure(value, structure)
        if not errors:
            passed += 1
            print(f"  PASS: {name}")
        else:
            failed += 1
            print(f"  FAIL: {name} — unexpected errors: {errors}")

    def test_invalid(name, value, structure, expected_fragment=None):
        global passed, failed
        errors = validate_structure(value, structure)
        if errors:
            if expected_fragment and not any(expected_fragment in e for e in errors):
                failed += 1
                print(f"  FAIL: {name} — expected '{expected_fragment}' in errors: {errors}")
            else:
                passed += 1
                print(f"  PASS: {name}")
        else:
            failed += 1
            print(f"  FAIL: {name} — expected validation errors, got none")

    # Leaf types
    test_valid("str leaf", "hello", str)
    test_valid("int leaf", 42, int)
    test_valid("float leaf (int accepted)", 42, float)
    test_valid("float leaf", 3.14, float)
    test_valid("bool leaf", True, bool)
    test_invalid("str vs int", 42, str, "expected str")
    test_invalid("int vs str", "hello", int, "expected int")
    test_invalid("bool is not int", True, int, "expected int")
    test_invalid("int is not bool", 1, bool, "expected bool")

    # Flat dict
    test_valid("flat dict", {"type": "compound", "reason": "because"}, {"type": str, "reason": str})
    test_invalid("flat dict missing key", {"type": "compound"}, {"type": str, "reason": str}, "missing required key 'reason'")
    test_invalid("flat dict wrong type", {"type": 123}, {"type": str}, "expected str")

    # Nested dict
    test_valid("nested dict",
               {"user": {"name": "Alice", "age": 30}},
               {"user": {"name": str, "age": int}})
    test_invalid("nested dict missing inner key",
                 {"user": {"name": "Alice"}},
                 {"user": {"name": str, "age": int}},
                 "$.user: missing required key 'age'")
    test_invalid("nested dict wrong inner type",
                 {"user": {"name": "Alice", "age": "thirty"}},
                 {"user": {"name": str, "age": int}},
                 "$.user.age: expected int")

    # List of scalars
    test_valid("list of str", ["a", "b", "c"], [str])
    test_valid("empty list", [], [str])
    test_invalid("list element wrong type", ["a", 1, "c"], [str], "$[1]: expected str")

    # List of dicts
    test_valid("list of dicts",
               [{"name": "a", "score": 1.0}, {"name": "b", "score": 2.5}],
               [{"name": str, "score": float}])
    test_invalid("list of dicts missing key",
                 [{"name": "a"}, {"name": "b", "score": 2.5}],
                 [{"name": str, "score": float}],
                 "$[0]: missing required key 'score'")

    # Deeply nested
    test_valid("deep nesting",
               {"a": {"b": {"c": [{"d": 1}]}}},
               {"a": {"b": {"c": [{"d": int}]}}})
    test_invalid("deep nesting wrong leaf",
                 {"a": {"b": {"c": [{"d": "wrong"}]}}},
                 {"a": {"b": {"c": [{"d": int}]}}},
                 "$.a.b.c[0].d: expected int")

    # Union types with tuple
    test_valid("union str|int (str)", "hello", (str, int))
    test_valid("union str|int (int)", 42, (str, int))
    test_invalid("union str|int (bool)", True, (str, int), "expected one of")
    test_valid("union in dict", {"val": "hello"}, {"val": (str, int)})
    test_valid("union in dict (int)", {"val": 42}, {"val": (str, int)})
    test_invalid("union in dict (wrong)", {"val": [1]}, {"val": (str, int)}, "expected one of")

    # None / null handling
    test_valid("nullable via union", {"x": None}, {"x": (str, type(None))})
    test_invalid("not nullable", {"x": None}, {"x": str}, "expected str")

    # Extra keys are OK (no strict mode)
    test_valid("extra keys allowed",
               {"type": "a", "reason": "b", "extra": 123},
               {"type": str, "reason": str})

    # Not a dict when dict expected
    test_invalid("list instead of dict", [1, 2], {"a": int}, "expected dict")

    # =======================================================================
    # 21. generate_json_dict with structure=
    # =======================================================================
    print("\n--- generate_json_dict with structure= ---")

    # Succeeds with valid structure
    try:
        def gen_valid_struct():
            return FakeMsg('{"type": "compound", "reason": "too complex", "count": 3}')
        parsed, resp = generate_json_dict(
            gen_valid_struct,
            structure={"type": str, "reason": str, "count": int},
        )
        assert parsed == {"type": "compound", "reason": "too complex", "count": 3}
        passed += 1
        print("  PASS: valid structure passes")
    except Exception as e:
        failed += 1
        print(f"  FAIL: valid structure passes — {e}")

    # Retries when structure doesn't match
    try:
        c = [0]
        def gen_fix_structure():
            c[0] += 1
            if c[0] == 1:
                return FakeMsg('{"type": "compound"}')  # missing "reason"
            return FakeMsg('{"type": "compound", "reason": "fixed"}')
        parsed, resp = generate_json_dict(
            gen_fix_structure,
            structure={"type": str, "reason": str},
            max_retries=3,
        )
        assert parsed == {"type": "compound", "reason": "fixed"}
        assert c[0] == 2
        passed += 1
        print("  PASS: retries on missing key")
    except Exception as e:
        failed += 1
        print(f"  FAIL: retries on missing key — {e}")

    # Retries when nested structure is wrong
    try:
        c = [0]
        def gen_fix_nested():
            c[0] += 1
            if c[0] == 1:
                return FakeMsg('{"user": {"name": 123}}')  # wrong type
            return FakeMsg('{"user": {"name": "Alice"}}')
        parsed, resp = generate_json_dict(
            gen_fix_nested,
            structure={"user": {"name": str}},
            max_retries=3,
        )
        assert parsed == {"user": {"name": "Alice"}}
        assert c[0] == 2
        passed += 1
        print("  PASS: retries on wrong nested type")
    except Exception as e:
        failed += 1
        print(f"  FAIL: retries on wrong nested type — {e}")

    # Fails after all retries
    try:
        c = [0]
        def gen_always_bad_struct():
            c[0] += 1
            return FakeMsg('{"wrong": "keys"}')
        generate_json_dict(
            gen_always_bad_struct,
            structure={"type": str, "reason": str},
            max_retries=2,
        )
        failed += 1
        print("  FAIL: exhausts retries on bad structure — expected error")
    except JSONParseError:
        assert c[0] == 2
        passed += 1
        print("  PASS: exhausts retries on bad structure")
    except Exception as e:
        failed += 1
        print(f"  FAIL: exhausts retries on bad structure — {e}")

    # With list-of-str structure (just required keys, no type check)
    try:
        def gen_with_keys():
            return FakeMsg('{"type": "atomic", "reason": "simple", "extra": 123}')
        parsed, resp = generate_json_dict(
            gen_with_keys,
            structure={"type": str, "reason": str},
        )
        assert "type" in parsed and "reason" in parsed
        passed += 1
        print("  PASS: extra keys allowed with structure")
    except Exception as e:
        failed += 1
        print(f"  FAIL: extra keys allowed with structure — {e}")

    # Nested structure with list validation
    try:
        def gen_nested_list():
            return FakeMsg('{"items": [{"name": "a", "score": 1.5}, {"name": "b", "score": 2.0}]}')
        parsed, resp = generate_json_dict(
            gen_nested_list,
            structure={"items": [{"name": str, "score": float}]},
        )
        assert len(parsed["items"]) == 2
        passed += 1
        print("  PASS: nested list structure validation")
    except Exception as e:
        failed += 1
        print(f"  FAIL: nested list structure validation — {e}")

    # Repair + structure validation combined
    try:
        def gen_malformed_but_valid_struct():
            return FakeMsg('{"type": "compound", "reason": "because",}')  # trailing comma
        parsed, resp = generate_json_dict(
            gen_malformed_but_valid_struct,
            structure={"type": str, "reason": str},
        )
        assert parsed == {"type": "compound", "reason": "because"}
        passed += 1
        print("  PASS: repair + structure validation combined")
    except Exception as e:
        failed += 1
        print(f"  FAIL: repair + structure validation combined — {e}")

    # =======================================================================
    # 22. generate_json_dict with json_schema=
    # =======================================================================
    print("\n--- generate_json_dict with json_schema= ---")

    try:
        import jsonschema as _jsonschema_check
        has_jsonschema = True
    except ImportError:
        has_jsonschema = False
        print("  SKIP: jsonschema not installed, skipping JSON Schema tests")

    if has_jsonschema:
        schema = {
            "type": "object",
            "required": ["type", "reason"],
            "properties": {
                "type": {"type": "string", "enum": ["compound", "atomic"]},
                "reason": {"type": "string"},
                "details": {
                    "type": "object",
                    "required": ["count"],
                    "properties": {
                        "count": {"type": "integer", "minimum": 0},
                        "items": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "required": ["name"],
                                "properties": {"name": {"type": "string"}},
                            },
                        },
                    },
                },
            },
        }

        # Valid against schema
        try:
            def gen_schema_ok():
                return FakeMsg('{"type": "compound", "reason": "complex task", "details": {"count": 2, "items": [{"name": "step1"}, {"name": "step2"}]}}')
            parsed, resp = generate_json_dict(gen_schema_ok, json_schema=schema)
            assert parsed["type"] == "compound"
            assert parsed["details"]["count"] == 2
            passed += 1
            print("  PASS: valid JSON Schema passes")
        except Exception as e:
            failed += 1
            print(f"  FAIL: valid JSON Schema passes — {e}")

        # Invalid enum value — retries
        try:
            c = [0]
            def gen_schema_fix_enum():
                c[0] += 1
                if c[0] == 1:
                    return FakeMsg('{"type": "unknown", "reason": "x"}')
                return FakeMsg('{"type": "atomic", "reason": "simple"}')
            parsed, resp = generate_json_dict(gen_schema_fix_enum, json_schema=schema, max_retries=3)
            assert parsed["type"] == "atomic"
            assert c[0] == 2
            passed += 1
            print("  PASS: retries on invalid enum")
        except Exception as e:
            failed += 1
            print(f"  FAIL: retries on invalid enum — {e}")

        # Invalid nested — minimum violated
        try:
            c = [0]
            def gen_schema_fix_minimum():
                c[0] += 1
                if c[0] == 1:
                    return FakeMsg('{"type": "compound", "reason": "x", "details": {"count": -1}}')
                return FakeMsg('{"type": "compound", "reason": "x", "details": {"count": 5}}')
            parsed, resp = generate_json_dict(gen_schema_fix_minimum, json_schema=schema, max_retries=3)
            assert parsed["details"]["count"] == 5
            assert c[0] == 2
            passed += 1
            print("  PASS: retries on minimum violation")
        except Exception as e:
            failed += 1
            print(f"  FAIL: retries on minimum violation — {e}")

        # Exhausts retries
        try:
            c = [0]
            def gen_schema_always_bad():
                c[0] += 1
                return FakeMsg('{"wrong": "shape"}')
            generate_json_dict(gen_schema_always_bad, json_schema=schema, max_retries=2)
            failed += 1
            print("  FAIL: JSON Schema exhausts retries — expected error")
        except JSONParseError:
            assert c[0] == 2
            passed += 1
            print("  PASS: JSON Schema exhausts retries")
        except Exception as e:
            failed += 1
            print(f"  FAIL: JSON Schema exhausts retries — {e}")

        # Cannot specify both structure and json_schema
        try:
            generate_json_dict(
                lambda: FakeMsg("{}"),
                structure={"a": str},
                json_schema=schema,
            )
            failed += 1
            print("  FAIL: both structure + json_schema — expected error")
        except ValueError:
            passed += 1
            print("  PASS: rejects both structure + json_schema")
        except Exception as e:
            failed += 1
            print(f"  FAIL: both structure + json_schema — {e}")

        # Repair + JSON Schema combined
        try:
            def gen_malformed_schema():
                return FakeMsg('{"type": "atomic", "reason": "fast",}')
            parsed, resp = generate_json_dict(gen_malformed_schema, json_schema=schema)
            assert parsed == {"type": "atomic", "reason": "fast"}
            passed += 1
            print("  PASS: repair + JSON Schema combined")
        except Exception as e:
            failed += 1
            print(f"  FAIL: repair + JSON Schema combined — {e}")

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
