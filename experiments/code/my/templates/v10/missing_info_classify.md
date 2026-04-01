

SYSTEM:
Your job is to classify a missing-information situation for a target function.

A previous diagnosis has already determined that the current function is missing some information required to proceed correctly.
Your job is to decide which of the following cases best explains that missing information:

{% if observed_variables["outer"] -%}
- `caller_has_it`
  - The needed information is already available in an outer caller scope (or caller's caller, etc.), but it was not passed into the current function.
{%- endif %}
{% if observed_variables["inner"] -%}
- `callee_has_it`
  - The needed information has already been observed or obtained within a callee function called by the current function (or by a deeper descendant callee), but that information is not currently available (discarded during returns).
{%- endif %}
- `never_seen`
  - The needed information has not yet been observed in caller-side scopes or callee-side scopes.

<observed_variables_explanation>
You are given `observed_variables`, which stores values already observed during execution.

{% if observed_variables["outer"] -%}
- `observed_variables["outer"]` contains values observed in outer caller scopes.
  - Each outer function name maps to the latest observed variables from that caller-side scope.
{%- endif %}
{% if observed_variables["inner"] -%}
- `observed_variables["inner"]` contains values observed in callee-side scopes beneath the current target function.
  - These are values already observed or produced by functions called by the current function (possibly through deeper descendants).
{%- endif %}

Use this information to decide whether the missing information:

- already exists in a caller-side scope but was not passed (`caller_has_it`),
- already exists in a callee-side scope but was not returned/reused (`callee_has_it`),
- or has truly never been seen yet (`never_seen`).
</observed_variables_explanation>

<return_json>
Response format:
```
{
  "think": "brief evidence-based justification",
  "classification": "caller_has_it | callee_has_it | never_seen"
}

USER:
Classify the missing-information situation for {{ snapshot.fn.name }}.

```python
{{ snapshot.fn.dumps(with_docstring=False, ctx=snapshot.ctx, print_locals=False, comment_locals=False) }}
```

<expected_functionality>
{{ snapshot.fn.doc(fmt="markdown") }}
</expected_functionality>

<exception_message>
{{ snapshot.ctx.exc.tb.message }}
</exception_message>

<previous_diagnosis>
{{ diagnosis }}
</previous_diagnosis>

<observed_variables>
{{ observed_variables | tojson(indent=2)  }}
</observed_variables>