import sys
from typing import Any, Awaitable, Callable, Optional

import grpc
import structlog.stdlib
from grpc._cython.cygrpc import AbortError

from duo_workflow_service.interceptors.monitoring_interceptor import GRPCMethodType

MAX_MESSAGE_SIZE = 4 * 1024 * 1024

log = structlog.stdlib.get_logger("grpc")


class MessageSizeInterceptor(grpc.aio.ServerInterceptor):

    async def intercept_service(
        self,
        continuation: Callable[
            [grpc.HandlerCallDetails], Awaitable[grpc.RpcMethodHandler]
        ],
        handler_call_details: grpc.HandlerCallDetails,
    ) -> Optional[grpc.RpcMethodHandler]:
        handler: Optional[grpc.RpcMethodHandler] = await continuation(
            handler_call_details
        )

        if handler is None:
            return None

        # Wrap handlers based on their streaming type
        if handler.request_streaming and handler.response_streaming:
            # Bidirectional streaming (ExecuteWorkflow)
            handler_factory = grpc.stream_stream_rpc_method_handler
            handler_func = self._wrap_stream_stream(
                handler.stream_stream, handler_call_details
            )
        elif handler.request_streaming and not handler.response_streaming:
            # Client streaming
            handler_factory = grpc.stream_unary_rpc_method_handler
            handler_func = self._wrap_stream_unary(
                handler.stream_unary, handler_call_details
            )
        elif not handler.request_streaming and handler.response_streaming:
            # Server streaming
            handler_factory = grpc.unary_stream_rpc_method_handler
            handler_func = self._wrap_unary_stream(
                handler.unary_stream, handler_call_details
            )
        else:
            # Unary (GenerateToken, ListTools)
            handler_factory = grpc.unary_unary_rpc_method_handler
            handler_func = self._wrap_unary_unary(
                handler.unary_unary, handler_call_details
            )

        return handler_factory(
            handler_func,
            request_deserializer=handler.request_deserializer,
            response_serializer=handler.response_serializer,
        )

    def _wrap_unary_unary(
        self,
        original_handler: Callable,
        handler_call_details: grpc.HandlerCallDetails,
    ):
        """Wrap unary to unary messages (GenerateToken, ListTools)"""

        async def wrapped_handler(request, context):
            # Check incoming message size
            await self._check_message_size(
                request,
                "incoming",
                handler_call_details,
                context,
                GRPCMethodType.UNARY,
            )

            response = await original_handler(request, context)

            # Check outgoing message size
            await self._check_message_size(
                response,
                "outgoing",
                handler_call_details,
                context,
                GRPCMethodType.UNARY,
            )

            return response

        return wrapped_handler

    def _wrap_unary_stream(
        self,
        original_handler: Callable,
        handler_call_details: grpc.HandlerCallDetails,
    ):
        """Wrap server only streaming."""

        async def wrapped_handler(request, context):
            # Check incoming message size
            await self._check_message_size(
                request,
                "incoming",
                handler_call_details,
                context,
                GRPCMethodType.SERVER_STREAMING,
            )

            async for response in original_handler(request, context):
                # Check each outgoing message size
                await self._check_message_size(
                    response,
                    "outgoing",
                    handler_call_details,
                    context,
                    GRPCMethodType.SERVER_STREAMING,
                )
                yield response

        return wrapped_handler

    def _wrap_stream_unary(
        self,
        original_handler: Callable,
        handler_call_details: grpc.HandlerCallDetails,
    ):
        """Wrap client only streaming."""

        async def wrapped_handler(request_iterator, context):
            async def checked_request_iterator():
                async for request in request_iterator:
                    # Check each incoming message size
                    await self._check_message_size(
                        request,
                        "incoming",
                        handler_call_details,
                        context,
                        GRPCMethodType.CLIENT_STREAMING,
                    )
                    yield request

            response = await original_handler(checked_request_iterator(), context)

            # Check outgoing message size
            await self._check_message_size(
                response,
                "outgoing",
                handler_call_details,
                context,
                GRPCMethodType.CLIENT_STREAMING,
            )

            return response

        return wrapped_handler

    def _wrap_stream_stream(
        self,
        original_handler: Callable,
        handler_call_details: grpc.HandlerCallDetails,
    ):
        """Wrap bidirectional streaming (ExecuteWorkflow)"""

        async def wrapped_handler(request_iterator, context):
            async def checked_request_iterator():
                async for request in request_iterator:
                    # Check each incoming message size (StartWorkflow, ActionResponse, etc.)
                    await self._check_message_size(
                        request,
                        "incoming",
                        handler_call_details,
                        context,
                        GRPCMethodType.BIDI_STREAMING,
                    )
                    yield request

            async for response in original_handler(checked_request_iterator(), context):
                # Check each outgoing message size (Actions, etc.)
                await self._check_message_size(
                    response,
                    "outgoing",
                    handler_call_details,
                    context,
                    GRPCMethodType.BIDI_STREAMING,
                )
                yield response

        return wrapped_handler

    async def _check_message_size(
        self,
        message: Any,
        direction: str,
        handler_call_details: grpc.HandlerCallDetails,
        context: grpc.aio.ServicerContext,
        grpc_type: GRPCMethodType,
    ):
        """Check if message size exceeds the 4MiB limit and abort if it does."""
        if message is None:
            return

        try:
            # Calculate message size using protobuf serialization (most accurate)
            if hasattr(message, "SerializeToString"):
                message_size = len(message.SerializeToString())
            else:
                # Fallback to Python object size
                message_size = sys.getsizeof(message)

            if message_size > MAX_MESSAGE_SIZE:
                method_name = handler_call_details.method
                size_mb = round(message_size / (1024 * 1024), 2)

                error_message = (
                    f"Error with {direction} message size ({message_size} bytes, "
                    f"{size_mb} MB) exceeds 4MiB limit"
                )

                # Log with structured logging for production debugging
                log.error(
                    error_message,
                    direction=direction,
                    method=method_name,
                    message_size_bytes=message_size,
                    max_size_bytes=MAX_MESSAGE_SIZE,
                    grpc_type=grpc_type,
                    size_mb=size_mb,
                    max_size_mb=4.0,
                )

                # Abort with proper RESOURCE_EXHAUSTED status
                # This prevents connection termination and allows proper error handling
                await context.abort(
                    grpc.StatusCode.RESOURCE_EXHAUSTED,
                    error_message,
                )

        except AbortError:
            # Expected exception from context.abort() - let it propagate up
            # This allows the gRPC framework to handle the RESOURCE_EXHAUSTED response properly
            raise

        except grpc.RpcError as e:
            # Only re-raise RESOURCE_EXHAUSTED errors (our expected abort scenario)
            # Other gRPC errors should be logged as they're unexpected in this context
            if e.code() == grpc.StatusCode.RESOURCE_EXHAUSTED:
                raise

            # Log unexpected gRPC errors
            log.error(
                "Unexpected gRPC error in message size check",
                error=str(e),
                grpc_code=e.code().name if hasattr(e, "code") else "unknown",
                direction=direction,
                method=handler_call_details.method,
            )

        except Exception as e:
            # Log error but don't fail the RPC for size checking issues
            log.error(
                "Error checking message size",
                error=str(e),
                direction=direction,
                method=handler_call_details.method,
            )
