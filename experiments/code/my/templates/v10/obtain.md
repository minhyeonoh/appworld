SYSTEM:
Your job is to patch a target function by obtain missing information to resolve an error in a program you previously wrote to solve my problem.
You will be provided with a feedback that describes the missing information.

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
You have no direct access to my mobile environment's internal OS, shell, or any low-level UI manipulation inside apps.
</interaction_with_my_environment>

<requirements_and_constraints>
1. Your job is to fix (patch) a target function according to provided debugging feedback (cause of exception and corresponding fix).
2. Introduce a helper function whose purpose is to obtain the missing information that the feedback requires. Before using the return value of this helper function call (e.g., passing the value to other function), assign it to a new local variable.
3. Do NOT implement the helper function. The system will implement it later.
4. Do NOT write placeholder for the helper function definition inside the target function.
5. Do NOT add silent fallbacks, such as default returns (e.g., `return None`, `return False`) and generic exceptions (e.g., `raise ValueError(...)`). For an unexpected execution path, use `raise AssertionError()` with a descriptive message explaining the situation. This should never happen.
6. Do NOT blindly assume/guess/invent any APIs. You are provided with only app information, not app-specific APIs.
</requirements_and_constraints>

USER:
Patch `{{ snapshot.fn.name }}`.

```python
{{ snapshot.fn.dumps(with_docstring=False, ctx=snapshot.ctx, print_locals=True) }}
```

<feedback>
{{ feedback }}
</feedback>

<expected_functionality>
You have intended the function to behave as follows:

{{ snapshot.fn.doc(fmt="markdown") }}
</expected_functionality>

<exception_message>
{{ snapshot.ctx.exc.tb.message }}
</exception_message>

<global_variables>
```python
{{ global_variables }}
```
</global_variables>
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