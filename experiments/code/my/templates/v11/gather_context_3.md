USER:
Let's begin Step 3.
Inspect the API specs and decide which API(s), if any, truly qualify as potentially useful API to gather contexts.

# API SPECS
{% for api, api_doc in api_doc_by_api.items() -%}
- `{{ api }}`:
	- Description: {{ api_doc["description"] }}
	- Parameters: {% if not api_doc["parameters"] %}This API does not require any parameters.{% endif %}
{%- for param in api_doc["parameters"] %}
		- `{{ param["name"] }}` ({{ param["type"] }}, {{ 'required' if param["required"] else 'optional' }}): {{ param["description"] }}{% if not param["required"] %} Default to {{ param["default"] }}.{% endif %}
{%- endfor %}
{% endfor %}
{% if include_response_format | default(true) -%}
# RESPONSE FORMAT
```
{
  "reason": "explain your api qualification",
  "qualified_apis": [
    "name of the api",
    ...
  ]
}
```

{% endif -%}