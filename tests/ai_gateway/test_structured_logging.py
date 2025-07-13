import pytest
from unittest.mock import Mock, patch, MagicMock
import structlog
from structlog.types import EventDict

from ai_gateway.structured_logging import (
    can_log_request_data,
    prevent_logging_if_disabled,
    sanitize_logs,
    get_request_logger,
    rename_event_key,
    drop_color_message_key,
    add_custom_keys,
)
from ai_gateway.config import Config, ConfigLogging, ConfigCustomModels
from ai_gateway.model_metadata import ModelMetadata


class TestCanLogRequestData:
    """Test cases for can_log_request_data function."""

    @patch('ai_gateway.structured_logging.get_config')
    @patch('ai_gateway.structured_logging.enabled_instance_verbose_ai_logs')
    @patch('ai_gateway.structured_logging.is_feature_enabled')
    def test_returns_true_when_enable_request_logging_is_true(
        self, mock_is_feature_enabled, mock_enabled_instance_verbose_ai_logs, mock_get_config
    ):
        """Test that function returns True when enable_request_logging is True."""
        # Arrange
        mock_config = Mock()
        mock_config.logging.enable_request_logging = True
        mock_get_config.return_value = mock_config
        mock_enabled_instance_verbose_ai_logs.return_value = False
        mock_is_feature_enabled.return_value = False
        
        # Act
        result = can_log_request_data()
        
        # Assert
        assert result is True
        mock_get_config.assert_called_once()

    @patch('ai_gateway.structured_logging.get_config')
    @patch('ai_gateway.structured_logging.enabled_instance_verbose_ai_logs')
    @patch('ai_gateway.structured_logging.is_feature_enabled')
    @patch('ai_gateway.structured_logging.CUSTOM_MODELS_ENABLED', True)
    def test_returns_true_when_custom_models_enabled_and_verbose_ai_logs(
        self, mock_is_feature_enabled, mock_enabled_instance_verbose_ai_logs, mock_get_config
    ):
        """Test that function returns True when custom models enabled and verbose AI logs enabled."""
        # Arrange
        mock_config = Mock()
        mock_config.logging.enable_request_logging = False
        mock_get_config.return_value = mock_config
        mock_enabled_instance_verbose_ai_logs.return_value = True
        mock_is_feature_enabled.return_value = False
        
        # Act
        result = can_log_request_data()
        
        # Assert
        assert result is True
        mock_get_config.assert_called_once()
        mock_enabled_instance_verbose_ai_logs.assert_called_once()

    @patch('ai_gateway.structured_logging.get_config')
    @patch('ai_gateway.structured_logging.enabled_instance_verbose_ai_logs')
    @patch('ai_gateway.structured_logging.is_feature_enabled')
    @patch('ai_gateway.structured_logging.CUSTOM_MODELS_ENABLED', False)
    def test_returns_true_when_expanded_ai_logging_feature_enabled(
        self, mock_is_feature_enabled, mock_enabled_instance_verbose_ai_logs, mock_get_config
    ):
        """Test that function returns True when EXPANDED_AI_LOGGING feature flag is enabled."""
        # Arrange
        mock_config = Mock()
        mock_config.logging.enable_request_logging = False
        mock_get_config.return_value = mock_config
        mock_enabled_instance_verbose_ai_logs.return_value = False
        mock_is_feature_enabled.return_value = True
        
        # Act
        result = can_log_request_data()
        
        # Assert
        assert result is True
        mock_get_config.assert_called_once()
        mock_is_feature_enabled.assert_called_once()

    @patch('ai_gateway.structured_logging.get_config')
    @patch('ai_gateway.structured_logging.enabled_instance_verbose_ai_logs')
    @patch('ai_gateway.structured_logging.is_feature_enabled')
    @patch('ai_gateway.structured_logging.CUSTOM_MODELS_ENABLED', False)
    def test_returns_false_when_all_conditions_false(
        self, mock_is_feature_enabled, mock_enabled_instance_verbose_ai_logs, mock_get_config
    ):
        """Test that function returns False when all logging conditions are False."""
        # Arrange
        mock_config = Mock()
        mock_config.logging.enable_request_logging = False
        mock_get_config.return_value = mock_config
        mock_enabled_instance_verbose_ai_logs.return_value = False
        mock_is_feature_enabled.return_value = False
        
        # Act
        result = can_log_request_data()
        
        # Assert
        assert result is False
        mock_get_config.assert_called_once()

    @patch('ai_gateway.structured_logging.get_config')
    def test_gets_config_dynamically_each_call(self, mock_get_config):
        """Test that config is fetched dynamically on each function call."""
        # Arrange
        mock_config1 = Mock()
        mock_config1.logging.enable_request_logging = False
        mock_config2 = Mock()
        mock_config2.logging.enable_request_logging = True
        
        mock_get_config.side_effect = [mock_config1, mock_config2]
        
        # Act & Assert
        with patch('ai_gateway.structured_logging.enabled_instance_verbose_ai_logs', return_value=False), \
             patch('ai_gateway.structured_logging.is_feature_enabled', return_value=False), \
             patch('ai_gateway.structured_logging.CUSTOM_MODELS_ENABLED', False):
            
            result1 = can_log_request_data()
            result2 = can_log_request_data()
            
            assert result1 is False
            assert result2 is True
            assert mock_get_config.call_count == 2


class TestPreventLoggingIfDisabled:
    """Test cases for prevent_logging_if_disabled processor."""

    @patch('ai_gateway.structured_logging.can_log_request_data')
    def test_returns_event_dict_when_logging_enabled(self, mock_can_log):
        """Test that event dict is returned when logging is enabled."""
        # Arrange
        mock_can_log.return_value = True
        event_dict = {"message": "test message", "level": "info"}
        
        # Act
        result = prevent_logging_if_disabled(None, None, event_dict)
        
        # Assert
        assert result == event_dict
        mock_can_log.assert_called_once()

    @patch('ai_gateway.structured_logging.can_log_request_data')
    def test_raises_drop_event_when_logging_disabled(self, mock_can_log):
        """Test that DropEvent is raised when logging is disabled."""
        # Arrange
        mock_can_log.return_value = False
        event_dict = {"message": "test message", "level": "info"}
        
        # Act & Assert
        with pytest.raises(structlog.DropEvent):
            prevent_logging_if_disabled(None, None, event_dict)
        
        mock_can_log.assert_called_once()


class TestSanitizeLogs:
    """Test cases for sanitize_logs processor."""

    def test_sanitizes_api_key_when_present(self):
        """Test that api_key is sanitized when present in event dict."""
        # Arrange
        event_dict = {"api_key": "secret-key-123", "message": "test"}
        
        # Act
        result = sanitize_logs(None, None, event_dict)
        
        # Assert
        assert result["api_key"] == "**********"
        assert result["message"] == "test"

    def test_sets_api_key_to_none_when_not_present(self):
        """Test that api_key is set to None when not present in event dict."""
        # Arrange
        event_dict = {"message": "test"}
        
        # Act
        result = sanitize_logs(None, None, event_dict)
        
        # Assert
        assert result["api_key"] is None
        assert result["message"] == "test"

    def test_sanitizes_model_metadata_api_key(self):
        """Test that api_key in model_metadata is sanitized."""
        # Arrange
        model_metadata = ModelMetadata(api_key="secret-model-key")
        inputs = Mock()
        inputs.model_metadata = model_metadata
        event_dict = {"inputs": inputs, "message": "test"}
        
        # Act
        result = sanitize_logs(None, None, event_dict)
        
        # Assert
        assert result["inputs"].model_metadata.api_key == "**********"
        assert result["message"] == "test"

    def test_handles_inputs_without_model_metadata(self):
        """Test that function handles inputs without model_metadata attribute."""
        # Arrange
        inputs = Mock(spec=[])
        event_dict = {"inputs": inputs, "message": "test"}
        
        # Act
        result = sanitize_logs(None, None, event_dict)
        
        # Assert
        assert result["inputs"] == inputs
        assert result["message"] == "test"
        assert result["api_key"] is None

    def test_handles_none_model_metadata(self):
        """Test that function handles None model_metadata."""
        # Arrange
        inputs = Mock()
        inputs.model_metadata = None
        event_dict = {"inputs": inputs, "message": "test"}
        
        # Act
        result = sanitize_logs(None, None, event_dict)
        
        # Assert
        assert result["inputs"].model_metadata is None
        assert result["message"] == "test"


class TestGetRequestLogger:
    """Test cases for get_request_logger function."""

    @patch('ai_gateway.structured_logging.structlog.wrap_logger')
    @patch('ai_gateway.structured_logging.structlog.get_logger')
    def test_returns_wrapped_logger_with_processors(self, mock_get_logger, mock_wrap_logger):
        """Test that get_request_logger returns a wrapped logger with correct processors."""
        # Arrange
        mock_logger = Mock()
        mock_wrapped_logger = Mock()
        mock_get_logger.return_value = mock_logger
        mock_wrap_logger.return_value = mock_wrapped_logger
        
        # Act
        result = get_request_logger("test_logger")
        
        # Assert
        assert result == mock_wrapped_logger
        mock_get_logger.assert_called_once_with("test_logger")
        mock_wrap_logger.assert_called_once_with(
            mock_logger,
            processors=[prevent_logging_if_disabled, sanitize_logs]
        )


class TestEventProcessors:
    """Test cases for event processing functions."""

    def test_rename_event_key(self):
        """Test that rename_event_key moves 'event' to 'message'."""
        # Arrange
        event_dict = {"event": "test event", "level": "info"}
        
        # Act
        result = rename_event_key(None, None, event_dict)
        
        # Assert
        assert "event" not in result
        assert result["message"] == "test event"
        assert result["level"] == "info"

    def test_drop_color_message_key_removes_color_message(self):
        """Test that drop_color_message_key removes 'color_message' key."""
        # Arrange
        event_dict = {"message": "test", "color_message": "colored", "level": "info"}
        
        # Act
        result = drop_color_message_key(None, None, event_dict)
        
        # Assert
        assert "color_message" not in result
        assert result["message"] == "test"
        assert result["level"] == "info"

    def test_drop_color_message_key_handles_missing_key(self):
        """Test that drop_color_message_key handles missing 'color_message' key."""
        # Arrange
        event_dict = {"message": "test", "level": "info"}
        
        # Act
        result = drop_color_message_key(None, None, event_dict)
        
        # Assert
        assert result == event_dict

    def test_add_custom_keys(self):
        """Test that add_custom_keys adds required custom fields."""
        # Arrange
        event_dict = {"message": "test", "level": "info"}
        
        # Act
        result = add_custom_keys(None, None, event_dict)
        
        # Assert
        assert result["type"] == "mlops"
        assert result["stage"] == "main"
        assert result["message"] == "test"
        assert result["level"] == "info"


class TestIntegration:
    """Integration tests for structured logging functionality."""

    @patch('ai_gateway.structured_logging.get_config')
    def test_end_to_end_logging_enabled(self, mock_get_config):
        """Test end-to-end flow when logging is enabled."""
        # Arrange
        mock_config = Mock()
        mock_config.logging.enable_request_logging = True
        mock_get_config.return_value = mock_config
        
        event_dict = {
            "event": "test message",
            "api_key": "secret-123",
            "color_message": "colored"
        }
        
        # Act - simulate the processor chain
        result = event_dict.copy()
        result = prevent_logging_if_disabled(None, None, result)
        result = sanitize_logs(None, None, result)
        result = rename_event_key(None, None, result)
        result = drop_color_message_key(None, None, result)
        result = add_custom_keys(None, None, result)
        
        # Assert
        assert result["message"] == "test message"
        assert "event" not in result
        assert result["api_key"] == "**********"
        assert "color_message" not in result
        assert result["type"] == "mlops"
        assert result["stage"] == "main"

    @patch('ai_gateway.structured_logging.get_config')
    def test_end_to_end_logging_disabled(self, mock_get_config):
        """Test end-to-end flow when logging is disabled."""
        # Arrange
        mock_config = Mock()
        mock_config.logging.enable_request_logging = False
        mock_get_config.return_value = mock_config
        
        event_dict = {"event": "test message", "api_key": "secret-123"}
        
        # Act & Assert
        with patch('ai_gateway.structured_logging.enabled_instance_verbose_ai_logs', return_value=False), \
             patch('ai_gateway.structured_logging.is_feature_enabled', return_value=False), \
             patch('ai_gateway.structured_logging.CUSTOM_MODELS_ENABLED', False):
            
            with pytest.raises(structlog.DropEvent):
                prevent_logging_if_disabled(None, None, event_dict)
