import json
from datetime import datetime, timezone
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.checkpoint.memory import BaseCheckpointSaver
from langgraph.graph import END, StateGraph

from duo_workflow_service.agents import HandoverAgent
from duo_workflow_service.components import ToolsRegistry
from duo_workflow_service.entities import (
    MessageTypeEnum,
    Plan,
    ToolStatus,
    UiChatLog,
    WorkflowState,
    WorkflowStatusEnum,
)
from duo_workflow_service.llm_factory import create_chat_model, AnthropicConfig
from ai_gateway.models import KindAnthropicModel
from duo_workflow_service.tracking import log_exception
from duo_workflow_service.workflows.abstract_workflow import (
    MAX_TOKENS_TO_SAMPLE,
    RECURSION_LIMIT,
    AbstractWorkflow,
)

AGENT_NAME = "simple_llm_agent"


class Workflow(AbstractWorkflow):
    def _parse_goal(self, goal: str) -> tuple[str, str]:
        """Parse goal input and return (system_prompt, user_prompt) tuple.

        The goal can be either:
        1. A plain string - uses default system prompt
        2. A JSON string representing a GoalObject with system_prompt and user_prompt
        """
        try:
            # Try to parse as JSON first
            goal_data = json.loads(goal)
            if (
                isinstance(goal_data, dict)
                and "system_prompt" in goal_data
                and "user_prompt" in goal_data
            ):
                return goal_data["system_prompt"], goal_data["user_prompt"]
        except (json.JSONDecodeError, KeyError):
            # If JSON parsing fails or required keys are missing, treat as plain string
            pass

        # Default system prompt for string goals
        return "Answer in a jokey/comedic fashion", goal

    async def _send_llm_prompt(self, state: WorkflowState) -> dict:
        """Send a simple prompt to the LLM and return the response."""
        # Get the goal from state (stored in last_human_input)
        goal = state.get("last_human_input", "Hello, how can you help me?")

        # Parse the goal to extract system and user prompts
        system_prompt, user_prompt = self._parse_goal(goal)

        # Debug: Log the model config
        self.log.info(f"Model config type: {type(self._model_config)}")
        self.log.info(f"Model config: {self._model_config}")
        self.log.info(f"Using system prompt: {system_prompt[:100]}...")
        self.log.info(f"Using user prompt: {user_prompt[:100]}...")

        # Create the LLM model using the workflow's model config
        # Add fallback in case model config is still None
        model_config = self._model_config
        if model_config is None:
            self.log.warning("Model config is None, using fallback AnthropicConfig")
            model_config = AnthropicConfig(
                model_name=KindAnthropicModel.CLAUDE_SONNET_4.value
            )

        model = create_chat_model(
            max_tokens=MAX_TOKENS_TO_SAMPLE,
            config=model_config,
        )

        # Send the prompt to the LLM with custom system and user prompts
        system_message = SystemMessage(content=system_prompt)
        user_message = HumanMessage(content=user_prompt)
        messages = [system_message, user_message]

        response = await model.ainvoke(messages)

        # Create a UI chat log entry for the response
        ui_log = UiChatLog(
            message_type=MessageTypeEnum.TOOL,
            message_sub_type=None,
            content=f"LLM Response: {response.content}",
            timestamp=datetime.now(timezone.utc).isoformat(),
            status=ToolStatus.SUCCESS,
            correlation_id=None,
            tool_info=None,
            context_elements=None,
        )

        return {
            "conversation_history": {
                AGENT_NAME: [system_message, user_message, response]
            },
            "ui_chat_log": [ui_log],
            "status": WorkflowStatusEnum.EXECUTION,
        }

    async def _handle_workflow_failure(
        self, error: BaseException, compiled_graph: Any, graph_config: Any
    ):
        log_exception(error, extra={"workflow_id": self._workflow_id})

    def _recursion_limit(self):
        return RECURSION_LIMIT

    def _compile(
        self,
        goal: str,
        tools_registry: ToolsRegistry,
        checkpointer: BaseCheckpointSaver,
    ):
        graph = StateGraph(WorkflowState)

        # Setup simple workflow graph
        graph = self._setup_simple_workflow_graph(graph, goal)

        return graph.compile(checkpointer=checkpointer)

    def _setup_simple_workflow_graph(self, graph: StateGraph, goal: str):
        """Setup a simple workflow that just sends a prompt to LLM and completes."""
        self.log.info("Starting simple LLM workflow graph compilation")

        # Set entry point
        graph.set_entry_point("send_prompt")

        # Add node to send prompt to LLM
        graph.add_node("send_prompt", self._send_llm_prompt)

        # Add completion node
        graph.add_node(
            "complete",
            HandoverAgent(
                new_status=WorkflowStatusEnum.COMPLETED, handover_from=AGENT_NAME
            ).run,
        )

        # Add edges
        graph.add_edge("send_prompt", "complete")
        graph.add_edge("complete", END)

        return graph

    def get_workflow_state(self, goal: str) -> WorkflowState:  # type: ignore[override]
        # Parse goal to get display text for UI
        try:
            goal_data = json.loads(goal)
            if isinstance(goal_data, dict) and "user_prompt" in goal_data:
                display_text = goal_data["user_prompt"]
            else:
                display_text = str(goal)
        except (json.JSONDecodeError, KeyError):
            display_text = str(goal)

        initial_ui_chat_log = UiChatLog(
            message_type=MessageTypeEnum.TOOL,
            message_sub_type=None,
            content=f"Starting simple LLM workflow with prompt: {display_text}",
            timestamp=datetime.now(timezone.utc).isoformat(),
            status=ToolStatus.SUCCESS,
            correlation_id=None,
            tool_info=None,
            context_elements=None,
        )

        return WorkflowState(
            status=WorkflowStatusEnum.NOT_STARTED,
            ui_chat_log=[initial_ui_chat_log],
            conversation_history={},
            plan=Plan(steps=[]),
            handover=[],
            last_human_input=goal,  # Store the full goal string in last_human_input
            files_changed=[],
        )
