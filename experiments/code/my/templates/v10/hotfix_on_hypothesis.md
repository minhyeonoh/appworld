SYSTEM:
Do NOT add silent fallbacks, such as default returns (e.g., `return None`, `return False`) and generic exceptions (e.g., `raise ValueError(...)`).
For an unexpected execution path, use `raise AssertionError()` with a descriptive message explaining the situation.
This should never happen.

USER:
Patch `{{ snapshot.fn.name }}` based on provided debugging feedback (cause of exception and corresponding fix).

```python
{{ snapshot.fn.dumps(with_docstring=False, ctx=snapshot.ctx, print_locals=True) }}
```

# FEEDBACK THAT REQUIRES PATCH
{{ feedback }}

# EXPECTED FUNCTIONALITY
{{ snapshot.fn.doc(fmt="markdown") }}

{% if snapshot.ctx.locals -%}
# PRINTED LOCAL VARIABLES
{{ snapshot.ctx.dumps_locals(snapshot.fn) }}

{% endif -%}
# CONSTRAINTS
1. Return exactly one Python function definition for the target function.
2. Do NOT add silent fallbacks, such as default returns (e.g., dummy/empty values) and generic exceptions (e.g., `raise ValueError(...)`). For an unexpected execution path, use `raise AssertionError()` with a descriptive message explaining the situation. This should never happen.