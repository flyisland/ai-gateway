from typing import Optional

from anthropic import APIError


class GitLabDocsErrorCode:
    def __init__(self, code: str, url: Optional[str] = None):
        self.code = code
        self.url = (
            url
            if url
            else f"https://docs.gitlab.com/user/gitlab_duo_chat/troubleshooting/#error-{self.code.lower()}"
        )

    def __str__(self):
        return f"Error code: [{self.code}]({self.url})"

    @staticmethod
    def from_exception(exception: Exception) -> "GitLabDocsErrorCode":
        if isinstance(exception, APIError):
            # Anthropic API error
            return GitLabDocsErrorCode("A1008")

        # Unexpected error
        return GitLabDocsErrorCode("A1007")
