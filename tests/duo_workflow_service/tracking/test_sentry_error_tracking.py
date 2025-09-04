import unittest
from unittest.mock import MagicMock, patch

from duo_workflow_service.tracking.sentry_error_tracking import (
    _should_filter_error,
    remove_private_info_fields,
    setup_error_tracking,
    sentry_tracking_available,
)


class TestSentryErrorTracking(unittest.TestCase):
    def test_should_filter_error_rate_limit(self):
        """Test filtering of rate limit errors."""
        event = {
            "exception": {
                "values": [
                    {
                        "type": "HTTPError",
                        "value": "429 Too Many Requests: Rate limit exceeded"
                    }
                ]
            }
        }
        self.assertTrue(_should_filter_error(event, None))

    def test_should_filter_error_overload(self):
        """Test filtering of overload errors."""
        event = {
            "exception": {
                "values": [
                    {
                        "type": "ServiceError",
                        "value": "Service overloaded, please retry later"
                    }
                ]
            }
        }
        self.assertTrue(_should_filter_error(event, None))

    def test_should_filter_error_timeout_with_retry(self):
        """Test filtering of timeout errors that are retried."""
        event = {
            "exception": {
                "values": [
                    {
                        "type": "TimeoutError",
                        "value": "Request timeout, will retry automatically"
                    }
                ]
            }
        }
        self.assertTrue(_should_filter_error(event, None))

    def test_should_filter_error_unauthorized(self):
        """Test filtering of unauthorized errors."""
        event = {
            "exception": {
                "values": [
                    {
                        "type": "AuthError",
                        "value": "401 Unauthorized access"
                    }
                ]
            }
        }
        self.assertTrue(_should_filter_error(event, None))

    def test_should_filter_error_handled_tag(self):
        """Test filtering of errors marked as handled."""
        event = {
            "tags": {
                "handled": "true"
            },
            "exception": {
                "values": [
                    {
                        "type": "CustomError",
                        "value": "Some error"
                    }
                ]
            }
        }
        self.assertTrue(_should_filter_error(event, None))

    def test_should_filter_error_expected_tag(self):
        """Test filtering of errors marked as expected."""
        event = {
            "tags": {
                "expected": "true"
            },
            "exception": {
                "values": [
                    {
                        "type": "CustomError",
                        "value": "Some error"
                    }
                ]
            }
        }
        self.assertTrue(_should_filter_error(event, None))

    def test_should_not_filter_unhandled_error(self):
        """Test that unhandled errors are not filtered."""
        event = {
            "exception": {
                "values": [
                    {
                        "type": "UnexpectedError",
                        "value": "Something went wrong"
                    }
                ]
            }
        }
        self.assertFalse(_should_filter_error(event, None))

    def test_should_not_filter_critical_error(self):
        """Test that critical errors are not filtered."""
        event = {
            "exception": {
                "values": [
                    {
                        "type": "CriticalError",
                        "value": "Database connection failed"
                    }
                ]
            }
        }
        self.assertFalse(_should_filter_error(event, None))

    def test_remove_private_info_fields_filters_error(self):
        """Test that remove_private_info_fields filters handled errors."""
        event = {
            "server_name": "test-server",
            "exception": {
                "values": [
                    {
                        "type": "HTTPError",
                        "value": "429 Too Many Requests"
                    }
                ]
            }
        }
        
        result = remove_private_info_fields(event, None)
        self.assertIsNone(result)  # Should be filtered out

    def test_remove_private_info_fields_removes_server_name(self):
        """Test that server_name is removed from unfiltered events."""
        event = {
            "server_name": "test-server",
            "exception": {
                "values": [
                    {
                        "type": "UnexpectedError",
                        "value": "Something went wrong"
                    }
                ]
            }
        }
        
        result = remove_private_info_fields(event, None)
        self.assertIsNotNone(result)
        self.assertIsNone(result["server_name"])

    @patch.dict('os.environ', {'SENTRY_ERROR_TRACKING_ENABLED': 'true', 'SENTRY_DSN': 'test-dsn'})
    def test_sentry_tracking_available_enabled(self):
        """Test sentry tracking availability when enabled."""
        self.assertTrue(sentry_tracking_available())

    @patch.dict('os.environ', {'SENTRY_ERROR_TRACKING_ENABLED': 'false'})
    def test_sentry_tracking_available_disabled(self):
        """Test sentry tracking availability when disabled."""
        self.assertFalse(sentry_tracking_available())

    @patch.dict('os.environ', {'SENTRY_ERROR_TRACKING_ENABLED': 'true'})
    def test_sentry_tracking_available_no_dsn(self):
        """Test sentry tracking availability when enabled but no DSN."""
        # Remove SENTRY_DSN if it exists
        import os
        if 'SENTRY_DSN' in os.environ:
            del os.environ['SENTRY_DSN']
        self.assertFalse(sentry_tracking_available())

    @patch('duo_workflow_service.tracking.sentry_error_tracking.sentry_sdk')
    @patch('duo_workflow_service.tracking.sentry_error_tracking.sentry_tracking_available')
    def test_setup_error_tracking_when_available(self, mock_available, mock_sentry_sdk):
        """Test setup_error_tracking when sentry is available."""
        mock_available.return_value = True
        
        setup_error_tracking()
        
        mock_sentry_sdk.init.assert_called_once()

    @patch('duo_workflow_service.tracking.sentry_error_tracking.sentry_sdk')
    @patch('duo_workflow_service.tracking.sentry_error_tracking.sentry_tracking_available')
    def test_setup_error_tracking_when_not_available(self, mock_available, mock_sentry_sdk):
        """Test setup_error_tracking when sentry is not available."""
        mock_available.return_value = False
        
        setup_error_tracking()
        
        mock_sentry_sdk.init.assert_not_called()


if __name__ == "__main__":
    unittest.main()