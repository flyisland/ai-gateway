import json
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
from pydantic import BaseModel, Field

from ai_gateway.api.auth_utils import StarletteUser
from ai_gateway.integrations.amazon_q.client import AmazonQClientFactory
from duo_workflow_service.tools import DuoBaseTool

__all__ = [
    "ChatAmazonQ",
]


def _convert_message_to_text(message: BaseMessage) -> str:
    content = cast(str, message.content)
    if isinstance(message, ChatMessage):
        message_text = f"\n\n{message.role.capitalize()}: {content}"
    elif isinstance(message, HumanMessage):
        message_text = f"{content}"
    elif isinstance(message, AIMessage):
        message_text = f"{content}"
    elif isinstance(message, SystemMessage):
        message_text = content
    elif isinstance(message, ToolMessage):
        message_text = content
    else:
        raise ValueError(f"Unknown type {message}")
    return message_text


class ReferenceSpan(BaseModel):
    shape: str = Field(strict=True, min_length=1)


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
            parts.append(f"{url}")
            if len(parts) > 1:
                parts[len(parts) - 2] += ":"
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

        message, history, tool_results = self._build_messages(messages)

        tool_spec = self._build_tool_spec(**kwargs)
        response = self._perform_api_request(
            message, history, tool_spec=tool_spec, tool_results=tool_results, **kwargs
        )

        stream = response["responseStream"]
        tool_requests: dict[str, dict] = {}
        assistant_chunk = None

        try:
            for event in stream:
                for key, value in event.items():
                    if (
                        key not in ["assistantResponseEvent", "toolUseEvent"]
                        and assistant_chunk
                    ):
                        yield assistant_chunk
                        assistant_chunk = None

                    if key == "toolUseEvent":
                        # tool use event always comes after/as part of assistant response event
                        tool_name = value.get("toolUseId")
                        existing_request = tool_requests.get(tool_name, {})
                        tool_use_request = (
                            existing_request if existing_request else value
                        )
                        if existing_request and not value.get("stop"):
                            tool_use_request["input"] = (
                                tool_use_request.get("input", "") + value["input"]
                            )

                        # Tool call request chunks always come as part of ai response
                        new_chunk = ChatGenerationChunk(
                            message=AIMessageChunk(
                                content="",
                                tool_call_chunks=[
                                    ToolCallChunk(
                                        name=(
                                            value.get("name")
                                            if not existing_request
                                            else None
                                        ),
                                        args=value.get("input"),
                                        id=(
                                            value.get("toolUseId")
                                            if not existing_request
                                            else None
                                        ),
                                        index=0,
                                    )
                                ],
                            )
                        )

                        assistant_chunk = (
                            assistant_chunk + new_chunk
                            if assistant_chunk
                            else new_chunk
                        )

                        tool_requests[tool_name] = tool_use_request

                    if key == "assistantResponseEvent":
                        content = value.get("content")
                        new_assistant_chunk = ChatGenerationChunk(
                            message=AIMessageChunk(content=content)
                        )
                        assistant_chunk = (
                            assistant_chunk + new_assistant_chunk
                            if assistant_chunk
                            else new_assistant_chunk
                        )

                    elif key == "codeReferenceEvent":
                        yield from self._process_code_reference_event(event)

            if assistant_chunk:
                yield assistant_chunk

        finally:
            stream.close()

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
        tool_results: Optional[List[dict[str, str]]] = None,
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
            tool_spec (list): A list of tool specs that are available to use
            tool_results (list): A list of tool call results
            kwargs (dict): Optional arguments.

        Returns:
            dict: A dict with "responseStream" key that contains a stream of events.
        """
        q_client = self.amazon_q_client_factory.get_client(
            current_user=user,
            role_arn=role_arn,
        )

        return q_client.send_message(
            message=message, history=history, tools=tool_spec, tool_results=tool_results
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

        history: List[dict] = []
        tool_results = []
        # get last of system, user, AI message
        system_message, user_message, assistant_message = None, None, None
        for msg in messages:
            if isinstance(msg, SystemMessage):
                system_message = msg
            if isinstance(msg, HumanMessage):
                user_message = msg
                history.append({"userInputMessage": {"content": str(msg.content)}})
            elif isinstance(msg, AIMessage):
                assistant_message = msg
                tool_uses: List[dict] = []
                for tool_call in msg.tool_calls:
                    tool_uses.append(
                        {
                            "toolUseId": tool_call.get("id"),
                            "name": tool_call.get("name"),
                            "input": tool_call.get("args"),
                        }
                    )
                history.append(
                    {
                        "assistantResponseMessage": {
                            "content": str(msg.content),
                            "toolUses": tool_uses,
                        }
                    }
                )
            elif isinstance(msg, ToolMessage):
                msg_content = json.loads(msg.text())["content"] if msg.text() else ""
                msg_status = "success" if msg.status == "success" else "error"
                tool_results.append(
                    {
                        "toolUseId": msg.tool_call_id,
                        "status": msg_status,
                        "content": [{"text": str(msg_content)}],
                    }
                )

        last_messages = list(
            filter(None, [system_message, user_message, assistant_message])
        )

        message = {
            "content": " ".join(
                _convert_message_to_text(message) for message in last_messages
            )
        }

        return message, history, tool_results

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
            return []

        tool_block_list: List[BedrockToolBlock] = []

        for tool in tools:
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
            tool_block["toolSpecification"] = tool_block.pop("toolSpec")  # type: ignore[typeddict-unknown-key]
            tool_block_list.append(tool_block)

        return tool_block_list

    @property
    def _identifying_params(self) -> Dict[str, Any]:
        return {
            "model": "amazon_q",
        }

    @property
    def _llm_type(self) -> str:
        return "amazon_q"

    def bind_tools(
        self,
        tools: Sequence[Union[Dict[str, Any], type, Callable, BaseTool]],  # noqa: UP006
        *,
        tool_choice: Optional[Union[str]] = None,
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
