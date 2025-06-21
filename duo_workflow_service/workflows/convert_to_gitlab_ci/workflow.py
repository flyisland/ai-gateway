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
    def _parse_goal(self, goal: str) -> list[dict]:
        """Parse goal input and return list of LLM steps.

        The goal can be either:
        1. A plain string - creates single step with default system prompt
        2. A JSON string with system_prompt and user_prompt - creates single step
        3. A JSON string with llm_steps array - returns the steps list
        """
        try:
            # Try to parse as JSON first
            goal_data = json.loads(goal)
            if isinstance(goal_data, dict):
                # Check if it has llm_steps array
                if "llm_steps" in goal_data and isinstance(
                    goal_data["llm_steps"], list
                ):
                    return goal_data["llm_steps"]
                # Check if it's a single step format
                elif "system_prompt" in goal_data and "user_prompt" in goal_data:
                    return [
                        {
                            "system_prompt": goal_data["system_prompt"],
                            "user_prompt": goal_data["user_prompt"],
                        },
                        {
                            "system_prompt": "You are a professional french translator.",
                            "user_prompt": "Please translate this into french:\n<input>{{input}}</input>",
                        },
                    ]
        except (json.JSONDecodeError, KeyError):
            # If JSON parsing fails, treat as plain string
            pass

        # Default single step for string goals
        return [
            {"system_prompt": "Answer in a jokey/comedic fashion", "user_prompt": goal},
            {
                "system_prompt": "You are a professional french translator.",
                "user_prompt": "Please translate this into french:\n<input>{{input}}</input>",
            },
        ]

    async def _process_llm_steps(self, state: WorkflowState) -> dict:
        """Process all LLM steps sequentially."""
        # Get the goal from state (stored in last_human_input)
        goal = state.get("last_human_input", "Hello, how can you help me?")

        # Parse the goal to extract LLM steps
        llm_steps = self._parse_goal(goal)

        # Debug: Log the steps
        self.log.info(f"Processing {len(llm_steps)} LLM steps")

        # Initialize conversation history and UI logs
        conversation_messages = []
        ui_logs = []

        # Process each step
        for step_index, step in enumerate(llm_steps):
            self.log.info(f"Processing step {step_index + 1}/{len(llm_steps)}")

            # Extract prompts from step
            system_prompt = step.get("system_prompt", "You are a helpful assistant.")
            user_prompt = step.get("user_prompt", "Hello")

            # For steps after the first, we can use the previous response as input
            if step_index > 0 and "{{input}}" in user_prompt:
                # Get the last AI response
                previous_response = ""
                for message in reversed(conversation_messages):
                    if hasattr(message, "content") and not isinstance(
                        message, (SystemMessage, HumanMessage)
                    ):
                        previous_response = message.content
                        break
                user_prompt = user_prompt.replace("{{input}}", previous_response)

            self.log.info(
                f"Step {step_index + 1} - System prompt: {system_prompt[:100]}..."
            )
            self.log.info(
                f"Step {step_index + 1} - User prompt: {user_prompt[:100]}..."
            )

            # Create the LLM model
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

            # Send the prompt to the LLM
            system_message = SystemMessage(content=system_prompt)
            user_message = HumanMessage(content=user_prompt)
            messages = [system_message, user_message]

            response = await model.ainvoke(messages)

            # Add messages to conversation history
            conversation_messages.extend([system_message, user_message, response])

            # Create UI chat log entry
            ui_log = UiChatLog(
                message_type=MessageTypeEnum.TOOL,
                message_sub_type=None,
                content=f"Step {step_index + 1} Response: {response.content}",
                timestamp=datetime.now(timezone.utc).isoformat(),
                status=ToolStatus.SUCCESS,
                correlation_id=None,
                tool_info=None,
                context_elements=None,
            )
            ui_logs.append(ui_log)

        return {
            "conversation_history": {AGENT_NAME: conversation_messages},
            "ui_chat_log": ui_logs,
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
        """Setup a dynamic workflow that processes a list of LLM steps sequentially."""
        self.log.info("Starting dynamic LLM workflow graph compilation")

        # Set entry point
        graph.set_entry_point("process_llm_steps")

        # Add node to process all LLM steps
        graph.add_node("process_llm_steps", self._process_llm_steps)

        # Add completion node
        graph.add_node(
            "complete",
            HandoverAgent(
                new_status=WorkflowStatusEnum.COMPLETED, handover_from=AGENT_NAME
            ).run,
        )

        # Add edges
        graph.add_edge("process_llm_steps", "complete")
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
