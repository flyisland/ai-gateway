import json
from typing import Any

import structlog
from langchain_core.messages import ToolMessage
from langchain_core.tools import BaseTool
from pydantic_core import ValidationError

from duo_workflow_service.agent_platform.experimental.components.agent.ui_log import (
    UILogEventsAgent,
    UILogWriterAgentTools,
)
from duo_workflow_service.agent_platform.experimental.state import (
    FlowState,
    FlowStateKeys,
    IOKey,
)
from duo_workflow_service.agent_platform.experimental.state.base import (
    get_vars_from_state,
)
from duo_workflow_service.agent_platform.experimental.ui_log import UIHistory
from duo_workflow_service.monitoring import duo_workflow_metrics
from duo_workflow_service.security.prompt_security import (
    PromptSecurity,
    SecurityException,
)
from duo_workflow_service.tools.toolset import Toolset
from lib.internal_events import InternalEventAdditionalProperties, InternalEventsClient
from lib.internal_events.event_enum import CategoryEnum, EventEnum, EventLabelEnum

__all__ = ["ToolNode"]


class ToolNode:
    def __init__(
        self,
        *,
        name: str,
        component_name: str,
        toolset: Toolset,
        tool_arguments_binding: list[IOKey],
        flow_id: str,
        flow_type: CategoryEnum,
        internal_event_client: InternalEventsClient,
        ui_history: UIHistory[UILogWriterAgentTools, UILogEventsAgent],
    ):
        self.name = name
        self._component_name = component_name
        self._toolset = toolset
        self._tool_arguments_binding = tool_arguments_binding
        self._flow_id = flow_id
        self._flow_type = flow_type
        self._internal_event_client = internal_event_client
        self._logger = structlog.stdlib.get_logger("agent_platform")
        self._ui_history = ui_history

    async def run(self, state: FlowState) -> dict:
        conversation_history = state[FlowStateKeys.CONVERSATION_HISTORY].get(
            self._component_name, []
        )

        # TODO: add ability to register all tool calls in a follow up
        # context = state["context"].get(self.component_name, {})
        # context.setdefault("tool_calls", [])

        last_message = conversation_history[-1]
        tool_calls = getattr(last_message, "tool_calls", [])
        tools_responses = []

        for tool_call in tool_calls:
            tool_name = tool_call["name"]
            tool_call_args = tool_call.get("args", {})
            tool_call_id = tool_call.get("id")

            if tool_name not in self._toolset:
                response = f"Tool {tool_name} not found"
                security_overrides = []
            else:
                # Apply argument bindings to enforce security boundaries
                # Returns list of what was overridden
                security_overrides = self._apply_argument_bindings(
                    tool_call_args=tool_call_args, state=state, tool_name=tool_name
                )

                response = await self._execute_tool(
                    tool=self._toolset[tool_name], tool_call_args=tool_call_args
                )

            # Sanitize and wrap response in <tool-response> tags
            response = self._sanitize_response(
                response=response,
                tool_name=tool_name,
            )
            # Attach security instructions if overrides occurred
            response = self._attach_jit_instructions(
                response=response,
                tool_name=tool_name,
                security_overrides=security_overrides,
            )

            tools_responses.append(
                ToolMessage(
                    content=response,
                    tool_call_id=tool_call_id,
                )
            )

        return {
            **self._ui_history.pop_state_updates(),
            FlowStateKeys.CONVERSATION_HISTORY: {
                self._component_name: tools_responses,
            },
        }

    async def _execute_tool(
        self, tool_call_args: dict[str, Any], tool: BaseTool
    ) -> str:
        try:
            with duo_workflow_metrics.time_tool_call(
                tool_name=tool.name, flow_type=self._flow_type.value
            ):
                tool_call_result = await tool.arun(tool_call_args)

            self._track_internal_event(
                event_name=EventEnum.WORKFLOW_TOOL_SUCCESS,
                tool_name=tool.name,
            )

            self._ui_history.log.success(
                tool=tool,
                tool_call_args=tool_call_args,
                event=UILogEventsAgent.ON_TOOL_EXECUTION_SUCCESS,
            )

            # Convert response to string if needed
            if isinstance(tool_call_result, (dict, list)):
                response_str = json.dumps(tool_call_result, indent=2)
            else:
                response_str = str(tool_call_result)

            return response_str
        except Exception as e:
            self._ui_history.log.error(
                tool=tool,
                tool_call_args=tool_call_args,
                event=UILogEventsAgent.ON_TOOL_EXECUTION_FAILED,
            )

            if isinstance(e, TypeError):
                err_format = self._format_type_error_response(tool=tool, error=e)
            elif isinstance(e, ValidationError):
                err_format = self._format_validation_error(tool_name=tool.name, error=e)
            else:
                err_format = self._format_execution_error(tool_name=tool.name, error=e)

            return err_format

    def _apply_argument_bindings(
        self, tool_call_args: dict[str, Any], state: FlowState, tool_name: str
    ) -> list[dict[str, Any]]:
        """Apply tool_arguments_binding to override tool call arguments.

        This method enforces security boundaries by overriding agent-provided
        arguments with bound values from the flow state. This prevents prompt
        injection attacks where an agent might be manipulated into accessing
        resources outside its prescribed scope.

        SECURITY: If binding extraction fails, this method raises an exception
        rather than continuing without enforcement. This prevents attack vectors
        where malicious actors could manipulate state to bypass security.

        Args:
            tool_call_args: The arguments provided by the agent for the tool call
            state: The current flow state containing bound values
            tool_name: Name of the tool being called (for logging)

        Returns:
            - security_overrides: list of override records for just-in-time instructions

        Raises:
            RuntimeError: If bound value cannot be extracted from state (security enforcement)

        Examples:
            Binding: from "context:project_id"
            State: {"context": {"project_id": 42}}
            Agent args: {"project_id": 999, "file": "x"}
            Result: ({"project_id": 42, "file": "x"}, [{"parameter": "project_id", "original": 999, "overridden": 42}])
        """
        if not self._tool_arguments_binding:
            return []

        try:
            overrides = get_vars_from_state(self._tool_arguments_binding, state)
        except (KeyError, TypeError) as e:
            # KeyError: Bound value path doesn't exist in state
            #   - Missing nested key (e.g., context.user.profile.id when profile missing)
            #   - Component hasn't produced expected output yet
            #   - Typo in binding path
            # TypeError: State value has unexpected type
            #   - Expected dict but got string/list/other type
            #   - Attempting to traverse non-dict value
            #
            # SECURITY: We MUST fail fast here rather than continue without enforcement.
            # Allowing the tool call to proceed with agent's arguments creates an attack vector:
            # An attacker could manipulate state to cause binding extraction failure,
            # thereby bypassing security boundaries.

            self._logger.error(
                f"SECURITY: Failed to extract bound value for {tool_name}: {e}. "
                f"Failing tool call to prevent security bypass.",
                extra={
                    "tool_name": tool_name,
                    "component": self._component_name,
                    "error_type": type(e).__name__,
                },
            )

            # Re-raise to fail the tool call
            # This ensures security boundaries are always enforced
            raise RuntimeError(
                f"Security enforcement failed at {self.name}: Cannot extract bound value"
                f"Tool {tool_name} execution blocked to prevent potential security bypass. "
                f"Original error: {type(e).__name__}: {e}"
            ) from e

        security_overrides = []

        # Use set intersection to efficiently find parameters that need overriding
        # Only process parameters that are both bound AND present in tool call args
        params_to_check = set(overrides.keys()) & set(tool_call_args.keys())

        for param_name in params_to_check:
            bound_value = overrides[param_name]
            original_value = tool_call_args[param_name]

            # Skip if values already match (no override needed)
            if original_value == bound_value:
                continue

            # Record the override for just-in-time instructions
            security_overrides.append(
                {
                    "parameter": param_name,
                    "original": original_value,
                    "overridden": bound_value,
                }
            )

            # Log the override
            self._logger.info(
                f"tool_arguments_binding: Overriding {tool_name}.{param_name}",
                extra={
                    "tool_name": tool_name,
                    "parameter": param_name,
                    "agent_value": str(original_value)[:100],
                    "bound_value": str(bound_value)[:100],
                    "component": self._component_name,
                },
            )

            # Apply the binding - this is the security enforcement
            tool_call_args[param_name] = bound_value

        return security_overrides

    def _sanitize_response(
        self,
        response: str,
        tool_name: str,
    ) -> str:
        """Sanitize tool response and wrap it in a JIT just-in-time instructions format.

        Args:
            response: The original tool response
            tool_name: Name of the tool that was executed
            security_overrides: List of parameter overrides that were applied

        Returns:
            Sanitized and wrapped response

        Raises:
            SecurityException: If sanitization fails
        """
        try:
            # First sanitize the raw response
            sanitized_response = PromptSecurity.apply_security_to_tool_response(
                response=response, tool_name=tool_name
            )
        except SecurityException as e:
            self._logger.error(f"Security validation failed for tool {tool_name}: {e}")
            raise

        return f"<tool-response>\n{sanitized_response}\n</tool-response>"

    def _attach_jit_instructions(
        self, response: str, security_overrides: list[dict[str, Any]], tool_name: str
    ) -> str:
        """Attach just-in-time instructions to the response.

        If any argument overrides were applied, create and attach security
        instructions describing what was overridden and why.

        Args:
            response: The tool response (stringified if needed)
            security_overrides: List of parameter overrides that were applied
            tool_name: Name of the tool that was executed):

        Returns:
            Response wrapped with just-in-time instructions
        """
        if not security_overrides:
            return response

        # Build security instructions with override details
        override_lines = []
        for override in security_overrides:
            param = override["parameter"]
            original = self._format_value_for_display(override["original"])
            overridden = self._format_value_for_display(override["overridden"])
            override_lines.append(
                f"- Parameter '{param}': original value '{original}' was overridden to '{overridden}'"
            )

        instructions = (
            f"SECURITY NOTICE: Tool {tool_name} call arguments were overridden due to security constraints:\n"
            + "\n".join(override_lines)
            + "\n\n"
            "You MUST operate within these security boundaries. Do not attempt to access "
            "resources outside the permitted scope."
        )

        # Apply security sanitization to instructions independently
        # SECURITY: If sanitization fails, we must re-raise rather than fall back.
        # Unsanitized instructions could contain injection vectors.
        try:
            sanitized_instructions = PromptSecurity.apply_security_to_tool_response(
                response=instructions, tool_name=f"{tool_name}_security_instructions"
            )
        except SecurityException as e:
            self._logger.error(
                f"SECURITY: Instruction sanitization failed for tool {tool_name}: {e}. "
                f"Blocking tool response to prevent security bypass.",
                extra={
                    "tool_name": tool_name,
                    "component": self._component_name,
                    "security_event": True,
                },
            )
            # Re-raise - do not fall back to unsanitized instructions
            raise

        return (
            f"{response}\n"
            f"<instructions>\n"
            f"{sanitized_instructions}\n"
            f"</instructions>"
        )

    @staticmethod
    def _format_value_for_display(value: Any) -> str:
        """Format a value for display in security instructions.

        Args:
            value: The value to format

        Returns:
            String representation suitable for display
        """
        if isinstance(value, (int, float, bool, type(None))):
            value = str(value)
        elif isinstance(value, (dict, list)):
            try:
                value = json.dumps(value)
            except (TypeError, ValueError):
                value = str(value)

        # Truncate long strings
        if len(value) > 100:
            return value[:97] + "..."
        return value

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
            value=self._flow_id,
            **extra,
        )
        self._record_metric(
            event_name=event_name,
            additional_properties=additional_properties,
        )
        self._internal_event_client.track_event(
            event_name=event_name.value,
            additional_properties=additional_properties,
            category=self._flow_type.value,
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
                flow_type=self._flow_type.value,
                tool_name=tool_name,
                failure_reason=failure_reason,
            )
