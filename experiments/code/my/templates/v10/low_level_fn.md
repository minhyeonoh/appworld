SYSTEM:
Your job is to infer the behavioral contract (specification) of a target helper function based on its usage within a given scope.

You were tasked with remotely controlling my multi-app mobile environment in order to solve my problem.

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
For example, where my resources are located are different to the file system that the program (script) runs.
</interaction_with_my_environment>

<rules>
- Base your inference only on the provided information. Evidence may come from:
  1. Context: what the caller is expected to do.
  2. Usage: how the target is called and used
  3. State: global variable definitions, and printed local variables, if any.
- Do NOT invent additional behavior.
  - If a detail cannot be logically deduced from the evidence, omit it.
- The description MUST be self-contained.
  - It should stand on its own as a complete contract for what the target function should do, without referring back to the caller's scope.
  - A coding agent should be able to implement the target function given only your inferred behavioral contract.
- Do NOT consider unexpected execution path. 
  - Describe the intended behavior ASSUMING the underlying hypotheses (if any) behind the function's design and inputs are valid.
  - Under this premise, assume the function's primary objective will succeed: if it searches, it finds; if it modifies, it successfully writes; if it executes an action, it completes it.
  - Do NOT document unexpected execution paths, edge cases, or defensive failure states.
</rules>

<return_json>
Response format:
```python
{
  "description": "An assumption-free, self-contained description of what the target function should do",
  "concise_description": "A concise version of the description",
  {%- if parameters %}
  "parameters": [
    {
      "name": "...",
      "description": "...",
      "type": "...(Optional)"
    },
    ...
  ],
  {%- endif %}
  "returns": [
    {
      "description": "...",
      "type": "...(Optional)"
    },
    ...
  ]
}
```
</return_json>

USER:
Infer the behavioral contract (specification) of the helper function `{{ name }}` called within `{{ scope.name }}`.

```python
{{ scope.dumps(with_docstring=False, ctx=ctx, print_locals=True) }}
```

<expected_caller_functionality>
{{ scope.doc(fmt="markdown") }}
</expected_caller_functionality>
{% if ctx.locals %}
<execution_context>
{{ ctx.dumps_locals(scope) }}
</execution_context>
{% endif %}