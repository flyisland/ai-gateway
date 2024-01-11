import pytest

from ai_gateway.code_suggestions.processing.base import LanguageId
from ai_gateway.prompts.parsers import CodeParser, CodeParsingError


@pytest.mark.asyncio
@pytest.mark.parametrize("lang_id", [None])
async def test_unsupported_languages(lang_id: LanguageId):
    with pytest.raises(ValueError) as exception:
        _ = await CodeParser.from_language_id("import Foundation", lang_id)

    assert str(exception.value) == "Unsupported language: None"


@pytest.mark.asyncio
async def test_non_utf8():
    value = b"\xc3\x28"  # Invalid UTF-8 byte sequence

    with pytest.raises(CodeParsingError) as exception:
        _ = await CodeParser.from_language_id(value, LanguageId.JS)

    assert (
        str(exception.value)
        == "Failed to parse code content: encoding without a string argument"
    )


@pytest.mark.asyncio
async def test_parse_timeout():
    value = "\n".join(["def foo():"] * 100)

    with pytest.raises(CodeParsingError) as exception:
        _ = await CodeParser.from_language_id(
            value, LanguageId.JS, parse_timeout_micros=1
        )

    assert str(exception.value) == "Failed to parse code content: Parsing failed"
