USER:
Infer the behavioral contract (specification) of the helper function `{{ name }}` based on its usage within the caller `{{ scope.name }}`.

```python
{{ scope.dumps(with_docstring=False, ctx=ctx, print_locals=True) }}
```

# THE CALLER'S EXPECTED FUNCTIONALITY
{{ scope.doc(fmt="markdown") }}

{% if ctx.locals -%}
# PRINTED LOCAL VARIABLES
{{ ctx.dumps_locals(scope) }}

{% endif -%}
# RULES
1. The description MUST be self-contained. It should stand on its own as a complete contract, without referring back to the caller's scope. A coding agent should be able to implement the target function given only your inferred behavioral contract.
2. Do NOT consider unexpected execution paths. Describe the intended behavior ASSUMING the underlying hypotheses are valid. Under this premise, assume the function's primary objective will succeed: if it searches, it finds; if it modifies, it writes; if it executes an action, it completes.
3. Do NOT use exemplary phrases. Do NOT use expressions like "such as", "e.g.", or "for example". These terms represent a form of hidden assumption. You must provide a definitive and precise description of the requirements based strictly on the provided context, ensuring the contract remains concrete rather than illustrative.
4. STATE "WHAT", NEVER "HOW". Describe only the expected behavioral outcome of the function. Do NOT attempt to explain the internal implementation details, step-by-step mechanics, or specific API calls required to achieve this outcome, as you do not yet know the specific APIs or exact system mechanics available within the apps.

{% if include_response_format | default(true) -%}
# RESPONSE FORMAT
```python
{
  "description": "An assumption-free, self-contained description of what the target function should do",
  "concise_description": "A concise version of the description",
  {%- if parameters %}
  "parameters": [
    {
      "name": "...",
      "description": "...",
      "type": "...(optional)"
    },
    ...
  ],
  {%- endif %}
  "returns": [
    {
      "description": "...",
      "type": "...(optional)"
    },
    ...
  ]
}
```

{% endif -%}