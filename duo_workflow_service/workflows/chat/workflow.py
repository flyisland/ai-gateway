# pylint: disable=attribute-defined-outside-init
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, List, override

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langgraph.checkpoint.memory import BaseCheckpointSaver
from langgraph.graph import END, StateGraph
from langgraph.types import Command

from ai_gateway.model_metadata import (
    ModelSelectionMetadata,
    current_model_metadata_context,
)
from duo_workflow_service.agents.chat_agent import ChatAgent
from duo_workflow_service.checkpointer.gitlab_workflow import WorkflowStatusEventEnum
from duo_workflow_service.components.tools_registry import ToolsRegistry
from duo_workflow_service.agents.history_compactor import HistoryCompactor
from duo_workflow_service.agents.interrupt_node import InterruptNode
from duo_workflow_service.agents.chat_tools_executor import ChatToolsExecutor
from duo_workflow_service.workflows.type_definitions import AdditionalContext
from duo_workflow_service.entities.state import (
    ChatWorkflowState,
    MAX_CONTEXT_TOKENS,
    MessageTypeEnum,
    ToolStatus,
    UiChatLog,
    WorkflowStatusEnum,
    ChatFlowEvent,
    ChatFlowEventType
)
from duo_workflow_service.token_counter.approximate_token_counter import (
    ApproximateTokenCounter,
)
from duo_workflow_service.tracking.errors import log_exception
from duo_workflow_service.workflows.abstract_workflow import AbstractWorkflow
from lib.feature_flags.context import FeatureFlag, is_feature_enabled


class Routes(StrEnum):
    COMPACT_HISTORY = "compact_history"
    CHECK_HISTORY = "check_history"
    TOOL_USE = "tool_use"
    STOP = "stop"


CHAT_READ_ONLY_TOOLS = [
    "list_issues",
    "get_issue",
    "list_issue_notes",
    "get_issue_note",
    "get_job_logs",
    "get_merge_request",
    "get_pipeline_errors",
    "get_project",
    "run_read_only_git_command",
    "list_all_merge_request_notes",
    "list_merge_request_diffs",
    "gitlab_issue_search",
    "gitlab_blob_search",
    "gitlab_merge_request_search",
    "gitlab_documentation_search",
    "read_file",
    "get_repository_file",
    "list_dir",
    "find_files",
    "grep",
    "list_repository_tree",
    "get_epic",
    "list_epics",
    "scan_directory_tree",
    "list_epic_notes",
    "get_commit",
    "list_commits",
    "get_commit_comments",
    "get_commit_diff",
    "get_work_item",
    "list_work_items",
    "list_vulnerabilities",
    "get_work_item_notes",
    "list_instance_audit_events",
    "list_group_audit_events",
    "list_project_audit_events",
    "get_current_user",
]


CHAT_GITLAB_MUTATION_TOOLS = [
    "create_issue",
    "update_issue",
    "create_issue_note",
    "create_merge_request",
    "update_merge_request",
    "create_merge_request_note",
    "create_epic",
    "update_epic",
    "create_commit",
    "dismiss_vulnerability",
    "create_work_item",
    "link_vulnerability_to_issue",
]


CHAT_MUTATION_TOOLS = [
    "create_file_with_contents",
    "edit_file",
    # "mkdir",
]

RUN_COMMAND_TOOLS = ["run_command"]


class UserDecision(StrEnum):
    APPROVE = "approval"
    REJECT = "rejection"


class Workflow(AbstractWorkflow):
    _stream: bool = True
    _agent: ChatAgent
    _history_compactor: HistoryCompactor

    def _are_tools_called(self, state: ChatWorkflowState) -> Routes:
        if state["status"] in [WorkflowStatusEnum.CANCELLED, WorkflowStatusEnum.ERROR]:
            return Routes.STOP

        if state["status"] == WorkflowStatusEnum.TOOL_CALL_APPROVAL_REQUIRED:
            return Routes.STOP

        history: List[BaseMessage] = state["conversation_history"][self._agent.name]
        last_message = history[-1]
        if isinstance(last_message, AIMessage) and len(last_message.tool_calls) > 0:
            return Routes.TOOL_USE

        return Routes.CHECK_HISTORY

    def _is_history_compaction_needed(self, state: ChatWorkflowState) -> Routes:
        if not hasattr(self, '_agent') or not self._agent:
            return Routes.STOP

        history: List[BaseMessage] = state["conversation_history"][self._agent.name]
        token_counter = ApproximateTokenCounter(self._agent.name)
        total_tokens = token_counter.count_tokens(history)

        if total_tokens >= MAX_CONTEXT_TOKENS:
            return Routes.COMPACT_HISTORY
        return Routes.STOP

    def get_workflow_state(self, goal: str) -> ChatWorkflowState:
        initial_ui_chat_log = UiChatLog(
            message_sub_type=None,
            message_type=MessageTypeEnum.USER,
            content=goal,
            timestamp=datetime.now(timezone.utc).isoformat(),
            status=ToolStatus.SUCCESS,
            correlation_id=None,
            tool_info=None,
            additional_context=self._additional_context,
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
            project=self._project,
            namespace=self._namespace,
            approval=None,
        )

    def _resume_command(self, goal: str, additional_context: list[AdditionalContext] | None) -> Command:
        self.log.info("RESUME_COMMAND"*50)
        self.log.info(self._approval)
        event = ChatFlowEvent(
            event_type=ChatFlowEventType.RESPONSE,
            message=goal,
            additional_context=additional_context or [],
        )
        if not self._approval:
            return Command(resume=event)

        match self._approval.WhichOneof("user_decision"):
            case UserDecision.APPROVE:
                event = ChatFlowEvent(
                    event_type=ChatFlowEventType.APPROVE,
                    additional_context=additional_context,
                )
            case UserDecision.REJECT:
                event = ChatFlowEvent(
                    event_type=ChatFlowEventType.REJECT,
                    message=self._approval.rejection.message,
                    additional_context=additional_context,
                )
            case _:
                event = ChatFlowEvent(
                    event_type=ChatFlowEventType.RESPONSE,
                    message=goal,
                    additional_context=additional_context or [],
                )

        return Command(resume=event)

    async def get_graph_input(self, goal: str, status_event: str) -> Any:
        #state status work might be necessary
        new_chat_message = goal
        additional_context = self._additional_context

        match status_event:
            case WorkflowStatusEventEnum.START:
                return self.get_workflow_state(goal)
            case WorkflowStatusEventEnum.RESUME:
                return self._resume_command(new_chat_message, additional_context)
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
        graph = StateGraph(ChatWorkflowState)
        tools = self._get_tools()
        agents_toolset = tools_registry.toolset(tools)

        prompt_version = "^1.0.0"
        model_metadata = current_model_metadata_context.get()
        if not model_metadata and is_feature_enabled(
            FeatureFlag.DUO_AGENTIC_CHAT_OPENAI_GPT_5
        ):
            model_metadata = ModelSelectionMetadata(name="gpt_5")

        self._agent: ChatAgent = self._prompt_registry.get_on_behalf(
            user=self._user,
            prompt_id="chat/agent",
            prompt_version=prompt_version,
            model_metadata=model_metadata,
            internal_event_category=__name__,
            tools=agents_toolset.bindable,
        )

        self._agent.tools_registry = tools_registry

        self._history_compactor: HistoryCompactor = self._prompt_registry.get_on_behalf(
            user=self._user,
            prompt_id="history_compactor",
            prompt_version="^1.0.0",
            compacting_from=self._agent,
        )

        chat_tools_runner = ChatToolsExecutor(
            tools_agent_name=self._agent.name,
            toolset=agents_toolset,
            workflow_id=self._workflow_id,
            workflow_type=self._workflow_type,
        ).run

        # Add nodes
        graph.add_node("agent", self._agent.run)
        graph.add_node("run_tools", chat_tools_runner)
        graph.add_node("history_compression", self._history_compactor.run)
        graph.add_node(
            "tool_interrupt_node",
            InterruptNode(
                agent_name=self._agent.name,
            ).run,
        )
        graph.add_node(
            "no_tool_interrupt_node",
            InterruptNode(
                agent_name=self._agent.name,
            ).run,
        )

        graph.set_entry_point("agent")

        graph.add_conditional_edges(
            "agent",
            self._are_tools_called,
            {
                Routes.TOOL_USE: "tool_interrupt_node",
                Routes.CHECK_HISTORY: "no_tool_interrupt_node",
                Routes.STOP: END,
            },
        )

        graph.add_conditional_edges(
            "no_tool_interrupt_node",
            self._is_history_compaction_needed,
            {
                Routes.COMPACT_HISTORY: "history_compression",
                Routes.STOP: END,
            },
        )

        graph.add_edge("tool_interrupt_node", "run_tools")

        graph.add_conditional_edges(
            "run_tools",
            self._is_history_compaction_needed,
            {
                Routes.COMPACT_HISTORY: "history_compression",
                Routes.STOP: END,
            },
        )
        graph.add_edge("history_compression", END)

        return graph.compile(checkpointer=checkpointer)

    def _get_tools(self):
        available_tools = CHAT_READ_ONLY_TOOLS + CHAT_MUTATION_TOOLS + RUN_COMMAND_TOOLS

        if is_feature_enabled(FeatureFlag.DUO_WORKFLOW_WEB_CHAT_MUTATION_TOOLS):
            available_tools += CHAT_GITLAB_MUTATION_TOOLS

        return available_tools

    async def _handle_workflow_failure(
        self, error: BaseException, compiled_graph: Any, graph_config: Any
    ):
        log_exception(
            error, extra={"workflow_id": self._workflow_id, "source": __name__}
        )

    @override
    def _support_namespace_level_workflow(self) -> bool:
        return True
