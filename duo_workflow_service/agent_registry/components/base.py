import re
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from enum import StrEnum
from functools import partial
from typing import Annotated, Any, Callable, Optional, Protocol, Self, Type, TypedDict, NamedTuple

from dependency_injector.wiring import Provide, inject
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage
from langchain_core.output_parsers import PydanticToolsParser, StrOutputParser
from langchain_core.tools import BaseTool
from langgraph.constants import END
from langgraph.graph import StateGraph
from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, model_validator, RootModel
from pydantic_core import ValidationError
from typing_extensions import Pattern

from ai_gateway.container import ContainerApplication
from ai_gateway.prompts import LocalPromptRegistry, Prompt
from duo_workflow_service.entities import (
    MessageTypeEnum,
    ToolInfo,
    ToolStatus,
    UiChatLog,
    WorkflowStatusEnum,
)
from duo_workflow_service.tools import PipelineException, Toolset, DuoBaseTool

__all__ = ["BaseComponent", "AgentComponent"]


InjectedValue = None


def get_vars_from_context(
    inputs: list[str], context: dict[str, Any], splitter: Optional[Pattern] = None
) -> dict[str, Any]:
    variables = {}

    if not splitter:
        splitter = re.compile(r"[\.#]")

    for inp in inputs:
        current = context
        keys = splitter.split(inp)

        for parent_key in keys:
            current = current[parent_key]

        variables[keys[-1]] = current

    return variables


class HasBaseStateFields(TypedDict):
    conversation_history: dict[str, dict[str, list[BaseMessage]]]
    context: dict[str, Any]
    ui_chat_log: list[UiChatLog]


class Routes(StrEnum):
    TOOL_USE = "tool_use"
    STOP = "stop"

class AgentFinalOutput(BaseModel):
    """Always use this tool if no other tools are appropriate."""

    text: str = Field(description="text")

    @property
    def content(self) -> str:
        return self.text


class LogEntry(NamedTuple):
    record: UiChatLog
    event: StrEnum


class UILogCallback(Protocol):
    def __call__(self, log_entry: LogEntry) -> None: ...


class BaseUILogWriter(ABC):
    def __init__(self, log_callback: UILogCallback):
        self._log_callback = log_callback

    def success(self, *args, **kwargs) -> None:
        event = kwargs.pop("event")
        record = self._create_success_log(*args, **kwargs)
        self._log_callback(LogEntry(record=record, event=event))

    def error(self, *args, **kwargs) -> None:
        event = kwargs.pop("event")
        record = self._create_error_log(*args, **kwargs)
        self._log_callback(LogEntry(record=record, event=event))

    def _create_success_log(self, *args, **kwargs) -> UiChatLog:
        raise NotImplementedError

    def _create_error_log(self, *args, **kwargs) -> UiChatLog:
        raise NotImplementedError


class UIHistory[W: BaseUILogWriter](BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    writer: Type[W]
    config: bool | list[StrEnum]
    _logs: list[LogEntry] = PrivateAttr(default_factory=list)

    def _add_log(self, log_entry: LogEntry) -> None:
        """Callback function for writers."""
        self._logs.append(log_entry)

    @property
    def log(self) -> W:
        return self.writer(self._add_log)

    @property
    def state(self) -> dict[str, Any]:
        logs = []
        if self.config and isinstance(self.config, bool):
            # All events are enabled to be logged
            logs.extend([log.record for log in self._logs])
        elif isinstance(self.config, list):
            # Log only specified events
            logs.extend([
                log.record
                for log in self._logs
                if log.event in self.config
            ])

        return {"ui_chat_log": logs}


class UIHistoryAgentConfig(BaseModel):
    class EventsLLM(StrEnum):
        ON_FINAL_ANSWER = "on_final_answer"

    class EventsTool(StrEnum):
        ON_EXECUTION_SUCCESS = "on_execution_success"
        ON_EXECUTION_FAILED = "on_execution_failed"

    llm: bool | list[EventsLLM] = Field(default=True)
    tools: bool | list[EventsTool] = Field(default=True)


class UIHistoryLambdaConfig(RootModel):
    class Events(StrEnum):
        ON_EXECUTION_SUCCESS = "on_execution_success"

    root: bool | list[Events] = Field(default=False)


class UILogWriterAgentLLM(BaseUILogWriter):
    def _create_success_log(
        self,
        message: str,
        **kwargs
    ) -> UiChatLog:
        return UiChatLog(
            message_type=MessageTypeEnum.AGENT,
            content=str(message),
            timestamp=datetime.now(timezone.utc).isoformat(),
            status=ToolStatus.SUCCESS,
            correlation_id=kwargs.get("correlation_id"),
            tool_info=None,
            context_elements=kwargs.get("context_elements", []),
        )


class UILogWriterAgentTools(BaseUILogWriter):
    def _create_success_log(
        self,
        tool: BaseTool,
        tool_call_args: dict[str, Any],
        **kwargs
    ) -> UiChatLog:
        return UiChatLog(
            message_type=MessageTypeEnum.TOOL,
            content=self._format_message(tool, tool_call_args),
            timestamp=datetime.now(timezone.utc).isoformat(),
            status=ToolStatus.SUCCESS,
            correlation_id=kwargs.get("correlation_id"),
            tool_info=ToolInfo(name=tool.name, args=tool_call_args),
            context_elements=kwargs.get("context_elements", []),
        )

    def _create_error_log(
        self,
        message: str,
        tool: BaseTool,
        tool_call_args: dict[str, Any],
        **kwargs
    ) -> UiChatLog:
        content = (
            f"Failed: {self._format_message(tool, tool_call_args)} - {message}"
        )

        return UiChatLog(
            message_type=MessageTypeEnum.TOOL,
            content=content,
            timestamp=datetime.now(timezone.utc).isoformat(),
            status=ToolStatus.FAILURE,
            correlation_id=kwargs.get("correlation_id"),
            tool_info=ToolInfo(name=tool.name, args=tool_call_args),
            context_elements=kwargs.get("context_elements", []),
        )

    @staticmethod
    def _format_message(tool: BaseTool, tool_call_args: dict[str, Any]) -> str:
        if not hasattr(tool, "format_display_message"):
            args_str = ", ".join(f"{k}={str(v)}" for k, v in tool_call_args.items())
            return f"Using {tool.name}: {args_str}"

        try:
            schema = getattr(tool, "args_schema", None)
            if isinstance(schema, type) and issubclass(schema, BaseModel):
                # type: ignore[arg-type]
                parsed = schema(**tool_call_args)
                return tool.format_display_message(parsed)
        except Exception:
            return tool.format_display_message(DuoBaseTool, tool_call_args)

        return tool.format_display_message(tool_call_args)


class UILogWriterLambda(BaseUILogWriter):
    def _create_success_log(
        self,
        message: str,
        *,
        role: MessageTypeEnum,
        **kwargs
    ) -> UiChatLog:
        return UiChatLog(
            message_type=role,
            content=message,
            timestamp=datetime.now(timezone.utc).isoformat(),
            status=ToolStatus.SUCCESS,
            correlation_id=kwargs.get("correlation_id"),
            tool_info=None,
            context_elements=kwargs.get("context_elements", []),
        )


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
        self, graph: StateGraph, router: Any
    ) -> Annotated[str, "Entry node name"]:
        pass

    @abstractmethod
    def __entry_hook__(self) -> Annotated[str, "Entry node name"]:
        pass


class EndComponent(BaseComponent):
    def __entry_hook__(self):
        return END

    def attach(self, graph: StateGraph, router: Any) -> str:
        return END


ConditionPredicateType = str | int

DEFAULT_ROUTE = "default_route"


class Router[T: HasBaseStateFields](BaseModel):
    input: Optional[str] = None
    from_component: BaseComponent
    to_component: BaseComponent | dict[ConditionPredicateType, BaseComponent]

    # validate that if input is None, then conditions is a BaseComponent
    @model_validator(mode="after")
    def validate_router_fields(self) -> Self:
        if self.input is None and not isinstance(self.to_component, BaseComponent):
            raise ValueError(
                "If input is None, then conditions must be a BaseComponent"
            )
        return self

    # validate that if input is not None, then conditions is a dict
    @model_validator(mode="after")
    def validate_router_fields_dict(self) -> Self:
        if self.input is not None and not isinstance(self.to_component, dict):
            raise ValueError("If input is not None, then conditions must be a dict")
        return self

    def attach(
        self,
        graph: StateGraph,
    ):
        self.from_component.attach(graph, self)

    def route(self, state: T) -> str:
        if self.input is None:
            return self.to_component.__entry_hook__()

        route_value = get_vars_from_context([self.input], state)
        route_value = str(route_value[self.input.split(".")[-1]])

        if route_value in self.to_component:
            return self.to_component[route_value].__entry_hook__()

        if DEFAULT_ROUTE in self.to_component:
            return self.to_component[DEFAULT_ROUTE].__entry_hook__()

        raise KeyError(
            f"Route key {route_value} not found in conditions {self.to_component}"
        )


class AgentNode[T: HasBaseStateFields](BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str
    component_name: str
    prompt: Prompt
    check_events: bool = True

    inputs: list[str]
    output_type: Optional[Type[BaseModel]]
    output: Optional[str]

    ui_history: UIHistory[UILogWriterAgentLLM]

    async def _try_parse_structured_response(
        self, completion: AIMessage
    ) -> Optional[dict[str, Any]]:
        if (
            self.output_type
            and len(completion.tool_calls) > 0
            and completion.tool_calls[0]["name"] == self.output_type.__name__
        ):
            output_parser = PydanticToolsParser(
                tools=[self.output_type], first_tool_only=True
            )
            parsed = await output_parser.ainvoke(completion)

            return parsed.model_dump(mode="json")

        return None

    async def _try_parse_raw_response(self, completion: AIMessage) -> Optional[str]:
        if not self.output_type and len(completion.tool_calls) == 0:
            output_parser = StrOutputParser()
            return await output_parser.ainvoke(completion)

        return None

    async def _process_final_response(self, completion: AIMessage) -> Any:
        parsers = [
            self._try_parse_structured_response,
            self._try_parse_raw_response,
        ]

        for parser in parsers:
            if response := await parser(completion):
                return response

        return None

    async def run(self, state: T) -> dict:
        history = state["conversation_history"].get(self.component_name, [])
        context = state["context"].get(self.component_name, {})

        variables = get_vars_from_context(self.inputs, state["context"])
        completion: AIMessage = await self.prompt.ainvoke(
            input={**variables, "history": history}
        )

        if final_response := await self._process_final_response(completion):
            if self.output:
                context[self.output] = final_response

            self.ui_history.log.success(
                final_response,
                event=UIHistoryAgentConfig.EventsLLM.ON_FINAL_ANSWER
            )

        # parsed_completion: BaseModel = await output_parser.ainvoke(completion)
        # context[self.output] = parsed_completion.model_dump(mode="json")
        # completion = AIMessage(content=parsed_completion.content)

        return {
            **self.ui_history.state,
            "context": {self.component_name: context},
            "conversation_history": {self.component_name: [*history, completion]},
        }


class ToolNode[T: HasBaseStateFields](BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str
    component_name: str
    toolset: Toolset

    ui_history: UIHistory[UILogWriterAgentTools]

    async def run(self, state: T) -> dict:
        conversation_history = state["conversation_history"].get(
            self.component_name, []
        )
        context = state["context"].get(self.component_name, {})
        context.setdefault("tool_calls", [])

        last_message = conversation_history[-1]
        tool_calls = getattr(last_message, "tool_calls", [])
        tools_responses = []

        for tool_call in tool_calls:
            tool_name = tool_call["name"]
            tool_call_args = tool_call.get("args", {})
            tool_call_id = tool_call.get("id")

            context["tool_calls"].append(
                {"id": tool_call_id, "name": tool_name, "args": tool_call_args}
            )

            if tool_name not in self.toolset:
                response = ToolMessage(
                    content=f"Tool {tool_name} not found", tool_call_id=tool_call_id
                )
            else:
                tool = self.toolset[tool_name]
                response = await self._execute_tool(tool_call_id, tool_call_args, tool)

            tools_responses.append(response)

        return {
            **self.ui_history.state,
            "conversation_history": {
                self.component_name: [*conversation_history, *tools_responses],
            },
            "context": {self.component_name: context},
        }

    async def _execute_tool(
        self, tool_call_id: str, tool_call_args: dict[str, Any], tool: BaseTool
    ) -> ToolMessage:
        # Several utility log functions to avoid boilerplate code
        log_success = partial(self.ui_history.log.success, tool=tool, tool_call_args=tool_call_args)
        log_error = partial(self.ui_history.log.error, tool=tool, tool_call_args=tool_call_args)

        try:
            tool_call_result = await tool.arun(tool_call_args)
            response = ToolMessage(content=tool_call_result, tool_call_id=tool_call_id)
            log_success(event=UIHistoryAgentConfig.EventsTool.ON_EXECUTION_SUCCESS)
        except TypeError as e:
            response = self._handle_type_error(tool_call_id, tool, e)
            log_error(
                "Invalid arguments",
                event=UIHistoryAgentConfig.EventsTool.ON_EXECUTION_FAILED
            )
        except ValidationError as e:
            response = self._handle_validation_error(tool_call_id, tool, e)
            log_error(
                "Validation error",
                event=UIHistoryAgentConfig.EventsTool.ON_EXECUTION_FAILED
            )
        except PipelineException as e:
            response = self._handle_pipeline_error(tool_call_id, tool, e)
            log_error(
                f"Pipeline error: {str(e)}",
                event=UIHistoryAgentConfig.EventsTool.ON_EXECUTION_FAILED
            )

        return response

    @staticmethod
    def _handle_type_error(
        tool_call_id: str, tool: BaseTool, _e: TypeError
    ) -> ToolMessage:
        schema = (
            f"The schema is: {tool.args_schema.model_json_schema()}"
            if tool.args_schema
            else "The tool does not accept any argument"
        )

        response = (
            f"Tool {tool.name} execution failed due to wrong arguments."
            f" You must adhere to the tool args schema! {schema}"
        )

        return ToolMessage(
            content=response,
            tool_call_id=tool_call_id,
        )

    @staticmethod
    def _handle_validation_error(
        tool_call_id: str,
        tool: BaseTool,
        e: ValidationError,
    ) -> ToolMessage:
        response = f"Tool {tool.name} raised validation error {str(e)}"

        return ToolMessage(content=response, tool_call_id=tool_call_id)

    @staticmethod
    def _handle_pipeline_error(
        tool_call_id: str,
        _tool: BaseTool,
        e: PipelineException,
    ) -> ToolMessage:
        response = f"Pipeline exception due to {str(e)}"

        return ToolMessage(content=response, tool_call_id=tool_call_id)


@inject
class AgentComponent[T: HasBaseStateFields](BaseComponent):
    prompt_id: str
    prompt_version: str
    toolset: Toolset

    output_type: Optional[Type[BaseModel]] = None
    ui_history_config: UIHistoryAgentConfig = Field(default_factory=UIHistoryAgentConfig)

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

    def _are_tools_called(self, state: T, component_name: str, router: Router) -> str:
        if state["status"] in [WorkflowStatusEnum.CANCELLED, WorkflowStatusEnum.ERROR]:
            return router.route(state)

        history: list[BaseMessage] = state["conversation_history"][component_name]
        last_message = history[-1]
        if isinstance(last_message, AIMessage) and len(last_message.tool_calls) > 0:
            if (
                self.output_type
                and last_message.tool_calls[0]["name"] == self.output_type.__name__
            ):
                return router.route(state)

            return f"{self.name}#tools"

        return router.route(state)

    def __entry_hook__(self):
        return f"{self.name}#agent"

    def attach(
        self, graph: StateGraph, router: Router[T]
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
            name=self.__entry_hook__(),
            component_name=self.name,
            prompt=prompt,
            inputs=self.inputs,
            output_type=self.output_type,
            output=self.output,
            ui_history=UIHistory(
                config=self.ui_history_config.llm,
                writer=UILogWriterAgentLLM
            ),
        )
        node_tools = ToolNode(
            name=f"{self.name}#tools",
            component_name=self.name,
            toolset=self.toolset,
            ui_history=UIHistory(
                config=self.ui_history_config.tools,
                writer=UILogWriterAgentTools
            ),
        )

        graph.add_node(self.__entry_hook__(), node_agent.run)
        graph.add_node(node_tools.name, node_tools.run)

        graph.add_conditional_edges(
            self.__entry_hook__(),
            partial(self._are_tools_called, component_name=self.name, router=router),
        )
        graph.add_edge(node_tools.name, node_agent.name)

        return self.__entry_hook__()


class HiltComponent(BaseComponent):
    human_prompt: str

    def __entry_hook__(self):
        return f"{self.name}#hilt"

    def attach(self, graph: StateGraph, router: Any) -> str:
        graph.add_node(self.__entry_hook__(), self._prompt_human)
        graph.add_edge(self.__entry_hook__(), f"{self.name}#check")
        graph.add_node(f"{self.name}#check", self._fetch_human_input)
        graph.add_conditional_edges(f"{self.name}#check", router.route)

        return self.__entry_hook__()

    def _prompt_human(self, _state):
        ui_log = UiChatLog(
            message_type=MessageTypeEnum.REQUEST,
            content=self.human_prompt,
            timestamp=datetime.now(timezone.utc).isoformat(),
            status=ToolStatus.SUCCESS,
            tool_info=None,
            context_elements=None,
        )
        return {"status": WorkflowStatusEnum.INPUT_REQUIRED, "ui_chat_log": [ui_log]}

    def _fetch_human_input(self, state):
        human_input: str = interrupt("Workflow interrupted")
        context = state["context"].get(self.name, {})
        context[self.output] = human_input

        return {"status": WorkflowStatusEnum.EXECUTION, "context": {self.name: context}}


class HiltChatBackComponent(BaseComponent):

    def __entry_hook__(self):
        return f"{self.name}#hiltChatBack"

    def attach(self, graph: StateGraph, router: Any) -> str:
        graph.add_node(self.__entry_hook__(), self._prompt_human)
        graph.add_edge(self.__entry_hook__(), f"{self.name}#hiltChatBackFetchResponse")
        graph.add_node(
            f"{self.name}#hiltChatBackFetchResponse", self._fetch_human_input
        )
        graph.add_conditional_edges(
            f"{self.name}#hiltChatBackFetchResponse", router.route
        )

        return self.__entry_hook__()

    def _prompt_human(self, _state):
        return {
            "status": WorkflowStatusEnum.INPUT_REQUIRED,
        }

    def _fetch_human_input(self, state):
        human_input: str = interrupt("Workflow interrupted")
        context = state["context"].get(self.name, {})
        context[self.output] = human_input
        return {
            "status": WorkflowStatusEnum.EXECUTION,
            "conversation_history": {
                self.output: [
                    *state["conversation_history"][self.output],
                    HumanMessage(content=human_input),
                ],
            },
        }


class LambdaComponent[T: HasBaseStateFields](BaseComponent):
    fn: Callable

    ui_role: MessageTypeEnum = Field(default=MessageTypeEnum.TOOL)
    ui_history_config: UIHistoryLambdaConfig = Field(default_factory=UIHistoryLambdaConfig)

    _ui_history: UIHistory[UILogWriterLambda] = PrivateAttr()

    @model_validator(mode="after")
    def init_component(self) -> Self:
        self._ui_history = UIHistory(config=self.ui_history_config.root, writer=UILogWriterLambda)

        return self

    def _run_lambda(self, state: T) -> dict[str, Any]:
        variables = get_vars_from_context(self.inputs, state["context"])
        context = state["context"].get(self.name, {})

        updates = self.fn(**variables)
        if updates and not self.output:
            raise Warning(
                "The lambda function returns a non-empty object, however the 'output' key was empty"
            )

        if updates:
            self._ui_history.log.success(
                str(updates),
                event=UIHistoryLambdaConfig.Events.ON_EXECUTION_SUCCESS,
                role=self.ui_role,
            )

            if self.output:
                context[self.output] = updates

        return {
            **self._ui_history.state,
            "context": {self.name: context}
        }

    def __entry_hook__(self):
        return f"{self.name}#lambda"

    def attach(
        self, graph: StateGraph, router: Router
    ) -> Annotated[str, "Entry node name"]:
        self.__entry_hook__()

        graph.add_node(self.__entry_hook__(), self._run_lambda)
        graph.add_conditional_edges(self.__entry_hook__(), router.route)

        return self.__entry_hook__()


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
            dep_name, _, _ = input_path.partition("#")
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
                name for name, deps in dependencies.items() if comp_name in deps
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
