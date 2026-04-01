SYSTEM:
A helper function has just been implemented and executed within the orchestration skeleton of `{{ snapshot.fn.name }}`.
Your job is to decide whether the remaining orchestration logic in `{{ snapshot.fn.name }}` needs to be updated, given the helper's actual return value.

<requirements_and_constraints>
1. The orchestration skeleton was written before the helper was implemented.
  - Now that the helper's behavior is concrete, the remaining logic may need adjustment.
2. If the return value matches what the skeleton assumed, respond "no".
3. If the return value reveals that the remaining logic needs to change (e.g., different data shape, missing steps, wrong variable usage), respond "yes" and provide the updated function body.
</requirements_and_constraints>

<return_json>
Response format:
```
{
  "think": "brief justification",
  "update": "yes|no"
}
```
If "yes", follow the JSON with the updated function:
```python
def {{ snapshot.fn.name }}(...):
  ...
```
</return_json>

USER:
The helper function `{{ helper_name }}` has just completed execution inside `{{ snapshot.fn.name }}`.

Here is the current orchestration function:

```python
{{ snapshot.fn.dumps(with_docstring=False, ctx=snapshot.ctx, print_locals=True) }}
```

<expected_functionality>
{{ snapshot.fn.doc(fmt="markdown") }}
</expected_functionality>

<helper_return_value>
`{{ helper_name }}` returned: {{ helper_return_value }} (type: {{ helper_return_value_type }})
</helper_return_value>
{% if globals_accessed %}
<global_variables>
```python
{{ global_variables }}
```
</global_variables>
{% endif -%}
{% if snapshot.ctx.locals %}
<local_variables>
{{ snapshot.ctx.dumps_locals(snapshot.fn) }}
</local_variables>
{% endif %}
