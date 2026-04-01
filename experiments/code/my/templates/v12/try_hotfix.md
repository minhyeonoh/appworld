USER:
Evaluate whether the provided information is sufficient to produce a correct patch for `{{ snapshot.fn.name }}`.
1. If yes, return the fully patched function definition.
2. Otherwise, return the function definition with `raise NeedMoreInformation(...)` in the body.

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
# TO PATCH OR NOT TO PATCH
Return exactly one Python function definition for the target function.
1. When to Implement (Sufficient Info): Implement the target function only if all information required for a correct implementation is already explicitly available in the prompt. Typical examples include simple field extraction, direct projection from existing values, straightforward formatting/conversion, or simple boolean checks over already available values.
2. When to Abort (Insufficient Info): If you want to ask for any additional information or rely on unsupported guesses or assumptions, do not implement. Instead, write `raise NeedMoreInformation()` with a descriptive message explaining the situation.

# CONSTRAINTS
Do NOT add silent fallbacks, such as default returns (e.g., dummy/empty values) and generic exceptions (e.g., `raise ValueError(...)`). For an unexpected execution path, use `raise AssertionError()` with a descriptive message explaining the situation. This should never happen.