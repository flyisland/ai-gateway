# Re-export SupervisorAgentComponent entities from v1 to prevent code duplication.
# The implementation has been migrated to v1; experimental re-exports for backward compatibility.
from duo_workflow_service.agent_platform.v1.components.supervisor.component import (  # noqa: F401
    SubagentConfig,
    SupervisorAgentComponent,
    extract_subagent_names,
)

__all__ = ["SubagentConfig", "SupervisorAgentComponent", "extract_subagent_names"]
