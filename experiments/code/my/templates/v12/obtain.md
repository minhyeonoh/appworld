USER:
Patch `{{ snapshot.fn.name }}` by calling a new helper function to obtain the missing information, in order to resolve an error in a program you previously wrote to solve my problem.
The provided diagnosis describes what is missing.

```python
{{ snapshot.fn.dumps(with_docstring=False, ctx=snapshot.ctx, print_locals=True) }}
```

# EXPECTED FUNCTIONALITY
{{ snapshot.fn.doc(fmt="markdown") }}

{% if snapshot.ctx.locals -%}
# PRINTED LOCAL VARIABLES
{{ snapshot.ctx.dumps_locals(snapshot.fn) }}

{% endif -%}
# EXCEPTION
{{ snapshot.ctx.exc.tb.message }}

# DIAGNOSIS
{{ diagnosis }}

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

# PATCH DISCIPLINE

## INTRODUCE HELPER TO OBTAIN MISSING INFORMATION
- Introduce helper function(s) whose purpose is to obtain the missing information that the diagnosis requires.
- Do NOT implement the helper function. The system will implement it later.
{% if snapshot.ctx.locals -%}
- PASS USEFUL INFORMATION TO THE HELPER:
	- When calling this helper, you MUST pass potentially useful information in a STRUCTURED manner (i.e., dictionaries with descriptive fields) so the helper has the necessary and sufficient clues to perform its task. 
	- Ensure the passed information is strictly visible in the printed LOCAL variables ({% for var in snapshot.ctx.locals %}`{{ var.id }}`{% if not loop.last %}, {% endif %}{% endfor %}). Do NOT pass information visible in the GLOBAL variables.
{% endif -%}
- ASSIGN HELPER'S RETURN VALUE:
	- Before using the return value of this helper function call (e.g., passing the value to another function), assign it to a new local variable.
	- When passing the return value, do NOT attempt to unpack, index, or access specific fields of this new local variable; assume the helper returns the exact data type needed, and pass the variable directly as-is.

## DO NOT IMPLEMENT, JUST CALL HELPER
- Do NOT write a placeholder for the helper function definition inside the target function.
- Do NOT blindly assume/guess/invent any APIs. You are provided with only app information, not app-specific APIs.
- Do NOT consider unexpected execution path for the helper function; assume it will successfully obtain the missing information. Therefore, absolutely NO silent fallbacks, such as default returns (e.g., `return None`, `return False`) and generic exceptions (e.g., `raise ValueError(...)`).
- Do NOT append any new statements or expressions to the end of the current function body. Your sole focus is to address the diagnosis by introducing the helper function to obtain the missing information. Attempting to guess and append new logic to "complete" the implementation will make the code brittle.

