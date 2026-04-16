"""Test suite for Flow builder supervisor wiring integration."""

# pylint: disable=file-naming-for-tests

from unittest.mock import Mock, patch

import pytest

from duo_workflow_service.agent_platform.experimental.components.base import (
    BaseComponent,
)
from duo_workflow_service.agent_platform.experimental.components.supervisor.component import (
    extract_subagent_names,
)
from duo_workflow_service.agent_platform.experimental.flows.base import Flow
from duo_workflow_service.agent_platform.experimental.flows.flow_config import (
    FlowConfig,
    FlowConfigMetadata,
)


class TestFlowBuilderSupervisorWiring:
    """Tests for Flow builder deferred construction and validation of supervisors."""

    def _make_flow(self, config: FlowConfig) -> Flow:
        """Create a Flow instance with the given config (bypassing __init__)."""
        flow = object.__new__(Flow)
        flow._config = config
        return flow

    def test_has_unresolved_dependencies_true_for_supervisor(self):
        """Test that supervisor with unbuilt subagents is detected as deferred."""
        config = FlowConfig(
            version="experimental",
            environment="remote",
            components=[
                {
                    "name": "developer",
                    "type": "AgentComponent",
                    "description": "Developer agent",
                    "prompt_id": "dev_prompt",
                    "toolset": ["read_file"],
                },
                {
                    "name": "supervisor",
                    "type": "AgentComponent",
                    "prompt_id": "supervisor_prompt",
                    "toolset": ["get_issue"],
                    "subagents": [{"name": "developer"}],
                    "max_delegations": 10,
                },
            ],
            routers=[{"from": "supervisor", "to": "end"}],
            flow=FlowConfigMetadata(entry_point="supervisor"),
        )

        flow = self._make_flow(config)

        # Before developer is built
        components: dict[str, BaseComponent] = {}
        assert flow._has_unresolved_dependencies(config.components[1], components)

        # After developer is built
        components["developer"] = Mock(spec=BaseComponent)
        assert not flow._has_unresolved_dependencies(config.components[1], components)

    def test_has_unresolved_dependencies_raises_for_malformed_subagent_entry(self):
        """Test that a malformed subagents entry raises ValueError with component name."""
        config = FlowConfig(
            version="experimental",
            environment="remote",
            components=[
                {
                    "name": "supervisor",
                    "type": "AgentComponent",
                    "prompt_id": "supervisor_prompt",
                    "toolset": [],
                    "subagents": ["developer"],  # plain string instead of dict
                    "max_delegations": 10,
                },
            ],
            routers=[{"from": "supervisor", "to": "end"}],
            flow=FlowConfigMetadata(entry_point="supervisor"),
        )

        flow = self._make_flow(config)

        with pytest.raises(ValueError, match="supervisor"):
            flow._has_unresolved_dependencies(config.components[0], {})

    def test_has_unresolved_dependencies_false_for_regular_component(self):
        """Test that regular components are never deferred."""
        config = FlowConfig(
            version="experimental",
            environment="remote",
            components=[
                {
                    "name": "agent",
                    "type": "AgentComponent",
                    "prompt_id": "prompt",
                    "toolset": ["read_file"],
                },
            ],
            routers=[{"from": "agent", "to": "end"}],
            flow=FlowConfigMetadata(entry_point="agent"),
        )

        flow = self._make_flow(config)

        assert not flow._has_unresolved_dependencies(config.components[0], {})

    def test_instantiate_component_injects_built_components_into_agent_factory(self):
        """Flow passes _built_components to the AgentComponent factory callable.

        This verifies that ``_instantiate_component`` injects the shared
        ``components`` dict as ``_built_components`` when the component type is
        ``AgentComponent``, allowing the factory to resolve subagent references
        internally without coupling ``Flow`` to supervisor-specific logic.
        """
        config = FlowConfig(
            version="experimental",
            environment="remote",
            components=[
                {
                    "name": "my_agent",
                    "type": "AgentComponent",
                    "prompt_id": "prompt",
                    "toolset": [],
                },
            ],
            routers=[{"from": "my_agent", "to": "end"}],
            flow=FlowConfigMetadata(entry_point="my_agent"),
        )

        flow = self._make_flow(config)

        existing_components: dict[str, BaseComponent] = {
            "end": Mock(spec=BaseComponent)
        }
        comp_params = {"name": "my_agent", "prompt_id": "prompt", "toolset": []}

        captured_kwargs: dict = {}

        mock_agent = Mock(spec=BaseComponent)

        def capturing_factory(**kwargs):
            captured_kwargs.update(kwargs)
            return mock_agent

        with patch(
            "duo_workflow_service.agent_platform.experimental.flows.base.load_component_class",
            return_value=capturing_factory,
        ):
            flow._instantiate_component(
                config.components[0], comp_params, existing_components
            )

        # The factory must have received _built_components pointing to the shared dict
        assert "_built_components" in captured_kwargs
        assert captured_kwargs["_built_components"] is existing_components

    def test_instantiate_component_pops_consumed_subagents_via_subagent_components(
        self,
    ):
        """Flow removes consumed subagents from the shared dict after component creation.

        When the created component has a ``subagent_components`` attribute (i.e. it
        is a SupervisorAgentComponent), ``_instantiate_component`` pops each consumed
        subagent name from the shared ``components`` dict.  This keeps the mutation
        explicit and owned by ``Flow`` rather than hidden inside the factory.
        """
        config = FlowConfig(
            version="experimental",
            environment="remote",
            components=[
                {
                    "name": "supervisor",
                    "type": "AgentComponent",
                    "prompt_id": "prompt",
                    "toolset": [],
                    "subagents": [{"name": "developer"}],
                    "max_delegations": 5,
                },
            ],
            routers=[{"from": "supervisor", "to": "end"}],
            flow=FlowConfigMetadata(entry_point="supervisor"),
        )

        flow = self._make_flow(config)

        developer_mock = Mock(spec=BaseComponent)
        existing_components: dict[str, BaseComponent] = {
            "end": Mock(spec=BaseComponent),
            "developer": developer_mock,
        }
        comp_params = {"name": "supervisor", "prompt_id": "prompt", "toolset": []}

        # Simulate a supervisor component that reports it consumed "developer"
        mock_supervisor = Mock(spec=BaseComponent)
        mock_supervisor.subagent_components = {"developer": developer_mock}

        def supervisor_factory(**_kwargs):
            return mock_supervisor

        with patch(
            "duo_workflow_service.agent_platform.experimental.flows.base.load_component_class",
            return_value=supervisor_factory,
        ):
            flow._instantiate_component(
                config.components[0], comp_params, existing_components
            )

        # Flow must have removed the consumed subagent from the shared dict
        assert "developer" not in existing_components
        # The supervisor itself must be present
        assert "supervisor" in existing_components


class TestExtractSubagentNames:
    """Unit tests for the extract_subagent_names helper."""

    def test_returns_names_in_order(self):
        """Valid entries return names in the original order."""
        subagents = [{"name": "alpha"}, {"name": "beta"}, {"name": "gamma"}]
        assert extract_subagent_names(subagents) == ["alpha", "beta", "gamma"]

    def test_raises_for_plain_string_entry(self):
        """A plain string entry raises ValueError."""
        with pytest.raises(ValueError, match="must be a dict with a 'name' key"):
            extract_subagent_names(["developer"])

    def test_raises_for_dict_missing_name_key(self):
        """A dict without a 'name' key raises ValueError."""
        with pytest.raises(ValueError, match="must be a dict with a 'name' key"):
            extract_subagent_names([{"role": "developer"}])

    def test_raises_for_duplicate_name(self):
        """Duplicate subagent names raise ValueError."""
        subagents = [{"name": "developer"}, {"name": "tester"}, {"name": "developer"}]
        with pytest.raises(ValueError, match="Duplicate subagent name 'developer'"):
            extract_subagent_names(subagents)

    def test_raises_for_duplicate_name_adjacent(self):
        """Adjacent duplicate subagent names raise ValueError."""
        subagents = [{"name": "developer"}, {"name": "developer"}]
        with pytest.raises(ValueError, match="Duplicate subagent name 'developer'"):
            extract_subagent_names(subagents)

    def test_empty_list_returns_empty(self):
        """An empty list returns an empty list without error."""
        assert not extract_subagent_names([])
