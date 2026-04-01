"""MWE test for insert_truncation_marker and truncate_at_marker."""

from dataclasses import dataclass

# Inline the functions under test (no heavy imports needed)
_TRUNCATION_MARKER = "# @@TRUNCATE_BELOW@@"


def insert_truncation_marker(code: str, ctx) -> str:
  lines = code.splitlines(keepends=True)
  error_line_idx = ctx.line - ctx.firstline  # 0-based index of the error line
  insert_at = error_line_idx  # insert marker before the error line
  if 0 < insert_at <= len(lines):
    target_line = lines[insert_at] if insert_at < len(lines) else lines[-1]
    indent = len(target_line) - len(target_line.lstrip())
    marker_line = " " * indent + _TRUNCATION_MARKER + "\n"
    lines.insert(insert_at, marker_line)
  return "".join(lines)


def truncate_at_marker(code: str, original_code: str | None = None) -> str:
  lines = code.splitlines(keepends=True)
  for i, line in enumerate(lines):
    if _TRUNCATION_MARKER in line:
      head = "".join(lines[:i]).rstrip("\n")
      if original_code is not None:
        orig_lines = original_code.splitlines(keepends=True)
        for j, orig_line in enumerate(orig_lines):
          if _TRUNCATION_MARKER in orig_line:
            tail = "".join(orig_lines[j + 1:])
            if tail.strip():
              return head + "\n" + tail.rstrip("\n")
            break
      return head
  return code


@dataclass
class FakeCtx:
  """Mimics ctx.line / ctx.firstline from the real Ctx.

  In the real system, firstline = function's first source line + 1
  (the +1 skips the @show_locals_on_exception decorator).
  So for a function starting at absolute line 10 (after decorator),
  firstline=10, and ctx.line is the absolute line of the error.
  """
  line: int
  firstline: int


# ── Test 1: error in the middle of a function ──────────────────────
# Simulate: the function starts at absolute line 5 (firstline=5),
# and the error is at absolute line 8 (the `result = x / y` line).

code_1 = """\
def compute(x, y):
  total = x + y
  diff = x - y
  result = x / y
  return total + diff + result"""

# Lines in code_1 (1-indexed within the code string):
#  1: def compute(x, y):
#  2:   total = x + y
#  3:   diff = x - y
#  4:   result = x / y      ← error here
#  5:   return total + diff + result
#
# firstline=5, line=8 → insert_at = 8 - 5 + 1 = 4
ctx_1 = FakeCtx(line=8, firstline=5)

marked_1 = insert_truncation_marker(code_1, ctx_1)
print("=== Test 1: insert marker ===")
print(marked_1)
print()

assert _TRUNCATION_MARKER in marked_1
# Marker should appear between line 3 (diff=) and line 4 (result=)
marked_lines = marked_1.splitlines()
marker_idx = next(i for i, l in enumerate(marked_lines) if _TRUNCATION_MARKER in l)
assert "diff = x - y" in marked_lines[marker_idx - 1]
assert "result = x / y" in marked_lines[marker_idx + 1]
print("✓ marker inserted at correct position\n")

# Now simulate: LLM receives the marked code, fixes lines above marker,
# but also writes junk below it.
llm_output_1 = """\
def compute(x, y):
  total = x + y
  diff = x - y
  # @@TRUNCATE_BELOW@@
  result = x / max(y, 1)
  extra_junk = "LLM added this"
  return total + diff + result + extra_junk"""

# Truncate with stitching: LLM's head + original tail
result_1 = truncate_at_marker(llm_output_1, marked_1)
print("=== Test 1: truncate with stitch ===")
print(result_1)
print()

assert "extra_junk" not in result_1
assert "result = x / y" in result_1  # original tail restored
assert "return total + diff + result" in result_1
print("✓ LLM junk removed, original tail stitched back\n")


# ── Test 2: error at the last line (no tail to stitch) ─────────────

code_2 = """\
def greet(name):
  msg = f"Hello, {name}!"
  print(msg)"""

# firstline=10, line=12 → insert_at = 12 - 10 + 1 = 3
ctx_2 = FakeCtx(line=12, firstline=10)

marked_2 = insert_truncation_marker(code_2, ctx_2)
print("=== Test 2: marker at last line ===")
print(marked_2)
print()

marked_lines_2 = marked_2.splitlines()
marker_idx_2 = next(i for i, l in enumerate(marked_lines_2) if _TRUNCATION_MARKER in l)
assert "print(msg)" in marked_lines_2[marker_idx_2 + 1]
print("✓ marker inserted before last line\n")

# LLM fixes and writes stuff after marker
llm_output_2 = """\
def greet(name):
  msg = f"Hello, {name}!"
  # @@TRUNCATE_BELOW@@
  print(msg)
  print("extra line from LLM")"""

result_2 = truncate_at_marker(llm_output_2, marked_2)
print("=== Test 2: truncate (last-line error, tail is just `print(msg)`) ===")
print(result_2)
print()

assert "extra line from LLM" not in result_2
assert "print(msg)" in result_2  # original tail
print("✓ correctly stitched\n")


# ── Test 3: LLM removes the marker entirely ────────────────────────

llm_output_3 = """\
def greet(name):
  msg = f"Hi, {name}!"
  print(msg)"""

result_3 = truncate_at_marker(llm_output_3, marked_2)
print("=== Test 3: LLM removed marker (fallback) ===")
print(result_3)
print()

assert result_3 == llm_output_3
print("✓ returned as-is when marker absent\n")


# ── Test 4: truncate without original (no stitch) ──────────────────

llm_output_4 = """\
def compute(x, y):
  total = x + y
  diff = x - y
  # @@TRUNCATE_BELOW@@
  result = x / max(y, 1)
  return total + diff + result"""

result_4 = truncate_at_marker(llm_output_4)  # no original_code
print("=== Test 4: truncate without stitch ===")
print(result_4)
print()

assert "result" not in result_4
assert result_4.endswith("diff = x - y")
print("✓ everything below marker removed, no stitch\n")


print("All tests passed.")
