USER:
You are gathering enough information for `{{ snapshot.fn.name }}` from my environment by calling APIs.

```python
{{ snapshot.fn.dumps(with_docstring=False, ctx=snapshot.ctx, print_locals=True, comment_return=False) }}
```

# EXPECTED FUNCTIONALITY
{{ snapshot.fn.doc(fmt="markdown") }}

{% if snapshot.ctx.locals -%}
# PRINTED LOCAL VARIABLES
{{ snapshot.ctx.dumps_locals(snapshot.fn) }}

{% endif -%}
{% if observed_variables -%}
# WORKING MEMORY
{{ observed_variables | tojson() }}

{% endif -%}
# EVALUATION
Based on the local variables collected so far, evaluate the gathered information as follows:
- `done`: sufficient to implement `{{ snapshot.fn.name }}`.
- `unhelpful`: contributes little or nothing toward `{{ snapshot.fn.name }}`'s expected functionality.
- `helpful-but-more`: promising, but requires additional API calls for a concrete additional verification or information-gathering step before proceeding implementation of `{{ snapshot.fn.name }}`.
- `helpful-but-retry`: promising, but requires calling the same API again with more appropriate arguments or for a more refined purpose.



{% if include_response_format | default(true) -%}
# RESPONSE FORMAT
```
{
  "reason": "brief justification",
  "evaluation": "done|unhelpful|helpful-but-more|helpful-but-retry"
}
```

{% endif -%}
