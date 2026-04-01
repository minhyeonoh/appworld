USER:
Classify the missing-information situation for `{{ snapshot.fn.name }}`.

```python
{{ snapshot.fn.dumps(with_docstring=False, ctx=snapshot.ctx, print_locals=False, comment_locals=False) }}
```

# EXPECTED FUNCTIONALITY
{{ snapshot.fn.doc(fmt="markdown") }}

# EXCEPTION
{{ snapshot.ctx.exc.tb.message }}

# PREVIOUS DIAGNOSIS
{{ diagnosis }}

# RESPONSE FORMAT
A previous diagnosis determined that the function is missing some information required to proceed correctly.
Decide which of the following cases best explains that missing information.
```
{
  "reason": "brief evidence-based justification",
  "classification": "{% if observed_variables['outer'] %}caller_has_it | {% endif %}{% if observed_variables['inner'] %}callee_has_it | {% endif %}never_seen"
}
```
where:
{% if observed_variables["outer"] -%}
- `caller_has_it`: The needed information is already available in an outer caller's scope (or caller's caller, etc.), but it was not passed into the current function.
{% endif -%}
{% if observed_variables["inner"] -%}
- `callee_has_it`: The needed information was already observed at some point during the prior execution trace (e.g., in a sibling function called earlier by the caller, or in a deeper callee of the current/sibling function), but that information is not currently available (discarded from the data flow).
{% endif -%}
- `never_seen`: The needed information has not yet been observed in caller-side scopes or callee-side scopes.

Here are observed variables.
```
observed_variables = {{ observed_variables | tojson() }}
```
{% if observed_variables["outer"] -%}
- `observed_variables["outer"]` contains values observed in outer caller scopes. Each outer function name maps to the latest observed variables from that caller-side scope.
{% endif -%}
{% if observed_variables["inner"] -%}
- `observed_variables["inner"]` contains values observed in all previously executed scopes that are NOT part of the active outer call stack. This includes values produced by "sibling" functions executed before the current function, deeper descendants, or any other previously finished calls.
{% endif -%}