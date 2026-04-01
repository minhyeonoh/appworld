SYSTEM:
Your job is to decide whether provided information is sufficient to produce a correct patch for a given Python function, and if so, implement it immediately.

Implement the target function only if all information required for a correct implementation is already explicitly available in the prompt.
Typical examples include simple field extraction, direct projection from existing values, straightforward formatting/conversion, or simple boolean checks over already available values.

Do NOT add silent fallbacks, such as default returns (e.g., dummy/empty values) and generic exceptions (e.g., `raise ValueError(...)`).
For an unexpected execution path, use `raise AssertionError()` with a descriptive message explaining the situation.
This should never happen.

If you want to ask for any additional information or rely on unsupported guesses or assumptions, do not implement.
Instead, write `raise NeedMoreInformation()` with a descriptive message explaining the situation.

Return exactly one Python function definition for the target function.

USER:
Evaluate whether the information is sufficient to patch `{{ snapshot.fn.name }}`.
If yes, return the fully implemented function definition. Otherwise, return the function definition with `raise NeedMoreInformation(...)` in the body.

Do not unnecessarily discard information that is naturally obtained while accomplishing the intended task, if that information is likely to be useful for downstream steps in the caller.

```python
{{ snapshot.fn.dumps(with_docstring=False, ctx=snapshot.ctx, print_locals=True) }}
```

<feedback>
{{ feedback }}
</feedback>

<expected_functionality>
{{ snapshot.fn.doc(fmt="markdown") }}
</expected_functionality>

<global_variables>
```python
{{ global_variables }}
```
</global_variables>
{% if snapshot.ctx.locals %}
<local_variables>
{{ snapshot.ctx.dumps_locals(snapshot.fn) }}
</local_variables>
{% endif %}

