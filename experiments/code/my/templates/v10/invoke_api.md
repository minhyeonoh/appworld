SYSTEM:
Your job is to call a specific API inside a target function based on the provided API details and context.

1. API parameter preparation:
    - Check the API parameters against the available variables (global, and local if any).
    - For each API parameter:
        - If the value exists in the available variables, pass it directly.
        - Otherwise, invent and call a helper function to retrieve it.
            - If the helper function needs any of the available variables to get that value, pass them as arguments.
2. API call and assignment:
    - Call the API using the prepared parameters.
    - Assign the result to a variable.
    - Do NOT write any statements/expressions after the assignment.
        - We will inspect the actual runtime value of this variable in the next step and then proceed implementation.

<common_mistakes>
You have curated the following mistakes when using APIs. Review them carefully:
{%- for item in working_memory.lessons.lessons["api_common_mistakes"] %}
{{ loop.index }}. {{ item }}
{%- endfor %}
</common_mistakes>

USER:
Inside `{{ snapshot.fn.name }}`, call `{{ app_name }}.{{ api_name }}`.

```python
{{ snapshot.fn.dumps(with_docstring=False, ctx=snapshot.ctx, print_locals=True) }}
```

<api_spec>
The details of `{{ app_name }}.{{ api_name }}` API:
- Description: {{ api_doc["description"] }}
- Parameters: {% if not api_doc["parameters"] %}This API does not require any parameters.{% endif %}
{%- for param in api_doc["parameters"] %}
    - `{{ param["name"] }}` ({{ param["type"] }}, {{ 'required' if param["required"] else 'optional' }}): {{ param["description"] }}{% if not param["required"] %} Default to {{ param["default"] }}.{% endif %} 
{%- endfor %}
</api_spec>

<expected_caller_functionality>
What `{{ snapshot.fn.name }}` is expected to do:

{{ snapshot.fn.doc(fmt="markdown") }}
</expected_caller_functionality>

<global_variables>
```python
{{ global_variables }}
```
</global_variables>
{% if snapshot.ctx.locals %}
<local_variables>
{{ snapshot.ctx.dumps_locals(snapshot.fn) }}
</local_variables>
{% endif %}
