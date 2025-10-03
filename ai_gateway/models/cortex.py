import httpx
from typing import Any, List, Mapping, Optional
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage, AIMessage, HumanMessage, SystemMessage


class CortexChatModel(BaseChatModel):
    """LangChain-style wrapper for Snowflake Cortex Agent API."""

    def __init__(
        self,
        database: str,
        schema: str,
        agent_name: str,
        api_token: str,
        base_url: str,
        streaming: bool = False,
        timeout: int = 60,
    ):
        self.database = database
        self.schema = schema
        self.agent_name = agent_name
        self.api_token = api_token
        self.base_url = base_url.rstrip("/")
        self.streaming = streaming
        self.timeout = timeout

    @property
    def _llm_type(self) -> str:
        return "cortex"

    async def _call(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> str:
        """Send messages to Cortex Agent and return assistant response as text."""

        log.info("🚀 CortexChatModel called!", extra={"database": self.database, "schema": self.schema})

        # Convert LangChain messages → Cortex API format
        formatted_msgs = []
        for m in messages:
            if isinstance(m, HumanMessage):
                formatted_msgs.append({
                    "role": "user",
                    "content": [{"type": "text", "text": m.content}],
                })
            elif isinstance(m, SystemMessage):
                formatted_msgs.append({
                    "role": "system",
                    "content": [{"type": "text", "text": m.content}],
                })
            elif isinstance(m, AIMessage):
                formatted_msgs.append({
                    "role": "assistant",
                    "content": [{"type": "text", "text": m.content}],
                })

        payload = {
            "thread_id": 0,
            "parent_message_id": 0,
            "messages": formatted_msgs,
        }

        url = f"{self.base_url}/api/v2/databases/{self.database}/schemas/{self.schema}/agents/{self.agent_name}:run"
        headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()

        # The API returns a stream of events, but for now we simplify:
        answer = ""
        for event in data.get("events", []):
            if event.get("type") == "message" and event["message"]["role"] == "assistant":
                answer += event["message"]["content"][0]["text"]

        return answer

    async def _agenerate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> AIMessage:
        text = await self._call(messages, stop, **kwargs)
        return AIMessage(content=text)


def cortex_model_factory(**kwargs):
    return CortexChatModel(
        database=kwargs.get("database", "MY_DB"),
        schema=kwargs.get("schema", "PUBLIC"),
        agent_name=kwargs.get("agent_name", "my_agent"),
        api_token=kwargs["api_token"],
        base_url=kwargs.get("base_url", "https://<snowflake-endpoint>"),
    )
