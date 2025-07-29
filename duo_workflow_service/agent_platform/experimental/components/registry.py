from collections.abc import Mapping
from typing import Callable, Optional, Self, Sequence, TypeAlias

from duo_workflow_service.agent_platform.experimental.components.base import (
    BaseComponent,
)

__all__ = ["ComponentRegistry", "register_component"]


ComponentClassAlias: TypeAlias = type[BaseComponent] | Callable[..., BaseComponent]
DecoratorAlias: TypeAlias = Callable[[ComponentClassAlias], ComponentClassAlias]


class ComponentRegistry(Mapping):
    """Singleton registry for managing BaseComponent classes.

    This registry implements the singleton pattern to ensure a single global
    registry for all component classes. Components can be registered and retrieved
    by name, enabling dynamic component loading and management.

    Example:
        >>> registry = ComponentRegistry.instance()
        >>> registry["MyComponent"] = MyComponent
        >>> component_class = registry["MyComponent"]
    """

    _instance: Optional[Self] = None

    def __new__(cls, force_new: bool = False):
        """Create a new instance or return singleton based on usage.

        Args:
            force_new: If True, always create a new instance.
                If False, create new instance (default for direct instantiation).

        Returns:
            A ComponentRegistry instance.
        """
        if force_new or cls._instance is None:
            instance = super().__new__(cls)
            return instance
        return cls._instance

    def __init__(self, force_new: bool = False):
        """Initialize the registry."""
        # Always initialize for new instances, or if not already initialized for singleton
        if force_new or not hasattr(self, "_registry"):
            self._registry: dict[str, ComponentClassAlias] = {}

    @classmethod
    def instance(cls) -> Self:
        """Get the singleton instance of ComponentRegistry.

        Returns:
            The singleton ComponentRegistry instance.
        """
        if cls._instance is None:
            cls._instance = cls(force_new=True)
        return cls._instance

    def register(
        self,
        value: type[BaseComponent],
        decorators: Sequence[DecoratorAlias],
    ) -> ComponentClassAlias:
        """Register a component class with the given name.

        Args:
            key: The unique name to register the component under.
            value: The component class to register.

        Raises:
            KeyError: If a component with the same name is already registered.
            TypeError: If a component doesn't inherit from BaseComponent.
        """
        if not issubclass(value, BaseComponent):
            raise TypeError(
                f"Invalid component class '{value.__name__}'. Components must inherit from BaseComponent class"
            )

        register_name = value.__name__

        for decorator in decorators:
            value: ComponentClassAlias = decorator(value)  # type: ignore[no-redef]

        if register_name in self._registry:
            raise KeyError(
                f"Component '{register_name}' is already registered. Use a different name"
            )

        self._registry[register_name] = value

        return value

    def __getitem__(self, key: str, /) -> ComponentClassAlias:
        """Retrieve a registered component class by name.

        Args:
            key: The name of the component to retrieve.

        Returns:
            The component class registered under the given name.

        Raises:
            KeyError: If no component is registered under the given name.
        """
        klass = self._registry.get(key, None)
        if not klass:
            raise KeyError(f"Component '{key}' not found in registry")

        return klass

    def __len__(self) -> int:
        return len(self._registry)

    def __iter__(self):
        yield from self._registry.__iter__()


def register_component(
    decorators: Optional[Sequence[DecoratorAlias]] = None,
) -> Callable:
    """Decorator to automatically register a component class with the ComponentRegistry.

    This decorator registers the decorated class with the global ComponentRegistry
    instance, optionally applying dependency injection if requested.

    Args:
        has_injection: Whether to apply dependency injection to the component class.
            If True, the component will be wrapped with the @inject decorator from dependency_injector.

    Returns:
        A decorator function that registers the component and returns the original class.

    Raises:
        KeyError: If a component with the same name is already registered.
        TypeError: If the decorated object is not a class or doesn't inherit from BaseComponent.

    Example:
        >>> @register_component()
        ... class MyComponent(BaseComponent):
        ...     pass

        >>> @register_component(has_injection=True)
        ... class AnotherComponent(BaseComponent):
        ...     prompt_registry: LocalPromptRegistry = Provide[
        ...        ContainerApplication.pkg_prompts.prompt_registry
        ...     ]
    """

    def decorator(cls: type[BaseComponent]) -> ComponentClassAlias:
        registry = ComponentRegistry.instance()
        registered_class = registry.register(cls, decorators if decorators else [])

        return registered_class

    return decorator
