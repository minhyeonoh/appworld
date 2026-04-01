
from appworld.evaluator import evaluate_task
from appworld import AppWorld
from appworld_agents.code.common.logger import Logger

logger = Logger(color=True, verbose=True)

task_id = "6b6ca61_1"
experiment_name = "domyself"

logger.initialize(
    experiment_name=experiment_name,
    num_tasks=1,
    num_processes=1,
    process_index=0,
)
with AppWorld.initializer(
    update_defaults=True, experiment_name=experiment_name, raise_on_failure=False,
):
    experiment_name = experiment_name or AppWorld.init_defaults.experiment_name
    with AppWorld(task_id=task_id) as world:
        logger.start_task(world)
        with open("domyself_code.txt") as fin:
            execution_output_content = world.execute(fin.read())
        logger.show_message(
            role="environment",
            content=execution_output_content,
            step_number=0,
        )

evaluate_task(task_id=task_id, experiment_name=experiment_name)
