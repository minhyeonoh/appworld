USER:
Inside `{{ snapshot.fn.name }}`, call `{{ app_name }}.{{ api_name }}`.

```python
{{ snapshot.fn.dumps(with_docstring=False, ctx=snapshot.ctx, print_locals=True, comment_return=False) }}
```

{% if include_expected_functionality | default(true) -%}
# EXPECTED FUNCTIONALITY OF `{{ snapshot.fn.name }}`
{{ snapshot.fn.doc(fmt="markdown") }}

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

# RULES
1. API parameter preparation:
	- Check the API parameters against the available variables (global, and local if any).
	- For each API parameter:
		- If the value exists in the available variables, pass it directly.
		- Otherwise, call a helper function to retrieve it.
			- If the helper function needs any of the available variables to get that value, pass them as arguments.
			- Do NOT implement helper functions. The system will implement them later.
2. API call and assignment:
	- Call the API using the prepared parameters.
	- Assign the result to a variable.
	- Do NOT write any statements/expressions after the assignment.
		- We will inspect the actual runtime value of this variable in the next step and then proceed implementation.

Treat the actual implementation details as a black box.
1. Every call must be a helper function call.
2. NEVER access inner fields. You must never access inner fields or properties of a return value. You do not know the data structures yet.
3. Pass the whole object. Even if a subsequent step only needs a specific piece of data, pass the entire object to the helper function to give the future implementation total freedom.

# COMMON MISTAKES
Review carefully:
{%- for item in working_memory.lessons.lessons["api_common_mistakes"] %}
{{ loop.index }}. {{ item }}
{%- endfor %}