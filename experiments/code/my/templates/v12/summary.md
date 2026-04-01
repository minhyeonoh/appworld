USER:
Your job is to transform the return shape of `{{ snapshot.fn.name }}` so that it becomes a more information-preserving object, while preserving the `{{ snapshot.fn.name }}`'s already-correct behavioral functionality. Upstream callers will be adapted separately later.

```python
{{ snapshot.fn.dumps(with_docstring=False, ctx=snapshot.ctx, print_locals=True) }}
```

# INITIALLY EXPECTED FUNCTIONALITY
{{ snapshot.fn.doc(fmt="markdown") }}

{% if snapshot.ctx.locals -%}
# PRINTED LOCAL VARIABLES
{{ snapshot.ctx.dumps_locals(snapshot.fn) }}

{% endif -%}
# WHY WE ARE DOING THIS
The core objective of this transformation is to rescue useful by-products.

When the upstream caller originally delegated the implementation of `{{ snapshot.fn.name }}` to you, it could not foresee exactly what information would become available during the actual implementation and execution. As a result, the initially expected functionality was forced to rely only on the limited context known at that time, making the functionality narrower than what the helper can naturally observe while successfully doing its job.

If the helper `{{ snapshot.fn.name }}` only returns the possibly narrow final result, the rich and useful context discovered along the way may be lost. To prevent this context loss, you are transforming the return shape to catch that evaporating data, preserving it as valuable clues for the upstream orchestrator's future planning and reasoning.

This does NOT count as adding extra behavior.

# RESPONSE FORMAT
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

# TRANSFORMATION DISCIPLINE
1. **PRESERVE BEHAVIOR WITH ENRICHMENT (BACKWARD COMPATIBILITY):** The transformed function's return value must include the result required by the original expected functionality in the `primary` field. If the result is a structured collection, you are encouraged to enrich its individual elements with additional information, as long as the enriched representatio still contains what the expected functionality initially requires.
2. **RESCUE GLOBAL CONTEXT:** Save overarching by-products in `extras`. If `primary` is a structured collection, `extras` should contain global information that applies to the collection as a whole. Do NOT duplicate per-item information in `extras`.
3. **AVOID OVERSTUFF:** Only rescue information that is already accessible within the function's existing successful execution trace and makes the result more useful for upstream callers. Do NOT try to obtain invisible information with heavy new computations. Do NOT try to save unrelated, temporary, or awkward internal variables.
4. **KEEP THE TRANSFORMATION LOCAL:**
	- You MUST NOT alter the function's input parameters. 
	- Assume upstream callers will be adapted separately later only to handle the new return shape, so do not worry about how they will unpack it.
	- You are allowed to modify the current implementation to rescue more information ONLY IF that information is already visible in the function's existing successful execution path. If the function already accesses a rich data source but currently discards certain information, you may adjust the implementation to retain and surface those fields. However,
		- Do NOT introduce new API calls.
		- Do NOT change/remove existing API calls.
