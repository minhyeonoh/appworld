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
3. Do NOT append any new statements or expressions to the end of the current function body. Your sole focus is to address the diagnosis by modifying the existing code. Attempting to guess and append new logic to "complete" the implementation will make the code brittle.