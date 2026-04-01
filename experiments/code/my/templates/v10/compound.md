SYSTEM:
Your job is to write a high-level orchestration skeleton in the body of a target function. 

You must decompose the function's requirements into modular, declarative subtasks, each represented by a distinct helper function call. This skeleton serves as a blueprint for future implementation: once the helper functions are individually implemented in the future, the function should operate correctly as orchestrated.

The skeleton must focus on what must be done and in what flow.
1. Identify distinct subtasks explicit in the requirements.
	- Call a helper functions for each of the subtasks.
	- Use control flow when needed to orchestrate those helper function calls.
2. Make data flow visible.
	- Assign the return value of every helper function call to a new local variable.
	- Pass that new variable to subsequent helper calls to make data flow explicit and traceable.
		- Do not pass the global variables, since helper functions can access them directly.
		- If the call is a "sink call" (i.e., there are no subsequent calls that require its return value), simply assign the return value to a local variable and pass it to `print`. This means that, except `print`, return value of any function call should be assinged to local variable properly.

The skeleton must be assumption-free.
1. Do not introduce extra behavior (e.g., logging, data validation, or exception handling) that is not explicitly required.
2. Do not assume anything.
	- Every call in the skeleton must be a helper function call.
	- Helper function names must describe what must be done (intents of subtasks), not how it is done.
  - NEVER access inner fields or properties of a return value of any helper function call.
    - Currently, you don't know what is possible.
		- Even if you need a specific piece of data from an object, pass the entire object to a helper function to give a helper function more freedom for implementation

USER:
Write a skeleton for the function `{{ snapshot.fn.name }}`.

```python
{{ snapshot.fn.dumps(with_docstring=False, ctx=snapshot.ctx, print_locals=True) }}
```

<expected_functionality>
{{ snapshot.fn.doc(fmt="markdown") }}
</expected_functionality>

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