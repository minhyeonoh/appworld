USER:
Evaluate whether `{{ snapshot.fn.name }}` is trivially implementable from the provided information.
1. If yes, return the fully implemented function definition.
2. Otherwise, return the function definition with `raise NeedMoreInformation(...)` in the body.

```python
{{ snapshot.fn.dumps(with_docstring=False, ctx=snapshot.ctx, print_locals=True) }}
```

# EXPECTED FUNCTIONALITY{% if snapshot.fn.name == "main" %} (GUARANTEED SOLVABLE){% else %} (PROVISIONAL){% endif %}
{{ snapshot.fn.doc(fmt="markdown") }}

# GLOBAL VARIABLES
```python
{{ global_variables }}
```

{% if snapshot.ctx.locals -%}
# PRINTED LOCAL VARIABLES
{{ snapshot.ctx.dumps_locals(snapshot.fn) }}

{% endif -%}
{% if observed_variables | default(false) -%}
# WORKING MEMORY
{{ observed_variables | tojson() }}

{% endif -%}
# TRIVIAL IMPLEMENTATION RULES
Return exactly one Python function definition for the target function.
1. Implement the target function only if all information required for a correct implementation is already explicitly available in the prompt. Typical examples include simple field extraction, direct projection from existing values, straightforward formatting/conversion, or simple boolean checks over already available values.
2. If you want to ask for any additional information or rely on unsupported guesses or assumptions, do not implement. Instead, write `raise NeedMoreInformation()` with a descriptive message explaining the situation.