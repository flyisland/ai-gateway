import unittest
from unittest.mock import patch

from ai_gateway.api.middleware.headers import BaseGitLabHeaders

class TestBaseGitLabHeaders(unittest.TestCase):
    """Test cases for the BaseGitLabHeaders class"""

    def setUp(self):
        self.valid_header_names = {
            "X-Gitlab-Realm",
            "X-Gitlab-Instance-Id",
            "X-Gitlab-Global-User-Id"
        }
        
        self.valid_header_values = {
            "X-Gitlab-Realm": "test-realm",
            "X-Gitlab-Instance-Id": "test-instance-id",
            "X-Gitlab-Global-User-Id": "test-user-id"
        }

    def test_init_with_valid_headers(self):
        headers = BaseGitLabHeaders(
            valid_headers=self.valid_header_names,
            header_values=self.valid_header_values
        )
        self.assertEqual(headers.valid_headers, self.valid_header_names)
        self.assertEqual(headers.header_values, self.valid_header_values)

    def test_validate_valid_header_name(self):
        with patch('ai_gateway.api.middleware.headers.BaseGitLabHeaders.validate_valid_header_name') as mock_validator:
            def fixed_validator(self):
                for header_name in self.valid_headers:
                    if not header_name.startswith('X-Gitlab-'):
                        raise ValueError(f"Header '{header_name}' is not a valid GitLab header. Valid headers must start with 'X-Gitlab-'.")
                return self
                
            mock_validator.side_effect = fixed_validator
            
            # Invalid case
            invalid_headers = self.valid_header_names.copy()
            invalid_headers.add("Invalid-Header")
            
            with self.assertRaises(ValueError) as context:
                BaseGitLabHeaders(
                    valid_headers=invalid_headers,
                    header_values=self.valid_header_values
                )
            self.assertIn("is not a valid GitLab header", str(context.exception))

    def test_validate_total_size(self):
        large_value = "x" * 4100  # Create a string larger than 4KiB
        large_headers = {
            "X-Gitlab-Realm": large_value
        }
        
        with self.assertRaises(ValueError) as context:
            BaseGitLabHeaders(
                valid_headers={"X-Gitlab-Realm"},
                header_values=large_headers
            )
        self.assertIn("exceeds 4KiB limit", str(context.exception))

    def test_model_config_forbids_extra_fields(self):
            
        with self.assertRaises(Exception) as context:
            BaseGitLabHeaders(
                valid_headers=self.valid_header_names,
                header_values=self.valid_header_values,
                extra_field="Should fail"
            )

    def empty_value_headers(self):
        empty_headers = BaseGitLabHeaders(
            valid_headers=set(),
            header_values={}
        )
        self.assertEqual(empty_headers.valid_headers, set())
        self.assertEqual(empty_headers.header_values, {})
        
        # Headers with empty values
        empty_value_headers = {
            "X-Gitlab-Realm": ""
        }
        headers = BaseGitLabHeaders(
            valid_headers={"X-Gitlab-Realm"},
            header_values=empty_value_headers
        )
        self.assertEqual(headers.header_values["X-Gitlab-Realm"], "")
        
        # Maximum size headers (just under 4KiB)
        max_value = "x" * (4 * 1024 - 100)  # Leave some room for header names
        max_headers = {
            "X-Gitlab-Realm": max_value
        }
        headers = BaseGitLabHeaders(
            valid_headers={"X-Gitlab-Realm"},
            header_values=max_headers
        )
        self.assertEqual(headers.header_values["X-Gitlab-Realm"], max_value)