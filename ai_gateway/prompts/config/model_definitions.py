from typing import Dict, List

from pydantic import BaseModel, Field

# class ProviderConfig(BaseModel):
#     name: str
#     params: Dict[str, str] = Field(default_factory=dict)

# class ModelDefinition(BaseModel):
#     name: str
#     description: str
#     providers: Dict[str, ProviderConfig]

# class ModelDefinitions(BaseModel):
#     models: List[ModelDefinition]