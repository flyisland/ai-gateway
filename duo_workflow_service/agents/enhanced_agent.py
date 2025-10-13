"""Enhanced agent with improved error handling.

This module provides an enhanced version of the Agent class that uses the new
structured error handling system instead of generic error messages.
"""

from datetime import datetime, timezone
from typing import Any, Sequence, cast
import structlog
from anthropic import APIStatusError
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.prompt_values import PromptValue
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.prompts.chat import MessageLikeRepresentation
from langchain_core.runnables import Runnable, RunnableConfig

from ai_gateway.prompts.config.base import PromptConfig
from duo_workflow_service.agents.base import BaseAgent
from duo_workflow_service.entities.event import WorkflowEvent, WorkflowEventType
from duo_workflow_service.entities.state import (
    DuoWorkflowStateType,
    MessageTypeEnum,
    ToolStatus,
    UiChatLog,
    WorkflowStatusEnum,
)
from duo_workflow_service.errors.enhanced_error_handler import handle_llm_error
from duo_workflow_service.errors.error_handler import ERROR_TYPES, ModelErrorType
from duo_workflow_service.gitlab.events import get_event
from duo_workflow_service.gitlab.http_client import GitlabHttpClient
from duo_workflow_service.llm_factory import AnthropicStopReason
from duo_workflow_service.monitoring import duo_workflow_metrics
from duo_workflow_service.tools.handover import HandoverTool

log = structlog.stdlib.get_logger("enhanced_agent")


class AgentPromptTemplate(Runnable[dict, PromptValue]):
    messages: list[BaseMessage]

    def __init__(
        self, agent_name: str, preamble_messages: Sequence[MessageLikeRepresentation]
    ):
        self.agent_name = agent_name
        self.preamble_messages = preamble_messages

    def invoke(
        self,
        input: dict,
        config: RunnableConfig | None = None,
        **kwargs: Any,
    ) -> PromptValue:
        if self.agent_name in input["conversation_history"]:
            messages = input["conversation_history"][self.agent_name]
        else:
            if "handover" in input:
                # Transform handover into an agent-readable representation
                input["handover"] = "\n".join(
                    map(lambda x: x.pretty_repr(), input["handover"])
                )
            messages = self.preamble_messages

        prompt_value = ChatPromptTemplate.from_messages(
            messages, template_format="jinja2"
        ).invoke(input, config, **kwargs)
        self.messages = prompt_value.to_messages()
        return prompt_value


class EnhancedAgent(BaseAgent):
    """Enhanced agent with improved error handling."""
    
    check_events: bool = True
    http_client: GitlabHttpClient
    prompt_template_inputs: dict = {}

    @classmethod
    def _build_prompt_template(
        cls, config: PromptConfig
    ) -> Runnable[dict, PromptValue]:
        messages = cls._prompt_template_to_messages(config.prompt_template)
        return AgentPromptTemplate(agent_name=config.name, preamble_messages=messages)

    async def run(self, state: DuoWorkflowStateType) -> dict[str, Any]:
        with duo_workflow_metrics.time_compute(
            operation_type=f"{self.name}_processing"
        ):
            updates: dict[str, Any] = {
                "handover": [],
            }

            model_name_attrs = {
                "ChatAnthropicVertex": "model_name",
                "ChatAnthropic": "model",
            }
            model_name = getattr(
                self.model,
                model_name_attrs.get(self.model.get_name()) or "missing_attr",
                "unknown",
            )
            request_type = f"{self.name}_completion"

            if self.check_events:
                event: WorkflowEvent | None = await get_event(
                    self.http_client, self.workflow_id, False
                )
                if event and event["event_type"] == WorkflowEventType.STOP:
                    return {"status": WorkflowStatusEnum.CANCELLED}

            try:
                input = self._prepare_input(state)
                with duo_workflow_metrics.time_llm_request(
                    model=model_name, request_type=request_type
                ):
                    model_completion = await super().ainvoke(input)

                stop_reason = model_completion.response_metadata.get("stop_reason")
                if stop_reason in AnthropicStopReason.abnormal_values():
                    log.warning(f"LLM stopped abnormally with reason: {stop_reason}")

                duo_workflow_metrics.count_llm_response(
                    model=model_name,
                    provider=self.model_provider,
                    request_type=request_type,
                    stop_reason=stop_reason,
                    # Hardcoded 200 status since model_completion only returns status codes for failures
                    status_code="200",
                    error_type="none",
                )

                if self.name in state["conversation_history"]:
                    updates["conversation_history"] = {self.name: [model_completion]}
                else:
                    messages = cast(AgentPromptTemplate, self.prompt_tpl).messages
                    updates["conversation_history"] = {
                        self.name: [*messages, model_completion]
                    }

                return {
                    **updates,
                    **self._respond_to_human(state, model_completion),
                }

            except APIStatusError as error:
                log.warning(f"Error processing agent: {error}")
                
                status_code = error.response.status_code
                duo_workflow_metrics.count_llm_response(
                    model=model_name,
                    provider=self.model_provider,
                    request_type=request_type,
                    status_code=status_code,
                    stop_reason="error",
                    error_type=ERROR_TYPES.get(status_code, ModelErrorType.UNKNOWN),
                )
                
                # Get workflow ID from state if available
                workflow_id = getattr(state, 'workflow_id', None) or str(getattr(state, 'id', 'unknown'))
                
                enhanced_response = handle_llm_error(
                    exception=error,
                    model_name=model_name,
                    workflow_id=workflow_id,
                    additional_context={
                        "agent_name": self.name,
                        "model_provider": self.model_provider,
                        "request_type": request_type,
                        "status_code": status_code,
                    }
                )
                
                # Create error message for conversation history
                error_message = HumanMessage(
                    content=enhanced_response["ui_chat_log"][0]["content"]
                )
                
                return {
                    "conversation_history": {self.name: [error_message]},
                    **enhanced_response,
                }
            
            except Exception as error:
                log.error(f"Unexpected error processing agent: {error}", exc_info=True)
                
                # Get workflow ID from state if available
                workflow_id = getattr(state, 'workflow_id', None) or str(getattr(state, 'id', 'unknown'))
                
                from duo_workflow_service.errors.enhanced_error_handler import handle_agent_error
                
                enhanced_response = handle_agent_error(
                    exception=error,
                    agent_name=self.name,
                    workflow_id=workflow_id,
                    additional_context={
                        "model_name": model_name,
                        "model_provider": self.model_provider,
                        "request_type": request_type,
                    }
                )
                
                # Create error message for conversation history
                error_message = HumanMessage(
                    content=enhanced_response["ui_chat_log"][0]["content"]
                )
                
                return {
                    "conversation_history": {self.name: [error_message]},
                    **enhanced_response,
                }

    def _prepare_input(self, state: DuoWorkflowStateType) -> dict:
        inputs = cast(dict, state)
        inputs["handover_tool_name"] = HandoverTool.tool_title
        return {**inputs, **self.prompt_template_inputs}

    def _respond_to_human(self, state, model_completion) -> dict[str, Any]:
        if not isinstance(model_completion, AIMessage):
            return {}

        last_human_input = state.get("last_human_input")
        if (
            isinstance(last_human_input, dict)
            and last_human_input.get("event_type") == WorkflowEventType.MESSAGE
        ):
            content = self._parse_model_content(model_completion.content)
            return {
                "ui_chat_log": ([self._create_ui_chat_log(content)] if content else []),
                "last_human_input": None,
            }
        return {}

    def _parse_model_content(self, content: str | list) -> str | None:
        if isinstance(content, str):
            return content
        if isinstance(content, list) and all(isinstance(item, str) for item in content):
            return "\n".join(content)
        return next(
            (
                item.get("text")
                for item in content
                if isinstance(item, dict) and item.get("text", False)
            ),
            None,
        )