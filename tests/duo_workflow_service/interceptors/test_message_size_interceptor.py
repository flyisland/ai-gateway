from unittest.mock import AsyncMock, MagicMock

import grpc
import pytest
from structlog.testing import capture_logs

from duo_workflow_service.interceptors.message_size_interceptor import (
    MAX_MESSAGE_SIZE,
    MessageSizeInterceptor,
)
from duo_workflow_service.interceptors.monitoring_interceptor import GRPCMethodType


# Mock message classes
class MockProtobufMessage:
    """Mock protobuf message with SerializeToString method."""

    def __init__(self, size_bytes: int):
        self.size_bytes = size_bytes

    def SerializeToString(self) -> bytes:
        return b"x" * self.size_bytes


class MockNonProtobufMessage:
    """Mock non-protobuf message for sys.getsizeof testing."""

    def __init__(self, size_bytes: int):
        self.size_bytes = size_bytes


class MockExceptionMessage:
    """Mock message that raises exception on SerializeToString."""

    def SerializeToString(self) -> bytes:
        raise RuntimeError("Serialization failed")


class MockRpcError(grpc.RpcError):
    """Mock RPC error."""

    def __init__(self, message: str, status_code: grpc.StatusCode):
        super().__init__(message)
        self._status_code = status_code

    def code(self) -> grpc.StatusCode:
        return self._status_code


# Test fixtures
@pytest.fixture
def interceptor():
    """MessageSizeInterceptor instance."""
    return MessageSizeInterceptor()


@pytest.fixture
def mock_context():
    """Mock gRPC context."""
    context = AsyncMock(spec=grpc.aio.ServicerContext)
    context.abort = AsyncMock()
    return context


@pytest.fixture
def mock_handler_call_details():
    """Mock handler call details."""
    details = MagicMock(spec=grpc.HandlerCallDetails)
    details.method = "/test.Service/TestMethod"
    return details


@pytest.fixture
def mock_handler():
    """Mock RPC method handler."""
    handler = MagicMock(spec=grpc.RpcMethodHandler)
    handler.request_deserializer = MagicMock()
    handler.response_serializer = MagicMock()
    return handler


@pytest.fixture
def mock_unary_handler(mock_handler):
    """Mock unary-unary handler."""
    mock_handler.request_streaming = False
    mock_handler.response_streaming = False
    mock_handler.unary_unary = AsyncMock()
    return mock_handler


@pytest.fixture
def mock_client_streaming_handler(mock_handler):
    """Mock client streaming handler."""
    mock_handler.request_streaming = True
    mock_handler.response_streaming = False
    mock_handler.stream_unary = AsyncMock()
    return mock_handler


@pytest.fixture
def mock_server_streaming_handler(mock_handler):
    """Mock server streaming handler."""
    mock_handler.request_streaming = False
    mock_handler.response_streaming = True
    mock_handler.unary_stream = AsyncMock()
    return mock_handler


@pytest.fixture
def mock_bidi_streaming_handler(mock_handler):
    """Mock bidirectional streaming handler."""
    mock_handler.request_streaming = True
    mock_handler.response_streaming = True
    mock_handler.stream_stream = AsyncMock()
    return mock_handler


# Message size fixtures
@pytest.fixture
def normal_message():
    """Normal-sized message (1KB)."""
    return MockProtobufMessage(1024)


@pytest.fixture
def just_under_limit_message():
    """Message just under the 4MiB limit."""
    return MockProtobufMessage(MAX_MESSAGE_SIZE - 1)


@pytest.fixture
def just_over_limit_message():
    """Message just over the 4MiB limit."""
    return MockProtobufMessage(MAX_MESSAGE_SIZE + 1)


@pytest.fixture
def significantly_oversized_message():
    """Significantly oversized message (5MB)."""
    return MockProtobufMessage(5 * 1024 * 1024)


@pytest.fixture
def non_protobuf_message():
    """Non-protobuf message for fallback testing."""
    return MockNonProtobufMessage(1024)


@pytest.fixture
def exception_message():
    """Message that raises exception on serialization."""
    return MockExceptionMessage()


# Parameterized size boundary tests
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "message_size,should_abort,test_description",
    [
        (1024, False, "normal sized message"),  # 1KB - should pass
        (MAX_MESSAGE_SIZE - 1, False, "just under limit"),  # 4MiB - 1 byte
        (MAX_MESSAGE_SIZE + 1, True, "just over limit"),  # 4MiB + 1 byte
        (5 * 1024 * 1024, True, "significantly oversized"),  # 5MB
    ],
)
@pytest.mark.parametrize(
    "grpc_type,request_streaming,response_streaming",
    [
        (GRPCMethodType.UNARY, False, False),
        (GRPCMethodType.CLIENT_STREAMING, True, False),
        (GRPCMethodType.SERVER_STREAMING, False, True),
        (GRPCMethodType.BIDI_STREAMING, True, True),
    ],
)
@pytest.mark.parametrize("direction", ["incoming", "outgoing"])
async def test_message_size_boundaries(
    interceptor,
    mock_context,
    mock_handler_call_details,
    message_size,
    should_abort,
    test_description,
    grpc_type,
    request_streaming,
    response_streaming,
    direction,
):
    """Test message size enforcement across all boundaries and gRPC types."""
    message = MockProtobufMessage(message_size)

    with capture_logs() as cap:
        await interceptor._check_message_size(
            message, direction, mock_handler_call_details, mock_context, grpc_type
        )

    if should_abort:
        mock_context.abort.assert_called_once_with(
            grpc.StatusCode.RESOURCE_EXHAUSTED,
            f"Error with {direction} message size ({message_size} bytes, "
            f"{round(message_size / (1024 * 1024), 2)} MB) exceeds 4MiB limit",
        )

        # Verify structured logging
        assert len(cap) == 1
        log_entry = cap[0]
        assert log_entry["direction"] == direction
        assert log_entry["method"] == "/test.Service/TestMethod"
        assert log_entry["message_size_bytes"] == message_size
        assert log_entry["max_size_bytes"] == MAX_MESSAGE_SIZE
        assert log_entry["grpc_type"] == grpc_type
        assert log_entry["size_mb"] == round(message_size / (1024 * 1024), 2)
        assert log_entry["max_size_mb"] == 4.0
    else:
        mock_context.abort.assert_not_called()
        assert len(cap) == 0


# None message handling tests
@pytest.mark.asyncio
async def test_none_message_handling(
    interceptor, mock_context, mock_handler_call_details
):
    """Test that None messages don't crash the interceptor."""
    with capture_logs() as cap:
        await interceptor._check_message_size(
            None,
            "incoming",
            mock_handler_call_details,
            mock_context,
            GRPCMethodType.UNARY,
        )

    mock_context.abort.assert_not_called()
    assert len(cap) == 0


# Non-protobuf message fallback tests
@pytest.mark.asyncio
async def test_non_protobuf_message_fallback(
    interceptor,
    mock_context,
    mock_handler_call_details,
    non_protobuf_message,
):
    """Test that non-protobuf messages use sys.getsizeof() fallback."""
    with capture_logs() as cap:
        await interceptor._check_message_size(
            non_protobuf_message,
            "incoming",
            mock_handler_call_details,
            mock_context,
            GRPCMethodType.UNARY,
        )

    mock_context.abort.assert_not_called()
    assert len(cap) == 0


# Empty handler case tests
@pytest.mark.asyncio
async def test_empty_handler_case(interceptor, mock_handler_call_details):
    """Test when continuation() returns None."""

    async def mock_continuation(details):
        return None

    result = await interceptor.intercept_service(
        mock_continuation, mock_handler_call_details
    )
    assert result is None


# Size calculation exception tests
@pytest.mark.asyncio
async def test_size_calculation_exception(
    interceptor, mock_context, mock_handler_call_details, exception_message
):
    """Test that serialization exceptions are logged but don't abort RPC."""
    with capture_logs() as cap:
        await interceptor._check_message_size(
            exception_message,
            "incoming",
            mock_handler_call_details,
            mock_context,
            GRPCMethodType.UNARY,
        )

    mock_context.abort.assert_not_called()
    assert len(cap) == 1
    log_entry = cap[0]
    assert "Error checking message size" in log_entry["event"]
    assert log_entry["error"] == "Serialization failed"
    assert log_entry["direction"] == "incoming"
    assert log_entry["method"] == "/test.Service/TestMethod"


# Abort exception propagation tests
@pytest.mark.asyncio
async def test_abort_exception_propagation(
    interceptor, mock_context, mock_handler_call_details, just_over_limit_message
):
    """Test that abort exceptions are re-raised."""
    mock_context.abort.side_effect = MockRpcError(
        "Message size limit exceeded", grpc.StatusCode.RESOURCE_EXHAUSTED
    )

    with pytest.raises(MockRpcError):
        await interceptor._check_message_size(
            just_over_limit_message,
            "incoming",
            mock_handler_call_details,
            mock_context,
            GRPCMethodType.UNARY,
        )


# Multiple messages in streams tests
@pytest.mark.asyncio
async def test_client_streaming_multiple_messages(
    interceptor, mock_client_streaming_handler, mock_handler_call_details, mock_context
):
    """Test client streaming with multiple messages, one oversized."""
    messages = [
        MockProtobufMessage(1024),  # Normal
        MockProtobufMessage(MAX_MESSAGE_SIZE + 1),  # Oversized
        MockProtobufMessage(1024),  # This shouldn't be processed
    ]

    async def mock_request_iterator():
        for msg in messages:
            yield msg

    # Configure abort to raise exception when called
    mock_context.abort.side_effect = MockRpcError(
        "Message size limit exceeded", grpc.StatusCode.RESOURCE_EXHAUSTED
    )

    # Create handler that consumes request iterator like real gRPC handler would
    async def mock_stream_unary_handler(request_iterator, context):
        async for request in request_iterator:
            pass  # Real handler would process each request
        return MockProtobufMessage(1024)

    mock_client_streaming_handler.stream_unary = mock_stream_unary_handler

    wrapped_handler = interceptor._wrap_stream_unary(
        mock_client_streaming_handler.stream_unary, mock_handler_call_details
    )

    with pytest.raises(MockRpcError):  # Should abort on oversized message
        await wrapped_handler(mock_request_iterator(), mock_context)


@pytest.mark.asyncio
async def test_server_streaming_multiple_messages(
    interceptor, mock_server_streaming_handler, mock_handler_call_details, mock_context
):
    """Test server streaming with multiple messages, one oversized."""
    # Configure abort to raise exception when called
    mock_context.abort.side_effect = MockRpcError(
        "Message size limit exceeded", grpc.StatusCode.RESOURCE_EXHAUSTED
    )

    # Create async generator that yields normal message then oversized message
    async def mock_response_generator(req, ctx):
        yield MockProtobufMessage(1024)  # Normal
        yield MockProtobufMessage(MAX_MESSAGE_SIZE + 1)  # Oversized
        yield MockProtobufMessage(1024)  # This shouldn't be yielded

    mock_server_streaming_handler.unary_stream = MagicMock(
        side_effect=mock_response_generator
    )

    wrapped_handler = interceptor._wrap_unary_stream(
        mock_server_streaming_handler.unary_stream, mock_handler_call_details
    )

    request = MockProtobufMessage(1024)
    response_count = 0

    with pytest.raises(MockRpcError):  # Should abort on oversized message
        async for response in wrapped_handler(request, mock_context):
            response_count += 1

    assert response_count == 1  # Only first message should be processed


@pytest.mark.asyncio
async def test_bidi_streaming_multiple_messages(
    interceptor, mock_bidi_streaming_handler, mock_handler_call_details, mock_context
):
    """Test bidirectional streaming with mix of normal and oversized messages."""
    request_messages = [
        MockProtobufMessage(1024),  # Normal
        MockProtobufMessage(MAX_MESSAGE_SIZE + 1),  # Oversized - should abort here
    ]

    async def mock_request_iterator():
        for msg in request_messages:
            yield msg

    async def mock_response_iterator(request_iter):
        async for req in request_iter:
            yield MockProtobufMessage(1024)  # Echo back normal responses

    mock_bidi_streaming_handler.stream_stream.side_effect = mock_response_iterator

    wrapped_handler = interceptor._wrap_stream_stream(
        mock_bidi_streaming_handler.stream_stream, mock_handler_call_details
    )

    with pytest.raises(Exception):  # Should abort on oversized request
        async for response in wrapped_handler(mock_request_iterator(), mock_context):
            pass


# Structured logging field completeness tests
@pytest.mark.asyncio
async def test_structured_logging_completeness(
    interceptor, mock_context, mock_handler_call_details, just_over_limit_message
):
    """Test that all required logging fields are present and correct."""
    with capture_logs() as cap:
        await interceptor._check_message_size(
            just_over_limit_message,
            "outgoing",
            mock_handler_call_details,
            mock_context,
            GRPCMethodType.SERVER_STREAMING,
        )

    assert len(cap) == 1
    log_entry = cap[0]

    # Verify all required fields are present
    required_fields = [
        "direction",
        "method",
        "message_size_bytes",
        "max_size_bytes",
        "grpc_type",
        "size_mb",
        "max_size_mb",
    ]
    for field in required_fields:
        assert field in log_entry, f"Missing required field: {field}"

    # Verify field values
    assert log_entry["direction"] == "outgoing"
    assert log_entry["method"] == "/test.Service/TestMethod"
    assert log_entry["message_size_bytes"] == MAX_MESSAGE_SIZE + 1
    assert log_entry["max_size_bytes"] == MAX_MESSAGE_SIZE
    assert log_entry["grpc_type"] == GRPCMethodType.SERVER_STREAMING
    assert log_entry["size_mb"] == round((MAX_MESSAGE_SIZE + 1) / (1024 * 1024), 2)
    assert log_entry["max_size_mb"] == 4.0


# Log levels and content tests
@pytest.mark.asyncio
async def test_no_logs_for_normal_messages(
    interceptor, mock_context, mock_handler_call_details, normal_message
):
    """Test that normal messages don't generate logs."""
    with capture_logs() as cap:
        await interceptor._check_message_size(
            normal_message,
            "incoming",
            mock_handler_call_details,
            mock_context,
            GRPCMethodType.UNARY,
        )

    assert len(cap) == 0
    mock_context.abort.assert_not_called()


@pytest.mark.asyncio
async def test_error_log_for_oversized_messages(
    interceptor,
    mock_context,
    mock_handler_call_details,
    significantly_oversized_message,
):
    """Test that oversized messages generate error logs with proper formatting."""
    message_size = 5 * 1024 * 1024

    with capture_logs() as cap:
        await interceptor._check_message_size(
            significantly_oversized_message,
            "incoming",
            mock_handler_call_details,
            mock_context,
            GRPCMethodType.UNARY,
        )

    assert len(cap) == 1
    log_entry = cap[0]

    expected_message = f"Error with incoming message size ({message_size} bytes, 5.0 MB) exceeds 4MiB limit"
    assert log_entry["event"] == expected_message


# Integration tests for handler wrapping
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "handler_fixture,handler_attr",
    [
        ("mock_unary_handler", "unary_unary"),
        ("mock_client_streaming_handler", "stream_unary"),
        ("mock_server_streaming_handler", "unary_stream"),
        ("mock_bidi_streaming_handler", "stream_stream"),
    ],
)
async def test_handler_wrapping(
    interceptor, mock_handler_call_details, handler_fixture, handler_attr, request
):
    """Test that all handler types are properly wrapped."""
    mock_handler = request.getfixturevalue(handler_fixture)

    async def mock_continuation(details):
        return mock_handler

    wrapped_handler = await interceptor.intercept_service(
        mock_continuation, mock_handler_call_details
    )

    assert wrapped_handler is not None
    assert hasattr(wrapped_handler, handler_attr)
