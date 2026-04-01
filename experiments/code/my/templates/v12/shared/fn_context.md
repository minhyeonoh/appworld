```python
{{ snapshot.fn.dumps(with_docstring=False, ctx=snapshot.ctx, print_locals=True) }}
```

<expected_functionality>
{{ snapshot.fn.doc(fmt="markdown") }}
</expected_functionality>
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