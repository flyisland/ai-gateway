from typing import Annotated, Any, Optional, Protocol, TypeAlias, Literal

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.runnables import RunnableBinding
from pydantic import AnyUrl, BaseModel, StringConstraints, UrlConstraints, Field

# NOTE: Do not change this to `BaseChatModel | RunnableBinding`. You'd think that's just equivalent, right? WRONG. If
# you do that, you'll get `object has no attribute 'get'` when you use a `RummableBinding`. Why? I have no idea.
# https://docs.python.org/3/library/stdtypes.html#types-union makes no mention of the order mattering. This might be
# a bug with Pydantic's type validations
Model: TypeAlias = RunnableBinding | BaseChatModel


class AmazonQModelMetadata(BaseModel):
    provider: Literal["amazon_q"]
    name: Literal["base"]
    role_arn: Annotated[str, StringConstraints(max_length=255)]

    def to_params(self) -> dict[str, str]:
        return { "metadata": { "role_arn": self.role_arn } }


class ModelMetadata(BaseModel):
    name: Annotated[str, StringConstraints(max_length=255)]
    provider: Annotated[str, StringConstraints(max_length=255)]
    endpoint: Optional[Annotated[AnyUrl, UrlConstraints(max_length=255)]] = None
    api_key: Optional[Annotated[str, StringConstraints(max_length=1000)]] = None
    identifier: Optional[Annotated[str, StringConstraints(max_length=1000)]] = None

    def to_params(self) -> dict[str, str]:
        params = {
            "api_base": str(self.endpoint).removesuffix("/"),
            "api_key": str(self.api_key),
            "model": self.name,
            "custom_llm_provider": self.provider,
        }

        if not self.identifier:
            return params

        provider, _, model_name = self.identifier.partition("/")

        if model_name:
            params["custom_llm_provider"] = provider
            params["model"] = model_name

            if provider == "bedrock":
                del params["api_base"]
        else:
            params["custom_llm_provider"] = "custom_openai"
            params["model"] = self.identifier

        return params


TypeModelMetadata: TypeAlias = ModelMetadata | AmazonQModelMetadata


class TypeModelFactory(Protocol):
    def __call__(self, *, model: str, **kwargs: Optional[Any]) -> Model: ...
