import hashlib
from collections.abc import Iterator, Sequence
from typing import Any, Callable, Dict, List, Optional, Union, cast

from langchain_core.callbacks.manager import CallbackManagerForLLMRun
from langchain_core.language_models import LanguageModelInput
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    BaseMessage,
    ChatMessage,
    HumanMessage,
    SystemMessage,
    ToolCallChunk,
    ToolMessage,
)
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool
from litellm.types.llms.bedrock import ToolBlock as BedrockToolBlock
from litellm.types.llms.bedrock import (
    ToolInputSchemaBlock as BedrockToolInputSchemaBlock,
)
from litellm.types.llms.bedrock import ToolJsonSchemaBlock as BedrockToolJsonSchemaBlock
from litellm.types.llms.bedrock import ToolSpecBlock as BedrockToolSpecBlock
from pydantic import BaseModel

from ai_gateway.api.auth_utils import StarletteUser
from ai_gateway.integrations.amazon_q.client import AmazonQClientFactory
from duo_workflow_service.tools import DuoBaseTool

__all__ = [
    "ChatAmazonQ",
]


def _convert_message_to_text(
    message: BaseMessage,
    human_prompt: str = "\n\nHuman:",
    ai_prompt: str = "\n\nAssistant:",
) -> str:
    content = cast(str, message.content)
    if isinstance(message, ChatMessage):
        message_text = f"\n\n{message.role.capitalize()}: {content}"
    elif isinstance(message, HumanMessage):
        message_text = f"{human_prompt} {content}"
    elif isinstance(message, AIMessage):
        message_text = f"{ai_prompt} {content}"
    elif isinstance(message, SystemMessage):
        message_text = content
    elif isinstance(message, ToolMessage):
        message_text = content
    else:
        raise ValueError(f"Unknown type {message}")
    return message_text


def _get_hash_int(input_str: str) -> int:
    """Hashes a string to a 64-bit integer."""
    # Encode the string to bytes
    hash_object = hashlib.sha256(input_str.encode("utf-8"))
    # Get the hexadecimal representation
    hex_digest = hash_object.hexdigest()
    # Convert the hexadecimal string to an integer
    return int(hex_digest, 16)


class ReferenceSpan(BaseModel):
    shape: str


class Reference(BaseModel):
    repository: Optional[ReferenceSpan | str] = None
    licenseName: Optional[ReferenceSpan | str] = None
    url: Optional[ReferenceSpan | str] = None
    recommendationContentSpan: Optional[ReferenceSpan | str] = None

    def get_repository(self) -> Optional[str]:
        return (
            self.repository.shape
            if isinstance(self.repository, ReferenceSpan)
            else self.repository
        )

    def get_license_name(self) -> Optional[str]:
        return (
            self.licenseName.shape
            if isinstance(self.licenseName, ReferenceSpan)
            else self.licenseName
        )

    def get_url(self) -> Optional[str]:
        return self.url.shape if isinstance(self.url, ReferenceSpan) else self.url

    def get_span(self) -> Optional[str]:
        return (
            self.recommendationContentSpan.shape
            if isinstance(self.recommendationContentSpan, ReferenceSpan)
            else self.recommendationContentSpan
        )

    def format_reference(self) -> str:
        parts = []

        if repository := self.get_repository():
            parts.append(str(repository))
        if license_name := self.get_license_name():
            parts.append(f"[{license_name}]")
        if url := self.get_url():
            parts.append(f": {url}")
        if span := self.get_span():
            parts.append(f"({span})")

        return " ".join(parts)


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
            for all_events in stream:
                for key, event in all_events.items():
                    if key == "assistantResponseEvent":
                        content = event.get("content")
                        yield ChatGenerationChunk(
                            message=AIMessageChunk(content=content)
                        )
                    if key == "toolUseEvent":
                        yield from self._process_tool_use_event(event=all_events)
                    elif key == "codeReferenceEvent":
                        yield from self._process_code_reference_event(all_events)

        finally:
            stream.close()

    def _process_tool_use_event(self, event: Dict) -> Iterator[ChatGenerationChunk]:
        inp = event.get("input")
        index = _get_hash_int(event.get("toolUseId", ""))
        if event.get("stop"):
            tool_call_chunk = ToolCallChunk(
                name=event.get("name"),
                args=inp,
                id=event.get("toolUseId"),
                index=index,
            )
        else:
            tool_call_chunk = ToolCallChunk(
                name=None,
                args=inp,
                id=None,
                index=index,
            )
        yield ChatGenerationChunk(
            message=AIMessageChunk(
                content="",
                tool_call_chunks=[tool_call_chunk],
            ),
        )

    def _process_code_reference_event(
        self, event: Dict
    ) -> Iterator[ChatGenerationChunk]:
        """Process code reference events and format them into a readable string. Uses Pydantic models for data
        validation and parsing.

        Args:
            event (Dict): The event containing code references

        Returns:
            Iterator[ChatGenerationChunk]: A response containing the code reference information

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
            ChatGenerationChunk with content:
            "example-repo [MIT]: https://github.com/example/repo (lines 10-20)
            another-repo [Apache-2.0]: https://github.com/another/repo (lines 5-15)"
        """
        try:
            references = event.get("codeReferenceEvent", {}).get("references", [])
            formatted_references = []

            for reference in references:
                try:
                    # Using model_validate instead of parse_obj
                    ref = Reference.model_validate(reference)
                    formatted_ref = ref.format_reference()
                    if formatted_ref:
                        formatted_references.append(formatted_ref)
                except ValueError:
                    # Handle validation errors if needed
                    continue

            if formatted_references:
                reference_content = "\n".join(formatted_references)
                yield ChatGenerationChunk(
                    message=AIMessageChunk(content=reference_content)
                )
            else:
                yield ChatGenerationChunk(message=AIMessageChunk(content=""))

        except Exception:
            # If there's any error in parsing/validation, return empty content
            yield ChatGenerationChunk(message=AIMessageChunk(content=""))

    def _perform_api_request(
        self,
        message: dict[str, str],
        history: List[dict[str, str]],
        user: StarletteUser,
        role_arn: str,
        tool_spec: Optional[List[dict[str, str]]] = None,
        **_kwargs,
    ):
        """Performs a `send_message` request to Q API.

        This method creates a Q client and performs a `send_message` request passing `message` and `history`.

        Args:
            message (dict): A dictionary with a "content" key that combines the system and the latest user and assistant messages.
            history (list): A list of dictionaries representing user and assistant message history,
                            with either {"userInputMessage": { "content" ... }} or {"assistantResponseMessage": {"content" ... }} formats.
            user (StarletteUser): The current user who performs the request.
            role_arn (str): The role arn of the identity provider.
            tool_spec (list): A list of tool specs to send to the model provider.
            kwargs (dict): Optional arguments.

        Returns:
            dict: A dict with "responseStream" key that contains a stream of events.
        """
        q_client = self.amazon_q_client_factory.get_client(
            current_user=user,
            role_arn=role_arn,
        )

        return q_client.send_message(
            message=message,
            history=history,
            tools=tool_spec,
        )

    def _build_messages(
        self,
        messages: List[BaseMessage],
    ):
        """Build a message and history from a list of provided messages that can be later passed to the `send_message`
        endpoint of Q API.

        Args:
            messages (List[BaseMessage]): A list of messages, including system, user, and assistant messages.

        Returns:
            tuple: A tuple containing:
                - message (dict): A dictionary with a "content" key that combines the system and the latest
                    user and assistant messages.
                - history (list): A list of dictionaries representing user and assistant message history,
                    with either {"userInputMessage": { "content" ... }} or {"assistantResponseMessage": {"content" ... }} formats.
        """
        messages = messages.copy()  # don't mutate the original list

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
                _convert_message_to_text(message) for message in messages
            )
        }

        return message, history

    def _build_tool_spec(
        self, tools: Optional[List[DuoBaseTool]] = None, **_kwargs: Any
    ):
        """
        Amazon Q toolConfig looks like:
        "tools": [
            {
                "toolSpecification": {
                    "name": "top_song",
                    "description": "Get the most popular song played on a radio station.",
                    "inputSchema": {
                        "json": {
                            "type": "object",
                            "properties": {
                                "sign": {
                                    "type": "string",
                                    "description": "The call sign for the radio station for which you want the most popular song. Example calls signs are WZPZ, and WKRP."
                                }
                            },
                            "required": [
                                "sign"
                            ]
                        }
                    }
                }
            }
        ]
        """
        if not tools:
            return None

        tool_block_list: List[BedrockToolBlock] = []

        for tool in tools:
            # FIXME: for now, limit to single tool
            if tool.name != "get_repository_file":
                continue

            parameters = tool.input_schema.model_json_schema()
            tool_input_schema = BedrockToolInputSchemaBlock(
                json=BedrockToolJsonSchemaBlock(
                    type=parameters.get("type", ""),
                    properties=parameters.get("properties", {}),
                    required=parameters.get("required", []),
                )
            )
            tool_spec = BedrockToolSpecBlock(
                inputSchema=tool_input_schema,
                name=tool.name,
                description=tool.description,
            )
            tool_block = BedrockToolBlock(toolSpec=tool_spec)
            # Amazon Q uses different spelling of spec field
            tool_block["toolSpecification"] = tool_block.pop("toolSpec")
            tool_block_list.append(tool_block)

        return tool_block_list

    def bind_tools(
        self,
        tools: Sequence[Union[Dict[str, Any], type, Callable, BaseTool]],  # noqa: UP006
        *,
        tool_choice: Optional[str] = None,
        **kwargs: Any,
    ) -> Runnable[LanguageModelInput, BaseMessage]:
        """Bind tools to the model.

        Args:
            tools: Sequence of tools to bind to the model.
            tool_choice: The tool to use. If "any" then any tool can be used.

        Returns:
            A Runnable that returns a message.
        """
        return self.bind(tools=tools, tool_choice=tool_choice, **kwargs)

    @property
    def _identifying_params(self) -> Dict[str, Any]:
        return {
            "model": "amazon_q",
        }

    @property
    def _llm_type(self) -> str:
        return "amazon_q"
