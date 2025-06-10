import pytest

from duo_workflow_service.entities.state import Plan, Task


@pytest.fixture
def plan_steps() -> list[Task]:
    return []


@pytest.fixture
def plan(plan_steps: list[Task]) -> Plan:
    return Plan(steps=plan_steps)
