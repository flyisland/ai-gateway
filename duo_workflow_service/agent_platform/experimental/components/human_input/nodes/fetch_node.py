from typing import Any

from langchain_core.messages import HumanMessage
from langgraph.types import interrupt
from pydantic import BaseModel

from duo_workflow_service.agent_platform.experimental.state import (
    FlowEvent,
    FlowEventType,
    FlowState,
    FlowStateKeys,
    IOKey,
)
from duo_workflow_service.entities.state import WorkflowStatusEnum

__all__ = ["FetchNode"]


class FetchNode(BaseModel):
    """Node that fetches user input via interrupt() and creates HumanMessage."""

    name: str
    component_name: str
    responds_to: str
    output: IOKey

    async def run(
        self, state: FlowState  # pylint: disable=unused-argument
    ) -> dict[str, Any]:
        """Execute the fetch node - interrupt for user input and create HumanMessage."""
        # Interrupt workflow to wait for user input
        event: FlowEvent = interrupt("Workflow interrupted; waiting for user input.")

        # Handle different event types
        if event["event_type"] in (FlowEventType.APPROVE, FlowEventType.REJECT):
            # Handle approval/rejection events
            # Store the user decision in the specified output location
            approval_value = event["event_type"].value  # "approve" or "reject"
            result = {
                FlowStateKeys.STATUS: WorkflowStatusEnum.EXECUTION.value,
                **self.output.to_nested_dict(approval_value),
            }

            # For REJECT events, also add HumanMessage to conversation history
            if event["event_type"] == FlowEventType.REJECT and "message" in event:
                human_message = HumanMessage(content=event["message"])
                result[FlowStateKeys.CONVERSATION_HISTORY] = {
                    self.responds_to: [human_message]
                }

            return result

        if event["event_type"] == FlowEventType.RESPONSE:
            # Extract user message from event
            user_message = event["message"]

            # Create HumanMessage for conversation history
            human_message = HumanMessage(content=user_message)

            # Return the message targeted to the responds_to component
            return {
                FlowStateKeys.STATUS: WorkflowStatusEnum.EXECUTION.value,
                FlowStateKeys.CONVERSATION_HISTORY: {self.responds_to: [human_message]},
            }

        # For any other event type, raise error as this should not happen
        raise ValueError(
            f"Unknown event type: {event['event_type']}. Expected one of: {list(FlowEventType)}"
        )
