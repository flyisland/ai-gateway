import json
import os
from pathlib import Path
from typing import Awaitable, Callable, Optional, Self

import grpc
import structlog

from ai_gateway.model_metadata import (
    create_model_metadata,
    current_model_metadata_context,
)
from duo_workflow_service.interceptors.authentication_interceptor import (
    current_user as current_user_context_var,
)

__all__ = [
    "ModelMetadataHeaderBasedInterceptor",
    "ModelMetadataEvalBasedInterceptor",
    "ModelMetadataInterceptor",
]

log = structlog.stdlib.get_logger("evaluation")


class ModelMetadataHeaderBasedInterceptor(grpc.aio.ServerInterceptor):
    """Interceptor that handles model metadata propagation."""

    X_GITLAB_AGENT_PLATFORM_MODEL_METADATA = "x-gitlab-agent-platform-model-metadata"

    async def intercept_service(
        self,
        continuation: Callable[
            [grpc.HandlerCallDetails], Awaitable[grpc.RpcMethodHandler]
        ],
        handler_call_details: grpc.HandlerCallDetails,
    ) -> grpc.RpcMethodHandler:
        """Intercept incoming requests to inject feature flags context."""
        metadata = dict(handler_call_details.invocation_metadata)

        try:
            data = json.loads(
                metadata.get(self.X_GITLAB_AGENT_PLATFORM_MODEL_METADATA, "")
            )

            model_metadata = create_model_metadata(data)
            if model_metadata:
                model_metadata.add_user(current_user_context_var.get())
            current_model_metadata_context.set(model_metadata)

        except json.JSONDecodeError:
            pass

        return await continuation(handler_call_details)


class ModelMetadataEvalBasedInterceptor(grpc.aio.ServerInterceptor):
    """Interceptor that handles model metadata propagation for evaluation environments.

    Reads metadata from patch_model_selection.json when AIGW_ENVIRONMENT='evaluation',
    enabling model selection for CEF flows and working around GoLang executor limitations.

    Example of the patch_model_selection.json file: {"provider": "gitlab", "name": "gpt_5"}

    Ref: https://gitlab.com/gitlab-org/modelops/ai-model-validation-and-research/ai-evaluation/prompt-library/-/issues/802
    """

    PATCH_LOOKUP_PATH = Path(__file__).parents[2] / "patch_model_selection.json"

    @classmethod
    def try_enable(cls) -> Optional[Self]:
        # pylint: disable-next=direct-environment-variable-reference
        if os.getenv("AIGW_ENVIRONMENT") != "evaluation":
            # Don't log any messages as the server may be running in prod
            return None

        patch_exists = cls.PATCH_LOOKUP_PATH.exists()

        log.info(
            "Model selection patching",
            status=patch_exists,
            details=(
                None
                if patch_exists
                else f"patch file {cls.PATCH_LOOKUP_PATH} not found"
            ),
        )

        return cls() if patch_exists else None

    async def intercept_service(
        self,
        continuation: Callable[
            [grpc.HandlerCallDetails], Awaitable[grpc.RpcMethodHandler]
        ],
        handler_call_details: grpc.HandlerCallDetails,
    ) -> grpc.RpcMethodHandler:
        """
        Ref: https://gitlab.com/gitlab-org/modelops/ai-model-validation-and-research/ai-evaluation/prompt-library/-/issues/802
        """

        try:
            with open(ModelMetadataEvalBasedInterceptor.PATCH_LOOKUP_PATH, "r") as fp:
                data = json.load(fp)
        except (FileNotFoundError, json.JSONDecodeError, PermissionError) as ex:
            log.error(
                "Failed to load the model metadata patch file",
                error=str(ex),
                path=str(ModelMetadataEvalBasedInterceptor.PATCH_LOOKUP_PATH),
            )
            return await continuation(handler_call_details)

        model_metadata = create_model_metadata(data)

        if model_metadata:
            model_metadata.add_user(current_user_context_var.get())
        current_model_metadata_context.set(model_metadata)

        return await continuation(handler_call_details)


class ModelMetadataInterceptor(grpc.aio.ServerInterceptor):
    def __init__(self):
        if interceptor := ModelMetadataEvalBasedInterceptor.try_enable():
            self.selected_interceptor = interceptor
        else:
            self.selected_interceptor = ModelMetadataHeaderBasedInterceptor()

    async def intercept_service(
        self,
        continuation: Callable[
            [grpc.HandlerCallDetails], Awaitable[grpc.RpcMethodHandler]
        ],
        handler_call_details: grpc.HandlerCallDetails,
    ) -> grpc.RpcMethodHandler:
        return await self.selected_interceptor.intercept_service(
            continuation, handler_call_details
        )
