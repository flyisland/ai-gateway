import json
from typing import Any, List, Optional, Type

from langchain_core.messages import ToolMessage
from langgraph.types import Command as LangGraphCommand
from pydantic import BaseModel, Field

from duo_workflow_service.agent_platform.experimental.state import get_vars_from_state, FlowState, IOKeyTemplate
from duo_workflow_service.entities.state import Plan, Task, TaskStatus
from duo_workflow_service.tools.duo_base_tool import DuoBaseTool


class CreatePlanInput(BaseModel):
    tasks: List[str] = Field(
        description=(
            "A list of tasks, where each task is a separate string element in the array. "
            "Do NOT provide a single multi-line string. "
            "Example: ['Check repo structure', 'Run tests', 'Fix warnings']"
        ),
    )

class CreatePlanV2(DuoBaseTool):
    name: str = "create_plan_v2"
    description: str = """Create a list of tasks for the plan.
    The tasks you provide here will set the tasks in the current plan.
    Please provide all the tasks that you want to show to the user.
    Tasks should be formatted in an array where each task is a string.
    """

    args_schema: Type[BaseModel] = CreatePlanInput

    def _run(self, tasks: List[str]) -> str:
        steps: List[Task] = []
        for i, task_description in enumerate(tasks):
            steps.append(
                Task(
                    id=f"task-{i}",
                    description=task_description,
                    status=TaskStatus.NOT_STARTED,
                )
            )

        return json.dumps({"plan": steps})

    def format_display_message(
        self, args: CreatePlanInput, _tool_response: Any = None
    ) -> str:
        return f"Create plan with {len(args.tasks)} tasks"
