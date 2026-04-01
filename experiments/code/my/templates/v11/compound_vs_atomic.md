USER:
Inspect the function `{{ snapshot.fn.name }}` and classify its task as either `compound` or `atomic`.

```python
{{ snapshot.fn.dumps(with_docstring=False, ctx=snapshot.ctx, print_locals=True) }}
```

# COMPOUND VS ATOMIC
- Classify as `atomic` if the core task is naturally completed by exactly one central, primary API call as the final task-completing step (the sink), with no API calls needed afterward. Branching, looping, or other processing is allowed after the sink if it does not involve additional API calls.
- Classify as `compound` otherwise.

# EXPECTED FUNCTIONALITY
{{ snapshot.fn.doc(fmt="markdown") }}

{% if include_response_format | default(true) -%}
# RESPONSE FORMAT
```
{
  "reason": "<brief explanation>",
  "type": "compound|atomic"
}
```

{% endif -%}