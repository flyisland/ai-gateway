from time import time
from typing import Annotated, AsyncIterator, Optional

from dependency_injector.providers import Factory
from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, HTTPException, Request, status
from gitlab_cloud_connector import (
    CloudConnectorConfig,
    GitLabFeatureCategory,
    GitLabUnitPrimitive,
)
from gitlab_cloud_connector.auth import AUTH_HEADER

from ai_gateway.api.auth_utils import StarletteUser, get_current_user
from ai_gateway.api.feature_category import feature_category
from ai_gateway.api.middleware import X_GITLAB_LANGUAGE_SERVER_VERSION
from ai_gateway.api.snowplow_context import get_snowplow_code_suggestion_context
from ai_gateway.api.v3.code.typing import (
    CodeContextPayload,
    CodeEditorComponents,
    CompletionRequest,
    CompletionResponse,
    EditorContentCompletionPayload,
    EditorContentGenerationPayload,
    ModelMetadata,
    ResponseMetadataBase,
    StreamHandler,
    StreamModelEngine,
    StreamSuggestionsResponse,
)
from ai_gateway.async_dependency_resolver import (
    get_code_suggestions_completions_amazon_q_factory_provider,
    get_code_suggestions_generations_amazon_q_factory_provider,
    get_config,
    get_container_application,
)
from ai_gateway.code_suggestions import (
    CodeCompletions,
    CodeCompletionsLegacy,
    CodeGenerations,
    CodeSuggestionsChunk,
    LanguageServerVersion,
    ModelProvider,
)
from ai_gateway.code_suggestions.base import SAAS_PROMPT_MODEL_MAP
from ai_gateway.config import Config
from ai_gateway.container import ContainerApplication
from ai_gateway.feature_flags.context import current_feature_flag_context
from ai_gateway.models import KindModelProvider
from ai_gateway.prompts import BasePromptRegistry
from ai_gateway.structured_logging import get_request_logger
from ai_gateway.tracking import SnowplowEventContext

__all__ = [
    "router",
    "code_suggestions",
]

request_log = get_request_logger("codesuggestions")

router = APIRouter()


async def get_prompt_registry():
    yield get_container_application().pkg_prompts.prompt_registry()


async def handle_stream(
    stream: AsyncIterator[CodeSuggestionsChunk],
    engine: StreamModelEngine,
) -> StreamSuggestionsResponse:
    async def _stream_response_generator():
        async for chunk in stream:
            yield chunk.text

    return StreamSuggestionsResponse(
        _stream_response_generator(), media_type="text/event-stream"
    )


@router.post("/completions")
@feature_category(GitLabFeatureCategory.CODE_SUGGESTIONS)
async def completions(
    request: Request,
    payload: CompletionRequest,
    current_user: Annotated[StarletteUser, Depends(get_current_user)],
    prompt_registry: Annotated[BasePromptRegistry, Depends(get_prompt_registry)],
    config: Annotated[Config, Depends(get_config)],
    completions_amazon_q_factory: Annotated[
        CodeCompletions,
        Depends(get_code_suggestions_completions_amazon_q_factory_provider),
    ],
    generations_amazon_q_factory: Annotated[
        CodeGenerations,
        Depends(get_code_suggestions_generations_amazon_q_factory_provider),
    ],
):
    request_log.debug("[v3/code/completions] payload", payload=payload)
    return await code_suggestions(
        request=request,
        payload=payload,
        current_user=current_user,
        prompt_registry=prompt_registry,
        config=config,
        completions_amazon_q_factory=completions_amazon_q_factory,
        generations_amazon_q_factory=generations_amazon_q_factory,
    )


# This function is also used by `v4/code/suggestions`. When making
# changes, ensure you consider its effects on both v3 and v4.
async def code_suggestions(
    request: Request,
    payload: CompletionRequest,
    current_user: StarletteUser,
    prompt_registry: BasePromptRegistry,
    config: Config,
    stream_handler: StreamHandler = handle_stream,
    completions_amazon_q_factory: Optional[CodeCompletions] = None,
    generations_amazon_q_factory: Optional[CodeGenerations] = None,
):
    language_server_version = LanguageServerVersion.from_string(
        request.headers.get(X_GITLAB_LANGUAGE_SERVER_VERSION, None)
    )
    component = payload.prompt_components[0]
    code_context = [
        component.payload.content
        for component in payload.prompt_components
        if component.type == CodeEditorComponents.CONTEXT
        and language_server_version.supports_advanced_context()
    ] or None

    snowplow_code_suggestion_context = get_snowplow_code_suggestion_context(
        req=request,
        prefix=component.payload.content_above_cursor,
        suffix=component.payload.content_below_cursor,
        language=component.payload.language_identifier,
        global_user_id=current_user.global_user_id,
        region=config.google_cloud_platform.location(),
    )
    if component.type == CodeEditorComponents.COMPLETION:
        request_log.debug("[code_suggestions] starting code completion")
        if not current_user.can(
            GitLabUnitPrimitive.COMPLETE_CODE,
            disallowed_issuers=[CloudConnectorConfig().service_name],
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Unauthorized to access code suggestions",
            )

        if component.payload.model_provider == KindModelProvider.AMAZON_Q:
            _validate_amazon_q_requirements(payload)
            engine = _create_amazon_q_engine(
                completions_amazon_q_factory,
                component.payload,
                current_user,
                request,
                payload.role_arn,
            )
        else:
            engine = None
        return await code_completion(
            payload=component.payload,
            code_context=code_context,
            stream_handler=stream_handler,
            snowplow_event_context=snowplow_code_suggestion_context,
            engine=engine,
        )
    if component.type == CodeEditorComponents.GENERATION:
        if not current_user.can(
            GitLabUnitPrimitive.GENERATE_CODE,
            disallowed_issuers=[CloudConnectorConfig().service_name],
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Unauthorized to access code suggestions",
            )

        if component.payload.model_provider == KindModelProvider.AMAZON_Q:
            _validate_amazon_q_requirements(payload)
            engine = _create_amazon_q_engine(
                generations_amazon_q_factory,
                component.payload,
                current_user,
                request,
                payload.role_arn,
            )
        else:
            engine = None
        return await code_generation(
            current_user=current_user,
            payload=component.payload,
            code_context=code_context,
            prompt_registry=prompt_registry,
            stream_handler=stream_handler,
            snowplow_event_context=snowplow_code_suggestion_context,
            engine=engine,
        )


@inject
async def code_completion(
    payload: EditorContentCompletionPayload,
    stream_handler: StreamHandler,
    completions_legacy_factory: Factory[CodeCompletionsLegacy] = Provide[
        ContainerApplication.code_suggestions.completions.vertex_legacy.provider
    ],
    completions_anthropic_factory: Factory[CodeCompletions] = Provide[
        ContainerApplication.code_suggestions.completions.anthropic.provider
    ],
    code_context: list[CodeContextPayload] = None,
    snowplow_event_context: Optional[SnowplowEventContext] = None,
    engine: CodeCompletions = None,
):
    kwargs = {}

    if payload.model_provider == ModelProvider.ANTHROPIC:
        # TODO: As we migrate to v3 we can rewrite this to use prompt registry
        engine = completions_anthropic_factory(model__name=payload.model_name)
        kwargs.update({"raw_prompt": payload.prompt})
    elif payload.model_provider == KindModelProvider.AMAZON_Q:
        if engine is None:
            raise ValueError(
                "Engine must be provided when using Amazon Q as the model provider"
            )
    else:
        engine = completions_legacy_factory()

    if payload.choices_count > 0:
        kwargs.update({"candidate_count": payload.choices_count})

    suggestions = await engine.execute(
        prefix=payload.content_above_cursor,
        suffix=payload.content_below_cursor,
        file_name=payload.file_name,
        editor_lang=payload.language_identifier,
        stream=payload.stream,
        code_context=code_context,
        snowplow_event_context=snowplow_event_context,
        **kwargs,
    )
    request_log.debug("Code completion suggestions:", suggestions=suggestions)
    if not isinstance(suggestions, list):
        suggestions = [suggestions]

    if isinstance(suggestions[0], AsyncIterator):
        return await stream_handler(suggestions[0], engine)

    return CompletionResponse(
        choices=_completion_suggestion_choices(suggestions),
        metadata=ResponseMetadataBase(
            timestamp=int(time()),
            model=ModelMetadata(
                engine=suggestions[0].model.engine,
                name=suggestions[0].model.name,
                lang=suggestions[0].lang,
            ),
            enabled_feature_flags=current_feature_flag_context.get(),
        ),
    )


def _completion_suggestion_choices(suggestions: list) -> list:
    if len(suggestions) == 0:
        return []

    choices = []
    for suggestion in suggestions:
        request_log.debug(
            "code completion suggestion:",
            suggestion=suggestion,
            score=suggestion.score,
            language=suggestion.lang,
        )

        if not suggestion.text:
            continue

        choices.append(CompletionResponse.Choice(text=suggestion.text))

    return choices


@inject
async def code_generation(
    payload: EditorContentGenerationPayload,
    current_user: StarletteUser,
    prompt_registry: BasePromptRegistry,
    stream_handler: StreamHandler,
    generations_vertex_factory: Factory[CodeGenerations] = Provide[
        ContainerApplication.code_suggestions.generations.vertex.provider
    ],
    generations_anthropic_factory: Factory[CodeGenerations] = Provide[
        ContainerApplication.code_suggestions.generations.anthropic_default.provider
    ],
    agent_factory: Factory[CodeGenerations] = Provide[
        ContainerApplication.code_suggestions.generations.agent_factory.provider
    ],
    code_context: list[CodeContextPayload] = None,
    snowplow_event_context: Optional[SnowplowEventContext] = None,
    engine: CodeGenerations = None,
):
    model_provider = payload.model_provider
    # TODO: Check if this check is correct
    if payload.prompt_id and payload.model_provider == KindModelProvider.AMAZON_Q:
        request_log.debug(
            "Validating engine", engine=engine, model_provider=payload.model_provider
        )
        if engine is None:
            raise ValueError(
                "Engine must be provided when using Amazon Q as the model provider"
            )
    elif payload.prompt_id:
        # for backward compatibility, eventually prmpt_version should be a mandatory field
        prompt_version = payload.prompt_version or "^1.0.0"
        # For SaaS: prompt_version and prompt_id are mandatory fields
        # in case prompt_id is present, model_provider is not directly passed in from request
        model_provider = SAAS_PROMPT_MODEL_MAP[prompt_version]["model_provider"]

        prompt = prompt_registry.get_on_behalf(
            user=current_user,
            prompt_id=payload.prompt_id,
            prompt_version=payload.prompt_version,
            internal_event_category=__name__,
        )
        engine = agent_factory(model__prompt=prompt)

        request_log.info(
            "Executing code generation with prompt registry",
            prompt_name=prompt.name,
            prompt_model_class=prompt.model.__class__.__name__,
            prompt_model_name=prompt.model_name,
        )
    else:
        # TODO: Since we are migrating to prompt registry, we should sunset this branch
        if model_provider == KindModelProvider.ANTHROPIC:
            engine = generations_anthropic_factory()
        else:
            engine = generations_vertex_factory()

        if payload.prompt:
            engine.with_prompt_prepared(payload.prompt)

    suggestion = await engine.execute(
        prefix=payload.content_above_cursor,
        file_name=payload.file_name,
        editor_lang=payload.language_identifier,
        model_provider=model_provider,
        stream=payload.stream,
        snowplow_event_context=snowplow_event_context,
        prompt_enhancer=payload.prompt_enhancer,
    )
    request_log.debug("Suggestions", suggestion=suggestion)
    if isinstance(suggestion, AsyncIterator):
        return await stream_handler(suggestion, engine)

    choices = (
        [CompletionResponse.Choice(text=suggestion.text)] if suggestion.text else []
    )

    return CompletionResponse(
        choices=choices,
        metadata=ResponseMetadataBase(
            timestamp=int(time()),
            model=ModelMetadata(
                engine=suggestion.model.engine,
                name=suggestion.model.name,
                lang=suggestion.lang,
            ),
            enabled_feature_flags=current_feature_flag_context.get(),
        ),
    )


def _validate_amazon_q_requirements(payload):
    """Validate required parameters for Amazon Q requests."""
    if not payload.role_arn:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="role_arn is required for Amazon Q",
        )


def _create_amazon_q_engine(amazon_q_factory, payload, current_user, request, role_arn):
    """Create Amazon Q engine with required parameters."""
    request_log.debug("Creating Amazon Q engine", payload=payload)
    if payload.model_provider == KindModelProvider.AMAZON_Q:
        return amazon_q_factory(
            model__current_user=current_user,
            model__auth_header=request.headers.get(AUTH_HEADER),
            model__role_arn=role_arn,
        )
    return None
