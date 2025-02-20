import pytest

from ai_gateway.code_suggestions.base import resolve_lang_name


class TestBase:
    @pytest.mark.parametrize(
        "file_name, expected_result, expected_exception",
        [
            ("example.py", "python", None),
            ("", None, None),
            ("invalid_filename", None, None),
            ("file.unsupported", None, None),
        ],
    )
    def test_resolve_lang_name(self, file_name, expected_result, expected_exception):
        """Test resolve_lang_name with various inputs"""
        if expected_exception:
            with pytest.raises(expected_exception):
                resolve_lang_name(file_name)
        else:
            result = resolve_lang_name(file_name)
            assert (
                result == expected_result
            ), f"Expected {expected_result}, but got {result}"
