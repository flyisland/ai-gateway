from unittest.mock import Mock, patch

import pytest

from duo_workflow_service.agent_platform.experimental.components.base import (
    BaseComponent,
)
from duo_workflow_service.agent_platform.experimental.components.registry import (
    ComponentRegistry,
    register_component,
)


class MockBaseComponent(BaseComponent):
    """Mock implementation of BaseComponent for testing."""

    def attach(self, graph, router=None):
        """Mock implementation."""

    def __entry_hook__(self):
        """Mock implementation."""


class TestComponentRegistry:
    """Test suite for ComponentRegistry class."""

    def test_singleton_pattern(self):
        """Test that ComponentRegistry follows singleton pattern."""
        registry1 = ComponentRegistry()
        registry2 = ComponentRegistry()

        assert registry1 is registry2

    def test_non_singleton_pattern(self):
        registry1 = ComponentRegistry(force_new=True)
        registry2 = ComponentRegistry(force_new=True)

        assert registry1 is not registry2

    def test_register_and_get_component_success(self):
        """Test successful component registration."""
        registry = ComponentRegistry(force_new=True)

        registry["TestComponent"] = MockBaseComponent
        component_class = registry.get("TestComponent")

        assert component_class is MockBaseComponent

    def test_register_component_already_exists_raises_error(self):
        """Test that registering existing component raises ValueError."""
        registry = ComponentRegistry(force_new=True)

        # Register component first time
        registry["TestComponent"] = MockBaseComponent

        # Try to register again
        with pytest.raises(
            KeyError, match="Component 'TestComponent' is already registered"
        ):
            registry["TestComponent"] = MockBaseComponent

    def test_get_component_not_found_raises_error(self):
        """Test that getting non-existent component raises KeyError."""
        registry = ComponentRegistry(force_new=True)

        with pytest.raises(
            KeyError, match="Component 'NonExistentComponent' not found in registry"
        ):
            _ = registry["NonExistentComponent"]

    def test_list_registered_components(self):
        """Test listing all registered components."""
        registry = ComponentRegistry(force_new=True)

        # Initially empty
        assert len(registry) == 0

        # Add components
        class Component1(MockBaseComponent):
            pass

        class Component2(MockBaseComponent):
            pass

        registry["Component1"] = Component1
        registry["Component2"] = Component2

        assert len(registry) == 2
        assert "Component1" in registry
        assert "Component2" in registry


class TestRegisterComponentDecorator:
    """Test suite for register_component decorator."""

    def test_register_component(self, component_registry):
        """Test decorator."""

        @register_component()
        class TestComponent(MockBaseComponent):
            pass

        component_registry.assert_called_once()

        registry = ComponentRegistry.instance()

        # pylint: disable-next=unsupported-membership-test
        assert "TestComponent" in registry
        assert registry.get("TestComponent") is TestComponent

    @patch(
        "duo_workflow_service.agent_platform.experimental.components.registry.inject"
    )
    def test_register_component_with_injection(self, mock_inject, component_registry):
        """Test decorator with dependency injection."""

        class TestComponent(MockBaseComponent):
            pass

        # Mock inject to return a modified class
        mock_injected_class = Mock()
        mock_inject.return_value = mock_injected_class

        # Call the decorator manually for the testing purposes
        register_component(has_injection=True)(TestComponent)

        component_registry.assert_called_once()

        registry = ComponentRegistry.instance()
        registered_class = registry.get("TestComponent")

        # Should be the injected class
        mock_inject.assert_called_with(TestComponent)

        assert registered_class is mock_injected_class

    def test_register_component_invalid_class_type(self):
        """Test decorator with non-class object raises TypeError."""

        with pytest.raises(TypeError, match="Invalid component class 'not_a_class'"):

            @register_component()
            def not_a_class():
                pass

    def test_register_component_not_basecomponent_subclass(self):
        """Test decorator with class not inheriting from BaseComponent."""

        with pytest.raises(TypeError, match="Invalid component class '_NotAComponent'"):

            @register_component()
            class _NotAComponent:
                pass
