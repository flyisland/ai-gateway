from typing import Annotated, Any, Dict, Literal, Optional, Protocol, TypeAlias

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.runnables import RunnableBinding
from pydantic import AnyUrl, BaseModel, StringConstraints, UrlConstraints

Model: TypeAlias = RunnableBinding | BaseChatModel


class AmazonQModelMetadata(BaseModel):
    provider: Literal["amazon_q"]
    name: Literal["base"]
    role_arn: Annotated[str, StringConstraints(max_length=255)]

    def to_params(self) -> Dict[str, Dict[str, str]]:
        return {"metadata": {"role_arn": self.role_arn}}


class ModelMetadata(BaseModel):
    name: Annotated[str, StringConstraints(max_length=255)]
    provider: Annotated[str, StringConstraints(max_length=255)]
    endpoint: Optional[Annotated[AnyUrl, UrlConstraints(max_length=255)]] = None
    api_key: Optional[Annotated[str, StringConstraints(max_length=255)]] = None
    identifier: Optional[Annotated[str, StringConstraints(max_length=255)]] = None

    def to_params(self) -> Dict[str, str]:
        params: Dict[str, str] = {}

        if self.endpoint:
            params["api_base"] = str(self.endpoint).removesuffix("/")
        if self.api_key:
            params["api_key"] = str(self.api_key)

        params["model"] = self.name
        params["custom_llm_provider"] = self.provider

        if self.identifier:
            provider, _, model_name = self.identifier.partition("/")

            if model_name:
                params["custom_llm_provider"] = provider
                params["model"] = model_name

                if provider == "bedrock":
                    params.pop("api_base", None)
            else:
                params["custom_llm_provider"] = "custom_openai"
                params["model"] = self.identifier

        return params


ModelMetadataType: TypeAlias = ModelMetadata | AmazonQModelMetadata


class TypeModelFactory(Protocol):
    def __call__(self, *, model: str, **kwargs: Optional[Any]) -> Model: ...
