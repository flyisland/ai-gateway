import os
from datetime import datetime, timezone
from enum import StrEnum
from typing import Annotated, Any, List, Optional

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.memory import BaseCheckpointSaver
from langgraph.graph import END, StateGraph

from duo_workflow_service.agents.chat_agent import ChatAgent
from duo_workflow_service.checkpointer.gitlab_workflow import WorkflowStatusEventEnum
from duo_workflow_service.components.tools_registry import ToolsRegistry
from duo_workflow_service.entities.state import (
    ChatWorkflowState,
    PoCWorkflowState,
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
from duo_workflow_service.agents import RunToolNode
from duo_workflow_service.tools import DuoBaseTool

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    MessageLikeRepresentation,
    SystemMessage,
)
import string
from pydantic import BaseModel, Field
import uuid

DEFAULT_PROMPT_TEMPLATE = [
    (
"system",
"""
You are software engieer working on issue triage. Your task is to annalyse issue description and discussion in the issue coments.
"""
    ),
    (
"human",
"""
{user_prompt}

Make sure to write a clear and professional comment on an issue provided in <issue> tag and call handover_tool to finish your work.

<issue>
{issue}
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
            model_completion: list[MessageLikeRepresentation]

            if self.name in state["conversation_history"]:
                model_completion = await self._model.ainvoke(
                    state["conversation_history"][self.name]
                )
                state["conversation_history"][self.name].append(model_completion)
            else:
                messages = self._conversation_preamble(state)
                model_completion = await self._model.ainvoke(messages)
                state["conversation_history"][self.name] = [*messages, model_completion]

            return state
    
    def _conversation_preamble(self, state: DuoWorkflowStateType) -> list[BaseMessage]:
        formatter = string.Formatter()

        conversation_preamble: list[BaseMessage] = []

        for type, template in self._prompt_template:
            keys = [field_name for _, field_name, _, _ in formatter.parse(template) if field_name]
            variables = {}

            for key in keys:
                if "__" in key:
                    subkeys = key.split("__")
                    current = state["context"]
                    for subkey in subkeys:
                        current = current[subkey]
                    variables[key] = current
                else:
                    variables[key] = state["context"].get(key, "")
            content  = template.format(**variables)

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
    _tools_agent_name: str
    def __init__(
            self,
            agent_name,
            toolset,
            workflow_id,
            workflow_type,
        ):
        self._tools_agent_name=agent_name
        self._toolset=toolset
        self._workflow_id=workflow_id
        self._workflow_type=workflow_type
  
    async def run(self, state: DuoWorkflowStateType):
        conversation_history=state["conversation_history"]
        context=state["context"]

        last_message = conversation_history[self._tools_agent_name][-1]
        tool_calls = getattr(last_message, "tool_calls", [])
        tools_responses = []

        for tool_call in tool_calls:
            tool_name = tool_call["name"]
            tool_args = tool_call.get("args", {})
            context[tool_name] = tool_args
            tool_response = f"Tool {tool_name} not found"
            if tool_name in self._toolset:
                tool_response = await self._toolset[tool_name].arun(tool_args)

            tools_responses.append(
                ToolMessage(content=tool_response, tool_call_id=tool_call.get("id"))
            )

        conversation_history[self._tools_agent_name].extend(tools_responses)
        return {
                'conversation_history': conversation_history,
                'context': context 
            }

class BaseComponent:
    inputs: list[str] = []
    output: Optional[str]
    _id: str

    def __init__(self, inputs, output):
        self.inputs = inputs
        self.output = output
        self._id = str(uuid.uuid4())   

class AgentComponent(BaseComponent):
    def __init__(
            self, 
            prompt_template,
            inputs, # ['issue']
            output,
            model, 
            toolset,
            workflow_id,
            workflow_type,
        ):
        # self._agent: ChatAgent = prompt_registry.get(  # type: ignore[assignment]
        #     "chat/agent", tools=toolset.bindable, prompt_version="^1.0.0"  # type: ignore[arg-type]
        # )

        super().__init__(inputs=inputs, output=output)
        self._prompt_template = prompt_template
        self._model = model
        self._toolset = toolset
        self._workflow_id = workflow_id
        self._workflow_type = workflow_type


    def _are_tools_called(self, state: ChatWorkflowState) -> Routes:
        if state["status"] in [WorkflowStatusEnum.CANCELLED, WorkflowStatusEnum.ERROR]:
            return Routes.STOP

        history: List[BaseMessage] = state["conversation_history"][self.agent_name]
        last_message = history[-1]
        if isinstance(last_message, AIMessage) and len(last_message.tool_calls) > 0:
            if last_message.tool_calls[0]['name'] == 'handover_tool':
                return Routes.STOP
            
            return Routes.TOOL_USE

        return Routes.STOP

    @property
    def agent_name(self):
        return f"agent_{self._id}"
    
    def attach(
            self, 
            graph: StateGraph,
            exit_node: str
        ) -> Annotated[str, "Entry node name"]:

        agent = AgentNode(
            model=self._model,
            name=self.agent_name,
            prompt_template=self._prompt_template,
            toolset=self._toolset,
            workflow_id=self._workflow_id,

        )
        tools_runner = ToolNode(
            agent_name=self.agent_name,
            toolset=self._toolset,
            workflow_id=self._workflow_id,
            workflow_type=self._workflow_type,
        ).run

        graph.add_node(f"{self.agent_name}", agent.run)
        graph.add_node(f"{self.agent_name}_run_tools", tools_runner)

        graph.add_conditional_edges(
            f"{self.agent_name}",
            self._are_tools_called,
            {
                Routes.TOOL_USE: f"{self.agent_name}_run_tools",
                Routes.STOP: exit_node
            },
        )
        graph.add_edge(f"{self.agent_name}_run_tools", f"{self.agent_name}")
        
        return f"{self.agent_name}"

class RunToolComponent(BaseComponent):
    _tool: DuoBaseTool

    def __init__(
            self,
            tool,
            output: str,
            inputs: list[str], # issue_iid
        ):
        super().__init__(inputs=inputs, output=output)
        self._tool = tool

    def output_parser(self, raw_outputs: list, state: PoCWorkflowState):
        context = state['context']
        context[self.output] = raw_outputs[0]

        return  { 'context': context }
    
    def input_parser(self, state: PoCWorkflowState):
        return [{key:state['context'][key] for key in self.inputs}]

    def attach(
        self, 
        graph: StateGraph,
        exit_node: str
    ) -> Annotated[str, "Entry node name"]:
        graph.add_node(
            f"tool_node_{self._id}",
            RunToolNode[PoCWorkflowState](self._tool, self.input_parser, self.output_parser).run
        )
        graph.add_edge(f"tool_node_{self._id}", exit_node)

        return f"tool_node_{self._id}"

class Workflow(AbstractWorkflow):
    _agent: ChatAgent

    def _get_issue_id_from_metadata(self):
        return self._workflow_metadata.get("issue_iid", "")

    
    def _build_dynamic_prompt_template(self, default_template, goal):
        prompts = dict(default_template)
        
        if "human" in prompts:
            prompts["human"] = prompts["human"].format(user_prompt=goal, issue="{issue}")
        
        return [
            ("system", prompts.get("system")),
            ("human", prompts.get("human"))
        ]



    def _assemble(self, components: list[BaseComponent], graph_input):
        graph = StateGraph(PoCWorkflowState)
        outputs = []
        previous_node = END
        for component in components:
            for input in component.inputs:
                if not input in outputs and not input in graph_input['context']:
                    raise Exception('missing inputs')
            outputs.append(component.output)
        
        for component in reversed(components):
            previous_node = component.attach(graph, exit_node=previous_node)
        
        graph.set_entry_point(previous_node)
        return graph

    def get_workflow_state(self, goal: str) -> PoCWorkflowState:
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
        issue_iid = self._get_issue_id_from_metadata()
        project_id = self._project.get('id')   
        return PoCWorkflowState(
            status=WorkflowStatusEnum.NOT_STARTED,
            conversation_history={
            },
            ui_chat_log=[initial_ui_chat_log],
            context={
                'issue_iid': issue_iid,
                'project_id': project_id,
            }
        )

    async def get_graph_input(self, goal: str, status_event: str) -> Any:
        match status_event:
            case WorkflowStatusEventEnum.START:
                return self.get_workflow_state(goal)
            case _:
                return None


    def _compile(
        self,
        goal: str,
        tools_registry: ToolsRegistry,
        checkpointer: BaseCheckpointSaver,
    ):
        self.log.info(
            "ChatWorkflow._compile: Starting chat workflow compilation",
            workflow_id=self._workflow_id,
            goal=goal,
        )

        self._goal = goal

        tools = [
            'create_issue_note',
            'handover_tool'
        ]
        agents_toolset = tools_registry.toolset(tools)
        deterministic_toolset = tools_registry.toolset(['get_issue'])
        dynamic_prompt_template = self._build_dynamic_prompt_template(DEFAULT_PROMPT_TEMPLATE, goal)
        components = [
            RunToolComponent(
                deterministic_toolset['get_issue'],
                inputs=['issue_iid', 'project_id'],
                output='issue'
            ),
            AgentComponent(
                prompt_template=dynamic_prompt_template,
                inputs=['issue'],
                output='create_issue_note__body',
                model=create_chat_model(self._model_config),
                toolset=agents_toolset,
                workflow_id=self._workflow_id,
                workflow_type=self._workflow_type
            )
        ]
        graph = self._assemble(components=components, graph_input=self.get_workflow_state(goal))

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
