"""Dashboard backend — writes agent state to files as it runs.

Zero UI dependencies.  The agent calls DashboardLog methods at key points,
and the log writes jsonl files that any frontend can read.

Directory layout (under ``log_dir``):
  t1.jsonl                  — SubAgent lifecycle events
  t2/{subagent_name}.jsonl  — full refinement-tree snapshot (overwritten each time)
  messages/{node_id}.jsonl  — LLM messages per refinement node
  state.json                — current active subagent / node (single file, overwritten)
"""

from __future__ import annotations

import json
import os
from typing import Any

_next_node_id = 0
_node_ids: dict[int, int] = {}  # id(RefinementNode) -> stable int id


def _node_id(node) -> int:
    global _next_node_id
    key = id(node)
    if key not in _node_ids:
        _next_node_id += 1
        _node_ids[key] = _next_node_id
    return _node_ids[key]


def _action_label(action) -> str:
    if action is None:
        return "Snapshot"
    name = action.__class__.__name__
    if hasattr(action, "app_name") and hasattr(action, "api_name"):
        return f"{name}({action.app_name}.{action.api_name})"
    return name


def _node_status(node) -> str:
    if node.result is None:
        return "skip"
    if not hasattr(node.result, "fn"):
        return "PENDING"
    return "resolved"


def _serialize_tree(node) -> dict:
    action = _action_label(node.action)
    status = "root" if node.action is None else _node_status(node)
    return {
        "id": _node_id(node),
        "label": f"{action} [{status}]" if status not in ("resolved",) else f"{action} +",
        "action": action,
        "status": status,
        "children": [_serialize_tree(c) for c in node.children],
    }


class DashboardLog:
    """Writes agent state to files.  Create one per task run."""

    def __init__(self, log_dir: str):
        self.log_dir = log_dir
        os.makedirs(log_dir, exist_ok=True)
        os.makedirs(os.path.join(log_dir, "t2"), exist_ok=True)
        os.makedirs(os.path.join(log_dir, "messages"), exist_ok=True)
        # Clear previous state
        for f in ("t1.jsonl", "state.json"):
            path = os.path.join(log_dir, f)
            if os.path.exists(path):
                os.remove(path)
        self._active_node_id: int | None = None

    def _append(self, filename: str, data: dict):
        path = os.path.join(self.log_dir, filename)
        with open(path, "a") as f:
            f.write(json.dumps(data) + "\n")

    def _write_json(self, filename: str, data: Any):
        path = os.path.join(self.log_dir, filename)
        with open(path, "w") as f:
            json.dump(data, f)

    # -- SubAgent lifecycle --

    def subagent_created(self, subagent):
        self._append("t1.jsonl", {
            "event": "created",
            "name": subagent.name,
            "parent": subagent.parent.name if subagent.parent else None,
        })

    def subagent_solving(self, subagent):
        self._append("t1.jsonl", {"event": "solving", "name": subagent.name})
        self._write_state(active_subagent=subagent.name)

    def subagent_solved(self, subagent):
        self._append("t1.jsonl", {"event": "solved", "name": subagent.name})

    # -- Refinement tree --

    def refinement_tree(self, subagent, root):
        """Write a full snapshot of the refinement tree."""
        self._write_json(f"t2/{subagent.name}.json", _serialize_tree(root))

    def node_exploring(self, subagent, node):
        self._active_node_id = _node_id(node)
        self._write_state(active_subagent=subagent.name, active_node=self._active_node_id)

    # -- Messages --

    def message(self, role: str, content: str, reasoning_content: str | None = None):
        if self._active_node_id is not None:
            self._append(f"messages/{self._active_node_id}.jsonl", {
                "role": role,
                "content": content,
                "reasoning": reasoning_content,
            })

    # -- State --

    def _write_state(self, active_subagent: str | None = None, active_node: int | None = None):
        self._write_json("state.json", {
            "active_subagent": active_subagent,
            "active_node": active_node or self._active_node_id,
        })
