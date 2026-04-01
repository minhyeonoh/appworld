# INTERACTION WITH MY ENVIRONMENT
Tasks are carried out by remotely controlling my multi-app mobile environment.
The only way to remotely control my environment is using app-specific high-level API requests.

## APPS IN MY ENVIRONMENT
The environment contains the following apps:
{% for app in app_descriptions -%}
- `{{ app["name"] }}`: {{ app["description"] }}
{% endfor %}
## MY ENVIRONMENT VS YOUR ENVIRONMENT
My environment and your own local machine where the program runs are PHYSICALLY SEPARATED.
As a result:
1. Whenever the program needs to access my environment—such as reading data, writing data, or triggering actions inside an app—it must do so through the APIs exposed by the relevant apps.
2. Any operation performed locally on your machine, unless it invokes an app API, has no effect on my environment. In particular, file I/O through `os`, `open`, or similar libraries only accesses your machine's local file system, not my mobile environment.