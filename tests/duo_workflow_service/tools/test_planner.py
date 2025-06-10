import json

import pytest

from duo_workflow_service.entities.state import Plan, Task, TaskStatus
from duo_workflow_service.tools.planner import (
    AddNewTask,
    AddNewTaskInput,
    CreatePlan,
    CreatePlanInput,
    GetPlan,
    RemoveTask,
    RemoveTaskInput,
    SetTaskStatus,
    SetTaskStatusInput,
    UpdateTaskDescription,
    UpdateTaskDescriptionInput,
    format_task_number,
)


@pytest.fixture
def plan_steps() -> list[Task]:
    return [
        {"id": "task-0", "description": "Task 1", "status": TaskStatus.NOT_STARTED},
        {"id": "task-1", "description": "Task 2", "status": TaskStatus.IN_PROGRESS},
    ]


def test_get_plan(plan: Plan, plan_steps: list[Task]):
    tool = GetPlan()
    tool.plan = plan
    assert tool._run() == json.dumps(plan_steps)


@pytest.mark.parametrize(
    "task_id, status, expected_result",
    [
        ("task-0", "In Progress", "Task status set: task-0 - In Progress"),
        ("task-1", "Completed", "Task status set: task-1 - Completed"),
    ],
)
def test_set_task_status(task_id: str, status: str, expected_result: str, plan: Plan):
    tool = SetTaskStatus()
    tool.plan = plan
    result = tool._run(task_id=task_id, status=status, description="")

    task = next(step for step in tool.plan["steps"] if step["id"] == task_id)
    assert task["status"] == status
    assert result == expected_result


def test_set_task_status_missing_task(plan: Plan):
    tool = SetTaskStatus()
    tool.plan = plan
    result = tool._run(task_id="task-2", status="In Progress", description="")
    assert result == "Task not found: task-2"


def test_add_new_task(plan: Plan):
    tool = AddNewTask()
    tool.plan = plan
    description = "Create new feature"

    result = tool._run(description=description)

    assert result == "Step added: task-2"
    assert tool.plan["steps"][-1] == {
        "id": "task-2",
        "description": description,
        "status": TaskStatus.NOT_STARTED,
    }


def test_add_new_task_format_display_message():
    tool = AddNewTask()

    input_data = AddNewTaskInput(description="Create new feature")

    message = tool.format_display_message(input_data)

    expected_message = "Add new task to the plan: Create new feature"
    assert message == expected_message


def test_remove_task(plan: Plan):
    tool = RemoveTask()
    tool.plan = plan

    result = tool._run(task_id="task-0", description="Task 1")

    assert result == "Task removed: task-0"
    assert tool.plan["steps"] == [
        {"id": "task-1", "description": "Task 2", "status": TaskStatus.IN_PROGRESS},
    ]


def test_remove_task_format_display_message():
    tool = RemoveTask()

    input_data = RemoveTaskInput(task_id="task-1", description="Task 1")

    message = tool.format_display_message(input_data)

    expected_message = "Remove task 'Task 1'"
    assert message == expected_message


def test_update_task_description(plan: Plan):
    tool = UpdateTaskDescription()
    tool.plan = plan
    task_id = "task-1"
    new_description = "Update project documentation"

    result = tool._run(task_id=task_id, new_description=new_description)

    assert result == f"Task updated: {task_id}"

    task = next(step for step in tool.plan["steps"] if step["id"] == task_id)
    assert task["description"] == "Update project documentation"


def test_update_task_description_format_display_message():
    tool = UpdateTaskDescription()

    input_data = UpdateTaskDescriptionInput(
        task_id="task-1", new_description="Update project documentation"
    )

    message = tool.format_display_message(input_data)

    expected_message = "Update description for task 'Update project documentation'"
    assert message == expected_message


@pytest.mark.parametrize(
    "task_id, status, description, expected_result",
    [
        (
            "task-1",
            "In Progress",
            "This is a test task",
            "Set task 'This is a test task' to 'In Progress'",
        ),
        (
            "task-2",
            "In Progress",
            "Thisisatestwithalongcharacterinputtomakesureitsshortened",
            "Set task 'Thisisatestwithalongcharacterinputtomakesureitssho...' to 'In Progress'",
        ),
        (
            "task-3",
            "Not Started",
            "Supercalifragilisticexpialidocious to test a long first word",
            "Set task 'Supercalifragilisticexpialidocious to test a long...' to 'Not Started'",
        ),
        (
            "task-4",
            "Completed",
            "This is a very long task description that exceeds both the word and character limits significantly",
            "Set task 'This is a very long...' to 'Completed'",
        ),
        (
            "task-5",
            "Cancelled",
            "Supercalifragilisticexpialidocious antidisestablishmentarianism",
            "Set task 'Supercalifragilisticexpialidocious...' to 'Cancelled'",
        ),
    ],
)
def test_set_task_status_format_display_message(
    task_id, status, description, expected_result
):
    tool = SetTaskStatus()

    input_data = SetTaskStatusInput(
        task_id=task_id,
        status=status,
        description=description,
    )

    message = tool.format_display_message(input_data)
    assert message == expected_result


def test_create_plan(plan: Plan):
    tool = CreatePlan()
    tool.plan = plan
    tasks = ["Task 1", "Task 2", "Task 3"]
    result = tool._run(tasks=tasks)
    assert tool.plan == Plan(
        steps=[
            Task(id="task-0", description="Task 1", status=TaskStatus.NOT_STARTED),
            Task(id="task-1", description="Task 2", status=TaskStatus.NOT_STARTED),
            Task(id="task-2", description="Task 3", status=TaskStatus.NOT_STARTED),
        ]
    )
    assert result == "Plan created"


def test_create_plan_format_display_message():
    create_plan = CreatePlan()
    tasks = ["Task 1", "Task 2", "Task 3"]
    input_data = CreatePlanInput(tasks=tasks)

    message = create_plan.format_display_message(input_data)
    assert message == "Create plan with 3 tasks"


@pytest.mark.parametrize(
    "input_id, expected_output",
    [
        ("0", "1"),
        ("1", "2"),
        ("5", "6"),
        ("10", "11"),
        ("task-0", "1"),
        ("task-1", "2"),
        ("task-5", "6"),
        ("task-10", "11"),
        ("abc", "abc"),  # Non-numeric strings should remain unchanged
        ("task-abc", "task-abc"),  # Task ID with non-numeric part
        ("00", "1"),
        ("task-00", "1"),
    ],
)
def testformat_task_number(input_id, expected_output):
    assert format_task_number(input_id) == expected_output
