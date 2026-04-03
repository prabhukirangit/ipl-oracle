"""
Robust JSON parser for LLM outputs.

LLMs frequently return JSON with trailing commas, // comments,
markdown fences, or surrounding prose. This module handles all
of those without pulling in a heavy dependency.
"""

from __future__ import annotations

import json
import re


def parse_llm_json(raw: str) -> dict:
    """
    Parse LLM output as JSON, tolerating common quirks:
      - Markdown fences (```json ... ```)
      - Trailing commas before } or ]
      - Single-line // comments
      - Explanatory text before/after the JSON block
    """
    text = raw.strip()

    # Strip markdown fences
    if "```" in text:
        m = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
        if m:
            text = m.group(1).strip()

    # If no fences, extract the outermost { ... }
    if not text.startswith("{"):
        m = re.search(r"\{[\s\S]*\}", text)
        if m:
            text = m.group(0)

    # Remove single-line // comments (not inside quoted strings)
    text = re.sub(r'(?<!["\w])//[^\n]*', "", text)

    # Remove trailing commas before } or ]
    text = re.sub(r",\s*([}\]])", r"\1", text)

    return json.loads(text)
