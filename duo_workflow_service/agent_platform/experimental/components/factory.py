"""AgentComponent factory for the experimental Flow Registry.

Registered in the experimental :class:`ComponentRegistry` under ``"AgentComponent"``.
Transparently dispatches to :class:`AgentComponent` or
:class:`SupervisorAgentComponent` depending on whether ``subagents`` is
present in the component configuration.

This reuses the v1 factory logic but imports experimental components,
which support experimental features like tool approval.
"""

from typing import Any, Union

from duo_workflow_service.agent_platform.experimental.components.agent.component import (
    AgentComponent,
    AgentComponentBase,
)
from duo_workflow_service.agent_platform.experimental.components.base import (
    BaseComponent,
)
from duo_workflow_service.agent_platform.experimental.components.registry import (
    register_component_factory,
)
from duo_workflow_service.agent_platform.experimental.components.supervisor.component import (
    SupervisorAgentComponent,
)
from duo_workflow_service.agent_platform.v1.components.agent.component import (
    AgentComponentBase as V1AgentComponentBase,
)

__all__ = ["agent_component_factory"]


@register_component_factory("AgentComponent")
def agent_component_factory(
    **kwargs: Any,
) -> Union[AgentComponentBase, V1AgentComponentBase]:
    """Dispatch to AgentComponent or SupervisorAgentComponent.

    Reuses v1 factory logic: creates SupervisorAgentComponent when subagents
    is present, otherwise creates AgentComponent. Uses experimental versions
    of these components.

    Args:
        **kwargs: Component constructor arguments from flow YAML, plus
            _built_components injected by the flow builder.

    Returns:
        An experimental AgentComponent or SupervisorAgentComponent instance.
    """
    # Same logic as v1 factory
    built_components: dict[str, BaseComponent] = kwargs.pop("_built_components", {})

    if kwargs.get("subagents"):
        return SupervisorAgentComponent(subagent_components=built_components, **kwargs)

    return AgentComponent(**kwargs)
