"""AgentComponent factory for the experimental Flow Registry.

Re-registers the v1 ``agent_component_factory`` in the experimental
``ComponentRegistry`` for backward compatibility with experimental flows.
The implementation has been migrated to v1; this module delegates to v1
components while keeping the factory available under the experimental registry.
"""

from duo_workflow_service.agent_platform.experimental.components.registry import (
    register_component_factory,
)
from duo_workflow_service.agent_platform.v1.components.factory import (  # noqa: F401
    agent_component_factory as _v1_agent_component_factory,
)

__all__ = ["agent_component_factory"]

agent_component_factory = register_component_factory("AgentComponent")(
    _v1_agent_component_factory
)
