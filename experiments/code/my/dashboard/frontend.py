"""Dashboard frontend — NiceGUI web app that watches agent log files.

Zero agent dependencies.  Reads the file layout written by DashboardLog:
  t1.jsonl, t2/{name}.json, messages/{node_id}.jsonl, state.json

Run standalone:  python -m experiments.code.my.dashboard.frontend <log_dir>
Then open:       http://localhost:8080
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from nicegui import ui, app


class Dashboard:

    def __init__(self, log_dir: str):
        self.log_dir = Path(log_dir)
        # T1 state
        self._t1_data: list[dict] = []   # nicegui tree nodes
        self._t1_lines_read = 0
        self._t1_status: dict[str, str] = {}
        # T2 state
        self._selected_subagent: str | None = None
        self._t2_mtime: float = 0
        # Messages
        self._active_node_id: int | None = None
        self._viewed_node_id: int | None = None
        self._msg_lines_read: dict[int, int] = {}
        # State
        self._state_mtime: float = 0
        # UI references (set in build())
        self.t1_tree: ui.tree = None
        self.t2_tree: ui.tree = None
        self.msg_log: ui.log = None
        self.status_label: ui.label = None

    def build(self):
        """Construct the UI. Call once inside a @ui.page."""
        ui.add_head_html("""
        <style>
            .q-tree__node--selected { background: rgba(25, 118, 210, 0.15) !important; }
            .msg-log { font-family: monospace; font-size: 13px; }
        </style>
        """)

        with ui.row().classes("w-full h-screen"):
            # Left: T1 tree
            with ui.card().classes("w-1/4 h-full overflow-auto"):
                ui.label("SubAgents (T1)").classes("text-lg font-bold")
                self.t1_tree = ui.tree(
                    [], label_key="label", on_select=self._on_t1_select
                ).props("default-expand-all dense")

            # Middle: T2 tree
            with ui.card().classes("w-1/3 h-full overflow-auto"):
                ui.label("Refinements (T2)").classes("text-lg font-bold")
                self.t2_tree = ui.tree(
                    [], label_key="label", on_select=self._on_t2_select
                ).props("default-expand-all dense")

            # Right: Messages
            with ui.card().classes("w-5/12 h-full"):
                ui.label("Messages").classes("text-lg font-bold")
                self.msg_log = ui.log(max_lines=500).classes("msg-log w-full h-full")

        # Status bar
        with ui.row().classes("w-full items-center px-4 py-1 bg-gray-100"):
            self.status_label = ui.label("Watching...").classes("text-sm text-gray-600")
            ui.space()
            ui.button("Refresh", on_click=self._poll, icon="refresh").props("flat dense")

        # Start polling
        ui.timer(0.5, self._poll)

    # -- Polling --

    def _poll(self):
        self._poll_state()
        self._poll_t1()
        self._poll_t2()
        self._poll_messages()

    def _poll_state(self):
        path = self.log_dir / "state.json"
        if not path.exists():
            return
        try:
            mtime = path.stat().st_mtime
            if mtime <= self._state_mtime:
                return
            self._state_mtime = mtime
            state = json.loads(path.read_text())
            new_sa = state.get("active_subagent")
            new_node = state.get("active_node")
            if new_sa != self._selected_subagent:
                self._selected_subagent = new_sa
                self._t2_mtime = 0
            if new_node != self._active_node_id:
                self._active_node_id = new_node
                self._viewed_node_id = new_node
                self._t2_mtime = 0
                self._show_messages_for(new_node)
            self.status_label.set_text(f"Active: {new_sa or '?'} / node {new_node or '?'}")
        except (json.JSONDecodeError, OSError):
            pass

    def _poll_t1(self):
        path = self.log_dir / "t1.jsonl"
        if not path.exists():
            return
        try:
            lines = path.read_text().splitlines()
            new_lines = lines[self._t1_lines_read:]
            if not new_lines:
                return
            self._t1_lines_read = len(lines)
            for line in new_lines:
                evt = json.loads(line)
                name = evt["name"]
                if evt["event"] == "created":
                    parent = evt.get("parent")
                    node = {"id": name, "label": f"  {name}", "children": []}
                    self._t1_status[name] = "pending"
                    if parent:
                        self._insert_t1_child(self._t1_data, parent, node)
                    else:
                        self._t1_data.append(node)
                elif evt["event"] == "solving":
                    self._update_t1_labels(self._t1_data, name, "solving")
                elif evt["event"] == "solved":
                    self._update_t1_labels(self._t1_data, name, "solved")
            self.t1_tree.props["nodes"] = self._t1_data
            self.t1_tree.update()
        except (json.JSONDecodeError, OSError):
            pass

    def _insert_t1_child(self, nodes, parent_id, child):
        for n in nodes:
            if n["id"] == parent_id:
                n.setdefault("children", []).append(child)
                return True
            if self._insert_t1_child(n.get("children", []), parent_id, child):
                return True
        return False

    def _update_t1_labels(self, nodes, name, status):
        for n in nodes:
            if n["id"] == name:
                prefix = {"pending": "  ", "solving": "> ", "solved": "+ "}.get(status, "  ")
                n["label"] = f"{prefix}{name}"
                self._t1_status[name] = status
                return True
            if self._update_t1_labels(n.get("children", []), name, status):
                return True
        return False

    def _poll_t2(self):
        if not self._selected_subagent:
            return
        path = self.log_dir / "t2" / f"{self._selected_subagent}.json"
        if not path.exists():
            return
        try:
            mtime = path.stat().st_mtime
            if mtime <= self._t2_mtime:
                return
            self._t2_mtime = mtime
            tree = json.loads(path.read_text())
            self._mark_active(tree)
            self.t2_tree.props["nodes"] = [tree]
            self.t2_tree.update()
        except (json.JSONDecodeError, OSError):
            pass

    def _mark_active(self, node):
        """Update label to show active indicator."""
        is_active = node["id"] == self._active_node_id
        action = node.get("action", node.get("label", "?"))
        status = node.get("status", "?")
        if is_active:
            node["label"] = f"▶ {action} [{status}]"
        elif status == "resolved":
            node["label"] = f"✓ {action}"
        elif status == "skip":
            node["label"] = f"✗ {action}"
        elif status == "root":
            node["label"] = action
        else:
            node["label"] = f"  {action} [{status}]"
        for child in node.get("children", []):
            self._mark_active(child)

    def _poll_messages(self):
        nid = self._viewed_node_id
        if nid is None:
            return
        path = self.log_dir / "messages" / f"{nid}.jsonl"
        if not path.exists():
            return
        try:
            lines = path.read_text().splitlines()
            prev = self._msg_lines_read.get(nid, 0)
            new_lines = lines[prev:]
            if not new_lines:
                return
            self._msg_lines_read[nid] = len(lines)
            for line in new_lines:
                msg = json.loads(line)
                self._push_message(msg)
        except (json.JSONDecodeError, OSError):
            pass

    def _show_messages_for(self, node_id: int | None):
        self.msg_log.clear()
        self._viewed_node_id = node_id
        if node_id is None:
            return
        path = self.log_dir / "messages" / f"{node_id}.jsonl"
        if not path.exists():
            return
        try:
            lines = path.read_text().splitlines()
            self._msg_lines_read[node_id] = len(lines)
            for line in lines:
                msg = json.loads(line)
                self._push_message(msg)
        except (json.JSONDecodeError, OSError):
            pass

    def _push_message(self, msg: dict):
        reasoning = msg.get("reasoning")
        if reasoning:
            trunc = reasoning[:200] + ("..." if len(reasoning) > 200 else "")
            self.msg_log.push(f"[thinking] {trunc}")
        self.msg_log.push(f"[{msg['role']}]")
        self.msg_log.push(msg.get("content") or "(empty)")
        self.msg_log.push("---")

    # -- Tree selection callbacks --

    def _on_t1_select(self, e):
        name = e.value
        if name and name in self._t1_status:
            self._selected_subagent = name
            self._t2_mtime = 0
            self._poll_t2()
            self.msg_log.clear()

    def _on_t2_select(self, e):
        node_id = e.value
        if node_id is not None:
            try:
                node_id = int(node_id)
            except (ValueError, TypeError):
                return
            self._show_messages_for(node_id)


@ui.page("/")
def index():
    log_dir = app.storage.general.get("log_dir", "my/dashboard_log")
    dashboard = Dashboard(log_dir)
    dashboard.build()


def main(log_dir: str = "my/dashboard_log", port: int = 8080):
    app.storage.general["log_dir"] = log_dir
    ui.run(port=port, title="PeTER Dashboard", reload=False)


if __name__ == "__main__":
    log_dir = sys.argv[1] if len(sys.argv) > 1 else "my/dashboard_log"
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 8080
    main(log_dir=log_dir, port=port)
