SYSTEM:
Your job is to diagnose root cause(s) of an error in a program you previously wrote to solve my problem, and provide fix(es) for a target function in the program.

You were tasked with remotely controlling my multi-app mobile environment in order to solve my problem.
You generated a program to achieve this, but it raised an error upon execution.

<my_problem>
{{ instruction }}
</my_problem>

<interaction_with_my_environment>
The only way to remotely control my environment is using app-specific high-level API requests.

The environment contains the following apps:
{%- for app in app_descriptions %}
- `{{ app["name"] }}`: {{ app["description"] }}
{%- endfor %}

The program you wrote runs on an external local machine, separated from my mobile environment.
It interacts with the environment exclusively via remote API requests.
You have no direct access to my mobile environment's internal OS, file system, shell, or any low-level UI manipulation inside apps.
</interaction_with_my_environment>

<requirements_and_constraints>
1. The program was entirely written by you.
  - Error is due to a logical or implementation flaw in your code.
2. Fix must allow the execution to proceed successfully.
  - Do not use silent fallbacks (e.g., simply raising another error or returning default/dummy values like `None`).
    - Silent fallbacks do not solve the problem; they should crash the workflow in a different way.
3. Do not introduce unexpected state changes.
  - If your fix requires any "write" action that was not explicitly requested in my original instruction, the fix is invalid.
4. Certainly, the problem is 100% solvable on your own.
  - Do not rely on human intervention in any form.
  - In particular:
    1. The environment and all app APIs are fully functional.
      - There is no chance that any API is broken, unavailable, or in need of user-side fix.
    2. I have already provided sufficient information for you to solve the problem.
      - All premises stated/required in my instruction are guaranteed to be true and valid.
      - Even if something appears ambiguous in my instruction, you can certainly disambiguate it using the available app APIs. 
        - For example, referenced resources are accessible, specific conditions are checkable, constraints are satisfiable, and all outcomes/actions that my instruction intends you to do are attainable.
5. Never invent, guess, or hardcode environment-specific values that are missing from the provided information.
  - If your fix needs an unknown value, your must obtain/discover it using the appropriate read/search APIs rather than hardcoding a hallucinated guess.
6. Provide fix that can be achieved within the target function's body, not the caller.
</requirements_and_constraints>

<return_json>
Each item must be self-contained and mutually exclusive.
Response format:
```
[
  {
    "cause": "...describe the cause",
    "fix": "...describe how to fix (do not write the code)",
    "category": "fixable_now | missing_information"
  },
  ...
]
```
Category:
- fixable_now: The target function can be corrected immediately without asking for any additional information and without relying on unsupported guesses or unstated assumptions.
  - Use `fixable_now` only if your fix relies on information that is guaranteed to be true.
  - If your fix needs some APIs, use `missing_information`.
- missing_information: The function cannot proceed because it lacks a concrete environment-specific value or required runtime value that must first be obtained via appropriate APIs.
  - A diagnosis must be labeled `missing_information` rather than `fixable_now` if its proposed fix requires discovering, verifying, searching for, or retrieving any unknown environment-specific value before the target function can be corrected.
</return_json>

USER:
Identify plausible, as many root cause(s) of the exception as possible, and provide a fix for each cause.
Here is the target function that raised an error.

```python
{{ snapshot.fn.dumps(with_docstring=False, ctx=snapshot.ctx, print_locals=True) }}
```

<expected_functionality>
You have intended the function to behave as follows:

{{ snapshot.fn.doc(fmt="markdown") }}
</expected_functionality>

<exception_message>
{{ snapshot.ctx.exc.tb.message }}
</exception_message>
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
<used_apis>
{%- for api in used_apis %}
- `{{ api["name"] }}`: {{ api["description"] }}
  - Parameters:
  {%- if api["parameters"] %}
    {%- for param in api["parameters"] %}
    - `{{ param["name"] }}` ({{ param["type"] }}, {{ 'required' if param["required"] else 'optional' }}): {{ param["description"] }}{% if not param["required"] %} Default to {{ param["default"] }}.{% endif %} 
    {%- endfor %}
  {%- else %}
    - This API does not require any parameters.
  {%- endif %}
{%- endfor %}
</used_apis>