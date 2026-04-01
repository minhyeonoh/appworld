USER:
Diagnose root cause(s) of the exception in a program you previously wrote to solve my problem, and for each cause, provide a fix for `{{ snapshot.fn.name }}` in the program.

```python
{{ snapshot.fn.dumps(with_docstring=False, ctx=snapshot.ctx, print_locals=True) }}
```

# EXPECTED FUNCTIONALITY
You have intended `{{ snapshot.fn.name }}` to behave as follows:

{{ snapshot.fn.doc(fmt="markdown") }}

{% if snapshot.ctx.locals -%}
# PRINTED LOCAL VARIABLES
{{ snapshot.ctx.dumps_locals(snapshot.fn) }}

{% endif -%}
# EXCEPTION
{{ snapshot.ctx.exc.tb.message }}

# USED APIS
{%- for api in used_apis %}
- `{{ api["name"] }}`: {{ api["description"] }}
	- Parameters:
	{%- if api["parameters"] %}
		{%- for param in api["parameters"] %}
		- `{{ param["name"] }}` ({{ param["type"] }}, {{ 'required' if param["required"] else 'optional' }}): {{ param["description"] }}{% if not param["required"] %} Default to {{ param["default"] }}.{% endif %}
		{%- endfor %}
	{%- else %}
		- This API does not require any parameters.
	{%- endif %}
{%- endfor %}

# DIAGNOSIS DISCIPLINE
Carefully adhere to R1, R2, and R3 while diagnosing the issue. Furthermore, you MUST follow these rules:
1. The program was entirely written by you. The error is due to a logical or implementation flaw in your code.
2. Fix must allow the execution to proceed successfully. Do not use silent fallbacks (e.g., simply raising another error or returning default/dummy values like `None`). Silent fallbacks do not solve the problem; they should crash the workflow in a different way.
3. Provide fix that can be achieved within the target function's body, not the caller.

# RESPONSE_FORMAT
Identify as many plausible root cause(s) of the exception as possible, and provide a fix for each cause.
Each item must be self-contained and mutually exclusive.
```
[
  {
    "cause": "...describe the cause",
    "fix": "...describe how to fix (do not write the code)",
    "category": "fixable_now | missing_information"
  },
  ...
]
```
where:
- `fixable_now` indicates that `{{ snapshot.fn.name }}` can be corrected immediately without asking for any additional information and without relying on unsupported guesses or unstated assumptions.
	- Use `fixable_now` only if your fix relies on information that is guaranteed to be true.
	- If your fix needs some additional APIs, use `missing_information`.
- `missing_information` indicates that `{{ snapshot.fn.name }}` cannot proceed because it lacks a concrete environment-specific value or required runtime value that must first be obtained via appropriate APIs.
	- A diagnosis must be labeled `missing_information` rather than `fixable_now` if its proposed fix requires discovering, verifying, searching for, or retrieving any unknown environment-specific value before the target function can be corrected.
  -  If the information you require is directly visible in the provided information, use `fixable_now`.