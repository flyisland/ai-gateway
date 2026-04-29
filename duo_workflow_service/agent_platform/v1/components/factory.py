"""AgentComponent factory for the Flow Registry.

Registered in the v1 :class:`ComponentRegistry` under ``"AgentComponent"``.
Transparently dispatches to :class:`AgentComponent` or
:class:`SupervisorAgentComponent` depending on whether ``subagents`` is
present in the component configuration, so flow YAML configs always use
``type: AgentComponent`` regardless of mode.

Note: This module must be imported **after** both ``agent.component`` and
``supervisor.component`` have been loaded (as ``__init__.py`` ensures) so that
the module-level imports below do not create circular dependencies.
"""

from typing import Any

from duo_workflow_service.agent_platform.v1.components.agent.component import (
    AgentComponent,
    AgentComponentBase,
)
from duo_workflow_service.agent_platform.v1.components.base import (
    BaseComponent,
)
from duo_workflow_service.agent_platform.v1.components.registry import (
    register_component_factory,
)
from duo_workflow_service.agent_platform.v1.components.supervisor.component import (
    SupervisorAgentComponent,
)

__all__ = ["agent_component_factory"]


@register_component_factory("AgentComponent")
def agent_component_factory(
    **kwargs: Any,
) -> AgentComponentBase:
    """Dispatch to AgentComponent or SupervisorAgentComponent.

    Creates a :class:`SupervisorAgentComponent` when ``subagents`` is present
    and non-empty, passing the ``_built_components`` dict injected by the flow
    builder as ``subagent_components``.  Otherwise creates a plain
    :class:`AgentComponent`.  The ``_built_components`` key is always popped
    from ``kwargs`` before forwarding to the constructor.

    Args:
        **kwargs: Component constructor arguments from the flow YAML, plus
            ``_built_components`` injected by the flow builder.

    Returns:
        An :class:`AgentComponent` or :class:`SupervisorAgentComponent` instance.
    """
    built_components: dict[str, BaseComponent] = kwargs.pop("_built_components", {})

    if kwargs.get("subagents"):
        return SupervisorAgentComponent(subagent_components=built_components, **kwargs)

    return AgentComponent(**kwargs)
