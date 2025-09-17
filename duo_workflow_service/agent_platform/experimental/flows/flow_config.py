import json
from pathlib import Path
from typing import Callable, ClassVar, Optional, Self

import yaml
from pydantic import BaseModel, model_validator

from duo_workflow_service.agent_platform.experimental.components import (
    BaseComponent,
    ComponentRegistry,
)

__all__ = ["FlowConfig", "load_component_class"]


_PREFIX_BLOCLIST = (
    "..",
    "/.../",
    r"\…..\\",
    "%00../../../../../",
    "%2e%2e%2f",
    "%252e%252e%252f",
    "%c0%ae%c0%ae%c0%af",
    "%uff0e%uff0e%u2215",
    "%uff0e%uff0e%u2216",
)

REQUIRED_INPUT_SCHEMA_KEYS = [
    "type",
    "properties",
    "additionalProperties",
    "$schema"
]

# class flowInput
#
# FlowConfigConfig
#     entry_point: set
#     inputs:

class FlowConfig(BaseModel):
    DIRECTORY_PATH: ClassVar[Path] = Path(__file__).resolve().parent / "configs"
    flow: dict
    components: list[dict]
    routers: list[dict]
    environment: str
    version: str
    prompts: Optional[list[dict]] = None

    @model_validator(mode='after')
    def validate_flow_input_schemas(self) -> Self:
        """Validate and parse the input schemas."""
        if self.flow['inputs'] is None:
            return self

        try:
            # pydantic model for flow_inputs ...

            inputs = self.flow['inputs']
            for input in inputs:
                if 'category' not in input.keys():
                    raise ValueError(f"input must have a category")

                category = input['category']

                if not isinstance(input, dict):
                    raise ValueError(
                        f"input '{category}' must be a dict, found {type(input).__name__}"
                    )

                schema = json.loads(input['schema'])

                if not all(key in schema for key in REQUIRED_INPUT_SCHEMA_KEYS):
                    raise ValueError(
                        f"input schema must have these fields: {REQUIRED_INPUT_SCHEMA_KEYS}"
                    )

        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in input schema: {e}")
        except Exception as e:
            raise ValueError(f"Invalid schema format: {e}")

        print("VALID! -----------")
        return self

    @classmethod
    def from_yaml_config(cls, path: str) -> Self:
        try:
            # Validate path before resolving to prevent directory traversal
            if any(prefix in path for prefix in _PREFIX_BLOCLIST) or path.startswith(
                "/"
            ):
                raise ValueError(f"Path traversal detected: {path}")

            base_path = cls.DIRECTORY_PATH.resolve()
            yaml_path = (base_path / f"{path}.yml").resolve()

            if not yaml_path.is_relative_to(base_path):
                raise ValueError(f"Path traversal detected: {path}")

            with open(yaml_path, "r", encoding="utf-8") as file:
                yaml_content = yaml.safe_load(file)

            return cls(**yaml_content)
        except FileNotFoundError:
            raise FileNotFoundError(f"{path} file not found in {cls.DIRECTORY_PATH}")
        except yaml.YAMLError as e:
            raise yaml.YAMLError(f"Error parsing YAML file: {e}") from e


def load_component_class(
    cls_name: str,
) -> type[BaseComponent] | Callable[..., BaseComponent]:
    """Load a component class by name from the ComponentRegistry.

    This function provides a convenient way to dynamically retrieve registered
    component classes from the global ComponentRegistry instance. It is primarily
    used within the flow system to instantiate components based on their string
    names as specified in flow configuration files.

    The function performs a simple lookup in the ComponentRegistry and returns
    the component class that was previously registered using the @register_component
    decorator or manual registry.register() calls.

    Args:
        cls_name: The name of the component class to load. This should match
            the class name that was used during registration. Component names
            are case-sensitive and must be exact matches.

    Returns:
        The component class registered under the given name. This can be either
        a direct BaseComponent subclass or a callable that returns a BaseComponent
        instance (if decorators were applied during registration).

    Raises:
        KeyError: If no component is registered under the given name.

    Example:
        Basic usage in flow configuration:
        >>> component_class = load_component_class("AgentComponent")
        >>> instance = component_class(name="agent", flow_id="flow_1", ...)

    Note:
        This function is typically called internally by the flow system when
        building flows from configuration files. Components must be registered
        before they can be loaded. See `components.register_component` decorator
        for information on how to register components for use with this function.
    """
    registry = ComponentRegistry.instance()

    # pylint: disable-next=unsubscriptable-object
    return registry[cls_name]
