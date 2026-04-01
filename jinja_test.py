
import os
from appworld_agents.code.my.message import render_messages_template

msgs = render_messages_template(
  "templates/v11/test.md",
)

for msg in msgs:
  print(msg.role.upper())

lines: list[str] = []
for i, msg in enumerate(msgs):
    role = msg.role
    content = msg.content
    lines.append("=" * 80)
    header = f"MESSAGE {i} | role: {role}"
    lines.append(header)
    lines.append("=" * 80)
    if content:
        lines.append(str(content))
    lines.append("")
dump_path = os.path.join("test_output.md")
with open(dump_path, "w") as f:
    f.write("\n".join(lines))
