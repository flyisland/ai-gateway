"""Utility functions for loading tool prompts from JSON files."""

import json
import os
from pathlib import Path

def load_tool_prompt(tool_name: str) -> dict:
    """
    Load a tool prompt from a JSON file.
    
    Args:
        tool_name: The name of the tool to load the prompt for.
        
    Returns:
        A dictionary containing the tool's prompt data.
        
    Raises:
        FileNotFoundError: If the prompt file does not exist.
    """
    base_dir = Path(__file__).parent.parent.parent
    prompt_path = base_dir / "prompts" / "definitions" / "duo_chat_tools" / f"{tool_name}.json"
    
    with open(prompt_path, 'r', encoding='utf-8') as f:
        return json.load(f)