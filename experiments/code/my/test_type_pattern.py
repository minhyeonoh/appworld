"""Test the regex pattern for Python builtin type annotations."""

import re

_BUILTINS = r"(?:str|int|float|bool|list|dict|tuple|set|bytes|None|Optional|Union|Any)"
_BUILTIN_TYPE_RE = re.compile(
    r"^(str|int|float|bool|list|dict|tuple|set|bytes|None|Optional|Union|Any)"
    r"(\[(str|int|float|bool|list|dict|tuple|set|bytes|None|Optional|Union|Any|,|\s|\[|\])*\])?$"
)


def _brackets_balanced(s: str) -> bool:
    depth = 0
    for c in s:
        if c == '[':
            depth += 1
        elif c == ']':
            depth -= 1
            if depth < 0:
                return False
    return depth == 0


BUILTIN_TYPE_PATTERN = _BUILTIN_TYPE_RE


def check(annotation: str) -> bool:
    return BUILTIN_TYPE_PATTERN.match(annotation) is not None and _brackets_balanced(annotation)


if __name__ == "__main__":
    passed = 0
    failed = 0

    def test_valid(name, annotation):
        global passed, failed
        if check(annotation):
            passed += 1
            print(f"  PASS: {name}: {annotation}")
        else:
            failed += 1
            print(f"  FAIL: {name}: {annotation} — expected valid")

    def test_invalid(name, annotation):
        global passed, failed
        if not check(annotation):
            passed += 1
            print(f"  PASS: {name}: {annotation}")
        else:
            failed += 1
            print(f"  FAIL: {name}: {annotation} — expected invalid")

    # =======================================================================
    # 1. Simple builtins
    # =======================================================================
    print("\n--- Simple builtins ---")
    test_valid("str", "str")
    test_valid("int", "int")
    test_valid("float", "float")
    test_valid("bool", "bool")
    test_valid("list", "list")
    test_valid("dict", "dict")
    test_valid("tuple", "tuple")
    test_valid("set", "set")
    test_valid("bytes", "bytes")
    test_valid("None", "None")
    test_valid("Any", "Any")
    test_valid("Optional", "Optional")
    test_valid("Union", "Union")

    # =======================================================================
    # 2. Single-level parameterized
    # =======================================================================
    print("\n--- Single-level parameterized ---")
    test_valid("list[str]", "list[str]")
    test_valid("list[int]", "list[int]")
    test_valid("list[bool]", "list[bool]")
    test_valid("set[str]", "set[str]")
    test_valid("tuple[int]", "tuple[int]")
    test_valid("dict[str, int]", "dict[str, int]")
    test_valid("dict[str,int]", "dict[str,int]")
    test_valid("Optional[str]", "Optional[str]")
    test_valid("Union[str, int]", "Union[str, int]")
    test_valid("Union[str,int,float]", "Union[str,int,float]")
    test_valid("tuple[str, int, bool]", "tuple[str, int, bool]")

    # =======================================================================
    # 3. Nested parameterized
    # =======================================================================
    print("\n--- Nested parameterized ---")
    test_valid("list[list[str]]", "list[list[str]]")
    test_valid("dict[str, list[int]]", "dict[str, list[int]]")
    test_valid("list[dict[str, int]]", "list[dict[str, int]]")
    test_valid("Optional[list[str]]", "Optional[list[str]]")
    test_valid("Union[str, list[int]]", "Union[str, list[int]]")
    test_valid("tuple[list[str], dict[str, int]]", "tuple[list[str], dict[str, int]]")
    test_valid("dict[str, set[int]]", "dict[str, set[int]]")

    # =======================================================================
    # 4. Double/triple nested
    # =======================================================================
    print("\n--- Double/triple nested ---")
    test_valid("list[list[list[int]]]", "list[list[list[int]]]")
    test_valid("dict[str, list[tuple[int, bool]]]", "dict[str, list[tuple[int, bool]]]")
    test_valid("dict[str, dict[str, list[int]]]", "dict[str, dict[str, list[int]]]")
    test_valid("Optional[dict[str, list[tuple[int, str]]]]", "Optional[dict[str, list[tuple[int, str]]]]")
    test_valid("Union[list[dict[str, int]], tuple[bool, float]]",
               "Union[list[dict[str, int]], tuple[bool, float]]")
    test_valid("list[list[list[list[str]]]]", "list[list[list[list[str]]]]")

    # =======================================================================
    # 5. With None in params
    # =======================================================================
    print("\n--- None in params ---")
    test_valid("Optional[None]", "Optional[None]")
    test_valid("Union[str, None]", "Union[str, None]")
    test_valid("dict[str, None]", "dict[str, None]")
    test_valid("list[None]", "list[None]")

    # =======================================================================
    # 6. Spacing variations
    # =======================================================================
    print("\n--- Spacing ---")
    test_valid("dict[str,  int]", "dict[str,  int]")
    test_valid("Union[str , int]", "Union[str , int]")
    test_valid("tuple[int,  str,  bool]", "tuple[int,  str,  bool]")

    # =======================================================================
    # 7. Non-builtin types — should REJECT
    # =======================================================================
    print("\n--- Non-builtin (should reject) ---")
    test_invalid("DataFrame", "DataFrame")
    test_invalid("np.ndarray", "np.ndarray")
    test_invalid("MyClass", "MyClass")
    test_invalid("list[DataFrame]", "list[DataFrame]")
    test_invalid("dict[str, MyClass]", "dict[str, MyClass]")
    test_invalid("Optional[Response]", "Optional[Response]")
    test_invalid("Union[str, CustomType]", "Union[str, CustomType]")
    test_invalid("list[np.int64]", "list[np.int64]")
    test_invalid("dict[str, pd.Series]", "dict[str, pd.Series]")
    test_invalid("Callable[[int], str]", "Callable[[int], str]")
    test_invalid("Iterator[str]", "Iterator[str]")
    test_invalid("Generator[int, None, None]", "Generator[int, None, None]")

    # =======================================================================
    # 8. Nested non-builtins — should REJECT
    # =======================================================================
    print("\n--- Nested non-builtins (should reject) ---")
    test_invalid("list[list[Foo]]", "list[list[Foo]]")
    test_invalid("dict[str, list[Bar]]", "dict[str, list[Bar]]")
    test_invalid("tuple[int, MyObj]", "tuple[int, MyObj]")
    test_invalid("dict[CustomKey, int]", "dict[CustomKey, int]")
    test_invalid("Optional[list[SomeClass]]", "Optional[list[SomeClass]]")

    # =======================================================================
    # 9. Malformed — should REJECT
    # =======================================================================
    print("\n--- Malformed (should reject) ---")
    test_invalid("empty string", "")
    test_invalid("just brackets", "[]")
    test_invalid("number", "123")
    test_invalid("unclosed bracket", "list[str")
    test_invalid("extra closing", "list[str]]")
    test_invalid("leading space", " str")
    test_invalid("trailing space", "str ")
    test_invalid("pipe union", "str | int")
    test_invalid("bare comma", "str, int")
    test_invalid("dot access", "typing.List[str]")

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
