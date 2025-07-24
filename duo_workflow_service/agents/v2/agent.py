import json
from datetime import datetime, timezone
from typing import Any, cast

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.prompt_values import PromptValue
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.prompts.chat import MessageLikeRepresentation
from langchain_core.runnables import Runnable, RunnableConfig

from ai_gateway.prompts import Prompt
from ai_gateway.prompts.base import jinja2_formatter
from ai_gateway.prompts.config.base import PromptConfig
from ai_gateway.prompts.config.models import ModelClassProvider
from duo_workflow_service.entities.event import WorkflowEvent, WorkflowEventType
from duo_workflow_service.entities.state import (
    DuoWorkflowStateType,
    MessageTypeEnum,
    UiChatLog,
    WorkflowStatusEnum,
)
from duo_workflow_service.gitlab.events import get_event
from duo_workflow_service.gitlab.http_client import GitlabHttpClient
from duo_workflow_service.monitoring import duo_workflow_metrics
from duo_workflow_service.tools.handover import HandoverTool


class AgentPromptTemplate(Runnable[DuoWorkflowStateType, PromptValue]):
    messages: list[BaseMessage]

    def __init__(self, agent_name: str, prompt_template: dict[str, str], **kwargs: Any):
        self.agent_name = agent_name
        self.prompt_template = prompt_template
        self.template_kwargs = kwargs

    def invoke(
        self,
        input: DuoWorkflowStateType,
        config: RunnableConfig | None = None,
        **kwargs: Any,
    ) -> PromptValue:
        messages: list[MessageLikeRepresentation] = []

        if self.agent_name in input["conversation_history"]:
            messages = cast(
                list[MessageLikeRepresentation],
                input["conversation_history"][self.agent_name],
            )
        else:
            messages = self._conversation_preamble(input, self.prompt_template)

        inputs = cast(dict, input)
        inputs["handover_tool_name"] = HandoverTool.tool_title
        inputs["get_plan_tool_name"] = "get_plan"
        inputs["set_task_status_tool_name"] = "set_task_status"
        inputs["is_anthropic_model"] = self.template_kwargs.get(
            "is_anthropic_model", False
        )

        prompt_value = ChatPromptTemplate.from_messages(
            messages, template_format="jinja2"
        ).invoke(inputs, config, **kwargs)
        self.messages = prompt_value.to_messages()

        return prompt_value

    def _conversation_preamble(
        self, state: DuoWorkflowStateType, prompt_template: dict[str, str]
    ) -> list[MessageLikeRepresentation]:
        conversation_preamble: list[MessageLikeRepresentation] = []

        if "system_static" in prompt_template:
            cached_content = jinja2_formatter(
                prompt_template["system_static"],
                get_plan_tool_name="get_plan",
                set_task_status_tool_name="set_task_status",
                is_anthropic_model=self.template_kwargs.get("is_anthropic_model"),
                handover_tool_name=HandoverTool.tool_title,
            )
            if self.template_kwargs.get("is_anthropic_model"):
                parsed_content = json.loads(cached_content)
                cached_content = parsed_content

            conversation_preamble.append(SystemMessage(content=cached_content))

        if "system_dynamic" in prompt_template:
            conversation_preamble.append(("system", prompt_template["system_dynamic"]))

        if state.get("handover"):  # type: ignore
            conversation_preamble.extend(
                [
                    HumanMessage(
                        content="The steps towards goal accomplished so far are as follow:"
                    ),
                    *state.get("handover"),  # type: ignore
                ]
            )

        if "user" in prompt_template:
            conversation_preamble.append(("user", prompt_template["user"]))

        return conversation_preamble


class Agent(Prompt[DuoWorkflowStateType, BaseMessage]):
    check_events: bool = True
    workflow_id: str
    http_client: GitlabHttpClient

    @staticmethod
    def _get_model_provider_attribute(config: PromptConfig) -> str | None:
        model_config = getattr(config, "model", None)
        if model_config:
            params = getattr(model_config, "params", None)
            if params:
                model_class_provider = getattr(params, "model_class_provider", None)
                return model_class_provider
        return None

    @classmethod
    def _build_prompt_template(
        cls, config: PromptConfig
    ) -> Runnable[DuoWorkflowStateType, PromptValue]:
        # Extract model config to determine if it's an Anthropic model
        model_class_provider = cls._get_model_provider_attribute(config)
        is_anthropic_model = model_class_provider is ModelClassProvider.ANTHROPIC
        return AgentPromptTemplate(
            config.name, config.prompt_template, is_anthropic_model=is_anthropic_model
        )

    async def run(self, state: DuoWorkflowStateType) -> dict[str, Any]:
        with duo_workflow_metrics.time_compute(
            operation_type=f"{self.name}_processing"
        ):
            updates: dict[str, Any] = {
                "handover": [],
            }

            if self.check_events:
                event: WorkflowEvent | None = await get_event(
                    self.http_client, self.workflow_id, False
                )

                if event and event["event_type"] == WorkflowEventType.STOP:
                    return {"status": WorkflowStatusEnum.CANCELLED}

            model_completion = await super().ainvoke(state)

            if self.name in state["conversation_history"]:
                updates["conversation_history"] = {self.name: [model_completion]}
            else:
                messages = cast(AgentPromptTemplate, self.prompt_tpl).messages
                updates["conversation_history"] = {
                    self.name: [*messages, model_completion]
                }

            return {
                **updates,
                **self._respond_to_human(state, model_completion),
            }

    def _respond_to_human(self, state, model_completion) -> dict[str, Any]:
        if not isinstance(model_completion, AIMessage):
            return {}

        last_human_input = state.get("last_human_input")
        if (
            isinstance(last_human_input, dict)
            and last_human_input.get("event_type") == WorkflowEventType.MESSAGE
        ):
            content = self._parse_model_content(model_completion.content)
            return {
                "ui_chat_log": ([self._create_ui_chat_log(content)] if content else []),
                "last_human_input": None,
            }

        return {}

    def _parse_model_content(self, content: str | list) -> str | None:
        if isinstance(content, str):
            return content

        if isinstance(content, list) and all(isinstance(item, str) for item in content):
            return "\n".join(content)

        return next(
            (
                item.get("text")
                for item in content
                if isinstance(item, dict) and item.get("text", False)
            ),
            None,
        )

    def _create_ui_chat_log(self, content: str) -> UiChatLog:
        return UiChatLog(
            message_type=MessageTypeEnum.AGENT,
            message_sub_type=None,
            content=content,
            timestamp=datetime.now(timezone.utc).isoformat(),
            status=None,
            correlation_id=None,
            tool_info=None,
            additional_context=None,
        )
