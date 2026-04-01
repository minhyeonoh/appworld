USER:
Previously I sketched a high-level orchestration skeleton for `{{ snapshot.fn.name }}` using helper function calls, each responsible for solving a specific subproblem.

```python
{{ snapshot.fn.dumps(with_docstring=True, ctx=snapshot.ctx, print_locals=True) }}
```

I requested my colleague to implement `{{ helper }}`, and after running the program, I found that `{{ helper }}` now returns a structured object with `primary` and `extras` fields:

```
{{ return_value }}
```

I now need to adapt the data flow of `{{ snapshot.fn.name }}` to correctly use this return value.

{% if snapshot.ctx.locals -%}
# PRINTED LOCAL VARIABLES
{{ snapshot.ctx.dumps_locals(snapshot.fn) }}

{% endif -%}
{% if include_global_variables | default(true) -%}
# GLOBAL VARIABLES
```python
{{ global_variables }}
```

{% endif -%}
# RETURN CONTRACT OF `{{ helper }}`
- `primary`: the helper's main result
- `extras`: additional useful information that may help downstream helpers, revealed during implementation/execution of `{{ helper }}`

# DATA-FLOW ADAPTATIOn DISCIPLINE
1. Preserve the intended orchestration of `{{ snapshot.fn.name }}`. Only adapt the data flow needed for the return shape of `{{ helper }}`.
2. When the result (or part of it) of `{{ helper }}` is forwarded to another helper, preserve useful information when reasonable instead of prematurely discarding it.
3. Do not introduce new API calls, new helper functions, or unrelated logic. Only rewrite the existing data flow to accommodate the revealed return value.

# RESPONSE FORMAT
Return only the rewritten function definition for `{{ snapshot.fn.name }}`.