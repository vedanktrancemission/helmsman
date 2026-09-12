"""LLMResult.text must be a str for every provider.

Gemini 3.x returns a list of content blocks rather than a plain string, and
nodes._parse_tool_call regex-matches the text, so a list leaks a TypeError
into the agent loop.
"""
from app.runtime.llm import _content_to_text
from app.runtime.nodes import _parse_tool_call


def test_plain_string_passes_through():
    assert _content_to_text("hello") == "hello"


def test_gemini_block_list_is_flattened():
    blocks = [{"type": "text", "text": 'CALL calculator {"expr": "2+2"}',
               "extras": {"signature": "abc"}}]
    assert _content_to_text(blocks) == 'CALL calculator {"expr": "2+2"}'


def test_non_text_blocks_are_dropped():
    blocks = [
        {"type": "thinking", "thinking": "internal"},
        {"type": "text", "text": "visible"},
    ]
    assert _content_to_text(blocks) == "visible"


def test_bare_strings_in_list():
    assert _content_to_text(["a", "b"]) == "ab"


def test_none_becomes_empty_string():
    assert _content_to_text(None) == ""


def test_flattened_gemini_output_parses_as_tool_call():
    blocks = [{"type": "text", "text": 'CALL calculator {"expr": "240000/12"}',
               "extras": {"signature": "sig"}}]
    assert _parse_tool_call(_content_to_text(blocks)) == (
        "calculator", {"expr": "240000/12"},
    )
