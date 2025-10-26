import httpx
from langchain_core.messages import AIMessage

class SnowflakePromptAdapter:
    def __init__(self, database, schema, agent_name, api_token, base_url="https://<snowflake-cortex-endpoint>"):
        self.database = database
        self.schema = schema
        self.agent_name = agent_name
        self.api_token = api_token
        self.base_url = base_url

    async def ainvoke(self, input_state):
        conversation_history = input_state.get("conversation_history", {}).get("chat_agent", [])
        messages_payload = [
            {"role": "user", "content": [{"type": "text", "text": msg.content}]}
            for msg in conversation_history if hasattr(msg, "content")
        ]
        
        payload = {
            "thread_id": 0,
            "parent_message_id": 0,
            "messages": messages_payload,
            "tool_choice": {"type": "auto"},
        }
        
        url = f"{self.base_url}/api/v2/databases/{self.database}/schemas/{self.schema}/agents/{self.agent_name}:run"
        headers = {"Authorization": f"Bearer {self.api_token}", "Content-Type": "application/json"}

        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()

        # convert Snowflake response to AIMessage
        return AIMessage(content=data["messages"][-1]["content"][0]["text"])
