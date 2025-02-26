"""
Test module for AWS error handlers.
Provides comprehensive test coverage for error handling and message formatting.
"""

import unittest
from unittest.mock import patch

from botocore.exceptions import ClientError

from ai_gateway.integrations.amazon_q.error_handers import AWSErrorHandler, ErrorConfig


class TestAWSErrorHandler(unittest.TestCase):
    """
    Test suite for AWSErrorHandler class.
    Tests various error scenarios, edge cases, and error message mappings.
    """

    def setUp(self):
        """
        Set up test fixtures before each test method.
        Creates common mock objects and test data.
        """
        # Create a mock ClientError response template
        self.mock_error_response = {"Error": {"Code": "", "Message": ""}}

    def create_client_error(self, code: str, message: str) -> ClientError:
        """
        Helper method to create a ClientError with specific code and message.

        Args:
            code (str): AWS error code
            message (str): Error message

        Returns:
            ClientError: Configured mock ClientError object
        """
        self.mock_error_response["Error"]["Code"] = code
        self.mock_error_response["Error"]["Message"] = message
        return ClientError(self.mock_error_response, "test_operation")

    def test_known_error_codes(self):
        """
        Test handling of all predefined error codes in ERROR_MAPPING.
        Verifies correct message mapping for each known error code.
        """
        for error_code, expected_message in AWSErrorHandler.ERROR_MAPPING.items():
            with self.subTest(error_code=error_code):
                # Create a client error with known error code
                client_error = self.create_client_error(
                    error_code, "Original AWS message"
                )

                # Handle the error
                error_config = AWSErrorHandler.handle_client_error(client_error)

                # Verify the response
                self.assertIsInstance(error_config, ErrorConfig)
                self.assertEqual(error_config.code, error_code)
                self.assertEqual(error_config.message, expected_message)

    def test_unknown_error_code(self):
        """
        Test handling of unknown error codes.
        Verifies proper fallback message generation for unexpected errors.
        """
        # Test data
        unknown_code = "UnknownErrorCode"
        error_message = "Some unexpected error occurred"

        # Create client error with unknown code
        client_error = self.create_client_error(unknown_code, error_message)

        # Handle the error
        error_config = AWSErrorHandler.handle_client_error(client_error)

        # Verify response
        self.assertEqual(error_config.code, unknown_code)
        self.assertEqual(error_config.message, f"AWS error occurred: {error_message}")

    def test_empty_error_details(self):
        """
        Test handling of empty error details.
        Verifies proper handling when error code or message is empty.
        """
        test_cases = [
            ("", "Empty message"),  # Empty code
            ("EmptyMessage", ""),  # Empty message
            ("", ""),  # Both empty
        ]

        for code, message in test_cases:
            with self.subTest(code=code, message=message):
                client_error = self.create_client_error(code, message)
                error_config = AWSErrorHandler.handle_client_error(client_error)

                self.assertEqual(error_config.code, code)
                expected_message = (
                    AWSErrorHandler.ERROR_MAPPING.get(code)
                    or f"AWS error occurred: {message}"
                )
                self.assertEqual(error_config.message, expected_message)

    def test_error_config_equality(self):
        """
        Test ErrorConfig equality comparison.
        Verifies that ErrorConfig objects compare correctly.
        """
        config1 = ErrorConfig("Code1", "Message1")
        config2 = ErrorConfig("Code1", "Message1")
        config3 = ErrorConfig("Code2", "Message2")

        self.assertEqual(config1, config2)
        self.assertNotEqual(config1, config3)

    @patch("botocore.exceptions.ClientError")
    def test_complex_error_handling(self, mock_client_error):
        """
        Test complex error scenarios with nested error details.
        Verifies handling of complex error structures and edge cases.
        """
        # Test nested error structure
        complex_error_response = {
            "Error": {
                "Code": "ComplexError",
                "Message": "Complex error message",
                "Details": {"SubError": "Additional error info"},
            }
        }

        mock_client_error.response = complex_error_response
        error_config = AWSErrorHandler.handle_client_error(mock_client_error)

        self.assertEqual(error_config.code, "ComplexError")
        self.assertEqual(
            error_config.message, "AWS error occurred: Complex error message"
        )

    def test_error_mapping_integrity(self):
        """
        Test integrity and completeness of ERROR_MAPPING.
        Verifies that all mapped messages are properly formatted.
        """
        for code, message in AWSErrorHandler.ERROR_MAPPING.items():
            with self.subTest(code=code):
                self.assertIsInstance(code, str)
                self.assertIsInstance(message, str)
                self.assertTrue(len(code) > 0)
                self.assertTrue(len(message) > 0)
                self.assertIn(".", message)  # Verify proper sentence formatting
