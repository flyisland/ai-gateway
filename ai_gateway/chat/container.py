from typing import TYPE_CHECKING

from dependency_injector import containers, providers

from ai_gateway.chat.agents import ReActAgent, TypeAgentEvent
from ai_gateway.chat.executor import GLAgentRemoteExecutor, TypeAgentFactory
from ai_gateway.chat.toolset import DuoChatToolsRegistry
from ai_gateway.integrations.amazon_q.chat import ChatAmazonQ
from ai_gateway.integrations.amazon_q.client import AmazonQClientFactory
from ai_gateway.integrations.amazon_q.message_processor import MessageProcessor
from ai_gateway.integrations.amazon_q.response_handlers import ResponseHandler

if TYPE_CHECKING:
    from ai_gateway.prompts import BasePromptRegistry

__all__ = [
    "ContainerChat",
]


def _react_agent_factory(
    prompt_registry: "BasePromptRegistry",
) -> TypeAgentFactory[TypeAgentEvent]:
    def _fn(**kwargs) -> ReActAgent:
        return prompt_registry.get("chat/react", "^1.0.0", **kwargs)

    return _fn


class ContainerChat(containers.DeclarativeContainer):
    prompts = providers.DependenciesContainer()
    models = providers.DependenciesContainer()
    internal_event = providers.DependenciesContainer()
    config = providers.Configuration(strict=True)

    # The dependency injector does not allow us to override the FactoryAggregate provider directly.
    # However, we can still override its internal sub-factories to achieve the same goal.
    _anthropic_claude_llm_factory = providers.Factory(models.anthropic_claude)
    _anthropic_claude_chat_factory = providers.Factory(models.anthropic_claude_chat)

    _react_agent_factory = providers.Factory(
        _react_agent_factory,
        prompt_registry=prompts.prompt_registry,
    )

    # Core dependencies
    message_processor = providers.Singleton(MessageProcessor)
    response_handler = providers.Singleton(ResponseHandler)

    # Client factory
    amazon_q_client_factory = providers.Singleton(
        AmazonQClientFactory, config=config.amazon_q
    )

    # Chat factory with validated config
    amazon_q_factory = providers.Factory(
        ChatAmazonQ,
        amazon_q_client_factory=amazon_q_client_factory,
        message_processor=message_processor,
        response_handler=response_handler,
        metadata=providers.Dict(user=providers.Callable(lambda: None)),
        model="amazon_q",
        temperature=0.7,
        max_retries=3,
    )

    # We need to resolve the model based on model name provided in request payload
    # Hence, `models._anthropic_claude` and `models._anthropic_claude_chat_factory` are only partially applied here.
    anthropic_claude_factory = providers.FactoryAggregate(
        llm=_anthropic_claude_llm_factory, chat=_anthropic_claude_chat_factory
    )

    litellm_factory = providers.Factory(models.litellm_chat)

    _tools_registry = providers.Factory(
        DuoChatToolsRegistry,
        self_hosted_documentation_enabled=config.custom_models.enabled,
    )

    gl_agent_remote_executor = providers.Factory(
        GLAgentRemoteExecutor,
        agent_factory=_react_agent_factory,
        tools_registry=_tools_registry,
        internal_event_client=internal_event.client,
    )
