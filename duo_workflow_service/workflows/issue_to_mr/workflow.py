import math
import os
from datetime import datetime, timezone
from enum import StrEnum
import random
from typing import Any

from langgraph.checkpoint.memory import BaseCheckpointSaver
from langgraph.graph import END, StateGraph
from langgraph.types import Command
from pydantic import BaseModel, Field

from duo_workflow_service.agent_registry.components.base import AgentComponent, EndComponent, HiltChatBackComponent, Router, DEFAULT_ROUTE, attach_components_to_graph
from duo_workflow_service.checkpointer.gitlab_workflow import WorkflowStatusEventEnum
from duo_workflow_service.components.tools_registry import ToolsRegistry
from duo_workflow_service.entities.state import (
    PoCWorkflowState,
    MessageTypeEnum,
    ToolStatus,
    UiChatLog,
    WorkflowStatusEnum,
)
from duo_workflow_service.tracking.errors import log_exception
from duo_workflow_service.workflows.abstract_workflow import AbstractWorkflow
from duo_workflow_service.workflows.chat.workflow import CHAT_READ_ONLY_TOOLS, CHAT_MUTATION_TOOLS

MAX_TOKENS_TO_SAMPLE = 8192
DEBUG = os.getenv("DEBUG")
MAX_MESSAGE_LENGTH = 200
RECURSION_LIMIT = 500


class Routes(StrEnum):
    CONTINUE = "continue"
    NO_CONVERSATION_HISTORY = "no_conversation_history"
    SHOW_AGENT_MESSAGE = "show_agent_message"
    TOOL_USE = "tool_use"
    STOP = "stop"


class AgentFinalOutput(BaseModel):
    """
    Always use this tool if no other tools are appropriate.
    """
    text: str = Field(description="text")

    @property
    def content(self) -> str:
        return self.text


class Workflow(AbstractWorkflow):
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
                "first": {
                    "task": goal,
                },
                "paths": {
                    "joke":  { "task": "Write a funny AI programming joke to joke.md in the repository root" },
                    "haiku": { "task": "Write a haiku about AI coding to haiku.md in the repository root" },
                }
            }
        )

    async def get_graph_input(self, goal: str, status_event: str) -> Any:
        match status_event:
            case WorkflowStatusEventEnum.START:
                return self.get_workflow_state(goal)
            case WorkflowStatusEventEnum.RESUME:
                return Command(resume=goal)
            case _:
                return None

    def _compile(
        self,
        goal: str,
        tools_registry: ToolsRegistry,
        checkpointer: BaseCheckpointSaver,
    ):
        self.log.info(
            "ChatWorkflow._compile: Starting chat workflow compilation",
            workflow_id=self._workflow_id,
            goal=goal,
        )

        agents_toolset = tools_registry.toolset(CHAT_READ_ONLY_TOOLS + CHAT_MUTATION_TOOLS)
        agent_component = AgentComponent(
            name="agent",
            prompt_id="agents/awesome",
            prompt_version="^1.0.0",
            workflow_id=self._workflow_id,
            workflow_type=self._workflow_type,
            toolset=agents_toolset,
            inputs=["first.task"],
            output_type=AgentFinalOutput,
            output="answer"
        )

        hilt_component = HiltChatBackComponent(
            name="hilt",
            workflow_id=self._workflow_id,
            workflow_type=self._workflow_type,
            inputs=[f"conversation_history.{agent_component.name}"],
            output=agent_component.name
        )


        end_component = EndComponent(
            name="end",
            inputs=[],
            workflow_id=self._workflow_id,
            workflow_type=self._workflow_type,
        )

        graph = StateGraph(PoCWorkflowState)
        
        Router(
            from_component=agent_component,
            to_component=hilt_component,
        ).attach(graph)

        Router(
            from_component=hilt_component,
            input="status",
            to_component={
                WorkflowStatusEnum.EXECUTION: agent_component,
                DEFAULT_ROUTE: end_component
            },
        ).attach(graph)

        graph.set_entry_point(agent_component.__entry_hook__())
        # graph = attach_components_to_graph(
        #     graph,
        #     [agent_component, lambda_component_1, lambda_component_2],
        #     start=agent_component.name,
        #     end=[lambda_component_2.name],
        # )

        return graph.compile(checkpointer=checkpointer)

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
