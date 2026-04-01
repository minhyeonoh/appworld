USER:
Your job is to evaluate whether the current implementation of `{{ snapshot.fn.name }}` exactly satisfies the expected functionality. If it does, you must immediately transform its return shape to preserve valuable context discovered during execution.

```python
{{ snapshot.fn.dumps(with_docstring=False, ctx=snapshot.ctx, print_locals=True) }}
```

# INITIALLY EXPECTED FUNCTIONALITY
{{ snapshot.fn.doc(fmt="markdown") }}

{% if snapshot.ctx.locals -%}
# PRINTED LOCAL VARIABLES
{{ snapshot.ctx.dumps_locals(snapshot.fn) }}

{% endif -%}
# PHASE 1: EVALUATION RULES
Evaluate if the current implementation matches the required functionality. Your evaluation result must be either "YES" (it matches) or "NO" (it does not), based on the following criteria:
1. **FOCUS ON THE "WHAT":** Verify that the implementation exactly fulfills the explicit requirements (e.g., return values, data types, and observable side effects).
2. **DO NOT PENALIZE THE "HOW":** Do NOT penalize the specific algorithmic approach, code style, or logic used, unless a specific method is explicitly mandated.
3. **TOLERANCE for UNDERSPECIFICATION:** If the expected functionality is silent about specific edge cases, accept ANY behavior that does not contradict the explicitly stated requirements. Do not invent unstated rules.

# PHASE 2: TRANSFORMATION RULES (IF EVALUATION IS "YES")
If your evaluation is "yes", your core objective is to rescue useful by-products. The initially expected functionality was forced to rely on limited context, making it narrower than what the helper can naturally observe. To prevent context loss, transform the return shape to catch evaporating data for the upstream orchestrator.

Rewrite the helper so that it returns an object of the form:
```python
{
  "primary": ...,
  "extras": {
    ...
  }
}
```
where:
- `primary` is the helper’s main result. If the main result is already a structured collection (e.g., a list of items, a dictionary-like record, or another structured object), you are encouraged to enrich its individual elements with newly discovered information that may be useful for upstream callers later. However, even after enriched, the transformed function must still provide the result required by the original expected functionality.
- `extras` contains additional information (e.g., raw, observed stuffs) that was revealed during execution but is not part of the main result. If `primary` is a structured collection, use this extras field to save overarching global information that applies to the entire elementes rather than to individual elements: avoid duplicating per-item information there.

## TRANSFORMATION DISCIPLINE
1. **PRESERVE BEHAVIOR WITH ENRICHMENT (BACKWARD COMPATIBILITY):** The transformed function's return value must include the result required by the original expected functionality in the `primary` field. If the result is a structured collection, you are encouraged to enrich its individual elements with additional information, as long as the enriched representatio still contains what the expected functionality initially requires.
2. **RESCUE GLOBAL CONTEXT:** Save overarching by-products in `extras`. If `primary` is a structured collection, `extras` should contain global information that applies to the collection as a whole. Do NOT duplicate per-item information in `extras`.
3. **AVOID OVERSTUFF:** Only rescue information that is already accessible within the function's existing successful execution trace and makes the result more useful for upstream callers. Do NOT try to obtain invisible information with heavy new computations. Do NOT try to save unrelated, temporary, or awkward internal variables.
4. **KEEP THE TRANSFORMATION LOCAL:**
	- You MUST NOT alter the function's input parameters. 
	- Assume upstream callers will be adapted separately later only to handle the new return shape, so do not worry about how they will unpack it.
	- You are allowed to modify the current implementation to rescue more information ONLY IF that information is already visible in the function's existing successful execution path. If the function already accesses a rich data source but currently discards certain information, you may adjust the implementation to retain and surface those fields. However,
		- Do NOT introduce new API calls.
		- Do NOT change/remove existing API calls.

{% if include_response_format | default(true) -%}
# RESPONSE FORMAT
Depending on your evaluation in PHASE 1, output your response in one of the following two STRICT formats:

## IF EVALUATION IS "NO"
Output ONLY a JSON block containing your evaluation and rationale. Do NOT output any code.
```json
{
  "rationale": "explain what is missing or incorrect",
  "evaluation": "no"
}
```

## IF EVALUATION IS "YES"
Do NOT output JSON. Output ONLY the fully transformed Python implementation of `{{ snapshot.fn.name }}` wrapped in a python code block.

```python
{{ snapshot.fn.header() }}:
  # Your transformed implementation returning {"primary": ..., "extras": ...}
  ...
```

{% endif -%}