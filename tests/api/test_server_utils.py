from unittest.mock import MagicMock

from ai_gateway.api.server_utils import extract_retry_after_header
from ai_gateway.models.base import ModelAPICallError


def test_extract_retry_after_header_with_valid_header():
    mock_response = MagicMock()
    mock_response.headers = {"retry-after": "30"}

    mock_error = MagicMock()
    mock_error.response = mock_response

    mock_exc = MagicMock(spec=ModelAPICallError)
    mock_exc.errors = [mock_error]

    result = extract_retry_after_header(mock_exc)

    assert result == "30"


def test_extract_retry_after_header_with_no_header():
    mock_response = MagicMock()
    mock_response.headers = {}

    mock_error = MagicMock()
    mock_error.response = mock_response

    mock_exc = MagicMock(spec=ModelAPICallError)
    mock_exc.errors = [mock_error]

    result = extract_retry_after_header(mock_exc)

    assert result is None


def test_extract_retry_after_header_with_no_response():
    mock_error = MagicMock(spec=[])

    mock_exc = MagicMock(spec=ModelAPICallError)
    mock_exc.errors = [mock_error]

    result = extract_retry_after_header(mock_exc)

    assert result is None


def test_extract_retry_after_header_with_empty_errors():
    mock_exc = MagicMock(spec=ModelAPICallError)
    mock_exc.errors = []

    result = extract_retry_after_header(mock_exc)

    assert result is None


def test_extract_retry_after_header_with_no_errors_attribute():
    mock_exc = MagicMock(spec=ModelAPICallError)
    delattr(mock_exc, "errors")

    result = extract_retry_after_header(mock_exc)
    assert result is None
