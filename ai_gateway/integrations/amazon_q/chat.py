import os

from typing import Any, Dict, Iterator, List, Optional

from langchain_core.callbacks.manager import CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, ChatMessageChunk
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult

from ai_gateway.integrations.amazon_q.errors import AWSException
from langchain_core.messages import AIMessageChunk

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
        message_stream = self._build_response(messages=messages)
        stream_output = message_stream["responseStream"]
        for event in stream_output:
          # Assuming each event in the EventStream has a 'content' field
          # You may need to adjust this based on the actual structure of your EventStream
          print("message_stream event: ", event)
          assistantResponseEvent = event['assistantResponseEvent']
          content = assistantResponseEvent.get('content', '')
          yield ChatGenerationChunk(message=AIMessageChunk(content=content))


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

        try:
          return  q_client.send_chat_message({
              "message": messages[0].content,
              "converstaion_id": "test_vivek"
            })
        except AWSException as e:
          raise e.to_http_exception()

    @property
    def _identifying_params(self) -> Dict[str, Any]:
        return {
            "model": "amazon_q",
        }

    @property
    def _llm_type(self) -> str:
        return "amazon_q"
