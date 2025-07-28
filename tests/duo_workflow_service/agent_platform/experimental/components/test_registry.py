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

    def setup_method(self):
        """Clear registry before each test."""
        registry = ComponentRegistry.instance()
        registry.clear()

    def test_singleton_pattern(self):
        """Test that ComponentRegistry follows singleton pattern."""
        registry1 = ComponentRegistry()
        registry2 = ComponentRegistry()
        registry3 = ComponentRegistry.instance()

        assert registry1 is registry2
        assert registry2 is registry3
        assert ComponentRegistry._instance is registry1

    def test_register_and_get_component_success(self):
        """Test successful component registration."""
        registry = ComponentRegistry.instance()

        registry.register("TestComponent", MockBaseComponent)
        component_class = registry.get("TestComponent")

        assert component_class is MockBaseComponent

    def test_register_component_already_exists_raises_error(self):
        """Test that registering existing component raises ValueError."""
        registry = ComponentRegistry.instance()

        # Register component first time
        registry.register("TestComponent", MockBaseComponent)

        # Try to register again
        with pytest.raises(
            KeyError, match="Component 'TestComponent' is already registered"
        ):
            registry.register("TestComponent", MockBaseComponent)

    def test_get_component_not_found_raises_error(self):
        """Test that getting non-existent component raises KeyError."""
        registry = ComponentRegistry.instance()

        with pytest.raises(
            KeyError, match="Component 'NonExistentComponent' not found in registry"
        ):
            registry.get("NonExistentComponent")

    def test_list_registered_components(self):
        """Test listing all registered components."""
        registry = ComponentRegistry.instance()

        # Initially empty
        assert registry.list_registered() == []

        # Add components
        class Component1(MockBaseComponent):
            pass

        class Component2(MockBaseComponent):
            pass

        registry.register("Component1", Component1)
        registry.register("Component2", Component2)

        registered = registry.list_registered()
        assert len(registered) == 2
        assert Component1 in registered
        assert Component2 in registered


class TestRegisterComponentDecorator:
    """Test suite for register_component decorator."""

    def setup_method(self):
        """Clear registry before each test."""
        registry = ComponentRegistry.instance()
        registry.clear()

    def test_register_component_with_default_name(self):
        """Test decorator with default component name."""

        @register_component()
        class TestComponent(MockBaseComponent):
            pass

        registry = ComponentRegistry.instance()
        # pylint: disable-next=unsupported-membership-test
        assert "TestComponent" in registry
        assert registry.get("TestComponent") is TestComponent

    def test_register_component_with_custom_name(self):
        """Test decorator with custom component name."""

        @register_component(name="CustomName")
        class TestComponent(MockBaseComponent):
            pass

        registry = ComponentRegistry.instance()
        assert registry.get("CustomName") is TestComponent
        # pylint: disable-next=unsupported-membership-test
        assert "CustomName" in registry
        # pylint: disable-next=unsupported-membership-test
        assert "TestComponent" not in registry

    @patch(
        "duo_workflow_service.agent_platform.experimental.components.registry.inject"
    )
    def test_register_component_with_injection(self, mock_inject):
        """Test decorator with dependency injection."""

        class TestComponent(MockBaseComponent):
            pass

        # Mock inject to return a modified class
        mock_injected_class = Mock()
        mock_inject.return_value = mock_injected_class

        # Call the decorator manually for the testing purposes
        decorated_class = register_component(has_injection=True)(TestComponent)

        registry = ComponentRegistry.instance()
        registered_class = registry.get("TestComponent")

        # Should be the injected class
        mock_inject.assert_called_once_with(TestComponent)
        assert registered_class is mock_injected_class
        # But the returned class should still be the original
        assert decorated_class is TestComponent

    def test_register_component_invalid_class_type(self):
        """Test decorator with non-class object raises TypeError."""

        with pytest.raises(TypeError, match="Invalid component class 'not_a_class'"):

            @register_component()
            def not_a_class():
                pass

    def test_register_component_not_basecomponent_subclass(self):
        """Test decorator with class not inheriting from BaseComponent."""

        with pytest.raises(TypeError, match="Invalid component class 'NotAComponent'"):

            @register_component()
            class _NotAComponent:
                pass
