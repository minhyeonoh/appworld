USER:
Choose a promising API from the following APIs provided by the `{{ app_name }}` app to view API spec.
{%- for info in api_descriptions %}
- `{{ info["name"] }}`: {{ info["description"] }}
{%- endfor %}

Response format:
```
{
  "think": "explain your API choice",
  "api": "name of the API"
}
```