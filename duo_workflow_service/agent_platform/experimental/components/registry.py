import inspect
from typing import Callable, Optional, Self, cast

from dependency_injector.wiring import inject

from duo_workflow_service.agent_platform.experimental.components.base import (
    BaseComponent,
    BaseComponentRegistry,
)

__all__ = ["ComponentRegistry", "register_component"]


class ComponentRegistry(BaseComponentRegistry):
    _instance: Optional[Self] = None
    _initialized: bool = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not self._initialized:
            self._registry: dict[str, type[BaseComponent]] = {}
            ComponentRegistry._initialized = True

    @classmethod
    def instance(cls) -> Self:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def register(self, name: str, component_class: type[BaseComponent]):
        if name in self._registry:
            raise ValueError("TODO: already registered")

        self._registry[name] = component_class

    def get(self, name: str) -> type[BaseComponent]:
        klass = self._registry.get(name, None)
        if not klass:
            raise KeyError("TODO: not found")

        return klass

    def list_registered(self) -> list[type[BaseComponent]]:
        return list(self._registry.values())

    def __contains__(self, name: str) -> bool:
        return name in self._registry


def register_component[T: BaseComponent](
    name: Optional[str] = None, has_injection: bool = False
) -> Callable:
    def decorator(cls: type[T]) -> T:
        if not (inspect.isclass(cls) and issubclass(cls, BaseComponent)):
            raise TypeError(f"TODO: '{cls}' must inherit from the BaseComponent class")

        register_name = name or cls.__name__
        register_class = inject(cls) if has_injection else cls

        ComponentRegistry.instance().register(register_name, register_class)

        return cast(T, cls)

    return decorator
