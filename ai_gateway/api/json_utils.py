import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


class JsonProcessingError(Exception):
    """Custom exception for JSON processing errors"""

    def __init__(self, message: str):
        self.message = message
        super().__init__(self.message)


@dataclass
class JsonProcessor:
    exclude_fields: List[str] = None
    ignore_null: bool = False

    def __post_init__(self):
        self.exclude_fields = self.exclude_fields or []

    def process(self, data: Any) -> Any:
        """
        Process JSON data recursively based on configuration

        Args:
            data: Input data to process (can be dict, list, or primitive types)

        Returns:
            Processed data with applied configurations
        """
        if isinstance(data, dict):
            return self._process_dict(data)
        if isinstance(data, list):
            return self._process_list(data)
        return data

    def add_exclude_field(self, field: str) -> None:
        """Add a field to exclude list"""
        if not isinstance(field, str):
            raise TypeError("Field must be a string")
        if field not in self.exclude_fields:
            self.exclude_fields.append(field)

    def remove_exclude_field(self, field: str) -> None:
        """Remove a field from exclude list"""
        if not isinstance(field, str):
            raise TypeError("Field must be a string")
        if field in self.exclude_fields:
            self.exclude_fields.remove(field)

    def set_ignore_null(self, ignore: bool) -> None:
        """Update ignore_null setting"""
        self.ignore_null = ignore

    def _process_dict(self, data: Dict) -> Dict:
        """Process dictionary objects"""
        result = {}
        if not isinstance(data, dict):
            raise AttributeError("Input must be a dictionary")
        for key, value in data.items():
            # Skip if key is in exclude list
            if key in self.exclude_fields:
                continue

            # Skip null values if ignore_null is True
            if self.ignore_null and value is None:
                continue

            # Recursively process nested structures
            processed_value = self.process(value)
            # Test if the value is JSON serializable
            json.dumps(processed_value)
            result[key] = processed_value

        return result

    def _process_list(self, data: List) -> List:
        """Process list objects"""
        return [self.process(item) for item in data]


def process_json(
    data: Dict, exclude_fields: Optional[List[str]] = None, ignore_null: bool = False
) -> Dict:
    """
    Convenience function to process JSON data

    Args:
        data: Input JSON data as dictionary
        exclude_fields: List of field names to exclude
        ignore_null: Whether to ignore null values

    Returns:
        Processed JSON data
    """
    processor = JsonProcessor(exclude_fields=exclude_fields, ignore_null=ignore_null)
    return processor.process(data)


def safe_process_json(
    data: Dict, exclude_fields: Optional[List[str]] = None, ignore_null: bool = False
) -> Dict:
    """
    Safely process JSON data with error handling
    """
    try:
        return process_json(data, exclude_fields, ignore_null)
    except (TypeError, ValueError) as e:
        raise JsonProcessingError(f"Error processing JSON: {str(e)}")
    except Exception as e:
        raise JsonProcessingError(f"Unexpected error: {str(e)}")
