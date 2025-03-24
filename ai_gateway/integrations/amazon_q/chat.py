from typing import Any, Dict, Iterator, List, Optional

from langchain_core.callbacks.manager import CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    BaseMessage,
    HumanMessage,
    SystemMessage,
)
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult

from ai_gateway.api.auth_utils import StarletteUser
from ai_gateway.integrations.amazon_q.client import AmazonQClientFactory

__all__ = [
    "ChatAmazonQ",
]


class ChatAmazonQ(BaseChatModel):
    amazon_q_client_factory: AmazonQClientFactory

    def _generate(
        self,
        *args: Any,
        **kwargs: Any,
    ) -> ChatResult:
        content = "".join(
            chunk.message.content
            for chunk in self._stream(*args, **kwargs)
            if isinstance(chunk.message.content, str)
        )

        generations = [ChatGeneration(message=AIMessage(content=content))]

        return ChatResult(generations=generations)

    def _stream(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> Iterator[ChatGenerationChunk]:
        message, history = self._build_messages(messages)
        response = self._perform_api_request(message, history, **kwargs)
        stream = response["responseStream"]

        try:
            for event in stream:
                for key, value in event.items():
                    if key == "assistantResponseEvent":
                        content = value.get("content")
                        yield ChatGenerationChunk(
                            message=AIMessageChunk(content=content)
                        )
                    elif key == "codeReferenceEvent":
                        yield from self._process_code_reference_event(event)

        finally:
            stream.close()

    def _perform_api_request(
        self,
        message: dict[str, str],
        history: List[dict[str, str]],
        user: StarletteUser,
        role_arn: str,
        **_kwargs,
    ):
        """
        Performs a `send_message` request to Q API.

        This method creates a Q client and performs a `send_message` request passing `message` and `history`.

        Args:
            message (dict): A dictionary with a "content" key that combines the system and the latest user and assistant messages.
            history (list): A list of dictionaries representing user and assistant message history,
                            with either {"userInputMessage": { "content" ... }} or {"assistantResponseMessage": {"content" ... }} formats.
            user (StarletteUser): The current user who performs the request.
            role_arn (str): The role arn of the identity provider.
            kwargs (dict): Optional arguments.

        Returns:
            dict: A dict with "responseStream" key that contains a stream of events.
        """
        q_client = self.amazon_q_client_factory.get_client(
            current_user=user,
            role_arn=role_arn,
        )

        return q_client.send_message(message=message, history=history)

    def _build_messages(
        self,
        messages: List[BaseMessage],
    ):
        """
        Build a message and history from a list of provided messages that can be later passed to the `send_message` endpoint of Q API.

        Args:
            messages (List[BaseMessage]): A list of messages, including system, user, and assistant messages.

        Returns:
            tuple: A tuple containing:
                - message (dict): A dictionary with a "content" key that combines the system and the latest
                  user and assistant messages.
                - history (list): A list of dictionaries representing user and assistant message history,
                  with either {"userInputMessage": { "content" ... }} or {"assistantResponseMessage": {"content" ... }} formats.
        """
        input_messages = []
        # Extract the system message to always send it as an input
        if messages and isinstance(messages[0], SystemMessage):
            input_messages.append(messages.pop(0))
        # Support prompt definitions with assistant messages (like react prompts)
        if len(messages) > 1 and isinstance(messages[-1], AIMessage):
            assistant_message = messages.pop()
            user_message = messages.pop()
            input_messages.append(user_message)
            input_messages.append(assistant_message)
        # Support prompt definitions with system + user messages (like explain code prompts)
        if messages and isinstance(messages[-1], HumanMessage):
            input_messages.append(messages.pop())

        history = []
        for msg in messages:
            if isinstance(msg, HumanMessage):
                history.append({"userInputMessage": {"content": str(msg.content)}})
            elif isinstance(msg, AIMessage):
                history.append(
                    {"assistantResponseMessage": {"content": str(msg.content)}}
                )

        message = {
            "content": " ".join(
                msg.content for msg in input_messages if isinstance(msg.content, str)
            )
        }

        return message, history

    def _process_code_reference_event(self, event: StreamEvent) -> StreamResponse:
        """
        Processes a code reference event and extracts code reference information.
        Args:
            event (StreamEvent): The code reference event to process
        Returns:
            StreamResponse: A response containing the code reference information
        
        Example:
            Input event:
            {
                "codeReferenceEvent": {
                    "references": [
                        {
                            "repository": {"shape": "example-repo"},
                            "licenseName": {"shape": "MIT"},
                            "url": {"shape": "https://github.com/example/repo"},
                            "recommendationContentSpan": {"shape": "lines 10-20"}
                        },
                        {
                            "repository": {"shape": "another-repo"},
                            "licenseName": {"shape": "Apache-2.0"},
                            "url": {"shape": "https://github.com/another/repo"},
                            "recommendationContentSpan": {"shape": "lines 5-15"}
                        }
                    ]
                }
            }
        
        Output:
            StreamResponse with content:
            "example-repo [MIT]: https://github.com/example/repo (lines 10-20)
            another-repo [Apache-2.0]: https://github.com/another/repo (lines 5-15)"
        """
        references = event.get("codeReferenceEvent")
        if not references:
            return StreamResponse(content="", error="Invalid references event: codeReferenceEvent is empty or missing")

        if not isinstance(references, dict):
            return StreamResponse(content="", error=f"Invalid references format: expected dict, got {type(references)}")

        content = references.get("references", "")
        if not content:
            return StreamResponse(content="")

        if not isinstance(content, (list, tuple)):
            return StreamResponse(content="", error=f"Invalid content format: expected list or tuple, got {type(content)}")

        formatted_references = []
        for item in content:
            if isinstance(item, dict):
                # Extract values, handling nested dictionary structure
                repository = item.get('repository', {}).get('shape') if isinstance(item.get('repository'), dict) else item.get('repository', '')
                license_name = item.get('licenseName', {}).get('shape') if isinstance(item.get('licenseName'), dict) else item.get('licenseName', '')
                url = item.get('url', {}).get('shape') if isinstance(item.get('url'), dict) else item.get('url', '')
                span = item.get('recommendationContentSpan', {}).get('shape') if isinstance(item.get('recommendationContentSpan'), dict) else item.get('recommendationContentSpan', '')

                # Build the reference string part by part
                parts = []
                if repository:
                    parts.append(repository)
                if license_name:
                    parts.append(f"[{license_name}]")
                if url:
                    parts.append(f": {url}")
                if span:
                    parts.append(f"({span})")

                # Join the parts with spaces, only if they exist
                formatted_ref = " ".join(parts)
                if formatted_ref:
                    formatted_references.append(f"\n{formatted_ref}")
            else:
                formatted_references.append(f"\n{str(item)}")

        referenceContent = "\n".join(formatted_references)
        return ChatGenerationChunk(
            message=AIMessageChunk(content=referenceContent)
        )
    
    @property
    def _identifying_params(self) -> Dict[str, Any]:
        return {
            "model": "amazon_q",
        }

    @property
    def _llm_type(self) -> str:
        return "amazon_q"
