USER:
You are exploring my environment, by calling specific APIs one at a time, to gather enough contexts for implementing `{{ snapshot.fn.name }}`. However, an exception occurred during your API-call attempt.

Your job is to fix this exception.
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
Understood completely.

I have reviewed the expected functionality of `{{ snapshot.fn.name }}`, the current exploration focus, the API attempted for this focus, the exception message, and the current working memory.

Based on my review, my diagnosis for the cause of the error is:
{{ diagnosis }}

USER:
Produce a correct patch for `{{ snapshot.fn.name }}` to resolve the exception based on your diagnosis.

# PATCH DISCIPLINE
Strictly adhere to the following rules:
1. **STRICT ALIGNMENT:** Your patch MUST strictly serve the `# YOUR CURRENT EXPLORATION FOCUS`. Do not suggest fixes that abandon/bypass this focus, or pivot to an unrelated task just to make the API call succeed without errors. Your ultimate objective is to fulfill the exploration focus.
2. **NO APPENDING:** Do NOT append any new statements or expressions to the end of the current function body. Your sole focus is to address your diagnosis by modifying the existing code. Attempting to guess and append new logic to "complete" the implementation will make the code brittle.
3. **NO SILENT FALLBACKS:** Do NOT add silent fallbacks, such as default returns (e.g., dummy/empty values) and generic exceptions (e.g., `raise ValueError(...)`). For an unexpected execution path, use `raise AssertionError()` with a descriptive message explaining the situation. This should never happen.

# RESPONSE FORMAT
Return exactly ONE Python function definition containing your patch.

```python
{{ snapshot.fn.header() }}:
  # Your patched code
  ...
```