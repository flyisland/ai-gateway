from enum import StrEnum

from ai_gateway.api.auth_utils import StarletteUser
from ai_gateway.integrations.amazon_q.client import AmazonQClientFactory
from ai_gateway.models.base import ModelMetadata
from ai_gateway.models.base_text import TextGenModelBase, TextGenModelOutput
from ai_gateway.safety_attributes import SafetyAttributes

__all__ = [
    "AmazonQModel",
    "KindAmazonQModel",
]


class KindAmazonQModel(StrEnum):
    AMAZON_Q = "amazon_q"


class AmazonQModel(TextGenModelBase):
    def __init__(
        self,
        current_user: StarletteUser,
        role_arn: str,
        client_factory: AmazonQClientFactory,
    ):
        self._current_user = current_user
        self._role_arn = role_arn
        self._client_factory = client_factory
        self._metadata = ModelMetadata(
            name=KindAmazonQModel.AMAZON_Q,
            engine=KindAmazonQModel.AMAZON_Q,
        )

    @property
    def input_token_limit(self) -> int:
        return 20480

    @property
    def metadata(self) -> ModelMetadata:
        return self._metadata

    async def generate(  # type: ignore[override]
        self,
        prefix: str,
        suffix: str,
        filename: str,
        language: str,
        **kwargs,
    ) -> list[TextGenModelOutput]:
        q_client = self._client_factory.get_client(
            current_user=self._current_user,
            role_arn=self._role_arn,
        )

        request_payload = {
            "fileContext": {
                "leftFileContent": prefix,
                "rightFileContent": suffix if suffix else "",
                "filename": filename,
                "programmingLanguage": {
                    "languageName": language,
                },
            },
            "maxResults": 1,
        }

        response = q_client.generate_code_recommendations(request_payload)

        recommendations = response.get("CodeRecommendations", [])

        return self._process_recommendations(recommendations)

    def _process_recommendations(
        self, recommendations: list
    ) -> list[TextGenModelOutput]:
        """
        Process code recommendations and convert them to TextGenModelOutput objects.

        Args:
            response (dict): Response from q_client.generate_code_recommendations

        Returns:
            list[TextGenModelOutput]: List of processed recommendations
        """
        # Use list comprehension instead of for loop
        return [
            TextGenModelOutput(
                text=rec.get("content", ""),
                score=10
                ** 5,  # Constant value could be defined as a class/module constant
                safety_attributes=SafetyAttributes(),
            )
            for rec in recommendations
        ]
