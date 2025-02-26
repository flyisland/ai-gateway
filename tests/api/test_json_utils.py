import pytest

from ai_gateway.api.json_utils import JsonProcessor


class TestJsonUtils:

    @pytest.mark.parametrize(
        "input_dict, expected_result",
        [
            (
                {"key1": "value1", "key2": None, "key3": "value3"},
                {"key1": "value1", "key3": "value3"},
            ),
            ({"a": None, "b": None, "c": None}, {}),
            ({}, {}),
        ],
    )
    def test_process_dict_with_null_values(self, input_dict, expected_result):
        """Test _process_dict method with various null value scenarios when ignore_null is True"""
        processor = JsonProcessor(ignore_null=True)
        result = processor._process_dict(input_dict)
        assert result == expected_result

    @pytest.mark.parametrize(
        "exclude_fields, input_data, expected_output",
        [
            (
                ["exclude_me"],
                {
                    "exclude_me": "should be excluded",
                    "include_me": "should be included",
                    "nested": {"key": "value"},
                },
                {"include_me": "should be included", "nested": {"key": "value"}},
            ),
            (["a", "b", "c"], {"a": 1, "b": 2, "c": 3}, {}),
            (
                ["exclude_me"],
                {
                    "exclude_me": "should not appear",
                    "null_value": None,
                    "keep_me": "should appear",
                },
                {"keep_me": "should appear"},
            ),
        ],
    )
    def test_process_dict_with_exclude_fields(
        self, exclude_fields, input_data, expected_output
    ):
        """Test _process_dict with various exclude field scenarios"""
        processor = JsonProcessor(exclude_fields=exclude_fields, ignore_null=True)
        result = processor._process_dict(input_data)
        assert result == expected_output

    @pytest.mark.parametrize(
        "invalid_input, expected_exception",
        [
            ("not a dictionary", AttributeError),
            (None, AttributeError),
            ({"key": set()}, TypeError),  # sets are not JSON serializable
        ],
    )
    def test_process_dict_invalid_inputs(self, invalid_input, expected_exception):
        """Test _process_dict with various invalid inputs"""
        processor = JsonProcessor()
        with pytest.raises(expected_exception):
            processor._process_dict(invalid_input)

    @pytest.mark.parametrize(
        "field, expected_type_error",
        [(123, True), (None, True), ("valid_field", False), ("", False)],
    )
    def test_add_exclude_field_validation(self, field, expected_type_error):
        """Test add_exclude_field with various inputs"""
        processor = JsonProcessor()
        if expected_type_error:
            with pytest.raises(TypeError):
                processor.add_exclude_field(field)
        else:
            processor.add_exclude_field(field)
            assert field in processor.exclude_fields

    @pytest.mark.parametrize(
        "primitive_input, expected",
        [(42, 42), ("hello", "hello"), (True, True), (None, None)],
    )
    def test_process_primitive_data(self, primitive_input, expected):
        """Test process method with primitive data types"""
        processor = JsonProcessor()
        assert processor.process(primitive_input) == expected
