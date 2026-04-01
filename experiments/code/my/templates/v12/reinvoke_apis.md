USER:
Inside `{{ snapshot.fn.name }}`, re-invoke the API{{ 's' if reinvoke_app_apis | length != 1 }}. Return a single Python function definition with the API call{{ 's' if reinvoke_app_apis | length != 1 }}.

# PHASE 1: PREPARE ARGUMENTS (SETUP)
Before calling the target API{{ 's' if reinvoke_app_apis | length != 1 }}, ensure every required parameter is ready.
- If a parameter's value is already available in GLOBAL, LOCAL, or WORKING MEMORY, use it directly.
- If a parameter's value is missing, you MUST create a variable for it by calling a new helper function first:
  - Call an unimplemented helper function to get the missing value. (The system will implement it later).
  - If necessary, pass only strictly visible and existing variables to this helper. Do NOT invent new context.
  - Assign the helper's return value to a local variable. Do NOT unpack or index this return value (assume it exactly matches the required type).

# PHASE 2: CALL TARGET API AND STOP (EXECUTION)
With all parameters prepared, invoke the target API{{ 's' if reinvoke_app_apis | length != 1 }}.
- Call the API{{ 's' if reinvoke_app_apis | length != 1 }} using the arguments prepared in Phase 1.
- Assign the result of an API call to a distinctly named local variable.
- You MUST stop coding immediately after this current body of `{{ snapshot.fn.name }}`. Do NOT write any subsequent logic including any statement/expression. Your sole focus is to properly call the API{{ 's' if reinvoke_app_apis | length != 1 }} and assign {% if reinvoke_app_apis | length == 1 -%} its return value to a local variable.{%- else -%} their return values to local variables.{%- endif %}

# COMMON MISTAKES
Review carefully to avoid:
{%- for item in working_memory.lessons.lessons["api_common_mistakes"] %}
{{ loop.index }}. {{ item }}
{%- endfor %}

# RESPONSE FORMAT
Return exactly ONE Python function definition containing your re-invoke.

```python
{{ snapshot.fn.header() }}:
  ...
```