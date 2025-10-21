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
                # Returns both modified args and list of what was overridden
                bound_args, security_overrides = self._apply_argument_bindings(
                    tool_call_args=tool_call_args,
                    state=state,
                    tool_name=tool_name
                )
                
                response = await self._execute_tool(
                    tool=self._toolset[tool_name], tool_call_args=bound_args
                )
            
            # Sanitize the raw response before wrapping
            sanitized_response = self._sanitize_response(
                response=response, tool_name=tool_name
            )
            
            # Wrap response with just-in-time security instructions
            # (sanitization is applied inside this method to both response and instructions)
            wrapped_response = self._wrap_response_with_security_instructions(
                response=sanitized_response,
                security_overrides=security_overrides,
                tool_name=tool_name
            )

            if not isinstance(wrapped_response, (str, list, dict)):
                raise ValueError(
                    f"Invalid response type for tool {tool_name}: {wrapped_response}"
                )

            tools_responses.append(
                ToolMessage(
                    content=wrapped_response,
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

            return tool_call_result
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
        self, 
        tool_call_args: dict[str, Any], 
        state: FlowState,
        tool_name: str
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        """Apply tool_arguments_binding to override tool call arguments.
        
        This method enforces security boundaries by overriding agent-provided
        arguments with bound values from the flow state. This prevents prompt
        injection attacks where an agent might be manipulated into accessing
        resources outside its prescribed scope.
        
        SECURITY: If binding extraction fails, this method raises an exception
        rather than continuing without enforcement. This prevents attack vectors
        where malicious actors could manipulate state to bypass security.
        
        Uses template_variable_from_state() for consistent data extraction,
        which automatically handles alias resolution and nested key access.
        
        Args:
            tool_call_args: The arguments provided by the agent for the tool call
            state: The current flow state containing bound values
            tool_name: Name of the tool being called (for logging)
            
        Returns:
            Tuple of (modified_args, security_overrides):
            - modified_args: tool_call_args with bound values overriding agent choices
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
            return tool_call_args, []
        
        # Create a copy to avoid modifying the original
        bound_args = tool_call_args.copy()
        security_overrides = []
        
        # Extract bound values from state and override arguments
        for binding in self._tool_arguments_binding:
            try:
                # Extract bound value using template_variable_from_state
                # This returns a dict with one key-value pair:
                # - {alias: value} if alias is set
                # - {last_subkey: value} if subkeys exist
                # - {target: value} otherwise
                template_vars = binding.template_variable_from_state(state)
                
                # Get the parameter name (key) and bound value from template vars
                param_name, bound_value = next(iter(template_vars.items()))
                
                # Check if tool actually accepts this parameter
                tool = self._toolset[tool_name]
                if hasattr(tool, "args_schema") and tool.args_schema:
                    tool_params = tool.args_schema.model_fields.keys()
                    
                    if param_name in tool_params:
                        # Check if we're overriding an agent-provided value
                        if param_name in bound_args:
                            original_value = bound_args[param_name]
                            if original_value != bound_value:
                                # Record the override for just-in-time instructions
                                security_overrides.append({
                                    "parameter": param_name,
                                    "original": original_value,
                                    "overridden": bound_value,
                                })
                                
                                # Log the override
                                self._logger.info(
                                    f"tool_arguments_binding: Overriding {tool_name}.{param_name}",
                                    extra={
                                        "tool_name": tool_name,
                                        "parameter": param_name,
                                        "agent_value": str(original_value)[:100],
                                        "bound_value": str(bound_value)[:100],
                                        "component": self._component_name,
                                    }
                                )
                        
                        # Apply the binding - this is the security enforcement
                        bound_args[param_name] = bound_value
                        
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
                param_name = binding.get_key_name()
                    
                self._logger.error(
                    f"SECURITY: Failed to extract bound value for {tool_name}.{param_name}: {e}. "
                    f"Failing tool call to prevent security bypass.",
                    extra={
                        "tool_name": tool_name,
                        "parameter": param_name,
                        "binding_source": f"{binding.target}:{'.'.join(binding.subkeys or [])}",
                        "component": self._component_name,
                        "error_type": type(e).__name__,
                        "security_event": True,
                    }
                )
                
                # Re-raise to fail the tool call
                # This ensures security boundaries are always enforced
                raise RuntimeError(
                    f"Security enforcement failed: Cannot extract bound value for parameter '{param_name}' "
                    f"from '{binding.target}:{'.'.join(binding.subkeys or [])}'. "
                    f"Tool execution blocked to prevent potential security bypass. "
                    f"Original error: {type(e).__name__}: {e}"
                ) from e
        
        return bound_args, security_overrides

    def _wrap_response_with_security_instructions(
        self,
        response: str | dict | list,
        security_overrides: list[dict[str, Any]],
        tool_name: str
    ) -> str:
        """Wrap tool response with just-in-time security instructions.
        
        This method implements defense-in-depth by informing the agent about
        security overrides directly in the tool response. This makes it much
        harder for prompt injection attacks to bypass security constraints, as
        the security information is delivered in-band with the tool results.
        
        Security sanitization is applied independently to both the response
        and instructions before they are wrapped in XML tags.
        
        Args:
            response: The original tool response (already sanitized)
            security_overrides: List of parameter overrides that were applied
            tool_name: Name of the tool that was executed
            
        Returns:
            Wrapped response with security instructions if overrides occurred
            
        Examples:
            Without overrides:
            ```
            <tool-response>
            {"file": "content here"}
            </tool-response>
            ```
            
            With overrides:
            ```
            <tool-response>
            {"file": "content here"}
            </tool-response>
            <instructions>
            SECURITY NOTICE: Tool call arguments were overridden due to security constraints:
            - Parameter 'project_id': original value '999' was overridden to '42'
            
            You MUST operate within these security boundaries. Do not attempt to access
            resources outside the permitted scope.
            </instructions>
            ```
        """
        # Convert response to string if needed
        if isinstance(response, (dict, list)):
            import json
            response_str = json.dumps(response, indent=2)
        else:
            response_str = str(response)
        
        # If no overrides, return simple wrapped response
        if not security_overrides:
            return f"<tool-response>\n{response_str}\n</tool-response>"
        
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
            "SECURITY NOTICE: Tool call arguments were overridden due to security constraints:\n"
            + "\n".join(override_lines) +
            "\n\n"
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
                }
            )
            # Re-raise - do not fall back to unsanitized instructions
            raise
        
        # Wrap response and instructions with XML tags
        # Both are now independently sanitized
        wrapped = (
            f"<tool-response>\n"
            f"{response_str}\n"
            f"</tool-response>\n"
            f"<instructions>\n"
            f"{sanitized_instructions}\n"
            f"</instructions>"
        )
        
        return wrapped

    @staticmethod
    def _format_value_for_display(value: Any) -> str:
        """Format a value for display in security instructions.
        
        Args:
            value: The value to format
            
        Returns:
            String representation suitable for display
        """
        if isinstance(value, str):
            # Truncate long strings
            if len(value) > 100:
                return value[:97] + "..."
            return value
        elif isinstance(value, (int, float, bool, type(None))):
            return str(value)
        elif isinstance(value, (dict, list)):
            import json
            try:
                formatted = json.dumps(value)
                if len(formatted) > 100:
                    return formatted[:97] + "..."
                return formatted
            except (TypeError, ValueError):
                return str(value)[:100]
        else:
            return str(value)[:100]

    def _sanitize_response(
        self, response: str | dict | list, tool_name: str
    ) -> str | list[str | dict]:
        try:
            return PromptSecurity.apply_security_to_tool_response(
                response=response, tool_name=tool_name
            )
        except SecurityException as e:
            self._logger.error(f"Security validation failed for tool {tool_name}: {e}")
            raise

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
