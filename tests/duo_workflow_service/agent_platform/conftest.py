from unittest.mock import patch

import pytest

from duo_workflow_service.agent_platform.experimental.components import (
    ComponentRegistry,
)


@pytest.fixture
def component_registry():
    # Mock component registry 'instance()' to always return a fresh object instead of the singleton
    with patch(
        "duo_workflow_service.agent_platform.experimental.components.ComponentRegistry.instance"
    ) as mock:
        mock.return_value = ComponentRegistry(force_new=True)
        yield mock
