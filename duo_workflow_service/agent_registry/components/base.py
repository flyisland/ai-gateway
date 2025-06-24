from abc import ABC, abstractmethod
from enum import StrEnum
from functools import partial
from typing import Optional, Annotated, Type, Self, Any, TypedDict, Callable

from dependency_injector.wiring import Provide, inject
from langchain_core.messages import ToolMessage, BaseMessage, AIMessage
from langchain_core.output_parsers import PydanticToolsParser
from langgraph.constants import END
from langgraph.graph import StateGraph
from pydantic import BaseModel, Field, ConfigDict, model_validator

from ai_gateway.container import ContainerApplication
from ai_gateway.prompts import Prompt, LocalPromptRegistry
from duo_workflow_service.entities import WorkflowStatusEnum
from duo_workflow_service.tools import Toolset

__all__ = ["BaseComponent", "AgentComponent"]


InjectedValue = None


def get_vars_from_context(
    inputs: list[str], context: dict[str, Any], splitter: str = "."
) -> dict[str, Any]:
    variables = {}
    for inp in inputs:
        current = context
        keys = inp.split(splitter)

        for parent_key in keys:
            current = current[parent_key]

        variables[keys[-1]] = current

    return variables


class HasBaseStateFields(TypedDict):
    conversation_history: dict[str, dict[str, list[BaseMessage]]]
    context: dict[str, Any]


class Routes(StrEnum):
    TOOL_USE = "tool_use"
    STOP = "stop"


class BaseComponent(BaseModel, ABC):
    model_config = ConfigDict(arbitrary_types_allowed=True, frozen=True)

    name: str
    workflow_id: str | int
    workflow_type: str

    inputs: list[str] = Field(default_factory=list)
    output: Optional[str] = None

    @model_validator(mode="after")
    def validate_base_fields(self) -> Self:
        if self.output and "." in self.output:
            raise ValueError(
                f"Invalid output key: '{self.output}'."
                " Output keys cannot contain dots (nested keys not supported)."
                " Use a simple key like 'result' instead of 'data.result'."
                f" Value will be stored in component '{self.name}' context."
            )

        return self

    @abstractmethod
    def attach(
        self, graph: StateGraph, exit_node: str
    ) -> Annotated[str, "Entry node name"]:
        pass


class AgentNode[T: HasBaseStateFields](BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str
    component_name: str
    prompt: Prompt
    check_events: bool = True

    inputs: list[str]
    output_type: Optional[Type[BaseModel]]
    output: Optional[str]

    async def run(self, state: T) -> dict:
        history = state["conversation_history"].get(self.component_name, [])
        context = state["context"].get(self.component_name, {})

        variables = get_vars_from_context(self.inputs, state["context"])
        completion: AIMessage = await self.prompt.ainvoke(
            input={**variables, "history": history}
        )

        if (
            self.output_type
            and len(completion.tool_calls) > 0
            and completion.tool_calls[0]["name"] == self.output_type.__name__
        ):
            output_parser = PydanticToolsParser(
                tools=[self.output_type], first_tool_only=True
            )
            parsed_completion: BaseModel = await output_parser.ainvoke(completion)
            context[self.output] = parsed_completion.model_dump(mode="json")

        return {
            "context": {self.component_name: context},
            "conversation_history": {self.component_name: [*history, completion]},
        }


class ToolNode[T: HasBaseStateFields](BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str
    component_name: str
    toolset: Toolset

    async def run(self, state: T) -> dict:
        conversation_history = state["conversation_history"].get(
            self.component_name, []
        )
        context = state["context"].get(self.component_name, {"tool_calls": []})

        last_message = conversation_history[-1]
        tool_calls = getattr(last_message, "tool_calls", [])
        tools_responses = []

        for tool_call in tool_calls:
            tool_name = tool_call["name"]
            tool_args = tool_call.get("args", {})
            tool_call_id = tool_call.get("id")

            context["tool_calls"].append(
                {"id": tool_call_id, "name": tool_name, "args": tool_args}
            )

            tool_response = f"Tool {tool_name} not found"
            if tool_name in self.toolset:
                tool_response = await self.toolset[tool_name].arun(tool_args)

            tools_responses.append(
                ToolMessage(content=tool_response, tool_call_id=tool_call_id)
            )

        return {
            "conversation_history": {
                self.component_name: [*conversation_history, *tools_responses],
            },
            "context": {self.component_name: context},
        }


@inject
class AgentComponent[T: HasBaseStateFields](BaseComponent):
    prompt_id: str
    prompt_version: str
    toolset: Toolset

    output_type: Optional[Type[BaseModel]] = None

    prompt_registry: Annotated[
        LocalPromptRegistry, Provide[ContainerApplication.pkg_prompts.prompt_registry]
    ] = InjectedValue

    @model_validator(mode="after")
    def validate_agent_fields(self) -> Self:
        if self.output_type and not self.output:
            raise ValueError(
                "Output is required when output_type is specified."
                " Please provide a value for the 'output' field."
            )

        if self.output and not self.output_type:
            raise ValueError(
                "Output type is required when output is specified."
                " Please provide an output schema for the 'output_type' field."
            )

        return self

    def _are_tools_called(self, state: T, component_name: str) -> Routes:
        if state["status"] in [WorkflowStatusEnum.CANCELLED, WorkflowStatusEnum.ERROR]:
            return Routes.STOP

        history: list[BaseMessage] = state["conversation_history"][component_name]
        last_message = history[-1]
        if isinstance(last_message, AIMessage) and len(last_message.tool_calls) > 0:
            if (
                self.output_type
                and last_message.tool_calls[0]["name"] == self.output_type.__name__
            ):
                return Routes.STOP

            return Routes.TOOL_USE

        return Routes.STOP

    def attach(
        self, graph: StateGraph, exit_node: str
    ) -> Annotated[str, "Entry node name"]:
        tools = self.toolset.bindable
        tool_choice = None
        if self.output_type:
            tools += [self.output_type]
            tool_choice = "any"  # make sure the LLM always uses a tool to respond.

        prompt = self.prompt_registry.get(
            self.prompt_id, self.prompt_version, tools=tools, tool_choice=tool_choice
        )

        node_agent = AgentNode(
            name=f"{self.name}#agent",
            component_name=self.name,
            prompt=prompt,
            inputs=self.inputs,
            output_type=self.output_type,
            output=self.output,
        )
        node_tools = ToolNode(
            name=f"{self.name}#tools", component_name=self.name, toolset=self.toolset
        )

        graph.add_node(node_agent.name, node_agent.run)
        graph.add_node(node_tools.name, node_tools.run)

        graph.add_conditional_edges(
            node_agent.name,
            partial(self._are_tools_called, component_name=self.name),
            {Routes.TOOL_USE: node_tools.name, Routes.STOP: exit_node},
        )
        graph.add_edge(node_tools.name, node_agent.name)

        return node_agent.name


class LambdaComponent[T: HasBaseStateFields](BaseComponent):
    fn: Callable[[...], Optional[Any]]

    def _run_lambda(self, state: T) -> dict[str, Any]:
        variables = get_vars_from_context(self.inputs, state["context"])
        context = state["context"].get(self.name, {})

        updates = self.fn(**variables)
        if updates and not self.output:
            raise Warning("The lambda function returns a non-empty object, however the 'output' key was empty")

        if self.output:
            context[self.output] = updates

        return {
            "context": {
                self.name: context
            }
        }

    def attach(self, graph: StateGraph, exit_node: str) -> Annotated[str, "Entry node name"]:
        lambda_node_name = f"{self.name}#lambda"

        graph.add_node(lambda_node_name, self._run_lambda)
        graph.add_edge(lambda_node_name, exit_node)

        return lambda_node_name


def attach_components_to_graph(graph, components, start, end):
    """Generic function to attach a list of components to a graph in a linear or tree structure."""

    # Create a mapping of component names to component instances
    component_map = {comp.name: comp for comp in components}

    # Validate input parameters
    if start not in component_map:
        raise ValueError(f"Input component '{start}' not found in components list")

    for _end in end:
        if _end not in component_map:
            raise ValueError(f"Output component '{_end}' not found in components list")

    # Build dependency graph based on component inputs
    dependencies = {}
    for comp in components:
        deps = []
        for input_path in comp.inputs:
            dep_name, _, _ = input_path.partition(".")
            if dep_name in component_map and dep_name != comp.name:
                deps.append(dep_name)
        dependencies[comp.name] = deps

    # Topological sort to determine correct attachment order
    def topological_sort():
        # Kahn's algorithm for topological sorting
        in_degree = {name: 0 for name in component_map.keys()}

        # Calculate in-degrees
        for comp_name, deps in dependencies.items():
            for dep in deps:
                in_degree[comp_name] += 1

        # Start with components that have no dependencies
        queue = [name for name, degree in in_degree.items() if degree == 0]
        sorted_order = []

        while queue:
            current = queue.pop(0)
            sorted_order.append(current)

            # Reduce in-degree for dependent components
            for comp_name, deps in dependencies.items():
                if current in deps:
                    in_degree[comp_name] -= 1
                    if in_degree[comp_name] == 0:
                        queue.append(comp_name)

        return sorted_order

    # Get the correct order for attachment (reverse of dependency order)
    execution_order = topological_sort()
    attachment_order = execution_order[::-1]  # Reverse for attachment

    # Track attached nodes
    attached_nodes = {}

    # Attach components in reverse dependency order
    for comp_name in attachment_order:
        component = component_map[comp_name]

        if comp_name in end:
            # Output components connect to END
            entry_node = component.attach(graph, END)
        else:
            # Find the next component in the chain
            next_components = [
                name for name, deps in dependencies.items()
                if comp_name in deps
            ]

            if next_components:
                # Connect to the first dependent component's entry node
                next_comp_name = next_components[0]
                if next_comp_name in attached_nodes:
                    exit_node = attached_nodes[next_comp_name]
                else:
                    # This shouldn't happen with proper topological sort
                    exit_node = END
            else:
                # No dependents, connect to END
                exit_node = END

            entry_node = component.attach(graph, exit_node)

        attached_nodes[comp_name] = entry_node

    # Set the entry point and return it
    entry_point = attached_nodes[start]
    graph.set_entry_point(entry_point)

    return graph
