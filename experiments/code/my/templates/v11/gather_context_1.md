USER:
Your job is to explore my environment, by calling specific APIs one at a time, to gather enough contexts for implementing `{{ snapshot.fn.name }}`.
Before proceeding, review the expected behavior of `{{ snapshot.fn.name }}` and exploration process.

```python
{{ snapshot.fn.dumps(with_docstring=False, ctx=snapshot.ctx, print_locals=True, comment_return=False) }}
```

# EXPECTED FUNCTIONALITY
{{ snapshot.fn.doc(fmt="markdown") }}

{% if snapshot.ctx.locals -%}
# PRINTED LOCAL VARIABLES
{{ snapshot.ctx.dumps_locals(snapshot.fn) }}

{% endif -%}
# EXPLORATION PROCESS
We will proceed in repeated exploration rounds.
Each round is for choosing and executing exactly one API call.
In each round:
1. You choose the plausible candidate app(s). I will then list the APIs contained within those apps.
2. You select promising API(s) from that list. I will then provide their detailed specifications.
3. You inspect the API specs and decide which API(s), if any, truly qualify as potentially useful API to gather contexts.

ASSISTANT:
Understood. I will follow the exploration rounds to choose and execute one API call at a time in order to gather enough grounded context for implementing `{{ snapshot.fn.name }}`.

{% if rationale -%}
{{ rationale }}

{% endif -%}
USER:
Let's begin Step 1.
Select the most promising app(s) to inspect in this round in order to gather grounded context for implementing `{{ snapshot.fn.name }}`.

{% if include_response_format | default(true) -%}
# RESPONSE FORMAT
```
{
  "reason": "state your specific goal for exploring these apps",
  "apps": [
    "name of the app",
    ...
  ]
}
```

{% endif -%}