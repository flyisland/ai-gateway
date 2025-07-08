import re
from abc import ABC, abstractmethod
from collections import defaultdict
from datetime import datetime, timezone
from enum import StrEnum
from functools import partial
from typing import (
    Annotated,
    Any,
    Callable,
    ClassVar,
    NamedTuple,
    Optional,
    Protocol,
    Self,
    Type,
    TypedDict,
)

from dependency_injector.wiring import Provide, inject
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_core.output_parsers import PydanticToolsParser, StrOutputParser
from langchain_core.tools import BaseTool
from langgraph.constants import END
from langgraph.graph import StateGraph
from langgraph.types import interrupt
from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, model_validator
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
from duo_workflow_service.tools import DuoBaseTool, PipelineException, Toolset

__all__ = ["BaseComponent", "AgentComponent"]


InjectedValue = None


class IOKey(NamedTuple):
    target: str
    subkeys: list[str]


def parse_io_keys(keys: list[str]) -> list[IOKey]:
    io_keys = []
    for key in keys:
        target, _, remaining = key.partition(":")
        if not remaining:
            subkeys = []
        else:
            subkeys = remaining.split(".")

        io_keys.append(IOKey(target=target, subkeys=subkeys))

    return io_keys


def parse_single_key(key: str) -> IOKey:
    io_keys = parse_io_keys([key])

    return io_keys[0]


class HasBaseStateFields(TypedDict):
    conversation_history: dict[str, dict[str, list[BaseMessage]]]
    context: dict[str, Any]
    ui_chat_log: list[UiChatLog]


class AgentFinalOutput(BaseModel):
    """Always use this tool if no other tools are appropriate."""

    text: str = Field(description="text")

    @property
    def content(self) -> str:
        return self.text


def get_vars_from_state[T: HasBaseStateFields](
    inputs: list[IOKey], state: T
) -> dict[str, Any]:
    variables = {}

    for inp in inputs:
        current = state[inp.target]
        for key in inp.subkeys:
            current = current[key]

        if inp.subkeys:
            variables[inp.subkeys[-1]] = current
        else:
            variables[inp.target] = current

    return variables


def create_nested_dict(keys: list[str], value: Any) -> dict[str, Any]:
    if not keys:
        return {}

    result = {}
    current = result

    # Navigate through all keys except the last one
    for key in keys[:-1]:
        current[key] = {}
        current = current[key]

    # Set the value at the last key
    current[keys[-1]] = value

    return result


##############################################################
########### Logging (Start)
##############################################################


class UILogEventsLLM(StrEnum):
    ON_FINAL_ANSWER = "on_final_answer"


class UILogEventsTool(StrEnum):
    ON_EXECUTION_SUCCESS = "on_execution_success"
    ON_EXECUTION_FAILED = "on_execution_failed"


UILogEvents = UILogEventsLLM | UILogEventsTool


class UILogEntry(NamedTuple):
    record: UiChatLog
    event: UILogEvents


class UILogCallback(Protocol):
    def __call__(self, log_entry: UILogEntry) -> None: ...


class BaseUILogWriter(ABC):
    def __init__(self, log_callback: UILogCallback):
        self._log_callback = log_callback

    def success(self, *args, **kwargs) -> None:
        event: UILogEvents = kwargs.pop("event")
        record = self._create_success_log(*args, **kwargs)
        self._log_callback(UILogEntry(record=record, event=event))

    def error(self, *args, **kwargs) -> None:
        event: UILogEvents = kwargs.pop("event")
        record = self._create_error_log(*args, **kwargs)
        self._log_callback(UILogEntry(record=record, event=event))

    def _create_success_log(self, *args, **kwargs) -> UiChatLog:
        raise NotImplementedError

    def _create_error_log(self, *args, **kwargs) -> UiChatLog:
        raise NotImplementedError


class UIHistory[W: BaseUILogWriter](BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    writer: Type[W]
    events: bool | list[UILogEvents]
    _logs: list[UILogEntry] = PrivateAttr(default_factory=list)

    def _add_log(self, log_entry: UILogEntry) -> None:
        """Callback function for writers."""
        self._logs.append(log_entry)

    @property
    def log(self) -> W:
        return self.writer(self._add_log)

    @property
    def state(self) -> dict[str, Any]:
        logs = []
        if self.events and isinstance(self.events, bool):
            # All events are enabled to be logged
            logs.extend([log.record for log in self._logs])
        elif isinstance(self.events, list):
            # Log only specified events
            logs.extend([log.record for log in self._logs if log.event in self.events])

        return {"ui_chat_log": logs}


class UILogAgentEvents(BaseModel):
    llm: bool | list[UILogEventsLLM] = Field(default=False)
    tools: bool | list[UILogEventsTool] = Field(default=False)


class UILogWriterAgentLLM(BaseUILogWriter):
    def _create_success_log(self, message: str, **kwargs) -> UiChatLog:
        return UiChatLog(
            message_type=MessageTypeEnum.AGENT,
            content=str(message),
            timestamp=datetime.now(timezone.utc).isoformat(),
            status=ToolStatus.SUCCESS,
            correlation_id=kwargs.get("correlation_id"),
            tool_info=None,
            context_elements=kwargs.get("context_elements", []),
            message_sub_type=None,
        )


class UILogWriterAgentTools(BaseUILogWriter):
    def _create_success_log(
        self, tool: BaseTool, tool_call_args: dict[str, Any], **kwargs
    ) -> UiChatLog:
        return UiChatLog(
            message_type=MessageTypeEnum.TOOL,
            content=self._format_message(tool, tool_call_args),
            timestamp=datetime.now(timezone.utc).isoformat(),
            status=ToolStatus.SUCCESS,
            correlation_id=kwargs.get("correlation_id"),
            tool_info=ToolInfo(name=tool.name, args=tool_call_args),
            context_elements=kwargs.get("context_elements", []),
            message_sub_type=None,
        )

    def _create_error_log(
        self, message: str, tool: BaseTool, tool_call_args: dict[str, Any], **kwargs
    ) -> UiChatLog:
        content = f"Failed: {self._format_message(tool, tool_call_args)} - {message}"

        return UiChatLog(
            message_type=MessageTypeEnum.TOOL,
            content=content,
            timestamp=datetime.now(timezone.utc).isoformat(),
            status=ToolStatus.FAILURE,
            correlation_id=kwargs.get("correlation_id"),
            tool_info=ToolInfo(name=tool.name, args=tool_call_args),
            context_elements=kwargs.get("context_elements", []),
            message_sub_type=None,
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
        self, message: str, *, role: MessageTypeEnum, **kwargs
    ) -> UiChatLog:
        return UiChatLog(
            message_type=role,
            content=message,
            timestamp=datetime.now(timezone.utc).isoformat(),
            status=ToolStatus.SUCCESS,
            correlation_id=kwargs.get("correlation_id"),
            tool_info=None,
            context_elements=kwargs.get("context_elements", []),
            message_sub_type=None,
        )


##############################################################
########### Logging (End)
##############################################################


class BaseRouter[R: HasBaseStateFields](BaseModel, ABC):
    DEFAULT_ROUTE: ClassVar[str] = "default_route"

    _allowed_input_targets: list[str] = []

    @model_validator(mode="after")
    def validate_input_field(self) -> Self:
        if self.input and self.input.target not in self._allowed_input_targets:
            raise ValueError(
                f"The '{self.__class__.__name__}' router doesn't support the input target '{self.input.target}'."
            )

        return self

    @abstractmethod
    def attach(self, graph: StateGraph):
        pass

    @abstractmethod
    def route(self, state: R) -> Annotated[str, "Next node"]:
        pass


class BaseComponent[T: HasBaseStateFields](BaseModel, ABC):
    model_config = ConfigDict(arbitrary_types_allowed=True, frozen=True)

    name: str
    workflow_id: str | int
    workflow_type: str

    inputs: list[IOKey] = Field(default_factory=list)
    output: Optional[IOKey] = None

    _allowed_input_targets: list[str] = []
    _allowed_output_targets: list[str] = []

    @model_validator(mode="before")
    @classmethod
    def build_base_component(cls, data: dict[str, Any]) -> dict[str, Any]:
        if "inputs" in data:
            data["inputs"] = parse_io_keys(data["inputs"])

        if "output" in data:
            data["output"] = parse_single_key(data["output"])

        return data

    @model_validator(mode="after")
    def validate_base_fields(self) -> Self:
        for inp in self.inputs:
            if inp.target not in self._allowed_input_targets:
                raise ValueError(
                    f"The '{self.__class__.__name__}' component doesn't support the input target '{inp.target}'."
                )

        if self.output and self.output.target not in self._allowed_output_targets:
            raise ValueError(
                f"The '{self.__class__.__name__}' component doesn't support the output target '{self.output.target}'."
            )

        return self

    @abstractmethod
    def attach(
        self, graph: StateGraph, router: BaseRouter[T]
    ) -> Annotated[str, "Entry node name"]:
        pass

    @abstractmethod
    def __entry_hook__(self) -> Annotated[str, "Entry node name"]:
        pass


class Router[R](BaseRouter[R]):
    input: Optional[IOKey] = None
    from_component: BaseComponent
    to_component: BaseComponent | dict[str | int, BaseComponent]

    _allowed_input_targets: list[str] = ["context", "status"]

    @model_validator(mode="before")
    @classmethod
    def build_router(cls, data: dict[str, Any]) -> dict[str, Any]:
        if "input" in data:
            data["input"] = parse_single_key(data["input"])

        return data

    @model_validator(mode="after")
    def validate_router_fields(self) -> Self:
        """Validate that if input is None, then conditions is a BaseComponent."""
        if self.input is None and not isinstance(self.to_component, BaseComponent):
            raise ValueError(
                "If input is None, then conditions must be a BaseComponent"
            )
        return self

    @model_validator(mode="after")
    def validate_router_fields_dict(self) -> Self:
        """Validate that if input is not None, then conditions is a dict."""
        if self.input is not None and not isinstance(self.to_component, dict):
            raise ValueError("If input is not None, then conditions must be a dict")
        return self

    def attach(self, graph: StateGraph):
        self.from_component.attach(graph, self)

    def route(self, state) -> Annotated[str, "Next node"]:
        if self.input is None:
            return self.to_component.__entry_hook__()

        variables = get_vars_from_state([self.input], state)
        route_value = str(next(iter(variables.values()))) if variables else None

        if route_value and route_value in self.to_component:
            return self.to_component[route_value].__entry_hook__()

        if Router.DEFAULT_ROUTE in self.to_component:
            return self.to_component[Router.DEFAULT_ROUTE].__entry_hook__()

        raise KeyError(
            f"Route key {self.input} not found in conditions {self.to_component}"
        )


class EndComponent(BaseComponent):
    def __entry_hook__(self):
        return END

    def attach(self, graph: StateGraph, router: BaseRouter) -> str:
        return END


class AgentNode[T: HasBaseStateFields](BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str
    component_name: str
    prompt: Prompt
    check_events: bool = True

    inputs: list[IOKey]
    output_type: Optional[Type[BaseModel]]
    output: Optional[IOKey]

    ui_history: UIHistory[UILogWriterAgentLLM]

    class _FinalResponse(NamedTuple):
        payload: str | BaseModel
        tool_call_id: Optional[str] = None

        @property
        def is_structured(self) -> bool:
            return self.tool_call_id and isinstance(self.payload, BaseModel)

        @property
        def content(self) -> str | dict[str, Any]:
            if self.is_structured:
                return self.payload.model_dump(mode="json")

            return self.payload

        def create_tool_message(self) -> Optional[ToolMessage]:
            if self.is_structured:
                return ToolMessage(content="", tool_call_id=self.tool_call_id)

            return None

    async def _try_parse_structured_response(
        self, completion: AIMessage
    ) -> Optional[_FinalResponse]:
        if (
            self.output_type
            and len(completion.tool_calls) > 0
            and completion.tool_calls[0]["name"] == self.output_type.__name__
        ):
            output_parser = PydanticToolsParser(
                tools=[self.output_type], first_tool_only=True
            )
            parsed = await output_parser.ainvoke(completion)

            return AgentNode._FinalResponse(
                tool_call_id=completion.tool_calls[0].get("id"),
                payload=parsed,
            )

        return None

    async def _try_parse_raw_response(
        self, completion: AIMessage
    ) -> Optional[_FinalResponse]:
        if not self.output_type and len(completion.tool_calls) == 0:
            output_parser = StrOutputParser()
            parsed = await output_parser.ainvoke(completion)

            return AgentNode._FinalResponse(payload=parsed)

        return None

    async def _process_final_response(
        self, completion: AIMessage
    ) -> Optional[_FinalResponse]:
        parsers = [
            self._try_parse_structured_response,
            self._try_parse_raw_response,
        ]

        for parser in parsers:
            if response := await parser(completion):
                return response

        return None

    async def run(self, state: T) -> dict:
        serialized = {}
        history = state["conversation_history"].get(self.component_name, [])

        variables = get_vars_from_state(self.inputs, state)
        completion: AIMessage = await self.prompt.ainvoke(
            input={**variables, "history": history}
        )

        completions: list[BaseMessage] = [completion]
        final_response = await self._process_final_response(completion)

        if final_response:
            if self.output:
                serialized[self.output.target] = create_nested_dict(
                    self.output.subkeys, final_response.content
                )

            self.ui_history.log.success(
                final_response.content, event=UILogEventsLLM.ON_FINAL_ANSWER
            )

            if final_response.is_structured:
                completions.append(final_response.create_tool_message())

        return {
            **self.ui_history.state,
            **serialized,
            "conversation_history": {self.component_name: completions},
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
                self.component_name: tools_responses,
            },
            "context": {self.component_name: context},
        }

    async def _execute_tool(
        self, tool_call_id: str, tool_call_args: dict[str, Any], tool: BaseTool
    ) -> ToolMessage:
        # Several utility log functions to avoid boilerplate code
        log_success = partial(
            self.ui_history.log.success, tool=tool, tool_call_args=tool_call_args
        )
        log_error = partial(
            self.ui_history.log.error, tool=tool, tool_call_args=tool_call_args
        )

        try:
            tool_call_result = await tool.arun(tool_call_args)
            response = ToolMessage(content=tool_call_result, tool_call_id=tool_call_id)
            log_success(event=UILogEventsTool.ON_EXECUTION_SUCCESS)
        except TypeError as e:
            response = self._handle_type_error(tool_call_id, tool, e)
            log_error("Invalid arguments", event=UILogEventsTool.ON_EXECUTION_FAILED)
        except ValidationError as e:
            response = self._handle_validation_error(tool_call_id, tool, e)
            log_error("Validation error", event=UILogEventsTool.ON_EXECUTION_FAILED)
        except PipelineException as e:
            response = self._handle_pipeline_error(tool_call_id, tool, e)
            log_error(
                f"Pipeline error: {str(e)}", event=UILogEventsTool.ON_EXECUTION_FAILED
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
class AgentComponent[T](BaseComponent[T]):
    prompt_id: str
    prompt_version: str
    toolset: Toolset

    output_type: Optional[Type[BaseModel]] = None
    ui_log_events: UILogAgentEvents = Field(default_factory=UILogAgentEvents)

    prompt_registry: Annotated[
        LocalPromptRegistry, Provide[ContainerApplication.pkg_prompts.prompt_registry]
    ] = InjectedValue

    _allowed_input_targets: list[str] = ["context"]
    _allowed_output_targets: list[str] = ["context"]

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

    def _are_tools_called(
        self, state: T, component_name: str, router: BaseRouter[T]
    ) -> str:
        if state["status"] in [WorkflowStatusEnum.CANCELLED, WorkflowStatusEnum.ERROR]:
            return router.route(state)

        history: list[BaseMessage] = state["conversation_history"][component_name]
        last_message = history[-1]
        if isinstance(last_message, AIMessage) and len(last_message.tool_calls) > 0:
            return f"{self.name}#tools"

        return router.route(state)

    def __entry_hook__(self) -> Annotated[str, "Entry node name"]:
        return f"{self.name}#agent"

    def attach(
        self, graph: StateGraph, router: BaseRouter[T]
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
                events=self.ui_log_events.llm, writer=UILogWriterAgentLLM
            ),
        )
        node_tools = ToolNode(
            name=f"{self.name}#tools",
            component_name=self.name,
            toolset=self.toolset,
            ui_history=UIHistory(
                events=self.ui_log_events.tools, writer=UILogWriterAgentTools
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


class HiltChatBackComponent[T](BaseComponent[T]):
    _allowed_output_targets: list[str] = ["context", "conversation_history"]

    def __entry_hook__(self) -> Annotated[str, "Entry node name"]:
        return f"{self.name}#hiltChatBack"

    def attach(self, graph: StateGraph, router: BaseRouter[T]) -> str:
        graph.add_node(self.__entry_hook__(), self._request_human_prompt)
        graph.add_node(
            f"{self.name}#hiltChatBackFetchResponse", self._fetch_human_input
        )

        graph.add_edge(self.__entry_hook__(), f"{self.name}#hiltChatBackFetchResponse")
        graph.add_conditional_edges(
            f"{self.name}#hiltChatBackFetchResponse", router.route
        )

        return self.__entry_hook__()

    def _request_human_prompt(self, _state: T) -> dict[str, Any]:
        return {"status": WorkflowStatusEnum.INPUT_REQUIRED}

    def _fetch_human_input(self, _state: T) -> dict[str, Any]:
        human_input: str = interrupt("Workflow interrupted")

        serialized = {}
        if self.output and self.output.target == "context":
            serialized["context"] = create_nested_dict(self.output.subkeys, human_input)

        elif self.output and self.output.target == "conversation_history":
            serialized["conversation_history"] = create_nested_dict(
                self.output.subkeys,
                [
                    HumanMessage(content=human_input),
                ],
            )

        return {
            **serialized,
            "status": WorkflowStatusEnum.EXECUTION,
        }


class LambdaComponent[T](BaseComponent[T]):
    fn: Callable

    ui_role: MessageTypeEnum = Field(default=MessageTypeEnum.TOOL)
    ui_log_events: bool | list[UILogEventsTool] = Field(default=False)

    _ui_history: UIHistory[UILogWriterLambda] = PrivateAttr()
    _allowed_input_targets: list[str] = ["context"]
    _allowed_output_targets: list[str] = ["context"]

    @model_validator(mode="after")
    def init_component(self) -> Self:
        self._ui_history = UIHistory(
            events=self.ui_log_events, writer=UILogWriterLambda
        )

        return self

    def _run_lambda(self, state: T) -> dict[str, Any]:
        variables = get_vars_from_state(self.inputs, state["context"])
        context = state["context"].get(self.name, {})

        updates = self.fn(**variables)
        if updates and not self.output:
            raise Warning(
                "The lambda function returns a non-empty object, however the 'output' key was empty"
            )

        if updates:
            self._ui_history.log.success(
                str(updates),
                event=UILogEventsTool.ON_EXECUTION_SUCCESS,
                role=self.ui_role,
            )

            if self.output:
                context[self.output] = updates

        return {**self._ui_history.state, "context": {self.name: context}}

    def __entry_hook__(self):
        return f"{self.name}#lambda"

    def attach(
        self, graph: StateGraph, router: BaseRouter[T]
    ) -> Annotated[str, "Entry node name"]:
        self.__entry_hook__()

        graph.add_node(self.__entry_hook__(), self._run_lambda)
        graph.add_conditional_edges(self.__entry_hook__(), router.route)

        return self.__entry_hook__()
