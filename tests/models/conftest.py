from unittest.mock import AsyncMock, patch

import pytest


@pytest.fixture(name="mock_litellm_acompletion_streamed")
def mock_litellm_acompletion_streamed_fixture():
    with patch("ai_gateway.models.litellm.acompletion") as mock_acompletion:
        streamed_response = AsyncMock()
        streamed_response.__aiter__.return_value = iter(
            [
                AsyncMock(
                    choices=[AsyncMock(delta=AsyncMock(content="Streamed content"))]
                )
            ]
        )

        mock_acompletion.return_value = streamed_response

        yield mock_acompletion
