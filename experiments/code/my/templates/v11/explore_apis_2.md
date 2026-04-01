USER:
Let's begin Step 2.
Select the CORE apis(s) essential for implementing `{{ snapshot.fn.name }}`.

# API DESCRIPTIONS
{% for app_name, apis in apis_by_candidate_app.items() -%}
{% for api_name, api_description in apis.items() -%}
- `{{ app_name }}.{{ api_name }}`: {{ api_description }}
{% endfor -%}
{% endfor %}
{% if include_response_format | default(true) -%}
# RESPONSE FORMAT
```
{
  "reason": "explain your api choice",
  "apis": [
    "name of the api",
    ...
  ]
}
```

{% endif -%}