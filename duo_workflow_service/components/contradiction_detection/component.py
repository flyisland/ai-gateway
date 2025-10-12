import json
import os
import re
from datetime import datetime, timezone
from typing import Dict, List, Optional

import structlog
from dependency_injector.wiring import Provide, inject
from gitlab_cloud_connector import CloudConnectorUser

from ai_gateway.container import ContainerApplication
from ai_gateway.prompts.registry import LocalPromptRegistry
from duo_workflow_service.components.base import BaseComponent
from duo_workflow_service.components.tools_registry import ToolsRegistry
from duo_workflow_service.entities.state import (
    MessageTypeEnum,
    ToolStatus,
    UiChatLog,
    WorkflowState,
)
from duo_workflow_service.gitlab.http_client import GitlabHttpClient
from duo_workflow_service.llm_factory import AnthropicConfig, VertexConfig
from duo_workflow_service.workflows.type_definitions import AdditionalContext
from lib.internal_events.event_enum import CategoryEnum

__all__ = ["ContradictionDetectionComponent"]


class ContradictionDetectionComponent(BaseComponent):
    """Legacy-compatible component for contradiction detection in traditional workflows."""

    @inject
    def __init__(
        self,
        workflow_id: str,
        workflow_type: CategoryEnum,
        goal: str,
        tools_registry: ToolsRegistry,
        model_config: AnthropicConfig | VertexConfig,
        http_client: GitlabHttpClient,
        additional_context: list[AdditionalContext] | None = None,
        user: CloudConnectorUser | None = None,
        prompt_registry: LocalPromptRegistry = Provide[
            ContainerApplication.pkg_prompts.prompt_registry
        ],
    ):
        super().__init__(
            workflow_id=workflow_id,
            workflow_type=workflow_type,
            goal=goal,
            tools_registry=tools_registry,
            model_config=model_config,
            http_client=http_client,
            additional_context=additional_context,
            user=user,
            prompt_registry=prompt_registry,
        )
        self._logger = structlog.stdlib.get_logger("contradiction_detection")

    async def run(self, state: WorkflowState) -> WorkflowState:
        """Process the workflow state to detect contradictions in recent messages."""
        # Check if feature is enabled via environment variable
        if not self._is_feature_enabled():
            self._logger.debug("Contradiction detection feature is disabled")
            return state

        # Get recent conversation history
        conversation_history = state.get("conversation_history", {})
        ui_chat_logs = state.get("ui_chat_log", [])

        # Look for recent tool responses to analyze
        recent_tool_responses = self._extract_recent_tool_responses(ui_chat_logs)

        if not recent_tool_responses:
            self._logger.debug("No recent tool responses found to analyze")
            return state

        # Analyze for contradictions
        contradictions_found = []
        processed_logs = []

        for log_entry in ui_chat_logs:
            if self._is_tool_response(log_entry):
                contradictions = self._analyze_tool_response_for_contradictions(
                    log_entry
                )
                if contradictions:
                    contradictions_found.extend(contradictions)

                # Add contradiction metadata if found
                if contradictions:
                    modified_log = self._add_contradiction_metadata_to_log(
                        log_entry, contradictions
                    )
                    processed_logs.append(modified_log)
                else:
                    processed_logs.append(log_entry)
            else:
                processed_logs.append(log_entry)

        # Log contradictions if found
        if contradictions_found:
            self._logger.warning(
                f"Found {len(contradictions_found)} contradictions in tool responses",
                contradictions=contradictions_found,
            )

            # Add summary log entry
            summary_log = UiChatLog(
                message_type=MessageTypeEnum.SYSTEM,
                message_sub_type="contradiction_analysis",
                content=f"⚠️  Detected {len(contradictions_found)} potential contradictions in tool responses",
                timestamp=datetime.now(timezone.utc).isoformat(),
                status=ToolStatus.SUCCESS,
                correlation_id=None,
                tool_info=None,
                additional_context={
                    "contradictions_detected": len(contradictions_found),
                    "contradictions": contradictions_found,
                },
            )
            processed_logs.append(summary_log)

        # Update state with processed logs and analysis results
        updated_state = state.copy()
        updated_state["ui_chat_log"] = processed_logs
        updated_state["contradiction_analysis"] = {
            "contradictions_found": contradictions_found,
            "total_responses_analyzed": len(recent_tool_responses),
            "has_contradictions": len(contradictions_found) > 0,
            "analysis_timestamp": datetime.now(timezone.utc).isoformat(),
        }

        return updated_state

    def _is_feature_enabled(self) -> bool:
        """Check if contradiction detection feature is enabled via environment variable."""
        return (
            os.environ.get(
                "DUO_WORKFLOW_ENABLE_CONTRADICTION_DETECTION", "false"
            ).lower()
            == "true"
        )

    def _extract_recent_tool_responses(
        self, ui_chat_logs: List[UiChatLog]
    ) -> List[UiChatLog]:
        """Extract recent tool response logs from UI chat logs."""
        # Get the last 10 tool responses
        tool_responses = [
            log
            for log in ui_chat_logs[-20:]  # Look at last 20 entries
            if self._is_tool_response(log)
        ]
        return tool_responses[-10:]  # Keep last 10 tool responses

    def _is_tool_response(self, log_entry: UiChatLog) -> bool:
        """Check if a log entry represents a tool response."""
        return (
            log_entry["message_type"] == MessageTypeEnum.TOOL
            and log_entry.get("tool_info") is not None
            and hasattr(log_entry["tool_info"], "tool_response")
        )

    def _analyze_tool_response_for_contradictions(
        self, log_entry: UiChatLog
    ) -> List[Dict]:
        """Analyze a single tool response log entry for contradictions."""
        contradictions = []

        tool_info = log_entry.get("tool_info")
        if not tool_info or not hasattr(tool_info, "tool_response"):
            return contradictions

        tool_response = tool_info.tool_response

        # Extract content from tool response
        content = None
        if hasattr(tool_response, "content"):
            content = tool_response.content
        elif hasattr(tool_response, "result"):
            content = tool_response.result

        if not content:
            return contradictions

        # Try to parse JSON content
        json_data = self._extract_json_from_content(content)
        if json_data:
            contradictions = self._detect_contradictions_in_data(
                json_data, tool_info.name
            )

        return contradictions

    def _extract_json_from_content(self, content) -> Optional[Dict]:
        """Extract JSON data from various content formats."""
        if isinstance(content, str):
            # Try to parse as JSON directly
            try:
                return json.loads(content)
            except json.JSONDecodeError:
                pass

            # Try to find JSON within the string using regex
            json_pattern = r"\{.*\}"
            matches = re.findall(json_pattern, content, re.DOTALL)
            for match in matches:
                try:
                    return json.loads(match)
                except json.JSONDecodeError:
                    continue

        elif isinstance(content, dict):
            return content
        elif isinstance(content, list) and content:
            # If it's a list, check the first dict item
            for item in content:
                if isinstance(item, dict):
                    return item

        return None

    def _detect_contradictions_in_data(self, data: Dict, tool_name: str) -> List[Dict]:
        """Detect contradictions in JSON data."""
        contradictions = []

        def _check_item(item: Dict, path: str = "") -> None:
            """Recursively check an item for title/description contradictions."""
            title = None
            description = None

            # Look for title and description fields (case insensitive)
            for key, value in item.items():
                if isinstance(value, str):
                    key_lower = key.lower()
                    if key_lower in ["title", "name", "subject", "heading"]:
                        title = value
                    elif key_lower in [
                        "description",
                        "desc",
                        "summary",
                        "content",
                        "body",
                    ]:
                        description = value

            # If we found both title and description, check for contradictions
            if title and description:
                contradiction = self._analyze_contradiction(title, description)
                if contradiction:
                    contradictions.append(
                        {
                            "tool_name": tool_name,
                            "path": path,
                            "title": title,
                            "description": description,
                            "contradiction_type": contradiction["type"],
                            "confidence": contradiction["confidence"],
                            "details": contradiction["details"],
                        }
                    )

        # Check the main data object
        if isinstance(data, dict):
            _check_item(data)

            # Also check nested objects and arrays
            for key, value in data.items():
                if isinstance(value, dict):
                    _check_item(value, f"{key}")
                elif isinstance(value, list):
                    for i, list_item in enumerate(value):
                        if isinstance(list_item, dict):
                            _check_item(list_item, f"{key}[{i}]")

        return contradictions

    def _analyze_contradiction(self, title: str, description: str) -> Optional[Dict]:
        """Analyze if there's a contradiction between title and description."""
        # Convert to lowercase for comparison
        title_lower = title.lower().strip()
        description_lower = description.lower().strip()

        # Skip if either is empty or too short
        if len(title_lower) < 3 or len(description_lower) < 3:
            return None

        # Basic contradiction patterns
        contradictions = []

        # 1. Opposite sentiment/status words - stronger contradiction patterns only
        positive_words = [
            "successful",
            "success",
            "completed successfully",
            "working perfectly",
            "excellent",
            "great success",
        ]
        negative_words = [
            "failed",
            "error",
            "broken",
            "failure",
            "unsuccessful",
            "crashed",
            "rejected",
        ]

        # Check for stronger patterns to avoid false positives
        title_has_strong_positive = any(word in title_lower for word in positive_words)
        title_has_strong_negative = any(word in title_lower for word in negative_words)
        desc_has_strong_positive = any(
            word in description_lower for word in positive_words
        )
        desc_has_strong_negative = any(
            word in description_lower for word in negative_words
        )

        # Only flag clear contradictions
        if (title_has_strong_positive and desc_has_strong_negative) or (
            title_has_strong_negative and desc_has_strong_positive
        ):
            contradictions.append(
                {
                    "type": "sentiment_contradiction",
                    "confidence": 0.8,
                    "details": "Title and description have clearly opposite sentiments",
                }
            )

        # 2. Contradictory action words
        action_pairs = [
            (["create", "add", "new"], ["delete", "remove", "destroy"]),
            (["start", "begin", "enable"], ["stop", "end", "disable"]),
            (["open", "unlock"], ["close", "lock"]),
            (["increase", "raise", "up"], ["decrease", "lower", "down"]),
        ]

        for positive_actions, negative_actions in action_pairs:
            title_has_positive = any(word in title_lower for word in positive_actions)
            title_has_negative = any(word in title_lower for word in negative_actions)
            desc_has_positive = any(
                word in description_lower for word in positive_actions
            )
            desc_has_negative = any(
                word in description_lower for word in negative_actions
            )

            if (title_has_positive and desc_has_negative) or (
                title_has_negative and desc_has_positive
            ):
                contradictions.append(
                    {
                        "type": "action_contradiction",
                        "confidence": 0.8,
                        "details": "Title and description describe contradictory actions",
                    }
                )

        # 3. Numerical contradictions (basic check)
        title_numbers = re.findall(r"\d+", title)
        desc_numbers = re.findall(r"\d+", description)

        if title_numbers and desc_numbers:
            title_nums = [int(n) for n in title_numbers]
            desc_nums = [int(n) for n in desc_numbers]

            # Simple check: if title says "0" and description mentions positive numbers
            if 0 in title_nums and any(n > 0 for n in desc_nums):
                contradictions.append(
                    {
                        "type": "numerical_contradiction",
                        "confidence": 0.6,
                        "details": "Title mentions zero while description mentions positive numbers",
                    }
                )

        # Return the highest confidence contradiction
        if contradictions:
            return max(contradictions, key=lambda x: x["confidence"])

        return None

    def _add_contradiction_metadata_to_log(
        self, log_entry: UiChatLog, contradictions: List[Dict]
    ) -> UiChatLog:
        """Add contradiction metadata to a log entry."""
        # Create a new log entry with updated additional_context
        updated_context = log_entry.get("additional_context") or {}
        updated_context["contradiction_analysis"] = {
            "contradictions_detected": len(contradictions),
            "contradictions": contradictions,
        }

        # Create new log entry with updated context
        return {
            "message_type": log_entry["message_type"],
            "message_sub_type": log_entry.get("message_sub_type"),
            "content": log_entry["content"],
            "timestamp": log_entry["timestamp"],
            "status": log_entry.get("status"),
            "correlation_id": log_entry.get("correlation_id"),
            "tool_info": log_entry.get("tool_info"),
            "additional_context": updated_context,
        }
