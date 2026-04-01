USER:
Your job is to explore the APIs available in my environment and identify the central, primary API candidate(s) for implementing `{{ snapshot.fn.name }}`.
Before proceeding, review the expected behavior of `{{ snapshot.fn.name }}`, exploration process, and exploration discipline.

```python
{{ snapshot.fn.dumps(with_docstring=False, ctx=snapshot.ctx, print_locals=True) }}
```

# EXPECTED FUNCTIONALITY
{{ snapshot.fn.doc(fmt="markdown") }}

{% if snapshot.ctx.locals -%}
# PRINTED LOCAL VARIABLES
{{ snapshot.ctx.dumps_locals(snapshot.fn) }}

{% endif -%}
# EXPLORATION PROCESS
We will proceed in an iterative 4-step loop:
1. You choose the most plausible candidate app(s). I will then list the APIs contained within those apps.
2. You select promising API(s) from that list. I will then provide their detailed specifications.
3. You inspect the API specs and decide which API(s), if any, truly qualify as the central primary API.
4. You either stop or repeat from step 1.

# EXPLORATION DISCIPLINE
Do not choose apps or APIs based on broad relevance alone. Identify the central, primary app(s) or API(s) that could support an implementation of `{{ snapshot.fn.name }}` where the execution ultimately ends in one standalone, main API call. The implementation may include minor surrounding pre/post-processing that does not require any API call, and preparatory API calls made *before* the main API call, only if they are necessary to invoke that final API call. However, additional API calls *after* the main API call are disallowed: the execution must culminate in one standalone, main API call that completes the core task.

There might be multiple different APIs that can achieve the target functionality. While multiple candidates may exist, the final implementation will ultimately terminate in and converge on ONE of them as its final, task-completing API call (sink). Therefore, every API you select must be capable of serving as the sole final API for the task.

ASSISTANT:
Understood. I will select only the apps that are plausible homes for a valid final, task-completing API call for `{{ snapshot.fn.name }}`, following the 4-step exploration process and excluding broadly relevant but non-core options.

USER:
Let's begin Step 1.
Select the CORE app(s) essential for implementing `{{ snapshot.fn.name }}`.

{% if include_response_format | default(true) -%}
# RESPONSE FORMAT
```
{
  "reason": "explain your app choice",
  "apps": [
    "name of the app",
    ...
  ]
}
```

{% endif -%}