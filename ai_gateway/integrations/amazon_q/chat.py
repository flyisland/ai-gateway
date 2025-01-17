import os

from typing import Any, Dict, Iterator, List, Optional

from langchain_core.callbacks.manager import CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, ChatMessageChunk
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult

__all__ = [
    "ChatAmazonQ",
]


class ChatAmazonQ(BaseChatModel):
    amazon_q_client_factory: Any

    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        message = self._build_response(messages=messages)
        generations = [ChatGeneration(message=AIMessage(content=message))]
        llm_output = {"token_usage": 100, "model": "amazon_q"}

        return ChatResult(generations=generations, llm_output=llm_output)

    def _stream(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> Iterator[ChatGenerationChunk]:
        message = self._build_response(messages=messages)
        cg_chunk = ChatGenerationChunk(
            message=ChatMessageChunk(content=message, role="system")
        )
        if run_manager:
            run_manager.on_llm_new_token(message, chunk=cg_chunk)
        yield cg_chunk

    def _build_response(self, messages: List[BaseMessage]):
        current_user = self.metadata["user"]
        # pylint: disable=direct-environment-variable-reference
        role_arn = os.environ.get("AWS_ROLE_ARN")
        # pylint: enable=direct-environment-variable-reference

        q_client = self.amazon_q_client_factory.get_client(
            current_user=current_user,
            auth_header=current_user.auth_header,
            role_arn=role_arn,
        )

        print(q_client.client) # returns the boto3 client

        return f"Amazon Q Response: {messages[0].content[0:100]}"

    @property
    def _identifying_params(self) -> Dict[str, Any]:
        return {
            "model": "amazon_q",
        }

    @property
    def _llm_type(self) -> str:
        return "amazon_q"
