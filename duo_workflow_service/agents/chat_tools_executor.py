import copy
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import structlog
from langchain_core.tools import BaseTool
from dependency_injector.wiring import Provide, inject
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage
from langchain_core.messages.tool import ToolCall
from langchain_core.output_parsers.string import StrOutputParser
from langgraph.types import Command
from pydantic import ValidationError

from ai_gateway.container import ContainerApplication
from duo_workflow_service.entities import WorkflowStatusEnum
from duo_workflow_service.entities.state import (
    DuoWorkflowStateType,
    MessageTypeEnum,
    ToolInfo,
    ToolStatus,
    UiChatLog,
)
from duo_workflow_service.monitoring import duo_workflow_metrics
from duo_workflow_service.tools import (
    Toolset,
    format_tool_display_message,
)
from lib.internal_events import InternalEventAdditionalProperties, InternalEventsClient
from lib.internal_events.event_enum import CategoryEnum, EventEnum, EventLabelEnum


class ChatToolsExecutor:
    @inject
    def __init__(
        self,
        tools_agent_name: str,
        toolset: Toolset,
        workflow_id: str,
        workflow_type: CategoryEnum,
        internal_event_client: InternalEventsClient = Provide[
            ContainerApplication.internal_event.client
        ],
    ) -> None:
        self._tools_agent_name = tools_agent_name
        self._toolset = toolset
        self._workflow_id = workflow_id
        self._logger = structlog.stdlib.get_logger("workflow")
        self._workflow_type = workflow_type
        self._internal_event_client = internal_event_client

    async def run(self, state: DuoWorkflowStateType):
        conversation_history = state["conversation_history"].get(self._tools_agent_name, [])
        last_message = conversation_history[-1]
        tool_calls: list[ToolCall] = getattr(last_message, "tool_calls", [])
        ui_chat_logs: List[UiChatLog] = []
        tool_responses = []

        self._create_ai_message_ui_chat_log(last_message, ui_chat_logs)

        for tool_call in tool_calls:
            tool_name = tool_call["name"]
            tool_call_args = tool_call.get("args", {})
            tool_call_id = tool_call.get("id")

            if tool_name not in self._toolset:
                response = f"Tool {tool_name} not found"
                ui_chat_logs.extend([])  # No chat logs for missing tools
            else:
                result = await self._execute_tool(
                    tool_call_args=tool_call_args, tool=self._toolset[tool_name], tool_name=tool_name
                )
                response = result.get("response")
                ui_chat_logs.extend(result.get("chat_logs", []))

            if not isinstance(response, (str, list, dict)):
                raise ValueError(
                    f"Invalid response type for tool {tool_name}: {response}"
                )

            tool_responses.append(
                ToolMessage(
                    content=response if isinstance(response, str) else str(response),
                    tool_call_id=tool_call_id,
                )
            )

        updated_conversation_history = conversation_history + tool_responses

        return {
            "conversation_history": {
                self._tools_agent_name: updated_conversation_history,
            },
            "ui_chat_log": ui_chat_logs,
        }

    def _create_tool_ui_chat_log(
        self,
        tool_name: str,
        tool_args: Dict[str, Any],
        status: ToolStatus = ToolStatus.SUCCESS,
        error_message: Optional[str] = None,
        tool_response: Optional[Any] = None,
    ) -> Optional[UiChatLog]:
        display_message = self.get_tool_display_message(tool_name, tool_args, tool_response)

        if not display_message:
            return None

        content = display_message
        if error_message:
            content = f"Failed: {display_message} - {error_message}"

        return UiChatLog(
            message_type=MessageTypeEnum.TOOL,
            message_sub_type=tool_name,
            content=content,
            timestamp=datetime.now(timezone.utc).isoformat(),
            status=status,
            correlation_id=None,
            tool_info=(
                ToolInfo(name=tool_name, args=tool_args)
                if status != ToolStatus.SUCCESS
                else None
            ),
            additional_context=None,
        )

    def get_tool_display_message(
        self, tool_name: str, args: Dict[str, Any], tool_response: Any = None
    ) -> Optional[str]:
        args_str = ", ".join(f"{k}={v}" for k, v in args.items())
        message = f"Using {tool_name}: {args_str}"

        if tool_name in self._toolset:
            tool = self._toolset[tool_name]
            message = (
                format_tool_display_message(tool, args, tool_response or "") or message
            )

        return message

    def _extract_ai_message_text(self, last_message: BaseMessage):
        if isinstance(last_message, AIMessage):
            return StrOutputParser().invoke(last_message)

        return None

    def _create_ai_message_ui_chat_log(
        self, message: BaseMessage, ui_chat_logs: List[UiChatLog]
    ):
        ai_message_content = self._extract_ai_message_text(message)

        if ai_message_content:
            ui_chat_logs.append(
                UiChatLog(
                    message_type=MessageTypeEnum.AGENT,
                    message_sub_type=None,
                    content=ai_message_content,
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    status=ToolStatus.SUCCESS,
                    correlation_id=None,
                    tool_info=None,
                    additional_context=None,
                )
            )

    def _add_tool_ui_chat_log(
        self,
        tool_info: Dict[str, Any],
        status: ToolStatus,
        ui_chat_logs: List[UiChatLog],
        error_message: Optional[str] = None,
        tool_response: Optional[Any] = None,
    ):
        chat_log = self._create_tool_ui_chat_log(
            tool_name=tool_info["name"],
            tool_args=tool_info["args"],
            status=status,
            error_message=error_message,
            tool_response=tool_response,
        )
        if chat_log:
            ui_chat_logs.append(chat_log)

    async def _execute_tool(
        self, tool_call_args: dict[str, Any], tool: BaseTool, tool_name: str
    ) -> Dict[str, Any]:
        chat_logs: List[UiChatLog] = []
        
        try:
            with duo_workflow_metrics.time_tool_call(tool_name=tool.name):
                tool_call_result = await tool.arun(tool_call_args)

            self._track_internal_event(
                event_name=EventEnum.WORKFLOW_TOOL_SUCCESS,
                tool_name=tool.name,
            )

            self._add_tool_ui_chat_log(
                tool_info={"name": tool_name, "args": tool_call_args},
                status=ToolStatus.SUCCESS,
                ui_chat_logs=chat_logs,
                tool_response=tool_call_result,
            )

            return {
                "response": tool_call_result,
                "chat_logs": chat_logs,
            }
        except Exception as e:
            if isinstance(e, TypeError):
                err_format = self._format_type_error_response(tool=tool, error=e)
                self._add_tool_ui_chat_log(
                    tool_info={"name": tool_name, "args": tool_call_args},
                    status=ToolStatus.FAILURE,
                    ui_chat_logs=chat_logs,
                    error_message="Invalid arguments",
                )
            elif isinstance(e, ValidationError):
                err_format = self._format_validation_error(tool_name=tool.name, error=e)
                self._add_tool_ui_chat_log(
                    tool_info={"name": tool_name, "args": tool_call_args},
                    status=ToolStatus.FAILURE,
                    ui_chat_logs=chat_logs,
                    error_message="Validation error",
                )
            else:
                err_format = self._format_execution_error(tool_name=tool.name, error=e)
                self._add_tool_ui_chat_log(
                    tool_info={"name": tool_name, "args": tool_call_args},
                    status=ToolStatus.FAILURE,
                    ui_chat_logs=chat_logs,
                    error_message="Execution error",
                )

            return {
                "response": err_format,
                "chat_logs": chat_logs,
            }


    def _track_internal_event(
        self,
        event_name: EventEnum,
        tool_name,
        extra=None,
    ):
        if extra is None:
            extra = {}
        additional_properties = InternalEventAdditionalProperties(
            label=EventLabelEnum.WORKFLOW_TOOL_CALL_LABEL.value,
            property=tool_name,
            value=self._workflow_id,
            **extra,
        )
        self._record_metric(
            event_name=event_name,
            additional_properties=additional_properties,
        )
        self._internal_event_client.track_event(
            event_name=event_name.value,
            additional_properties=additional_properties,
            category=self._workflow_type.value,
        )

    def _format_type_error_response(self, tool: BaseTool, error: TypeError) -> str:
        if tool.args_schema:
            schema = f"The schema is: {tool.args_schema.model_json_schema()}"  # type: ignore[union-attr]
        else:
            schema = "The tool does not accept any argument"

        response = (
            f"Tool {tool.name} execution failed due to wrong arguments."
            f" You must adhere to the tool args schema! {schema}"
        )

        self._track_internal_event(
            event_name=EventEnum.WORKFLOW_TOOL_FAILURE,
            tool_name=tool.name,
            extra={
                "error": str(error),
                "error_type": type(error).__name__,
            },
        )

        return response

    def _format_validation_error(
        self,
        tool_name: str,
        error: ValidationError,
    ) -> str:
        self._track_internal_event(
            event_name=EventEnum.WORKFLOW_TOOL_FAILURE,
            tool_name=tool_name,
            extra={
                "error": str(error),
                "error_type": type(error).__name__,
            },
        )
        return f"Tool {tool_name} raised validation error {str(error)}"

    def _format_execution_error(
        self,
        tool_name: str,
        error: Exception,
    ) -> str:
        self._track_internal_event(
            event_name=EventEnum.WORKFLOW_TOOL_FAILURE,
            tool_name=tool_name,
            extra={
                "error": str(error),
                "error_type": type(error).__name__,
            },
        )

        return f"Tool runtime exception due to {str(error)}"

    def _record_metric(
        self,
        event_name: EventEnum,
        additional_properties: InternalEventAdditionalProperties,
    ) -> None:
        if event_name == EventEnum.WORKFLOW_TOOL_FAILURE:
            tool_name = additional_properties.property or "unknown"
            failure_reason = additional_properties.extra.get("error_type", "unknown")
            duo_workflow_metrics.count_agent_platform_tool_failure(
                flow_type=self._workflow_type.value,
                tool_name=tool_name,
                failure_reason=failure_reason,
            )
