import inspect
from typing import Callable, Optional, Self, cast

from dependency_injector.wiring import inject

from duo_workflow_service.agent_platform.experimental.components.base import (
    BaseComponent,
    BaseComponentRegistry,
)

__all__ = ["ComponentRegistry", "register_component"]


class ComponentRegistry(BaseComponentRegistry):
    """Singleton registry for managing BaseComponent classes.

    This registry implements the singleton pattern to ensure a single global
    registry for all component classes. Components can be registered and retrieved
    by name, enabling dynamic component loading and management.

    Example:
        >>> registry = ComponentRegistry.instance()
        >>> registry.register("MyComponent", MyComponent)
        >>> component_class = registry.get("MyComponent")
    """

    _instance: Optional[Self] = None
    _initialized: bool = False

    def __new__(cls):
        """Create or return the singleton instance.

        Returns:
            The singleton ComponentRegistry instance.
        """
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """Initialize the registry if not already initialized."""
        if not self._initialized:
            self._registry: dict[str, type[BaseComponent]] = {}
            ComponentRegistry._initialized = True

    @classmethod
    def instance(cls) -> Self:
        """Get the singleton instance of ComponentRegistry.

        Returns:
            The singleton ComponentRegistry instance.
        """
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def register(self, name: str, component_class: type[BaseComponent]) -> None:
        """Register a component class with the given name.

        Args:
            name: The name to register the component under.
            component_class: The component class to register.

        Raises:
            KeyError: If a component with the same name is already registered.
        """
        if name in self._registry:
            raise KeyError(
                f"Component '{name}' is already registered. Use a different name"
            )

        self._registry[name] = component_class

    def get(self, name: str) -> type[BaseComponent]:
        """Retrieve a registered component class by name.

        Args:
            name: The name of the component to retrieve.

        Returns:
            The component class registered under the given name.

        Raises:
            KeyError: If no component is registered under the given name.
        """
        klass = self._registry.get(name, None)
        if not klass:
            raise KeyError(f"Component '{name}' not found in registry")

        return klass

    def list_registered(self) -> list[type[BaseComponent]]:
        """Get a list of all registered component classes.

        Returns:
            A list containing all registered component classes.
        """
        return list(self._registry.values())

    def __contains__(self, name: str) -> bool:
        """Check if a component is registered under the given name.

        Args:
            name: The name to check for.

        Returns:
            True if a component is registered under the name, False otherwise.
        """
        return name in self._registry

    def clear(self) -> None:
        """Clear all registered components from the registry."""
        self._registry.clear()


def register_component[T: BaseComponent](
    name: Optional[str] = None, has_injection: bool = False
) -> Callable:
    """Decorator to automatically register a component class with the ComponentRegistry.

    This decorator registers the decorated class with the global ComponentRegistry
    instance, optionally applying dependency injection if requested.

    Args:
        name: Optional custom name for the component. If not provided, uses the class name.
        has_injection: Whether to apply dependency injection to the component class.
            If True, the component will be wrapped with the @inject decorator from dependency_injector.

    Returns:
        A decorator function that registers the component and returns the original class.

    Raises:
        TypeError: If the decorated object is not a class or doesn't inherit from BaseComponent.

    Example:
        >>> @register_component()
        ... class MyComponent(BaseComponent):
        ...     pass

        >>> @register_component(name="CustomName")
        ... class MyComponent(BaseComponent):
        ...     pass

        >>> @register_component(has_injection=True)
        ... class AnotherComponent(BaseComponent):
        ...     prompt_registry: LocalPromptRegistry = Provide[
        ...        ContainerApplication.pkg_prompts.prompt_registry
        ...     ]
    """

    def decorator(cls: type[T]) -> type[T]:
        if not (inspect.isclass(cls) and issubclass(cls, BaseComponent)):
            raise TypeError(
                f"Invalid component class '{cls.__name__}'. Components must inherit from BaseComponent class"
            )

        register_name = name or cls.__name__
        register_class = inject(cls) if has_injection else cls

        ComponentRegistry.instance().register(register_name, register_class)

        return cast(type[T], cls)

    return decorator
