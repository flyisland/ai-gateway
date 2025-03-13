import json
import os
from datetime import datetime, timedelta, timezone
from unittest import mock
from unittest.mock import MagicMock, patch

import pytest
import requests
from jose import jwt

from ai_gateway.auth.glgo import GlgoAuthority


class TestGlgoAuthority:
    @pytest.fixture
    def base_url(self):
        return "https://example.com"

    @pytest.fixture
    def signing_key(self, assets_dir):
        filepath = assets_dir / "keys" / "signing_key.pem"
        return open(filepath).read()

    @pytest.fixture
    def public_key(self, assets_dir):
        filepath = assets_dir / "keys" / "public_key.pem"
        return open(filepath).read()

    @pytest.fixture
    def kid(self):
        return "7zzcwTGSip6wDUBxSOzfHDnRGcdlJwiMWE0Y4jnnUtY"

    @pytest.fixture
    def endpoint(self):
        return "https://example.com/cc/token"

    @pytest.fixture
    def glgo_authority(self, base_url, signing_key):
        return GlgoAuthority(signing_key=signing_key, glgo_base_url=base_url)

    @pytest.mark.parametrize(
        ("cc_endpoint_enabled", "expected_kid"),
        [
            ("True", "7zzcwTGSip6wDUBxSOzfHDnRGcdlJwiMWE0Y4jnnUtY"),
            ("False", None),
        ],
    )
    def test_kid(self, base_url, signing_key, cc_endpoint_enabled, expected_kid):
        with mock.patch.dict(
            os.environ, {"CC_ENDPOINT_ENABLED": cc_endpoint_enabled}, clear=True
        ):
            glgo_authority = GlgoAuthority(
                signing_key=signing_key, glgo_base_url=base_url
            )

            assert glgo_authority.kid == expected_kid

    @patch("requests.post")
    @pytest.mark.parametrize(
        ("cc_endpoint_enabled", "expected_endpoint"),
        [
            ("False", "https://example.com/aws/token"),
            ("True", "https://example.com/cc/token"),
        ],
    )
    def test_token_success(
        self,
        requests_mock,
        base_url,
        signing_key,
        public_key,
        cc_endpoint_enabled,
        expected_endpoint,
    ):
        with mock.patch.dict(
            os.environ, {"CC_ENDPOINT_ENABLED": cc_endpoint_enabled}, clear=True
        ):

            glgo_authority = GlgoAuthority(
                signing_key=signing_key, glgo_base_url=base_url
            )

            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"token": "mock-token"}
            requests_mock.return_value = mock_response

            token = glgo_authority.token(
                user_id="test-user", cloud_connector_token="mock-cloud-token"
            )

            assert token == "mock-token"
            requests_mock.assert_called_once()

            kwargs = requests_mock.call_args.kwargs
            assert kwargs["url"] == expected_endpoint
            assert kwargs["json"] == {"user_id": "test-user"}

            _, _, token = kwargs["headers"]["Authorization"].partition(" ")
            if cc_endpoint_enabled == "True":
                jwt_token = jwt.decode(token, public_key, audience="glgo")
                current_time = datetime.now(timezone.utc)
                current_time_posix = int(current_time.timestamp())

                assert jwt_token["cct"] == "mock-cloud-token"
                assert jwt_token["iss"] == "https://cloud.gitlab.com"
                assert jwt_token["uid"] == "test-user"
                assert jwt_token["exp"] > current_time_posix
                assert jwt_token["exp"] <= int(
                    (current_time + timedelta(hours=1)).timestamp()
                )
                assert jwt_token["nbf"] <= current_time_posix
                assert jwt_token["iat"] <= current_time_posix

    @patch("requests.post")
    def test_token_failure(self, requests_mock, base_url, signing_key, endpoint):
        glgo_authority = GlgoAuthority(signing_key=signing_key, glgo_base_url=base_url)

        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError
        requests_mock.return_value = mock_response

        with pytest.raises(requests.exceptions.HTTPError):
            glgo_authority.token(
                user_id="test-user", cloud_connector_token="mock-cloud-token"
            )

        requests_mock.assert_called_once()

    @patch("requests.post")
    def test_token_network_error(self, requests_mock, signing_key, base_url, endpoint):
        glgo_authority = GlgoAuthority(signing_key=signing_key, glgo_base_url=base_url)

        requests_mock.side_effect = requests.exceptions.ConnectionError

        with pytest.raises(requests.exceptions.ConnectionError):
            glgo_authority.token(
                user_id="test-user", cloud_connector_token="mock-cloud-token"
            )

        requests_mock.assert_called_once()

    @patch("requests.post")
    def test_token_invalid_response(
        self, requests_mock, signing_key, base_url, endpoint
    ):
        glgo_authority = GlgoAuthority(signing_key=signing_key, glgo_base_url=base_url)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {}  # Empty response
        requests_mock.return_value = mock_response

        token = glgo_authority.token(
            user_id="test-user", cloud_connector_token="mock-cloud-token"
        )

        assert token is None
        requests_mock.assert_called_once()
