import math
import os
import random
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

import yaml
from langgraph.checkpoint.memory import BaseCheckpointSaver
from langgraph.graph import END, StateGraph
from langgraph.types import Command
from pydantic import BaseModel, Field

from duo_workflow_service.agent_registry.components.base import (
    DEFAULT_ROUTE,
    AgentComponent,
    AgentFinalOutput,
    EndComponent,
    HiltChatBackComponent,
    Router,
    attach_components_to_graph,
)
from duo_workflow_service.checkpointer.gitlab_workflow import WorkflowStatusEventEnum
from duo_workflow_service.components.tools_registry import ToolsRegistry
from duo_workflow_service.entities.state import (
    MessageTypeEnum,
    PoCWorkflowState,
    ToolStatus,
    UiChatLog,
    WorkflowStatusEnum,
)
from duo_workflow_service.tracking.errors import log_exception
from duo_workflow_service.workflows.abstract_workflow import AbstractWorkflow
from duo_workflow_service.workflows.chat.workflow import (
    CHAT_MUTATION_TOOLS,
    CHAT_READ_ONLY_TOOLS,
)

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


class Workflow(AbstractWorkflow):
    def load_yaml_config(
        self, config_key: str = "example_issue_to_mr_workflow"
    ) -> dict:
        """Load YAML configuration from proposal.yaml file.

        Args:
            config_key: The key to extract from the YAML file (default: "example_issue_to_mr_workflow")

        Returns:
            dict: The configuration dictionary for the specified key

        Raises:
            FileNotFoundError: If proposal.yaml is not found
            KeyError: If the specified config_key is not found in the YAML
            yaml.YAMLError: If there's an error parsing the YAML file
        """
        try:
            # Get the path to proposal.yaml relative to the project root
            current_dir = os.path.dirname(os.path.abspath(__file__))
            project_root = os.path.join(current_dir, "..", "..", "..")
            yaml_path = os.path.join(project_root, "proposal.yaml")

            with open(yaml_path, "r", encoding="utf-8") as file:
                yaml_content = yaml.safe_load(file)

            if config_key not in yaml_content:
                raise KeyError(
                    f"Configuration key '{config_key}' not found in proposal.yaml"
                )

            return yaml_content[config_key]

        except FileNotFoundError:
            raise FileNotFoundError("proposal.yaml file not found in project root")
        except yaml.YAMLError as e:
            raise yaml.YAMLError(f"Error parsing YAML file: {e}")

    def load_output_model_class(self, output_type_name: str):
        """Load output model class from duo_workflow_service.agent_registry.components.base.

        Args:
            output_type_name: The name of the output model class (e.g., "AgentFinalOutput")

        Returns:
            Type: The output model class

        Raises:
            AttributeError: If the specified output_type_name is not found in the base module
        """
        # Import the base module to get available classes
        from duo_workflow_service.agent_registry.components import base

        # Check if the class exists in the base module
        if not hasattr(base, output_type_name):
            raise AttributeError(
                f"Output model class '{output_type_name}' not found in duo_workflow_service.agent_registry.components.base"
            )

        # Get and return the class
        output_class = getattr(base, output_type_name)

        # Verify it's a class (not a function or other object)
        if not isinstance(output_class, type):
            raise TypeError(
                f"'{output_type_name}' is not a class in duo_workflow_service.agent_registry.components.base"
            )

        return output_class

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
        # Load YAML configuration for the example_issue_to_mr_workflow
        config = self.load_yaml_config("example_issue_to_mr_workflow")

        # TODO: Implement workflow graph building using the loaded config
        component_classes = {
            "AgentComponent": AgentComponent,
            "HiltChatBackComponent": HiltChatBackComponent,
            "EndComponent": EndComponent,
        }

        # Create components from array-based configuration
        components = {}
        for comp_config in config["components"]:  # components is now an array
            comp_name = comp_config["name"]  # explicit name field
            comp_type = comp_config["type"]
            comp_class = component_classes[comp_type]

            # Remove name and type from config before passing to constructor
            comp_params = {
                k: v for k, v in comp_config.items() if k not in ["name", "type"]
            }

            # Add workflow metadata
            comp_params.update(
                {
                    "name": comp_name,
                    "workflow_id": self._workflow_id,
                    "workflow_type": self._workflow_type,
                }
            )

            # Handle special fields (toolset, output_type, etc.)
            if "toolset" in comp_params:
                comp_params["toolset"] = tools_registry.toolset(comp_params["toolset"])

            # Handle output_type by loading the class from base module
            if "output_type" in comp_params:
                comp_params["output_type"] = self.load_output_model_class(
                    comp_params["output_type"]
                )

            # Check for duplicate component names
            if comp_name in components:
                raise ValueError(
                    f"Duplicate component name: '{comp_name}'. Component names must be unique."
                )

            components[comp_name] = comp_class(**comp_params)

        # Create graph
        graph = StateGraph(PoCWorkflowState)

        # Create and attach routers
        for router_config in config["routers"]:
            from_comp = components[router_config["from"]]

            if "condition" in router_config:
                # Conditional router
                to_components = {}
                for route_key, comp_name in router_config["condition"][
                    "routes"
                ].items():
                    to_components[route_key] = components[comp_name]

                router = Router(
                    from_component=from_comp,
                    input=router_config["condition"]["input"],
                    to_component=to_components,
                )
            else:
                # Simple router
                to_comp = components[router_config["to"]]
                router = Router(from_component=from_comp, to_component=to_comp)

            router.attach(graph)

        # Set entry point
        entry_component = components[config["flow"]["entry_point"]]
        graph.set_entry_point(entry_component.__entry_hook__())

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
