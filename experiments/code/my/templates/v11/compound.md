USER:
Write a high-level orchestration skeleton for the function `{{ snapshot.fn.name }}`.

```python
{{ snapshot.fn.dumps(with_docstring=False, ctx=snapshot.ctx, print_locals=True) }}
```

# EXPECTED FUNCTIONALITY
{{ snapshot.fn.doc(fmt="markdown") }}

# ORCHESTRATION DISCIPLINE
This skeleton is a blueprint with helper function calls.
Decompose the function's requirements into modular, declarative subtasks, each represented by a distinct helper function call.
Once the helper functions are individually implemented in the future, the function should operate correctly as orchestrated.

Carefully adhere to R1, R2, and R3 while orchestrating. Furthermore, you MUST follow the rules below.

## FOCUS ON WHAT
Focus on what must be done and in what flow.
1. Identify distinct subtasks explicit in the expected functionality of `{{ snapshot.fn.name }}`.
2. Name the helper functions for each subtask. Helper function names must describe what must be done (the intent), not how it is done.
3. Call the helper functions to orchestrate the execution flow. When needed, use standard control flow statements (e.g., if/else, loops).

## EXPLICIT DATA FLOW
Make data flow across helper functions visible.
1. Assign before pass. Assign the return value of every helper function call to a new local variable.
2. Pass forward. Pass these new local variables as arguments to subsequent helper calls to show explicit data dependency. If a call is a "sink call" (no subsequent calls need its return value), you must still assign its return value to a local variable, and simply pass it to `print`. This explicitly means that, with the exception of print, the return value of every function call must be properly assigned to a local variable.

## DO NOT IMPLEMENT
Treat the actual implementation details as a black box.
1. Every call must be a helper function call.
2. NEVER access inner fields or properties of a return value. You do not know the data structures yet. Do NOT call any helper function (e.g., `extract_some_field`) for such field access. Instead, pass the whole object.
3. Pass the whole object. Even if a subsequent step only needs a specific piece of data, pass the entire object to the helper function to give the future implementation total freedom.