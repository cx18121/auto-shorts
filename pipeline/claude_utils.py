"""
pipeline/claude_utils.py — Shared Claude/JSON helpers used across formats.

Public API:
    parse_json(text)              -> Any      (strips markdown fences, parses JSON)
    strip_markdown_fences(text)   -> str      (strips ```json ... ``` wrapper if present)
"""

import json
from typing import Any


def strip_markdown_fences(text: str) -> str:
    """Strip markdown code fences from a string if present.

    Claude sometimes wraps JSON output in ```json ... ``` fences despite
    being instructed not to. This normalises the output before parsing.
    """
    text = text.strip()
    if text.startswith("```"):
        parts = text.split("```")
        text = parts[1] if len(parts) > 1 else text
        if text.startswith("json"):
            text = text[4:]
    return text.strip()


def parse_json(text: str) -> Any:
    """Strip markdown fences and parse JSON. Raises json.JSONDecodeError on failure."""
    return json.loads(strip_markdown_fences(text))
