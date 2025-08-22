from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, cast

import structlog
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.messages.tool import ToolCall
from langchain_core.output_parsers.string import StrOutputParser
from langchain_core.prompt_values import ChatPromptValue, PromptValue
from langchain_core.runnables import Runnable, RunnableConfig

from ai_gateway.prompts import Prompt, jinja2_formatter
from ai_gateway.prompts.config.base import PromptConfig
from ai_gateway.prompts.config.models import ModelClassProvider
from duo_workflow_service.components.tools_registry import ToolsRegistry
from duo_workflow_service.entities.state import (
    ApprovalStateRejection,
    ChatWorkflowState,
    MessageTypeEnum,
    ToolInfo,
    ToolStatus,
    UiChatLog,
    WorkflowStatusEnum,
)
from duo_workflow_service.gitlab.gitlab_api import Namespace, Project
from duo_workflow_service.gitlab.gitlab_instance_info_service import (
    GitLabInstanceInfoService,
)
from duo_workflow_service.gitlab.gitlab_service_context import GitLabServiceContext
from duo_workflow_service.llm_factory import AnthropicStopReason
from duo_workflow_service.slash_commands.goal_parser import parse as slash_command_parse
from duo_workflow_service.structured_logging import _workflow_id
from lib.internal_events import InternalEventAdditionalProperties
from lib.internal_events.event_enum import CategoryEnum, EventEnum, EventPropertyEnum

log = structlog.stdlib.get_logger("chat_agent")


class ChatAgentPromptTemplate(Runnable[ChatWorkflowState, PromptValue]):
    def __init__(self, prompt_template: dict[str, str]):
        self.prompt_template = prompt_template

    def invoke(
        self,
        input: ChatWorkflowState,
        config: Optional[RunnableConfig] = None,  # pylint: disable=unused-argument
        **kwargs: Any,
    ) -> PromptValue:
        messages: list[BaseMessage] = []
        agent_name = kwargs["agent_name"]
        project: Project | None = input.get("project")
        namespace: Namespace | None = input.get("namespace")

        gitlab_instance_info = GitLabServiceContext.get_current_instance_info()

        self._add_system_messages(
            messages, gitlab_instance_info, project, namespace, kwargs
        )
        self._add_conversation_messages(messages, input, agent_name)

        return ChatPromptValue(messages=messages)

    def _add_system_messages(
        self,
        messages: list[BaseMessage],
        gitlab_instance_info: Any,
        project: Project | None,
        namespace: Namespace | None,
        kwargs: Dict[str, Any],
    ) -> None:
        self._add_static_system_message(messages, gitlab_instance_info, kwargs)
        self._add_dynamic_system_message(messages, project, namespace)

    def _add_static_system_message(
        self,
        messages: list[BaseMessage],
        gitlab_instance_info: Any,
        kwargs: Dict[str, Any],
    ) -> None:
        if "system_static" not in self.prompt_template:
            return

        static_content_text = jinja2_formatter(
            self.prompt_template["system_static"],
            gitlab_instance_type=getattr(
                gitlab_instance_info, "instance_type", "Unknown"
            ),
            gitlab_instance_url=getattr(
                gitlab_instance_info, "instance_url", "Unknown"
            ),
            gitlab_instance_version=getattr(
                gitlab_instance_info, "instance_version", "Unknown"
            ),
        )

        is_anthropic = kwargs.get("is_anthropic_model", False)
        if is_anthropic:
            cached_content: Sequence[dict[str, Any]] = [
                {
                    "text": static_content_text,
                    "type": "text",
                    "cache_control": {"type": "ephemeral", "ttl": "1h"},
                }
            ]
            messages.append(SystemMessage(content=list(cached_content)))
        else:
            messages.append(SystemMessage(content=static_content_text))

    def _add_dynamic_system_message(
        self,
        messages: list[BaseMessage],
        project: Project | None,
        namespace: Namespace | None,
    ) -> None:
        if "system_dynamic" not in self.prompt_template:
            return

        now = datetime.now()
        dynamic_content = jinja2_formatter(
            self.prompt_template["system_dynamic"],
            current_date=now.strftime("%Y-%m-%d"),
            current_time=now.strftime("%H:%M:%S"),
            current_timezone=now.astimezone().tzname(),
            project=project,
            namespace=namespace,
        )
        messages.append(SystemMessage(content=dynamic_content))

    def _add_conversation_messages(
        self,
        messages: list[BaseMessage],
        input: ChatWorkflowState,
        agent_name: str,
    ) -> None:
        for message in input["conversation_history"][agent_name]:
            if isinstance(message, HumanMessage):
                self._process_human_message(messages, message)
            else:
                messages.append(message)  # AIMessage or ToolMessage

    def _process_human_message(
        self, messages: list[BaseMessage], message: HumanMessage
    ) -> None:
        slash_command = self._extract_slash_command(message)
        formatted_message = HumanMessage(
            jinja2_formatter(
                self.prompt_template["user"],
                message=message,
                slash_command=slash_command,
            )
        )
        messages.append(formatted_message)

    def _extract_slash_command(self, message: HumanMessage) -> Optional[Dict[str, str]]:
        if not isinstance(
            message.content, str
        ) or not message.content.strip().startswith("/"):
            return None

        command_name, remaining_text = slash_command_parse(message.content)
        return {"name": command_name or "", "input": remaining_text or ""}


class ChatAgent(Prompt[ChatWorkflowState, BaseMessage]):
    tools_registry: Optional[ToolsRegistry] = None

    @classmethod
    def _build_prompt_template(cls, config: PromptConfig) -> Runnable:
        return ChatAgentPromptTemplate(config.prompt_template)

    def _get_approvals(
        self, message: AIMessage, preapproved_tools: List[str]
    ) -> tuple[bool, list[UiChatLog]]:
        approval_required = False
        approval_messages = []

        for call in message.tool_calls:
            if (
                self.tools_registry
                and self.tools_registry.approval_required(call["name"])
                and call["name"] not in preapproved_tools
                and not getattr(self.model, "_is_agentic_mock_model", False)
            ):
                approval_required = True
                approval_messages.append(self._create_approval_message(call))

        return approval_required, approval_messages

    def _create_approval_message(self, tool_call: ToolCall) -> UiChatLog:
        return UiChatLog(
            message_type=MessageTypeEnum.REQUEST,
            message_sub_type=None,
            content=f"Tool {tool_call['name']} requires approval. Please confirm if you want to proceed.",
            timestamp=datetime.now(timezone.utc).isoformat(),
            status=ToolStatus.SUCCESS,
            correlation_id=None,
            tool_info=ToolInfo(name=tool_call["name"], args=tool_call["args"]),
            additional_context=None,
        )

    async def run(self, input: ChatWorkflowState) -> Dict[str, Any]:
        try:
            self._handle_approval_rejection(input)
            agent_response = await self._get_agent_response(input)

            self._log_abnormal_stop_reason(agent_response)

            if isinstance(agent_response, AIMessage):
                self._track_tokens_data(agent_response)

            return self._build_response(agent_response, input)

        except Exception as error:
            log.warning(f"Error processing chat agent: {error}")
            return self._create_error_response(error)

    def _handle_approval_rejection(self, input: ChatWorkflowState) -> None:
        approval_state = input.get("approval", None)
        if not isinstance(approval_state, ApprovalStateRejection):
            return

        last_message = input["conversation_history"][self.name][-1]
        tool_message_content = self._get_rejection_message(approval_state)

        messages = [
            ToolMessage(
                content=tool_message_content,
                tool_call_id=tool_call.get("id"),
            )
            for tool_call in getattr(last_message, "tool_calls", [])
        ]

        input["conversation_history"][self.name].extend(messages)

    def _get_rejection_message(self, approval_state: ApprovalStateRejection) -> str:
        # Handle null message from frontend
        # todo: remove this line once we have fixed the frontend to return None instead of 'null'
        # https://gitlab.com/gitlab-org/modelops/applied-ml/code-suggestions/ai-assist/-/issues/1259
        if approval_state.message == "null":
            approval_state.message = None

        if approval_state.message:
            return f"Tool is cancelled temporarily as user has a comment. Comment: {approval_state.message}"

        return "Tool is cancelled by user. Don't run the command and stop tool execution in progress."

    async def _get_agent_response(self, input: ChatWorkflowState) -> BaseMessage:
        with GitLabServiceContext(
            GitLabInstanceInfoService(),
            project=input.get("project"),
            namespace=input.get("namespace"),
        ):
            is_anthropic_model = self.model_provider == ModelClassProvider.ANTHROPIC
            return await super().ainvoke(
                input=input,
                agent_name=self.name,
                is_anthropic_model=is_anthropic_model,
            )

    def _log_abnormal_stop_reason(self, agent_response: BaseMessage) -> None:
        stop_reason = agent_response.response_metadata.get("stop_reason")
        if stop_reason in AnthropicStopReason.abnormal_values():
            log.warning(f"LLM stopped abnormally with reason: {stop_reason}")

    def _build_response(
        self, agent_response: BaseMessage, input: ChatWorkflowState
    ) -> Dict[str, Any]:
        if not isinstance(agent_response, AIMessage) or not agent_response.tool_calls:
            return self._build_text_response(agent_response)

        return self._build_tool_response(agent_response, input)

    def _build_text_response(self, agent_response: BaseMessage) -> Dict[str, Any]:
        ui_chat_log = UiChatLog(
            message_type=MessageTypeEnum.AGENT,
            message_sub_type=None,
            content=StrOutputParser().invoke(agent_response) or "",
            timestamp=datetime.now(timezone.utc).isoformat(),
            status=ToolStatus.SUCCESS,
            correlation_id=None,
            tool_info=None,
            additional_context=None,
        )

        return {
            "conversation_history": {self.name: [agent_response]},
            "status": WorkflowStatusEnum.INPUT_REQUIRED,
            "ui_chat_log": [ui_chat_log],
        }

    def _build_tool_response(
        self, agent_response: AIMessage, input: ChatWorkflowState
    ) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "conversation_history": {self.name: [agent_response]},
            "status": WorkflowStatusEnum.EXECUTION,
        }

        preapproved_tools = input.get("preapproved_tools") or []
        tools_need_approval, approval_messages = self._get_approvals(
            agent_response, preapproved_tools
        )

        if len(agent_response.tool_calls) > 0 and tools_need_approval:
            result["status"] = WorkflowStatusEnum.TOOL_CALL_APPROVAL_REQUIRED
            result["ui_chat_log"] = approval_messages

        return result

    def _create_error_response(self, error: Exception) -> Dict[str, Any]:
        error_message = HumanMessage(
            content=f"There was an error processing your request: {error}"
        )

        ui_chat_log = UiChatLog(
            message_type=MessageTypeEnum.AGENT,
            message_sub_type=None,
            content=(
                "There was an error processing your request. Please try again or contact support if "
                "the issue persists."
            ),
            timestamp=datetime.now(timezone.utc).isoformat(),
            status=ToolStatus.FAILURE,
            correlation_id=None,
            tool_info=None,
            additional_context=None,
        )

        return {
            "conversation_history": {self.name: [error_message]},
            "status": WorkflowStatusEnum.INPUT_REQUIRED,
            "ui_chat_log": [ui_chat_log],
        }

    def _track_tokens_data(self, message: AIMessage) -> None:
        if not self.internal_event_client:
            return

        usage_metadata: Any = message.usage_metadata or {}
        usage_dict: Dict[str, Any] = (
            usage_metadata.__dict__
            if hasattr(usage_metadata, "__dict__")
            else cast(Dict[str, Any], usage_metadata)
        )

        additional_properties = InternalEventAdditionalProperties(
            label=self.name,
            property=EventPropertyEnum.WORKFLOW_ID.value,
            value=_workflow_id.get(),
            input_tokens=usage_dict.get("input_tokens"),
            output_tokens=usage_dict.get("output_tokens"),
            total_tokens=usage_dict.get("total_tokens"),
        )

        self.internal_event_client.track_event(
            event_name=EventEnum.TOKEN_PER_USER_PROMPT.value,
            additional_properties=additional_properties,
            category=CategoryEnum.WORKFLOW_CHAT.value,
        )
