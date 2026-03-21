"""Prompt template loader."""
from pathlib import Path

PROMPTS_DIR = Path(__file__).parent

def load_prompt(name: str, **kwargs: str) -> str:
    """Load a prompt template and fill in placeholders."""
    path = PROMPTS_DIR / f"{name}.md"
    template = path.read_text()
    return template.format(**kwargs)
