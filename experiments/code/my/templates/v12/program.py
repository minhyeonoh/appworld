{% for defn in defns %}
{%- if 'FunctionNotFound' not in defn %}
@show_locals_on_exception(type_hints=False)
{%- endif %}
{{ defn }}
{% endfor %}

observed_callee_history = defaultdict(list)

try:
  main()
except (FunctionNotFound, NotImplementedError, ReturnAsException, HelperReturnAsException):
  pass