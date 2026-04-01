USER:
Step 2. Select promising API(s) to inspect in this round in order to gather the target information.
1. There may be multiple different APIs that are useful for a similar exploratory purpose, even if their functionalities are not identical.
2. Prefer primary APIs that offer the most direct path to the target information.

# API DESCRIPTIONS
{% for app_name, apis in apis_by_candidate_app.items() -%}
{% for api_name, api_description in apis.items() -%}
- `{{ app_name }}.{{ api_name }}`: {{ api_description }}
{% endfor -%}
{% endfor %}
{% if include_response_format | default(true) -%}
# RESPONSE FORMAT
```json
{
  "rationale": "explain your api choice",
  "apis": [
    "name of the api",
    ...
  ]
}
```

{% endif -%}