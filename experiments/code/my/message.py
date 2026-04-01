import os
from jinja2 import Environment, FileSystemLoader, Template

from typing import cast
from pydantic import BaseModel, RootModel
from appworld_agents.code.my.parser import parse_messages

from appworld.common.io import read_file

_DIR = os.path.dirname(os.path.abspath(__file__))
_JINJA_ENV = Environment(
  loader=FileSystemLoader(_DIR),
  keep_trailing_newline=True,
)


class Msg(BaseModel, extra="allow"):
  role: str
  content: str

class Msgs(RootModel):

  root: list[Msg] = []

  def add(self, *, role, content, **kwargs):
    self.root.append(
      Msg(role=role, content=content, **kwargs)
    )

  def extend(self, messages):
    for msg in messages:
      if isinstance(msg, Msg):
        msg = msg.model_dump()
      self.add(**msg)

  def remove(self, index: int | slice):
    del self.root[index]

  def copy(self):
    return self.model_copy(deep=True)

  def __iter__(self):
    return iter(self.root)

  def __getitem__(self, index) -> Msg:
    return self.root[index]

  # def to_raw(self):
  #   return [msg.model_dump() for msg in self.messages]


def render_template(path, **params):
  if os.path.isabs(path):
    # Fallback for absolute paths: use standalone Template (no {% include %} support)
    template = Template(cast(str, read_file(path.replace("/", os.sep))).strip())
  else:
    # Use Environment-based loader so {% include %} resolves relative to _DIR
    template = _JINJA_ENV.get_template(path.replace(os.sep, "/"))
  return template.render(params).strip()


def render_messages_template(path, **params):
  messages = Msgs()
  for header, content in parse_messages(render_template(path, **params)):
    role = {
      "SYSTEM:": "system", 
      "USER:": "user", 
      "ASSISTANT:": "assistant", 
    }[header]
    messages.add(role=role, content=content)
  return messages