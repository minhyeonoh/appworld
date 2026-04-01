USER:
Inside `{{ snapshot.fn.name }}`, call `{{ app_name }}.{{ api_name }}`. Return a single Python function definition with the API call.

```python
{{ snapshot.fn.dumps(with_docstring=False, ctx=snapshot.ctx, print_locals=True, comment_return=False) }}
```

{% if include_why | default(true) -%}
# PURPOSE OF THIS API CALL
{{ rationale }}

{% endif -%}
# GLOBAL VARIABLES
```python
{{ global_variables }}
```

{% if snapshot.ctx.locals -%}
# PRINTED LOCAL VARIABLES
{{ snapshot.ctx.dumps_locals(snapshot.fn) }}

{% endif -%}
{% if observed_variables -%}
# WORKING MEMORY
{{ observed_variables | tojson() }}

{% endif -%}
# API SPEC OF `{{ app_name }}.{{ api_name }}`
- Description: {{ api_doc["description"] }}
- Parameters: {% if not api_doc["parameters"] %}This API does not require any parameters.{% endif %}
{%- for param in api_doc["parameters"] %}
	- `{{ param["name"] }}` ({{ param["type"] }}, {{ 'required' if param["required"] else 'optional' }}): {{ param["description"] }}{% if not param["required"] %} Default to {{ param["default"] }}.{% endif %}
{%- endfor %}

# RULES FOR API CALL

## PHASE 1: PREPARE ARGUMENTS (SETUP)
Before calling the target API, ensure every required parameter is ready.
- If a parameter's value is already available in GLOBAL, LOCAL, or WORKING MEMORY, use it directly.
- If a parameter's value is missing, you MUST create a variable for it by calling a new helper function first:
  - Call an unimplemented helper function to get the missing value. (The system will implement it later).
  - If necessary, pass only strictly visible and existing variables to this helper. Do NOT invent new context.
  - Assign the helper's return value to a local variable. Do NOT unpack or index this return value (assume it exactly matches the required type).

## PHASE 2: CALL TARGET API AND STOP (EXECUTION)
With all parameters prepared, invoke the target API.
- Call `{{ app_name }}.{{ api_name }}` using the arguments prepared in Phase 1.
- Assign the result of this API call to a distinctly named local variable.
- You MUST stop coding immediately after this single assignment of the API's return value. Do NOT write any subsequent logic including any statement/expression. Your sole focus is to properly call the API and assign its return value to a local variable.

# COMMON MISTAKES
Review carefully to avoid:
{%- for item in working_memory.lessons.lessons["api_common_mistakes"] %}
{{ loop.index }}. {{ item }}
{%- endfor %}