import os
from datetime import datetime, timezone
from enum import StrEnum
from typing import Annotated, Any, List

from dependency_injector.wiring import Provide, inject
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langgraph.checkpoint.memory import BaseCheckpointSaver
from langgraph.graph import END, StateGraph
from langgraph.types import Command

from ai_gateway.container import ContainerApplication
from ai_gateway.prompts.registry import LocalPromptRegistry
from duo_workflow_service.agents import Agent
from duo_workflow_service.agents.chat_agent import ChatAgent
from duo_workflow_service.agents.tools_executor import ToolsExecutor
from duo_workflow_service.checkpointer.gitlab_workflow import WorkflowStatusEventEnum
from duo_workflow_service.components.tools_registry import ToolsRegistry
from duo_workflow_service.entities.state import (
    ChatWorkflowState,
    MessageTypeEnum,
    ToolStatus,
    UiChatLog,
    WorkflowStatusEnum,
)
from duo_workflow_service.interceptors.feature_flag_interceptor import (
    current_feature_flag_context,
)
from duo_workflow_service.tracking.errors import log_exception
from duo_workflow_service.workflows.abstract_workflow import AbstractWorkflow
from duo_workflow_service.llm_factory import create_chat_model

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


from langchain_core.runnables import Runnable
from duo_workflow_service.tools import Toolset
from langchain_core.language_models.chat_models import BaseChatModel
from duo_workflow_service.entities.state import DuoWorkflowStateType
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    MessageLikeRepresentation,
    SystemMessage,
)
import string
from pydantic import BaseModel

PROMPT_TEMPLATE = [(
"system",
"""
You are software engieer working on issue triage. 
Your task is to annalyse issue description and discussion 
in the issue coments, then base on that information create
an implementation plan. 
"""
),
(
"human",
"""
Prepare implementation plan for the issue provided in <issue> tag

To complete your assignment once you are ready you must call the handover_tool          
{state}

<issue>
{context.issue}
</issue>
"""
),
]

class AgentNode:
    name: str

    _model: Runnable
    _prompt_template: str
    _toolset: Toolset

    def __init__(
        self,
        *,
        model: BaseChatModel,
        name: str,
        prompt_template: list[tuple[str,str]],
        toolset: Toolset,
        workflow_id: str,
        check_events: bool = True,
    ):
        self._model = model.bind_tools(toolset.bindable)
        self._prompt_template = prompt_template
        self.name = name
        self._workflow_id = workflow_id
        self._toolset = toolset
        self._check_events = check_events

    async def run(self, state: DuoWorkflowStateType) -> dict:
            updates: dict[str, Any] = {
                "handover": [],
            }
            model_completion: list[MessageLikeRepresentation]

            if self.name in state["conversation_history"]:
                model_completion = self._model.ainvoke(
                    state["conversation_history"][self.name]
                )
                updates["conversation_history"] = {self.name: model_completion}
            else:
                messages = self._conversation_preamble(state)
                model_completion = await self._model.ainvoke(messages)
                updates["conversation_history"] = {
                    self.name: [*messages, *model_completion]
                }

            return updates
    
    def _conversation_preamble(self, state: DuoWorkflowStateType) -> list[BaseMessage]:
        formatter = string.Formatter()

        conversation_preamble: list[BaseMessage] = []

        for type, template in self._prompt_template:
            keys = [field_name for _, field_name, _, _ in formatter.parse(template) if field_name]
            content  = template.format(**{key:state['context'][key] for key in keys})

            if type == "system":
                conversation_preamble.append(
                    SystemMessage(content=content)
                )
            else:
                conversation_preamble.append(
                    HumanMessage(content=content)
                )
                
        return conversation_preamble

class ToolNode:
    _tool: Runnable    
    async def run(self, state: DuoWorkflowStateType):
        last_message = state["conversation_history"][self._tools_agent_name][-1]
        tool_calls = getattr(last_message, "tool_calls", [])
        tools_responses = []

        for tool_call in tool_calls:
            tool_name = tool_call["name"]
            tool_response = f"Tool {tool_name} not found"
            tool_args = tool_call.get("args", {})

            if tool_name in self._toolset:
                tool_response = await self._toolset[tool_name].arun(tool_args)

            tools_responses.append(
                ToolMessage(content=tool_response, tool_call_id=tool_call.get("id"))
            )

        return {
            "conversation_history": {self._tools_agent_name: tools_responses},
        }
    
class AgentComponent:
    inputs: list[str] = []
    outputs: BaseModel

    def __init__(
            self, 
            prompt_template,
            inputs, # ['issue']
            model, 
            toolset,
            workflow_id,
            workflow_type,
        ):
        # self._agent: ChatAgent = prompt_registry.get(  # type: ignore[assignment]
        #     "chat/agent", tools=toolset.bindable, prompt_version="^1.0.0"  # type: ignore[arg-type]
        # )
        self._agent_name = "chat/agent" + datetime.today().strftime("%Y%m%d")
        self.inputs = inputs
        self._agent = AgentNode(
            model=model,
            name=self._agent_name,
            prompt_template=prompt_template,
            toolset=toolset,
            workflow_id=workflow_id,

        )
        self.tools_runner = ToolNode(
            tools_agent_name=self._agent.name,
            toolset=toolset,
            workflow_id=workflow_id,
            workflow_type=workflow_type,
        ).run

    def _are_tools_called(self, state: ChatWorkflowState) -> Routes:
        if state["status"] in [WorkflowStatusEnum.CANCELLED, WorkflowStatusEnum.ERROR]:
            return Routes.STOP

        history: List[BaseMessage] = state["conversation_history"][self._agent.name]
        last_message = history[-1]
        if isinstance(last_message, AIMessage) and len(last_message.tool_calls) > 0:
            return Routes.TOOL_USE

        return Routes.STOP
    


    def attach(
            self, 
            graph: StateGraph,
            exit_node: str
        ) -> Annotated[str, "Entry node name"]:

        graph.add_node("agent", self._agent.run)
        graph.add_node("run_tools", self.tools_runner)

        graph.add_conditional_edges(
            "agent",
            self._are_tools_called,
            {
                Routes.TOOL_USE: "run_tools",
                Routes.STOP: exit_node
            },
        )
        graph.add_edge("run_tools", "agent")
        
        return "agent"


class JokerOputput(BaseModel):
    joke: str

class MyAwesomeWorkflow:
    def compile():
        comedian_agent = AgentComponent(
            inputs=['context.subject']
            outputs=JokerOputput,
            external_updates_emmiter=
        )
        censor_agent = AgentComponent(
            inputs=['context.joke', 'conversation_history[comic_agent.name]']
            outputs=JokerOputput,
        )

        self._assemble([
            comedian_agent,
            censor_agent,
        ])

    def _assemble(self, components: list[AgentComponent]):
        graph = StateGraph(ChatWorkflowState)
        outputs = []
        for component in components:
            if not component.inputs in outputs:
                raise Exception('missing inputs')
            
            outputs.append(component.outputs)            
            component.attach(graph,exit_node=END)


class Workflow(AbstractWorkflow):
    _stream: bool = True
    _agent: ChatAgent

    def _are_tools_called(self, state: ChatWorkflowState) -> Routes:
        if state["status"] in [WorkflowStatusEnum.CANCELLED, WorkflowStatusEnum.ERROR]:
            return Routes.STOP

        history: List[BaseMessage] = state["conversation_history"][self._agent.name]
        last_message = history[-1]
        if isinstance(last_message, AIMessage) and len(last_message.tool_calls) > 0:
            return Routes.TOOL_USE

        return Routes.STOP

    def get_workflow_state(self, goal: str) -> ChatWorkflowState:
        contextElements = self._context_elements or []

        initial_ui_chat_log = UiChatLog(
            message_type=MessageTypeEnum.TOOL,
            content=f"Starting chat: {goal}",
            timestamp=datetime.now(timezone.utc).isoformat(),
            status=ToolStatus.SUCCESS,
            correlation_id=None,
            tool_info=None,
            context_elements=contextElements,
        )

        return ChatWorkflowState(
            plan={"steps": []},
            status=WorkflowStatusEnum.NOT_STARTED,
            conversation_history={
                self._agent.name: [
                    HumanMessage(
                        content=goal,
                        additional_kwargs={
                            "additional_context": self._additional_context
                        },
                    ),
                ]
            },
            ui_chat_log=[initial_ui_chat_log],
            last_human_input=None,
            context_elements=contextElements,
            project=self._project,
        )

    async def get_graph_input(self, goal: str, status_event: str) -> Any:
        match status_event:
            case WorkflowStatusEventEnum.START:
                return self.get_workflow_state(goal)
            case WorkflowStatusEventEnum.RESUME:
                return Command(
                    goto="agent",
                    update={
                        "status": WorkflowStatusEnum.EXECUTION,
                        "conversation_history": {
                            self._agent.name: [
                                HumanMessage(
                                    content=goal,
                                    additional_kwargs={
                                        "additional_context": self._additional_context
                                    },
                                )
                            ]
                        },
                    },
                )
            case _:
                return None

    @inject
    def _compile(
        self,
        goal: str,
        tools_registry: ToolsRegistry,
        checkpointer: BaseCheckpointSaver,
        prompt_registry: LocalPromptRegistry = Provide[
            ContainerApplication.pkg_prompts.prompt_registry
        ],
    ):
        self.log.info(
            "ChatWorkflow._compile: Starting chat workflow compilation",
            workflow_id=self._workflow_id,
            goal=goal,
        )

        self._goal = goal
        graph = StateGraph(ChatWorkflowState)

        tools = self._get_tools()
        agents_toolset = tools_registry.toolset(tools)

        chat_agent_component = ReactAgentComponent(
            prompt="You are a helpful assistant. Your answers should be useful, polite, concise, and human-friendly.",
            model=create_chat_model(
                max_tokens=MAX_TOKENS_TO_SAMPLE,
                config=self._model_config,
            ),
            toolset=agents_toolset,
            workflow_id=self._workflow_id,
            workflow_type=self._workflow_type,
        )
        compoment_entry_point = chat_agent_component.attach(
            graph, 
            exit_node=END
        )
        self._agent = chat_agent_component._agent
        graph.set_entry_point(compoment_entry_point)

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

    def _get_tools(self):
        available_tools = CHAT_READ_ONLY_TOOLS
        feature_flags = current_feature_flag_context.get()
        if "duo_workflow_chat_mutation_tools" in feature_flags:
            available_tools = CHAT_READ_ONLY_TOOLS + CHAT_MUTATION_TOOLS

        if "duo_workflow_mcp_support" in feature_flags:
            available_tools += [tool.name for tool in self._additional_tools]

        return available_tools

    async def _handle_workflow_failure(
        self, error: BaseException, compiled_graph: Any, graph_config: Any
    ):
        log_exception(error, extra={"workflow_id": self._workflow_id})
