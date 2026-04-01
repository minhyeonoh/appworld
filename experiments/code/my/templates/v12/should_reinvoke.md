USER:
Your job is to explore my environment, by calling specific APIs one at a time, to gather enough contexts for implementing `{{ snapshot.fn.name }}`.
Before proceeding, review the expected behavior of `{{ snapshot.fn.name }}` and exploration process, then explicitly state your exact immediate exploration target.

```python
{{ snapshot.fn.dumps(with_docstring=False, ctx=snapshot.ctx, print_locals=True, comment_return=False) }}
```

# EXPECTED FUNCTIONALITY{% if snapshot.fn.name == "main" %} (GUARANTEED SOLVABLE){% else %} (PROVISIONAL){% endif %}
{{ snapshot.fn.doc(fmt="markdown") }}

{% if snapshot.ctx.locals -%}
# PRINTED LOCAL VARIABLES
{{ snapshot.ctx.dumps_locals(snapshot.fn) }}

{% endif -%}
# EXPLORATION PROCESS
We will proceed in repeated exploration rounds.
Each round is for choosing and executing exactly one API call.
In each round:
1. You select plausible candidate app(s). I will then list the APIs contained within those apps.
2. You select promising API(s) from that list. I will then provide their detailed specifications.
3. You inspect the API specs and decide which API(s), if any, truly qualify as potentially useful API to gather contexts.

ASSISTANT:
Understood. I will follow the exploration rounds to choose and execute one API call at a time in order to gather enough grounded context for implementing `{{ snapshot.fn.name }}`.

# CURRENT EXPLORATION TARGET
{{ rationale }}

USER:
Since you have already invoked some APIs, decide whether to re-invoke one or more of them differently, or start a new exploration round to try a not-yet-tried API.

# PREVIOUSLY INVOKED APIs
Below are the specification of APIs you have already tried.
{%- for name, doc in explored_apis.items() %}
- `{{ name }}`: {{ doc["description"] }}
	- Parameters:
	{%- if doc["parameters"] %}
		{%- for param in doc["parameters"] %}
		- `{{ param["name"] }}` ({{ param["type"] }}, {{ 'required' if param["required"] else 'optional' }}): {{ param["description"] }}{% if not param["required"] %} Default to {{ param["default"] }}.{% endif %}
		{%- endfor %}
	{%- else %}
		- This API does not require any parameters.
	{%- endif %}
{%- endfor %}

{% if include_response_format | default(true) -%}
# DECISION CRITERIA
1. **Re-invoke:** Choose this when right API(s) was/were already called, but with incorrect or suboptimal parameters. Re-invoking it differently is expected to yield the needed result.
2. **Explore:** Choose this when the needed information cannot be obtained from any of the previously invoked APIs, regardless of the parameters used. You need to search for a different API.

# RESPONSE FORMAT
Output a JSON object.
1. If you decide to **re-invoke**, list the exact `{app_name}.{api_name}` string(s).
2. If you decide to **explore** new APIs instead, leave the list empty (`[]`).
```json
{
  "rationale": "briefly explain why you are re-invoking or exploring",
  "re-invoke": [
    "{app_name}.{api_name}",
    ...
  ]
}
```

{% endif -%}