USER:
You are exploring my environment, by calling specific APIs one at a time, to gather enough contexts for implementing `{{ snapshot.fn.name }}`. However, an exception occurred during your API-call attempt.

Your job is to diagnose various distinct causes of this exception.
Before proceeding, thoroughly review and understand the current situation.

```python
{{ snapshot.fn.dumps(with_docstring=False, ctx=snapshot.ctx, print_locals=True, comment_return=False) }}
```

# EXPECTED FUNCTIONALITY OF `{{ snapshot.fn.name }}`{% if snapshot.fn.name == "main" %} (GUARANTEED SOLVABLE){% else %} (PROVISIONAL){% endif %}
{{ snapshot.fn.doc(fmt="markdown") }}

# YOUR CURRENT EXPLORATION FOCUS
{{ rationale }}

# ATTEMPTED API
You tried to call `{{ app_name }}.{{ api_name }}` with the following specification:
- Description: {{ api_doc["description"] }}
- Parameters: {% if not api_doc["parameters"] %}This API does not require any parameters.{% endif %}
{%- for param in api_doc["parameters"] %}
	- `{{ param["name"] }}` ({{ param["type"] }}, {{ 'required' if param["required"] else 'optional' }}): {{ param["description"] }}{% if not param["required"] %} Default to {{ param["default"] }}.{% endif %}
{%- endfor %}

# EXCEPTION
{{ snapshot.ctx.exc.tb.message }}

{% if snapshot.ctx.locals -%}
# PRINTED LOCAL VARIABLES
{{ snapshot.ctx.dumps_locals(snapshot.fn) }}

{% endif -%}
{% if observed_variables or solved_helpers[snapshot.fn.name] -%}
# WORKING MEMORY
{% if observed_variables and solved_helpers[snapshot.fn.name] -%}
You have observed various things and implemented various helper tools before calling `{{ snapshot.fn.name }}`.

{% elif observed_variables -%}
You have observed various things before calling `{{ snapshot.fn.name }}`.

{% elif solved_helpers[snapshot.fn.name] -%}
You have implemented various tools before calling `{{ snapshot.fn.name }}`.

{% endif -%}
{% if observed_variables -%}
## OBSERVED VARIABLES SO FAR (EXCEPT LOCALS)
{{ observed_variables | tojson() }}

{% endif -%}
{% if solved_helpers[snapshot.fn.name] -%}
## RESOLVED HELPERS
{%- for helper in solved_helpers[snapshot.fn.name].values() %}
- `{{ helper.name }}`: {{ helper.description }}
	- Parameters:
	{%- if helper.parameters %}
		{%- for param in helper.parameters %}
		- `{{ param.name }}` ({{ param.type }}, {{ 'required' if param.required else 'optional' }}): {{ param.description }}{% if not param.required %} Default to {{ param.default }}.{% endif %}
		{%- endfor %}
	{%- else %}
		- This helper does not require any parameters.
	{%- endif %}
{%- endfor %}

{% endif -%}
{% endif -%}

ASSISTANT:
Understood completely. I have reviewed the expected functionality of `{{ snapshot.fn.name }}`, the current exploration focus, the API attempted for this focus, the exception message, and the current working memory.

USER:
Now, diagnose multiple plausible causes of the exception and categorize your hypotheses based on whether you currently have sufficient information to fix them.

# SUFFICIENT VS. INSUFFICIENT
1. `sufficient`
Use this category if the correct workarounds rely ONLY on the provided context; i.e., if you can correct the error immediately WITHOUT asking for any additional information and WITHOUT relying on unsupported guesses or unstated assumptions. Typical examples include parameter formatting issue, typo, or minor flaw. If workarounds need some additional API calls, use the `insufficient` category.
2. `insufficient`
Use this category if the correct workarounds can be inferred, but cannot be 100% surely determined from what is available; i.e., if you cannot proceed because you lack a concrete environment-specific value or required runtime value that must first be obtained via appropriate APIs. This requires discovering, verifying, searching for, or retrieving an unknown environment-specific value before retrying. If the information you require is already directly visible in the provided information, use the `sufficient` category.

# DIAGNOSIS DISCIPLINE
Any diagnosis, whether `sufficient` or `insufficient`, MUST strictly serve the `# YOUR CURRENT EXPLORATION FOCUS`. Do not suggest fixes that abandon/bypass this focus, or pivot to an unrelated task just to make an API call succeed without errors. Your ultimate objective is to fulfill the exploration focus.

# RESPONSE FORMAT
1. If no hypotheses fit a specific category, leave its list empty (`[]`).
2. You MUST provide at least one cause in total. Both categories cannot be empty simultaneously.
```json
{
  "sufficient": [
    "......describe the potential cause that you can fix right now",
    ...
  ],
  "insufficient": [
    "...describe the potential cause that requires further exploration",
    ...
  ]
}
```