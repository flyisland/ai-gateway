import os
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, StateGraph

from duo_workflow_service.agents.agent import Agent
from duo_workflow_service.components import ToolsRegistry
from duo_workflow_service.components.goal_disambiguation import (
    GoalDisambiguationComponent,
)
from duo_workflow_service.components.goal_disambiguation.component import _AGENT_NAME
from duo_workflow_service.components.goal_disambiguation.prompts import (
    ASSIGNMENT_PROMPT,
    PROMPT,
    SYS_PROMPT,
)
from duo_workflow_service.entities import (
    MessageTypeEnum,
    Plan,
    WorkflowEventType,
    WorkflowState,
    WorkflowStatusEnum,
)
from duo_workflow_service.gitlab.http_client import GitlabHttpClient
from duo_workflow_service.llm_factory import AnthropicConfig
from duo_workflow_service.tools import HandoverTool
from duo_workflow_service.tools.request_user_clarification import (
    RequestUserClarificationTool,
)
from lib.feature_flags import current_feature_flag_context
from lib.internal_events.event_enum import CategoryEnum


@pytest.fixture
def mock_create_model():
    with patch(
        "duo_workflow_service.components.goal_disambiguation.component.create_chat_model"
    ) as mock:
        mock.return_value = mock
        mock.bind_tools.return_value = mock
        yield mock


@pytest.fixture
def mock_agent():
    with patch(
        "duo_workflow_service.components.goal_disambiguation.component.Agent"
    ) as mock:
        mock_agent = MagicMock(spec=Agent)
        mock.return_value = mock_agent
        yield mock_agent


class TestGoalDisambiguationComponent:
    @pytest.fixture
    def mock_http_client(self):
        return AsyncMock(spec=GitlabHttpClient)

    @pytest.fixture
    def graph_config(self) -> RunnableConfig:
        return RunnableConfig(
            recursion_limit=50,
            configurable={"thread_id": "test-workflow"},
        )

    @pytest.fixture
    def tools_registry_mock(self):
        mock = MagicMock(ToolsRegistry)
        mock.get_batch.return_value = [RequestUserClarificationTool]
        return mock

    @pytest.fixture
    def graph_input(self) -> WorkflowState:
        return WorkflowState(
            plan=Plan(steps=[]),
            status=WorkflowStatusEnum.NOT_STARTED,
            conversation_history={},
            last_human_input=None,
            handover=[],
            ui_chat_log=[],
            project=None,
            goal=None,
            additional_context=None,
        )

    @pytest.fixture
    def llm_judge_response_unclear(self) -> AIMessage:
        return AIMessage(
            content="Please list which bugs you want to be fixed",
            tool_calls=[
                {
                    "id": "1",
                    "name": "request_user_clarification_tool",
                    "args": {
                        "recommendations": ["List issue links for bugs to fix"],
                        "message": "I need to understand which bug do you need to fix",
                        "clarity_score": 2.1,
                        "clarity_verdict": "UNCLEAR",
                    },
                }
            ],
        )

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("env_var", "env_var_val"),
        [
            ("FEATURE_GOAL_DISAMBIGUATION", "False"),
            ("USE_MEMSAVER", "True"),
        ],
    )
    @pytest.mark.usefixtures("mock_create_model")
    async def test_attach_with_feature_disabled(
        self,
        env_var: str,
        env_var_val: str,
        tools_registry_mock: ToolsRegistry,
        mock_http_client: GitlabHttpClient,
        graph_config: RunnableConfig,
    ):
        graph = StateGraph(WorkflowState)

        with (patch.dict(os.environ, {env_var: env_var_val}),):
            component = GoalDisambiguationComponent(
                goal="fix that bug",
                workflow_id=graph_config["configurable"]["thread_id"],
                allow_agent_to_request_user=True,
                model_config=AnthropicConfig(model_name="claude-sonnet-4-20250514"),
                tools_registry=tools_registry_mock,
                http_client=mock_http_client,
                workflow_type=CategoryEnum.WORKFLOW_SOFTWARE_DEVELOPMENT,
            )
            entry_point = component.attach(
                graph=graph,
                component_exit_node="test_node",
                component_execution_state=WorkflowStatusEnum.PLANNING,
                graph_termination_node=END,
            )

            assert (
                entry_point == "test_node"
            ), "Then disambiguation component should be skipped"

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("mock_create_model")
    @patch.dict(os.environ, {"FEATURE_GOAL_DISAMBIGUATION": "True"})
    async def test_attach_without_allow_agent_to_request_user(
        self,
        tools_registry_mock: ToolsRegistry,
        mock_http_client: GitlabHttpClient,
        graph_config: RunnableConfig,
    ):
        graph = StateGraph(WorkflowState)

        component = GoalDisambiguationComponent(
            goal="fix that bug",
            workflow_id=graph_config["configurable"]["thread_id"],
            allow_agent_to_request_user=False,
            model_config=AnthropicConfig(model_name="claude-sonnet-4-20250514"),
            tools_registry=tools_registry_mock,
            http_client=mock_http_client,
            workflow_type=CategoryEnum.WORKFLOW_SOFTWARE_DEVELOPMENT,
        )
        entry_point = component.attach(
            graph=graph,
            component_exit_node="test_node",
            component_execution_state=WorkflowStatusEnum.PLANNING,
            graph_termination_node=END,
        )

        assert (
            entry_point == "test_node"
        ), "Then disambiguation component should be skipped"

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("mock_create_model")
    @patch.dict(os.environ, {"FEATURE_GOAL_DISAMBIGUATION": "True"})
    async def test_component_prompt_construction(
        self,
        tools_registry_mock: ToolsRegistry,
        mock_http_client: GitlabHttpClient,
        graph_input: WorkflowState,
        graph_config: RunnableConfig,
        mock_agent: MagicMock,
    ):
        graph = StateGraph(WorkflowState)
        human_msg = HumanMessage(content="Please fix all the bugs in my code")
        ai_msg = AIMessage(content="Sure, will do")
        goal = "Fix all the bugs"
        graph_input["handover"] = [human_msg, ai_msg]

        expected_state = WorkflowState(
            plan=Plan(steps=[]),
            status=WorkflowStatusEnum.NOT_STARTED,
            conversation_history={
                _AGENT_NAME: [
                    SystemMessage(content=SYS_PROMPT),
                    HumanMessage(
                        content=PROMPT.format(
                            clarification_tool=RequestUserClarificationTool.tool_title,
                            handover_tool=HandoverTool.tool_title,
                        )
                    ),
                    HumanMessage(
                        content=ASSIGNMENT_PROMPT.format(
                            goal=goal,
                            conversation_history=f"{human_msg.pretty_repr()}\n{ai_msg.pretty_repr()}",
                        )
                    ),
                ]
            },
            ui_chat_log=[],
            handover=[human_msg, ai_msg],
            last_human_input=None,
            project=None,
            goal=None,
            additional_context=None,
        )
        mock_agent.run.return_value = {
            "conversation_history": {
                "clarity_judge": [AIMessage(content="All clear please proceed")]
            },
        }

        component = GoalDisambiguationComponent(
            goal=goal,
            workflow_id=graph_config["configurable"]["thread_id"],  # etype:ignore
            allow_agent_to_request_user=True,
            model_config=AnthropicConfig(model_name="claude-sonnet-4-20250514"),
            tools_registry=tools_registry_mock,
            http_client=mock_http_client,
            workflow_type=CategoryEnum.WORKFLOW_SOFTWARE_DEVELOPMENT,
        )
        entry_point = component.attach(
            graph=graph,
            component_exit_node=END,
            component_execution_state=WorkflowStatusEnum.PLANNING,
            graph_termination_node=END,
        )
        graph.set_entry_point(entry_point)
        compiled_graph = graph.compile()

        await compiled_graph.ainvoke(input=graph_input, config=graph_config)

        mock_agent.run.assert_has_calls(
            [call(expected_state)],
            any_order=True,
        )

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("mock_create_model")
    @patch.dict(os.environ, {"FEATURE_GOAL_DISAMBIGUATION": "True"})
    async def test_component_run_with_clear_goal(
        self,
        tools_registry_mock: ToolsRegistry,
        mock_http_client: GitlabHttpClient,
        graph_input: WorkflowState,
        graph_config: RunnableConfig,
        mock_agent: MagicMock,
    ):
        current_feature_flag_context.set({"duo_workflow_use_handover_summary"})
        graph = StateGraph(WorkflowState)
        input = WorkflowState(
            plan=Plan(steps=[]),
            status=WorkflowStatusEnum.NOT_STARTED,
            conversation_history={},
            last_human_input=None,
            handover=[],
            ui_chat_log=[],
            project=None,
            goal=None,
            additional_context=None,
        )

        mock_agent.run.return_value = {
            "conversation_history": {
                "clarity_judge": [
                    AIMessage(
                        content="All clear please proceed",
                        tool_calls=[
                            {
                                "id": "1",
                                "name": "handover_tool",
                                "args": {"summary": "This is a summary"},
                            }
                        ],
                    )
                ]
            },
        }

        component = GoalDisambiguationComponent(
            goal="Fix all the bugs",
            workflow_id=graph_config["configurable"]["thread_id"],
            allow_agent_to_request_user=True,
            model_config=AnthropicConfig(model_name="claude-sonnet-4-20250514"),
            tools_registry=tools_registry_mock,
            http_client=mock_http_client,
            workflow_type=CategoryEnum.WORKFLOW_SOFTWARE_DEVELOPMENT,
        )
        entry_point = component.attach(
            graph=graph,
            component_exit_node=END,
            component_execution_state=WorkflowStatusEnum.PLANNING,
            graph_termination_node=END,
        )
        graph.set_entry_point(entry_point)
        compiled_graph = graph.compile()

        response = await compiled_graph.ainvoke(input=graph_input, config=graph_config)

        assert len(response["handover"]) == 1
        assert response["handover"][-1] == AIMessage(content="This is a summary")

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("mock_create_model")
    @patch("duo_workflow_service.components.goal_disambiguation.component.interrupt")
    @patch.dict(os.environ, {"FEATURE_GOAL_DISAMBIGUATION": "True"})
    async def test_component_run_with_unclear_goal(
        self,
        mock_interrupt,
        tools_registry_mock: ToolsRegistry,
        mock_http_client: GitlabHttpClient,
        graph_input: WorkflowState,
        graph_config: RunnableConfig,
        llm_judge_response_unclear: AIMessage,
        mock_agent: MagicMock,
    ):
        current_feature_flag_context.set({"duo_workflow_use_handover_summary"})
        graph = StateGraph(WorkflowState)
        mock_interrupt.return_value = {
            "event_type": WorkflowEventType.MESSAGE,
            "message": "Bugs are described in issues 1, 2, 3, and 4",
        }

        mock_agent.run.side_effect = [
            {
                "conversation_history": {"clarity_judge": [llm_judge_response_unclear]},
            },
            {
                "conversation_history": {
                    "clarity_judge": [
                        AIMessage(
                            content="All clear please proceed",
                            tool_calls=[
                                {
                                    "id": "1",
                                    "name": "handover_tool",
                                    "args": {"summary": "This is a summary"},
                                }
                            ],
                        )
                    ]
                },
            },
        ]

        component = GoalDisambiguationComponent(
            goal="Fix all the bugs",
            workflow_id=graph_config["configurable"]["thread_id"],
            allow_agent_to_request_user=True,
            model_config=AnthropicConfig(model_name="claude-sonnet-4-20250514"),
            tools_registry=tools_registry_mock,
            http_client=mock_http_client,
            workflow_type=CategoryEnum.WORKFLOW_SOFTWARE_DEVELOPMENT,
        )
        entry_point = component.attach(
            graph=graph,
            component_exit_node=END,
            component_execution_state=WorkflowStatusEnum.PLANNING,
            graph_termination_node=END,
        )
        graph.set_entry_point(entry_point)
        compiled_graph = graph.compile()

        response = await compiled_graph.ainvoke(input=graph_input, config=graph_config)

        # assert that the component requested user input
        mock_interrupt.assert_called_once()
        # assert correct ui communication between the component and UI client
        assert len(response["ui_chat_log"]) == 3
        assert (
            response["ui_chat_log"][0]["content"]
            == "I need to understand which bug do you need to fix\n\nI'm ready to help with your project but I need a few key details:\n\n1. List issue links for bugs to fix"
        )
        assert response["ui_chat_log"][0]["message_type"] == MessageTypeEnum.REQUEST
        assert (
            response["ui_chat_log"][1]["content"]
            == "Bugs are described in issues 1, 2, 3, and 4"
        )
        assert response["ui_chat_log"][1]["message_type"] == MessageTypeEnum.USER
        assert response["ui_chat_log"][2]["content"] == "This is a summary"
        assert response["ui_chat_log"][2]["message_type"] == MessageTypeEnum.AGENT

        # assert clarity reevaluation cycle
        assert mock_agent.run.call_count == 2
        # only 1 handover message which is a summary
        assert len(response["handover"]) == 1
        assert response["handover"][-1].content == "This is a summary"

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("mock_create_model")
    @patch("duo_workflow_service.components.goal_disambiguation.component.interrupt")
    @patch.dict(os.environ, {"FEATURE_GOAL_DISAMBIGUATION": "True"})
    async def test_component_run_with_string_recommendations(
        self,
        mock_interrupt,
        tools_registry_mock: ToolsRegistry,
        mock_http_client: GitlabHttpClient,
        graph_input: WorkflowState,
        graph_config: RunnableConfig,
        llm_judge_response_unclear: AIMessage,
        mock_agent: MagicMock,
    ):

        llm_judge_response_unclear.tool_calls[0]["args"][
            "recommendations"
        ] = "List issue links for bugs to fix"

        graph = StateGraph(WorkflowState)
        mock_interrupt.return_value = {
            "event_type": WorkflowEventType.MESSAGE,
            "message": "Bugs are described in issues 1, 2, 3, and 4",
        }

        mock_agent.run.side_effect = [
            {
                "conversation_history": {"clarity_judge": [llm_judge_response_unclear]},
            },
            {
                "conversation_history": {
                    "clarity_judge": [AIMessage(content="All clear please proceed")]
                },
            },
        ]

        component = GoalDisambiguationComponent(
            goal="Fix all the bugs",
            workflow_id=graph_config["configurable"]["thread_id"],
            allow_agent_to_request_user=True,
            model_config=AnthropicConfig(model_name="claude-sonnet-4-20250514"),
            tools_registry=tools_registry_mock,
            http_client=mock_http_client,
            workflow_type=CategoryEnum.WORKFLOW_SOFTWARE_DEVELOPMENT,
        )
        entry_point = component.attach(
            graph=graph,
            component_exit_node=END,
            component_execution_state=WorkflowStatusEnum.PLANNING,
            graph_termination_node=END,
        )
        graph.set_entry_point(entry_point)
        compiled_graph = graph.compile()

        response = await compiled_graph.ainvoke(input=graph_input, config=graph_config)

        # assert that the component requested user input
        mock_interrupt.assert_called_once()
        # assert correct ui communication between the component and UI client
        assert len(response["ui_chat_log"]) == 2
        assert (
            response["ui_chat_log"][0]["content"]
            == "I need to understand which bug do you need to fix\n\nI'm ready to help with your project but I need a few key details:\n\n1. List issue links for bugs to fix"
        )

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("mock_create_model")
    @patch("duo_workflow_service.components.goal_disambiguation.component.interrupt")
    @patch.dict(os.environ, {"FEATURE_GOAL_DISAMBIGUATION": "True"})
    async def test_component_run_with_resume(
        self,
        mock_interrupt,
        tools_registry_mock: ToolsRegistry,
        mock_http_client: GitlabHttpClient,
        graph_input: WorkflowState,
        graph_config: RunnableConfig,
        llm_judge_response_unclear: AIMessage,
        mock_agent: MagicMock,
    ):
        graph = StateGraph(WorkflowState)
        mock_interrupt.side_effect = [
            {
                "event_type": WorkflowEventType.RESUME,
                "message": "",
            },
            {
                "event_type": WorkflowEventType.MESSAGE,
                "message": "Bugs are described in issues 1, 2, 3, and 4",
            },
        ]

        mock_agent.run.side_effect = [
            {
                "conversation_history": {"clarity_judge": [llm_judge_response_unclear]},
            },
            {
                "conversation_history": {
                    "clarity_judge": [AIMessage(content="All clear please proceed")]
                },
            },
        ]

        component = GoalDisambiguationComponent(
            goal="Fix all the bugs",
            workflow_id=graph_config["configurable"]["thread_id"],
            allow_agent_to_request_user=True,
            model_config=AnthropicConfig(model_name="claude-sonnet-4-20250514"),
            tools_registry=tools_registry_mock,
            http_client=mock_http_client,
            workflow_type=CategoryEnum.WORKFLOW_SOFTWARE_DEVELOPMENT,
        )
        entry_point = component.attach(
            graph=graph,
            component_exit_node=END,
            component_execution_state=WorkflowStatusEnum.PLANNING,
            graph_termination_node=END,
        )
        graph.set_entry_point(entry_point)
        compiled_graph = graph.compile()

        await compiled_graph.ainvoke(input=graph_input, config=graph_config)

        # Assert that interrupt was called twice - first for cancellation, then for message event
        assert mock_interrupt.call_count == 2

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("mock_create_model")
    @patch("duo_workflow_service.components.goal_disambiguation.component.interrupt")
    @patch.dict(os.environ, {"FEATURE_GOAL_DISAMBIGUATION": "True"})
    async def test_component_run_with_stop_event(
        self,
        mock_interrupt,
        tools_registry_mock: ToolsRegistry,
        mock_http_client: GitlabHttpClient,
        graph_input: WorkflowState,
        graph_config: RunnableConfig,
        llm_judge_response_unclear: AIMessage,
        mock_agent: MagicMock,
    ):
        graph = StateGraph(WorkflowState)
        mock_interrupt.side_effect = [
            {
                "event_type": WorkflowEventType.STOP,
                "message": "",
            },
        ]

        mock_agent.run.return_value = {
            "conversation_history": {"clarity_judge": [llm_judge_response_unclear]},
        }

        component = GoalDisambiguationComponent(
            goal="Fix bug in pipeline configuration",
            workflow_id=graph_config["configurable"]["thread_id"],
            allow_agent_to_request_user=True,
            model_config=AnthropicConfig(model_name="claude-sonnet-4-20250514"),
            tools_registry=tools_registry_mock,
            http_client=mock_http_client,
            workflow_type=CategoryEnum.WORKFLOW_SOFTWARE_DEVELOPMENT,
        )
        entry_point = component.attach(
            graph=graph,
            component_exit_node=END,
            component_execution_state=WorkflowStatusEnum.PLANNING,
            graph_termination_node=END,
        )
        graph.set_entry_point(entry_point)
        compiled_graph = graph.compile()

        response = await compiled_graph.ainvoke(input=graph_input, config=graph_config)

        assert mock_agent.run.call_count == 1
        mock_interrupt.assert_called_once()
        assert response["handover"] == graph_input["handover"]

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("mock_create_model")
    @patch.dict(os.environ, {"FEATURE_GOAL_DISAMBIGUATION": "True"})
    @patch("duo_workflow_service.components.goal_disambiguation.component.interrupt")
    async def test_component_run_with_agent_stop_response(
        self,
        mock_interrupt,
        tools_registry_mock: ToolsRegistry,
        mock_http_client: GitlabHttpClient,
        graph_input: WorkflowState,
        graph_config: RunnableConfig,
        llm_judge_response_unclear: AIMessage,
        mock_agent: MagicMock,
    ):
        graph = StateGraph(WorkflowState)

        mock_agent.run.return_value = {"status": WorkflowStatusEnum.CANCELLED}

        component = GoalDisambiguationComponent(
            goal="Fix bug in pipeline configuration",
            workflow_id=graph_config["configurable"]["thread_id"],
            allow_agent_to_request_user=True,
            model_config=AnthropicConfig(model_name="claude-sonnet-4-20250514"),
            tools_registry=tools_registry_mock,
            http_client=mock_http_client,
            workflow_type=CategoryEnum.WORKFLOW_SOFTWARE_DEVELOPMENT,
        )
        entry_point = component.attach(
            graph=graph,
            component_exit_node=END,
            component_execution_state=WorkflowStatusEnum.PLANNING,
            graph_termination_node=END,
        )
        graph.set_entry_point(entry_point)
        compiled_graph = graph.compile()

        response = await compiled_graph.ainvoke(input=graph_input, config=graph_config)

        assert mock_agent.run.call_count == 1
        assert response["status"] == WorkflowStatusEnum.CANCELLED
        assert response["handover"] == graph_input["handover"]
        mock_interrupt.assert_not_called()
