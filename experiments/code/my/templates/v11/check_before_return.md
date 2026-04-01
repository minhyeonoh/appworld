USER:
Evaluate whether the current implementation of `{{ snapshot.fn.name }}` exactly satisfies the expected functionality.

```python
{{ snapshot.fn.dumps(with_docstring=False, ctx=snapshot.ctx, print_locals=True) }}
```

# EXPECTED FUNCTIONALITY
{{ snapshot.fn.doc(fmt="markdown") }}

{% if snapshot.ctx.locals -%}
# PRINTED LOCAL VARIABLES
{{ snapshot.ctx.dumps_locals(snapshot.fn) }}

{% endif -%}
# EVALUATION RULES
Respond "yes" iff the implementation matches the required functionality; otherwise respond "no".

Your evaluation must strictly adhere to the following criteria:
1. Focus on the "What": Verify that the implementation exactly fulfills the explicit requirements (e.g., return values, data types, and observable side effects).
2. Do Not Penalize the "How": Do NOT penalize the specific algorithmic approach, code style, or logic used, unless a specific method is explicitly mandated in the expected functionality.
3. Tolerance for Underspecification: If the expected functionality is silent about specific edge cases or behaviors, you must accept ANY behavior that does not contradict the explicitly stated requirements. Do not invent or enforce unstated rules.

{% if include_response_format | default(true) -%}
# RESPONSE FORMAT
```
{
  "reason": "brief justification",
  "evaluation": "yes|no"
}
```

{% endif -%}