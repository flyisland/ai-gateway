import os
from datetime import datetime, timezone
from typing import Any, Type

from pydantic import BaseModel
import yaml
from langgraph.graph import StateGraph
from langgraph.types import Command

from duo_workflow_service.agent_registry.components.base import (
    AgentComponent,
    AgentFinalOutput,
    EndComponent,
    HiltChatBackComponent,
    Router,
    UILogAgentEvents,
)
from duo_workflow_service.checkpointer.gitlab_workflow import WorkflowStatusEventEnum
from duo_workflow_service.entities.state import (
    MessageTypeEnum,
    PoCWorkflowState,
    ToolStatus,
    UiChatLog,
    WorkflowStatusEnum,
)
from duo_workflow_service.tracking.errors import log_exception
from duo_workflow_service.workflows.abstract_workflow import AbstractWorkflow

MAX_TOKENS_TO_SAMPLE = 8192
DEBUG = os.getenv("DEBUG")
MAX_MESSAGE_LENGTH = 200
RECURSION_LIMIT = 500

class FlowConfig(BaseModel):
    flow: dict
    components: list[dict]
    routers: list[dict]
    environment: str
    version: int

class Flow(AbstractWorkflow): 
    def log_workflow_elements(self, element):
        self.log.info("###############################")
        if "ui_chat_log" in element:
            for log in element["ui_chat_log"]:
                self.log.info(
                    f"%s: %{'' if DEBUG else f'.{MAX_MESSAGE_LENGTH}'}s",
                    log["message_type"],
                    log["content"],
                )

    async def _handle_workflow_failure(
        self, error: BaseException, compiled_graph: Any, graph_config: Any
    ):
        log_exception(error, extra={"workflow_id": self._workflow_id})

    def get_workflow_state(self, goal: str) -> PoCWorkflowState:
        context_elements = self._context_elements or []

        initial_ui_chat_log = UiChatLog(
            message_type=MessageTypeEnum.TOOL,
            content=f"Starting chat: {goal}",
            timestamp=datetime.now(timezone.utc).isoformat(),
            status=ToolStatus.SUCCESS,
            correlation_id=None,
            tool_info=None,
            context_elements=context_elements,
        )

        return PoCWorkflowState(
            status=WorkflowStatusEnum.NOT_STARTED,
            conversation_history={},
            ui_chat_log=[initial_ui_chat_log],
            context={
                "project_id": self._project.get("id"),
                "task": goal,
            },
        )

    async def get_graph_input(self, goal: str, status_event: str) -> Any:
        match status_event:
            case WorkflowStatusEventEnum.START:
                return self.get_workflow_state(goal)
            case WorkflowStatusEventEnum.RESUME:
                return Command(resume=goal)
            case _:
                return None

    def _compile(self, goal, tools_registry, checkpointer):

        # Create graph
        graph = StateGraph(PoCWorkflowState)
        agent_tools = [
            "read_file", "list_dir", "find_files", "grep", "create_file_with_contents", "edit_file", "mkdir"
        ]
        agent_component = AgentComponent(
            name="agent",
            inputs=["context:task"],
            output="context:agent.answer",
            output_type=AgentFinalOutput,
            prompt_id="agents/awesome",
            prompt_version="^1.0.0",
            toolset=tools_registry.toolset(agent_tools),
            ui_log_events=UILogAgentEvents(llm=True, tools=True),
            workflow_id=self._workflow_id,
            workflow_type=self._workflow_type,
        )
        get_user_input = HiltChatBackComponent(
            name="user_input",
            output="conversation_history:agent",
            workflow_id=self._workflow_id,
            workflow_type=self._workflow_type,
        )
        end_component = EndComponent(
            name="end",
            workflow_id=self._workflow_id,
            workflow_type=self._workflow_type,
        )
        agent_router = Router(
            from_component=agent_component,
            to_component=get_user_input
        )
        user_input_router = Router(
            from_component=get_user_input,
            input="status",
            to_component={
                "Execution": agent_component,
                "default_route": end_component,
            }
        )

        agent_router.attach(graph)
        user_input_router.attach(graph)
        graph.set_entry_point(agent_component.__entry_hook__())

        return graph.compile(checkpointer=checkpointer)


