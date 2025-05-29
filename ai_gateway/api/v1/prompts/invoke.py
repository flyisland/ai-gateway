from http.client import responses
from typing import Annotated, Any, AsyncIterator, Optional, Protocol

from fastapi import APIRouter, Depends, HTTPException, Request, status
from gitlab_cloud_connector import GitLabFeatureCategory, WrongUnitPrimitives
from poetry.core.constraints.version.exceptions import ParseConstraintError
from pydantic import BaseModel, RootModel
from starlette.responses import StreamingResponse

from ai_gateway.api.auth_utils import StarletteUser, get_current_user
from ai_gateway.api.feature_category import feature_category
from ai_gateway.async_dependency_resolver import get_prompt_registry
from ai_gateway.prompts import BasePromptRegistry, Prompt


class PromptInputs(RootModel):
    root: dict[str, Any]


class PromptRequest(BaseModel):
    inputs: PromptInputs
    prompt_version: Optional[str] = None
    stream: Optional[bool] = False


class PromptChunk(Protocol):
    content: str


router = APIRouter()


@router.post(
    "/{prompt_id:path}",
    response_model=str,
    status_code=status.HTTP_200_OK,
)
@feature_category(GitLabFeatureCategory.AI_ABSTRACTION_LAYER)
async def invoke(
    request: Request,  # pylint: disable=unused-argument
    prompt_request: PromptRequest,
    prompt_id: str,
    current_user: Annotated[StarletteUser, Depends(get_current_user)],
    prompt_registry: Annotated[BasePromptRegistry, Depends(get_prompt_registry)],
):
    # tgao
    import pdb;pdb.set_trace()
    try:
        prompt = prompt_registry.get_on_behalf(
            current_user,
            prompt_id,
            prompt_request.prompt_version,
            internal_event_category=__name__,
        )
        #
        # prompts_registered[str(prompt_id_with_model_name)] = PromptRegistered(
        #   klass = klass, versions = versions
        # )
        # str(prompt_id_with_model_name)
        # 'review_merge_request/base'
        # (Pdb)
        # versions
        # {'2.0.0': PromptConfig(
        #     name='Claude 4.0 Multi File Review Merge Request',
        #     model=ModelConfig(name='claude-sonnet-4-20250514',
        #     params=ChatAnthropicParams(temperature=0.0, top_p=None, top_k=None,
        #     max_tokens=8192, max_retries=1,
        #     model_class_provider= < ModelClassProvider.ANTHROPIC: 'anthropic' >,
        #     custom_llm_provider = None,
        #     default_headers = None)), unit_primitives = [ < GitLabUnitPrimitive.REVIEW_MERGE_REQUEST: 'review_merge_request' >],
        #     prompt_template = {
        #     'system': "{% include 'review_merge_request/system/1.0.0.jinja' %}\n",
        #     'user': "{% include 'review_merge_request/user/1.0.0.jinja' %}\n"
        #     }, params = None),
        #
        # '1.0.0': PromptConfig(
        #     name='Claude 3.7 Multi File Review Merge Request',
        #     model=ModelConfig(name='claude-3-7-sonnet-20250219',                                                                max_retries=1,
        #     model_class_provider= < ModelClassProvider.ANTHROPIC: 'anthropic' >,
        #     custom_llm_provider = None, default_headers = None)),
        #     unit_primitives = [ < GitLabUnitPrimitive.REVIEW_MERGE_REQUEST: 'review_merge_request' >],
        #     prompt_template = {
        #     'system': "{% include 'review_merge_request/system/1.0.0.jinja' %}\n",
        #     'user': "{% include 'review_merge_request/user/1.0.0.jinja' %}\n"
        #     },
        #     params = None)}
        # (Pdb)
        # versions.keys()
        # dict_keys(['2.0.0', '1.0.0'])
        # (Pdb)
        # class 'ai_gateway.prompts.base.Prompt'>
    except ParseConstraintError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid version constraint",
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Prompt '{prompt_id}' not found",
        )
    except WrongUnitPrimitives:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Unauthorized to access '{prompt_id}'",
        )

    # We don't use `isinstance` because we don't want to match subclasses
    if not type(prompt) is Prompt:  # pylint: disable=unidiomatic-typecheck
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Prompt '{prompt_id}' is not supported",
        )

    try:
        if prompt_request.stream:
            response: AsyncIterator[PromptChunk] = prompt.astream(
                prompt_request.inputs.root
            )

            async def _handle_stream():
                async for chunk in response:
                    yield chunk.content

            return StreamingResponse(_handle_stream(), media_type="text/event-stream")

        response_chunk: PromptChunk = await prompt.ainvoke(prompt_request.inputs.root)
        return response_chunk.content
    except KeyError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )
    except Exception as e:
        if hasattr(e, "status_code"):
            status_code = e.status_code
            err_status = f"{status_code}: {responses[status_code]}"
            raise HTTPException(
                status_code=status.HTTP_421_MISDIRECTED_REQUEST,
                # Misdirected Request https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/421
                # To signal to the client the model has produced and error
                # and not the AI Gateway
                detail=err_status,
            )
        raise e
