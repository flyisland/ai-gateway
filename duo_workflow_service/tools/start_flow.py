import json
from typing import Any, ClassVar, Literal, Optional, Type

import structlog
from langchain_core.tools import ToolException
from packaging.version import Version
from pydantic import BaseModel, Field

from duo_workflow_service.tools.duo_base_tool import DuoBaseTool

log = structlog.stdlib.get_logger(__name__)


class StartFlowInput(BaseModel):
    workflow_definition: Literal[
        "fix_pipeline/v1", "code_review/v1", "developer/v1"
    ] = Field(
        description=(
            "Flow identifier. Available flows:\n"
            "- fix_pipeline/v1: Diagnose and fix a failing CI/CD pipeline. "
            "Requires pipeline URL as goal.\n"
            "- code_review/v1: Perform an automated code review on a merge request. "
            "Requires merge request IID as goal.\n"
            "- developer/v1: Convert an issue into a merge request. "
            "Requires issue URL as goal."
        )
    )
    goal: str = Field(
        description=(
            "The primary input for the flow:\n"
            "- fix_pipeline/v1: The full URL of the failing pipeline "
            "(e.g. https://gitlab.com/group/project/-/pipelines/123)\n"
            "- code_review/v1: The merge request IID (numeric ID within the project)\n"
            "- developer/v1: The full URL of the issue to implement "
            "(e.g. https://gitlab.com/group/project/-/issues/456)"
        )
    )
    merge_request_url: Optional[str] = Field(
        default=None,
        description=(
            "Required for fix_pipeline/v1. The full URL of the merge request associated "
            "with the failing pipeline (e.g. https://gitlab.com/group/project/-/merge_requests/1)."
        ),
    )
    pipeline_source_branch: Optional[str] = Field(
        default=None,
        description=(
            "Required for fix_pipeline/v1. The source branch of the failing pipeline "
            "(e.g. 'feature-branch' or 'main')."
        ),
    )


class StartFlow(DuoBaseTool):
    name: str = "start_flow"
    tool_version: ClassVar[Version] = Version("0.0.1")
    description: str = """Start a foundational flow to complete a complex task autonomously.

Use this tool when the user wants to run one of these automated workflows:

- **fix_pipeline/v1**: Diagnose and fix issues in a GitLab CI/CD pipeline.
    Use when the user asks to fix a failing pipeline, repair CI failures, or debug pipeline errors.
    Requires: pipeline URL as `goal`, merge request URL as `merge_request_url`,
    and source branch as `pipeline_source_branch`.

- **code_review/v1**: Analyze code changes, comments, and linked issues for a merge request.
    Use when the user asks for a code review, MR review, or automated review of changes.
    Requires: merge request IID as `goal`.

- **developer/v1**: Convert an issue into an actionable merge request.
    Use when the user asks to implement an issue, work on a ticket, or turn an issue into code.
    Requires: issue URL as `goal`.

The flow runs asynchronously. This tool returns a session ID and URL immediately so the user
can track progress. The user must approve this tool call before the flow starts.
"""
    args_schema: Type[BaseModel] = StartFlowInput

    async def _execute(
        self,
        workflow_definition: str,
        goal: str,
        merge_request_url: Optional[str] = None,
        pipeline_source_branch: Optional[str] = None,
    ) -> str:
        payload: dict[str, Any] = {
            "workflow_definition": workflow_definition,
            "goal": goal,
            "environment": "ambient",
            "start_workflow": True,
        }

        if self.project:
            payload["project_id"] = self.project.get("id")

        if workflow_definition == "fix_pipeline/v1":
            additional_context = []
            if merge_request_url:
                additional_context.append(
                    {
                        "Category": "merge_request",
                        "Content": json.dumps({"url": merge_request_url}),
                    }
                )
            else:
                raise ToolException(
                    f"Failed to start {workflow_definition} flow: merge_request_url is missing"
                )
            if pipeline_source_branch:
                additional_context.append(
                    {
                        "Category": "pipeline",
                        "Content": json.dumps(
                            {"source_branch": pipeline_source_branch}
                        ),
                    }
                )
            else:
                raise ToolException(
                    f"Failed to start {workflow_definition} flow: source_branch is missing"
                )
            if additional_context:
                payload["additional_context"] = additional_context

        response = await self.gitlab_client.apost(
            path="/api/v4/ai/duo_workflows/agent_workflows",
            body=json.dumps(payload),
        )

        if not response.is_success():
            log.error(
                "start_flow: failed to create workflow",
                status_code=response.status_code,
                body=response.body,
                workflow_definition=workflow_definition,
            )
            raise ToolException(
                f"Failed to start flow: HTTP {response.status_code}: "
                f"{str(response.body)[:300]}"
            )

        body = response.body
        if isinstance(body, str):
            body = json.loads(body)

        workflow_id = body.get("id")
        session_url = (
            f"{self.project['web_url']}/-/automate/agent-sessions/{workflow_id}"
            if self.project and workflow_id
            else None
        )

        return json.dumps(
            {
                "status": "started",
                "workflow_id": workflow_id,
                "session_url": session_url,
                "flow_name": workflow_definition,
            }
        )

    def format_display_message(
        self, args: StartFlowInput, _tool_response: Any = None
    ) -> str:
        if _tool_response:
            try:
                content = getattr(_tool_response, "content", _tool_response)
                if isinstance(content, str):
                    data = json.loads(content)
                    workflow_id = data.get("workflow_id")
                    if workflow_id:
                        session_url = data.get("session_url")
                        msg = f"Started flow **{args.workflow_definition}** (workflow ID: {workflow_id})"
                        if session_url:
                            msg += f" — [View session]({session_url})"
                        return msg
            except (json.JSONDecodeError, AttributeError, TypeError):
                pass
        return f"Starting flow {args.workflow_definition} with goal: {args.goal}"
