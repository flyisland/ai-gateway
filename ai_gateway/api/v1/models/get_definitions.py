from fastapi import APIRouter, status
from gitlab_cloud_connector import GitLabUnitPrimitive
from pydantic import BaseModel
from starlette.responses import JSONResponse

from ai_gateway.model_selection import ModelSelectionConfig

router = APIRouter()


class _GetModelResponseModel(BaseModel):
    name: str
    identifier: str


class _GetModelResponseUnitPrimitive(BaseModel):
    feature_setting: str
    default_model: str  # deprecated, maintained for backward compatibility
    default_models: list[str]
    selectable_models: list[str]
    beta_models: list[str]
    unit_primitives: list[GitLabUnitPrimitive]


class _GetModelResponse(BaseModel):
    models: list[_GetModelResponseModel]
    unit_primitives: list[_GetModelResponseUnitPrimitive]


@router.get(
    "/definitions",
    status_code=status.HTTP_200_OK,
    description="List of available large language models powering GitLab Duo features",
)
async def get_models():
    selection_config = ModelSelectionConfig()
    unit_primitives = []

    for primitive in selection_config.get_unit_primitive_config():
        values = primitive.model_dump()
        values["default_model"] = values["default_models"][0]
        unit_primitives.append(_GetModelResponseUnitPrimitive(**values))

    response = _GetModelResponse(
        models=[
            _GetModelResponseModel(
                name=definition.name, identifier=definition.gitlab_identifier
            )
            for definition in selection_config.get_llm_definitions().values()
        ],
        unit_primitives=unit_primitives,
    )

    return JSONResponse(content=response.model_dump())
