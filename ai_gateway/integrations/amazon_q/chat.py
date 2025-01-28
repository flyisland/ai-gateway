import os
from typing import Any, Dict, Iterator, List, Optional

from botocore.exceptions import ClientError
from requests.exceptions import RequestException, Timeout
from langchain_core.callbacks.manager import CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    BaseMessage,
    SystemMessage,
)
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from requests import RequestException, Timeout
import time
from ai_gateway.api.auth_utils import StarletteUser

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
        try:
            message_stream = self._build_response(messages=messages)
            print(message_stream)
            stream_output = message_stream["responseStream"]
            print(stream_output)

            for event in stream_output:
                try:
                    if 'messageMetadataEvent' in event:
                        content = event['messageMetadataEvent'].get('conversationId', '')
                    elif 'assistantResponseEvent' in event:
                        content = event['assistantResponseEvent'].get('content', '')
                    else:
                        content = event.get('content', '')

                    yield ChatGenerationChunk(message=AIMessageChunk(content=content))
                except KeyError as e:
                    error_message = f"Error processing response: {str(e)}"
                    yield ChatGenerationChunk(
                        message=AIMessageChunk(
                            content=f"An error occurred: {error_message}"
                        )
                    )
                    break

        except Timeout as e:
            error_message = "Connection timed out while receiving data from Amazon Q."
            yield ChatGenerationChunk(
                message=AIMessageChunk(
                    content=f"Error: {error_message}"
                )
            )

        except ClientError as e:
            error_code = e.response['Error']['Code']
            error_message = e.response['Error']['Message']

            if error_code == 'ExpiredTokenException':
                error_text = "AWS credentials have expired. Please refresh your credentials."
            elif error_code == 'UnrecognizedClientException':
                error_text = "Invalid AWS credentials. Please check your credentials."
            elif error_code == 'AccessDeniedException':
                error_text = "Insufficient permissions to access Amazon Q."
            elif error_code == 'ThrottlingException':
                error_text = "Request was throttled. Please try again later."
            elif error_code == 'RequestTimeoutException':
                error_text = "Request timed out. Please try again."
            else:
                error_text = f"AWS error occurred: {error_message}"

            yield ChatGenerationChunk(
                message=AIMessageChunk(
                    content=f"Error ({error_code}): {error_text}"
                )
            )

        except RequestException as e:
            error_message = f"Error communicating with Amazon Q: {str(e)}"
            yield ChatGenerationChunk(
                message=AIMessageChunk(
                    content=f"Connection Error: {error_message}"
                )
            )

        except Exception as e:
            error_message = f"Unexpected error occurred: {str(e)}"
            yield ChatGenerationChunk(
                message=AIMessageChunk(
                    content=f"Internal Error: {error_message}"
                )
            )
        finally:
            # Ensure the stream is properly closed
            #This ensures proper cleanup of resources even if an error  occurs during stream processing.
            if 'stream_output' in locals():
              try:
                  stream_output.close()
              except:
                  pass

    def _build_response(self, messages: List[BaseMessage]):
      try:
          current_user = self.metadata["user"]
          role_arn = os.environ.get("AWS_ROLE_ARN")

          q_client = self.amazon_q_client_factory.get_client(
              current_user=current_user,
              auth_header=current_user.auth_header,
              role_arn=role_arn,
          )

          send_message_params = self._calculate_send_message_params(messages, current_user)

          return q_client.send_chat_message(send_message_params)

      except Exception as e:
          # Let the _stream method handle the error
          raise


    def _calculate_send_message_params(self, messages: List[BaseMessage], current_user: StarletteUser):
        if messages and isinstance(messages[0], SystemMessage):
            system_message = messages.pop(0)
            if messages:
                messages[0].content = f"{system_message.content}{messages[0].content}"

        message_content = messages.pop().content if messages else ""

        history = [
            {
                "userInputMessage": messages[i].content,
                "assistantResponseMessage": messages[i + 1].content,
            }
            for i in range(0, len(messages) - 1, 2)
        ]

        print("DEBUG: history", history)
        print("DEBUG: message_content", message_content)
        unique_id = self.generate_unique_id()
        print("DEBUG: unique_id", unique_id)
        conversation_id = f"{current_user.global_user_id}_{unique_id}"
        print("DEBUG: conversation_id", conversation_id)

        return {
            "message": message_content,
            "conversation_id": conversation_id,
            "history": history,
        }

    def generate_unique_id(self):
      return str(int(time.time() * 1000))

    @property
    def _identifying_params(self) -> Dict[str, Any]:
        return {
            "model": "amazon_q",
        }

    @property
    def _llm_type(self) -> str:
        return "amazon_q"
