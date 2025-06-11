import re
from enum import Enum
from typing import Any, Dict, List, Tuple, Optional


class SecurityException(Exception):
    """Custom exception raised when security validation fails"""

    pass


class SecurityFunction(Enum):
    """Available security functions"""

    ENCODE_TAGS = "encode_tags"
    STRIP_TOOL_CALLS = "strip_tool_calls"
    DETECT_CONTRADICTIONS = "detect_contradictions"
    MONITOR_DIVERGENCE = "monitor_divergence"


class PromptSecurity:
    """Security class with multiple security functions"""

    # Define dangerous tags to encode
    DANGEROUS_TAGS = {
        "goal": "goal",
        "system": "system",
        "s": "system",  # Shortened version
        # Add more tags here as needed
    }

    # Define which security functions to apply for each tool
    TOOL_SECURITY_CONFIG = {
        "get_issue": [SecurityFunction.ENCODE_TAGS, SecurityFunction.STRIP_TOOL_CALLS],
        "get_epic": [SecurityFunction.ENCODE_TAGS, SecurityFunction.STRIP_TOOL_CALLS],
        "create_issue": [
            SecurityFunction.ENCODE_TAGS,
            SecurityFunction.DETECT_CONTRADICTIONS,
            SecurityFunction.MONITOR_DIVERGENCE,
        ],
        # Add more tools and their security functions here
    }

    @staticmethod
    def apply_security(response: Any, tool_name: str) -> Any:
        """
        Apply all configured security functions for a specific tool.

        Args:
            response: The response to secure
            tool_name: Name of the tool being used

        Returns:
            Secured response

        Raises:
            SecurityException: If validation fails
        """
        # Get security functions for this tool
        security_functions = PromptSecurity.TOOL_SECURITY_CONFIG.get(tool_name, [])

        # Apply each security function in order
        secured_response = response
        for func in security_functions:
            result = PromptSecurity._apply_function(secured_response, func)

            # Check if this is a validation result (tuple) or transformed data
            if isinstance(result, tuple) and len(result) == 2:
                is_safe, error_message = result
                if not is_safe:
                    raise SecurityException(
                        f"Security validation failed: {error_message}"
                    )
            else:
                # It's transformed data, update the response
                secured_response = result

        return secured_response

    @staticmethod
    def _apply_function(data: Any, function: SecurityFunction) -> Any:
        """
        Apply a specific security function to data.

        Returns:
            - For transform functions: transformed data
            - For validation functions: (is_safe, error_message) tuple
        """
        function_map = {
            SecurityFunction.ENCODE_TAGS: PromptSecurity._encode_tags_recursive,
            SecurityFunction.STRIP_TOOL_CALLS: PromptSecurity._strip_tool_calls_wrapper,
            SecurityFunction.DETECT_CONTRADICTIONS: PromptSecurity._detect_contradictions_wrapper,
            SecurityFunction.MONITOR_DIVERGENCE: PromptSecurity._monitor_divergence_wrapper,
        }

        func = function_map.get(function)
        if func:
            return func(data)
        return data

    # === Wrapper functions for validation (return tuples) ===

    @staticmethod
    def _strip_tool_calls_wrapper(data: Any) -> Any:
        """Wrapper for strip_tool_calls that transforms data"""
        # For now, just return the data unchanged (placeholder)
        # In real implementation, this would strip unauthorized tool calls
        return data

    @staticmethod
    def _detect_contradictions_wrapper(data: Any) -> Tuple[bool, Optional[str]]:
        """Wrapper for detect_contradictions that validates data"""
        # Extract title and description from data
        if isinstance(data, dict):
            title = data.get("title", "")
            description = data.get("description", "")

            # Call the actual validation function
            return PromptSecurity.detect_contradictory_inputs(title, description)

        # If data format is unexpected, pass validation
        return True, None

    @staticmethod
    def _monitor_divergence_wrapper(data: Any) -> Tuple[bool, Optional[str]]:
        """Wrapper for monitor_divergence that validates data"""
        # Extract original intent and comments from data
        if isinstance(data, dict):
            original_intent = {
                "title": data.get("title", ""),
                "description": data.get("description", ""),
            }
            comments = data.get("comments", [])

            # Call the actual validation function
            return PromptSecurity.monitor_comment_divergence(original_intent, comments)

        # If data format is unexpected, pass validation
        return True, None

    @staticmethod
    def _encode_tags_recursive(data: Any) -> Any:
        """Recursively encode all dangerous tags"""
        if isinstance(data, str):
            return PromptSecurity._encode_tags(data)
        elif isinstance(data, dict):
            return {
                k: PromptSecurity._encode_tags_recursive(v) for k, v in data.items()
            }
        elif isinstance(data, list):
            return [PromptSecurity._encode_tags_recursive(item) for item in data]
        return data

    @staticmethod
    def _encode_tags(text: str) -> str:
        """Encode all dangerous tags in text"""
        # Process each dangerous tag
        for tag, replacement in PromptSecurity.DANGEROUS_TAGS.items():
            # Handle exact tag
            text = text.replace(f"<{tag}>", f"&lt;{replacement}&gt;")
            text = text.replace(f"</{tag}>", f"&lt;/{replacement}&gt;")

            # Handle case variations and spaces
            # Create pattern for case-insensitive matching with optional spaces
            tag_pattern = "".join(f"[{c.upper()}{c.lower()}]" for c in tag)

            # Opening tag with optional spaces
            text = re.sub(
                f"<(\\s*{tag_pattern}\\s*)>",
                lambda m: f"&lt;{replacement}&gt;",
                text,
                flags=re.IGNORECASE,
            )

            # Closing tag with optional spaces
            text = re.sub(
                f"</(\\s*{tag_pattern}\\s*)>",
                lambda m: f"&lt;/{replacement}&gt;",
                text,
                flags=re.IGNORECASE,
            )

        return text

    @staticmethod
    def strip_tool_calls(text: str, allowed_tools: List[str] = None) -> str:
        """
        Strip out any specifically named tool calls found in user-generated content.

        Args:
            text: Input text that may contain tool call attempts
            allowed_tools: List of tools that are allowed (if any)

        Returns:
            Text with unauthorized tool calls removed

        Example:
            Input: "Please call get_admin_access() and then get_issue()"
            Output: "Please call and then get_issue()" (if get_issue is allowed)
        """
        # TODO: Implement tool call detection and stripping
        pass

    @staticmethod
    def detect_contradictory_inputs(
        title: str, description: str, threshold: float = 0.7
    ) -> Tuple[bool, Optional[str]]:
        """
        Detect if issue title and description are significantly contradictory.

        Args:
            title: Issue title
            description: Issue description
            threshold: Similarity threshold (0-1) below which inputs are considered contradictory

        Returns:
            Tuple of (is_safe, contradiction_message)

        Example:
            Title: "Add user authentication"
            Description: "Remove all security features"
            Returns: (False, "Title suggests adding security but description suggests removing it")
        """
        # TODO: Implement using embeddings or semantic similarity
        pass

    @staticmethod
    def monitor_comment_divergence(
        original_intent: Dict[str, str], comments: List[str], threshold: float = 0.6
    ) -> Tuple[bool, Optional[str]]:
        """
        Monitor if comments deviate substantially from original issue intent.

        Args:
            original_intent: Dict with 'title' and 'description' of original issue
            comments: List of comment texts
            threshold: Divergence threshold (0-1) below which comments are considered off-topic

        Returns:
            Tuple of (is_safe, divergence_message)

        Example:
            Original: {"title": "Update documentation", "description": "Fix typos in README"}
            Comments: ["Let's refactor the entire codebase", "We should rewrite in Rust"]
            Returns: (False, "Comments have diverged significantly from original documentation task")
        """
        # TODO: Implement comment divergence detection
        pass

    @staticmethod
    def add_tool_config(tool_name: str, security_functions: List[SecurityFunction]):
        """Add or update security configuration for a tool"""
        PromptSecurity.TOOL_SECURITY_CONFIG[tool_name] = security_functions

    @staticmethod
    def get_tool_config(tool_name: str) -> List[SecurityFunction]:
        """Get security configuration for a tool"""
        return PromptSecurity.TOOL_SECURITY_CONFIG.get(tool_name, [])
