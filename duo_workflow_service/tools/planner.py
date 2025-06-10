import json
from typing import List, Optional, Type

from pydantic import BaseModel, Field

from duo_workflow_service.entities.state import Plan, Task, TaskStatus
from duo_workflow_service.tools.duo_base_tool import DuoBaseTool


def format_task_number(task_id: str) -> str:
    task_num = task_id.split("-")[-1] if "-" in task_id else task_id
    try:
        return str(int(task_num) + 1)
    except (ValueError, TypeError):
        return task_id


def format_short_task_description(
    description: str,
    word_limit: Optional[int] = None,
    char_limit: int = 100,
    suffix: str = "...",
) -> str:

    words = description.strip().split()
    shortened_description = " ".join(words[:word_limit])

    if len(shortened_description) > char_limit:
        shortened_description = shortened_description[:char_limit].rsplit(" ", 1)[0]

    return (
        f"{shortened_description}{suffix}"
        if (word_limit and len(words) > word_limit)
        or len(shortened_description) < len(description.strip())
        else shortened_description
    )


class AddNewTaskInput(BaseModel):
    description: str = Field(description="The description of the new task to add")


class AddNewTask(DuoBaseTool):
    name: str = "add_new_task"
    description: str = """Add a task to a plan for a workflow.
    A plan consists of a list of tasks and the status of each task.
    This tool adds a task to the list of tasks but should never update the status of a task."""

    args_schema: Type[BaseModel] = AddNewTaskInput

    def _run(self, description: str) -> str:
        new_task = Task(
            id=f"task-{len(self.plan['steps'])}",
            description=description,
            status=TaskStatus.NOT_STARTED,
        )
        self.plan["steps"].append(new_task)

        return f"Step added: {new_task['id']}"

    def format_display_message(self, args: AddNewTaskInput) -> str:
        return f"Add new task to the plan: {format_short_task_description(args.description, char_limit=100)}"


class RemoveTaskInput(BaseModel):
    task_id: str = Field(description="The ID of the task to remove")
    description: str = Field(description="The description of the task to remove")


class RemoveTask(DuoBaseTool):
    name: str = "remove_task"
    description: str = """Remove a task from a plan based on its ID.
    A plan consists of a list of tasks and the status of each task.
    This tool removes a task from the list of tasks."""
    args_schema: Type[BaseModel] = RemoveTaskInput

    def _run(
        self, task_id: str, description: str  # pylint: disable=unused-argument
    ) -> str:
        self.plan["steps"] = [
            step for step in self.plan["steps"] if step["id"] != task_id
        ]

        return f"Task removed: {task_id}"

    def format_display_message(self, args: RemoveTaskInput) -> str:
        short_description = format_short_task_description(
            args.description, word_limit=5, char_limit=50
        )
        return f"Remove task '{short_description}'"


class UpdateTaskDescriptionInput(BaseModel):
    task_id: str = Field(description="The ID of the task to update")
    new_description: str = Field(description="The new description for the task")


class UpdateTaskDescription(DuoBaseTool):
    name: str = "update_task_description"
    description: str = """Update the description of a task in the plan.
    A plan consists of a list of tasks and the status of each task.
    This tool updates the description of a task but should never update the status of a task."""
    args_schema: Type[BaseModel] = UpdateTaskDescriptionInput

    def _run(self, task_id: str, new_description: str) -> str:
        for step in self.plan["steps"]:
            if step["id"] == task_id:
                if new_description:
                    step["description"] = new_description
                    return f"Task updated: {task_id}"

        return f"Task not found: {task_id}"

    def format_display_message(self, args: UpdateTaskDescriptionInput) -> str:
        short_new_description = format_short_task_description(
            args.new_description, word_limit=5, char_limit=50
        )
        return f"Update description for task '{short_new_description}'"


class GetPlan(DuoBaseTool):
    name: str = "get_plan"
    description: str = """Fetch a list of tasks for a workflow.
    A plan consists of a list of tasks and the status of each task."""

    def _run(self) -> str:
        return json.dumps(self.plan["steps"])


class SetTaskStatusInput(BaseModel):
    task_id: str = Field(description="The ID of the task to update")
    status: str = Field(
        description="""The status of the task.
                        The status can be `Not Started`, `In Progress`,
                        `Completed` or `Cancelled`"""
    )
    description: str = Field(description="A description of the task for context")


class SetTaskStatus(DuoBaseTool):
    name: str = "set_task_status"
    description: str = "Set the status of a single task in the plan"
    args_schema: Type[BaseModel] = SetTaskStatusInput

    def _run(
        self,
        task_id: str,
        status: str,
        description: str,  # pylint: disable=unused-argument
    ) -> str:
        for step in self.plan["steps"]:
            if step["id"] == task_id:
                step["status"] = TaskStatus(status)
                return f"Task status set: {task_id} - {status}"

        return f"Task not found: {task_id}"

    def format_display_message(self, args: SetTaskStatusInput) -> str:
        task_description = format_short_task_description(
            args.description, word_limit=5, char_limit=50
        )
        return f"Set task '{task_description}' to '{args.status}'"


class CreatePlanInput(BaseModel):
    tasks: List[str] = Field(
        description=(
            "A list of tasks, where each task is a separate string element in the array. "
            "Do NOT provide a single multi-line string. "
            "Example: ['Check repo structure', 'Run tests', 'Fix warnings']"
        ),
    )


class CreatePlan(DuoBaseTool):
    name: str = "create_plan"
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
        # pylint: disable=unsupported-assignment-operation
        self.plan = Plan(steps=steps)

        return "Plan created"

    def format_display_message(self, args: CreatePlanInput) -> str:
        return f"Create plan with {len(args.tasks)} tasks"
