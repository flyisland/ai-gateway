import json
from typing import Any, Dict, Tuple, List, Type
import httpx
from pydantic import BaseModel, Field

from duo_workflow_service.tools.duo_base_tool import DuoBaseTool


class RunCortexAgentInput(BaseModel):
    query: str = Field(
        description="The query string to execute with the cortex agent.",
    )
    

API_HEADERS = {
    "Authorization": f"Bearer INSERT_TOKEN_HERE",
    "X-Snowflake-Authorization-Token-Type": "PROGRAMMATIC_ACCESS_TOKEN",
    "Content-Type": "application/json",
}

SNOWFLAKE_AGENT_URL="https://sfsenorthamerica-gitlab-poc.snowflakecomputing.com/api/v2/databases/gitlab_poc/schemas/indexing/agents/SAMPLE_GITLAB_V1:run"

async def process_sse_response(resp: httpx.Response) -> Tuple[str, str, List[Dict]]:
    """
    Process SSE stream lines from Snowflake Cortex Agent API.
    Based on: https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-agents-run
    """
    text = ""
    current_event = None
    
    async for raw_line in resp.aiter_lines():
        if not raw_line:
            continue
        raw_line = raw_line.strip()
        
        if raw_line.startswith("event:"):
            current_event = raw_line[len("event:"):].strip()
            continue
        
        if not raw_line.startswith("data:"):
            continue
            
        payload = raw_line[len("data:"):].strip()
        if payload in ("", "[DONE]"):
            continue
            
        try:
            evt = json.loads(payload)
        except json.JSONDecodeError:
            continue
        
        # response.text.delta - streaming text tokens
        if current_event == "response.text.delta":
            text += evt.get("text", "")
        
        # response.text - complete text block with annotations (citations)
        elif current_event == "response.text":
            text += evt.get("text", "")
        
        # response - final complete response
        elif current_event == "response":
            # This is the final aggregated response
            for content_item in evt.get("content", []):
                if content_item.get("type") == "text":
                    text += content_item.get("text", "")
    
    return text

async def run_cortex_agents(query: str) -> Dict[str, Any]:
    """Run the Cortex agent with the given query, streaming SSE."""
    payload = {
        "tool_choice": {"type": "auto"},
        "messages": [
            {"role": "user", "content": [{"type": "text", "text": query}]}
        ],
    }

    url = SNOWFLAKE_AGENT_URL
    headers = {
        **API_HEADERS,
        "Accept": "text/event-stream",
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        async with client.stream(
            "POST",
            url,
            json=payload,
            headers=headers,
        ) as resp:
            resp.raise_for_status()
            text = await process_sse_response(resp)

    return text

class RunCortexAgent(DuoBaseTool):
    name: str = "run_cortex_agent"

    # editorconfig-checker-disable
    description: str = """Execute a query through a Cortex Agent."""
    # editorconfig-checker-enable

    args_schema: Type[BaseModel] = RunCortexAgentInput  # type: ignore

    async def _arun(self, **kwargs: Any) -> str:
        query = kwargs.get("query")

        if not query:
            return json.dumps({"error": "Query parameter is required"})

        try:
            response = await run_cortex_agents(query)

            return json.dumps({"cortex_response": response})
        except Exception as e:
            return json.dumps({"error": str(e)})

    def format_display_message(
        self, args: RunCortexAgentInput, _tool_response: Any = None
    ) -> str:
        # Truncate long queries for display
        query_preview = args.query[:100] + "..." if len(args.query) > 100 else args.query
        return f"Sending query to Cortex Agent: {query_preview}"
