
USER:
Keep R1, R2, R3 and R4 in mind while solving my problem. You will solve my problem by writing a Python program. Each function in the program will be introduced/implemented just-in-time, only when it becomes necessary during execution.

{% if include_implementation_first | default(false) -%}
# PLAN-FIRST VS. EXPLORATION-FIRST VS. IMPLEMENTATION-FIRST
For each function, you must choose one of three modes for implementation: `plan-first`, `exploration-first`, or `implementation-first`.

# WHEN TO PLAN, EXPLORE, OR IMPLEMENT
{% else -%}
# PLAN-FIRST VS. EXPLORATION-FIRST
For each function, you must choose one of two modes for implementation: `plan-first` or `exploration-first`.

# WHEN TO PLAN AND WHEN TO EXPLORE
{% endif -%}
1. `plan-first` 
Use this mode when the task-solving structure or control/execution flow is crystal clear and highly unlikely to change.
To be considered "crystal clear":
	- The flow of sub-problems must be robust to any implementation/execution details.
	- Even if additional observations arrive, the overall flow should remain the same and only the details (e.g., expected return values/types) might change.
	- Based only on the provided information, you must be able to guarantee that each sub-problem is solvable.
2. `exploration-first`
Use this mode when the task-solving structure or flow itself is still unclear.
To be considered "unclear":
	- You are not certain how to safely decompose the task into sub-problems.
	- You are missing critical information that may fundamentally alter (or invalidate) the overall task-solving structure or execution flow if assumptions turn out to be incorrect.
	- Attempting to plan now would rely on blind assumptions or guesses.
{%- if include_implementation_first %}
3. `implementation-first`
Use this mode when the expected functionality is trivial.
To be considered "trivial":
	- All information required for a correct implementation of the functionality is already explicitly visible/provided.
	- The task requires NO API calls. Because you do not yet know the available APIs, needing an API inherently means you lack sufficient information, which disqualifies the task from being trivial.
	- Typical examples include simple field extraction, direct projection from existing values, straightforward formatting/conversion, or simple boolean checks over already available values.
{%- endif %}

# ACTION BY MODE
Depending on the selected mode, behave as follows:
1. For `plan-first`, outline the robust, unlikely-to-change task-solving flow by breaking it down into distinct sub-problems.
2. For `exploration-first`, define a precise, immediate exploration target (exactly one specific thing you need to discover, verify, or confirm next).
{%- if include_implementation_first %}
3. For `implementation-first`, briefly describe the direct implementation logic.
{%- endif %}

ASSISTANT:
{% if include_implementation_first | default(false) -%}
Understood. I will evaluate the complexity and clarity of the expected functionality and choose between `plan-first` to outline a robust execution flow, `exploration-first` to set an immediate exploration target, or `implementation-first` to suggest trivial logic.
{% else -%}
Understood. I will evaluate the clarity of the task-solving structure for a given function and choose between `plan-first` to outline a robust execution flow, or `exploration-first` to set an immediate exploration target.
{% endif -%}

USER:
{% if snapshot.ctx.locals -%}
Now, choose the implementation mode for `{{ snapshot.fn.name }}` based on the EXPECTED FUNCTIONALITY and PRINTED LOCAL VARIABLES (observed).

```python
{{ snapshot.fn.dumps(with_docstring=False, ctx=snapshot.ctx, print_locals=True, comment_return=False) }}
```

# EXPECTED FUNCTIONALITY
{{ snapshot.fn.doc(fmt="markdown") }}

# PRINTED LOCAL VARIABLES
{{ snapshot.ctx.dumps_locals(snapshot.fn) }}

{% else -%}
Now, choose implementation mode for `{{ snapshot.fn.name }}` whose expected functionality is:

{{ snapshot.fn.doc(fmt="markdown") }}

{% endif -%}
{% if include_response_format | default(true) -%}
# RESPONSE FORMAT
```json
{
{%- if include_implementation_first %}
  "mode": "plan-first|exploration-first|implementation-first",
  "strategy": "for plan-first, describe your robust task-solving skeleton (sub-problems). for exploration-first, describe your exact immediate exploration target. for implementation-first, describe the direct implementation logic."
{%- else %}
  "mode": "plan-first|exploration-first",
  "strategy": "for plan-first, describe your robust task-solving skeleton (sub-problems). for exploration-first, describe your exact immediate exploration target."
{%- endif %}
}
```

{% endif -%}