from typing import Any, cast

from appworld.task import Task, load_task_ids
from appworld_agents.code.my.agent import Agent


def extract_dataset_name(runner_config: dict[str, Any]) -> str:
    if "dataset" not in runner_config:
        raise Exception("Dataset name not found in the runner config.")
    return cast(str, runner_config["dataset"])


def _build_agent_and_tasks(
    experiment_name: str,
    runner_config: dict[str, Any],
    task_id: str | None = None,
):
    agent_config = runner_config.pop("agent")
    dataset_name = runner_config.pop("dataset")
    if runner_config:
        raise Exception(f"Unexpected keys in the runner config: {runner_config}")
    if task_id:
        task_ids = [task_id]
    else:
        task_ids = load_task_ids(dataset_name)
    for task_id in task_ids:
        Task.load(task_id=task_id)
    agent = Agent.from_dict(agent_config)
    return agent, task_ids


def run_experiment(
    experiment_name: str,
    runner_config: dict[str, Any],
    task_id: str | None = None,
    num_processes: int = 1,
    process_index: int = 0,
) -> None:
    agent, task_ids = _build_agent_and_tasks(experiment_name, runner_config, task_id)
    agent.solve_tasks(
        task_ids=task_ids,
        experiment_name=experiment_name,
        num_processes=num_processes,
        process_index=process_index,
    )


def run_experiment_dashboard(
    experiment_name: str,
    runner_config: dict[str, Any],
    task_id: str | None = None,
    port: int = 8080,
) -> None:
    """Run agent with dashboard logging, launch NiceGUI web UI."""
    import os
    import subprocess
    import sys
    import threading
    import webbrowser

    agent, task_ids = _build_agent_and_tasks(experiment_name, runner_config, task_id)

    # Dashboard log directory
    log_dir = os.path.join("my", "dashboard_log")

    # Wire dashboard logging into the agent
    from experiments.code.my.dashboard import DashboardLog
    agent._dashboard_log = DashboardLog(log_dir)

    # Launch NiceGUI frontend in a subprocess
    frontend_proc = subprocess.Popen(
        [sys.executable, "-m", "experiments.code.my.dashboard.frontend", log_dir, str(port)],
    )

    # Open browser after a short delay
    threading.Timer(2.0, lambda: webbrowser.open(f"http://localhost:{port}")).start()

    try:
        agent.solve_tasks(
            task_ids=task_ids,
            experiment_name=experiment_name,
            num_processes=1,
            process_index=0,
        )
    finally:
        print(f"\nAgent finished. Dashboard still running at http://localhost:{port}")
        print("Press Ctrl+C to stop.")
        try:
            frontend_proc.wait()
        except KeyboardInterrupt:
            frontend_proc.terminate()
