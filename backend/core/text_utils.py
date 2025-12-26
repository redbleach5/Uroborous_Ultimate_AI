"""
Text processing utilities for code extraction and manipulation
"""

import re
from typing import Optional, List, Tuple


def extract_code_from_markdown(text: str, preferred_language: Optional[str] = None) -> str:
    """
    Extract code from markdown code blocks.
    
    Args:
        text: Text potentially containing markdown code blocks
        preferred_language: If specified, prefer blocks with this language tag
        
    Returns:
        Extracted code (largest block if multiple), or original text if no blocks found
    """
    if "```" not in text:
        return text
    
    # Try regex first for better handling of multi-line code blocks
    code_block_pattern = r'```(\w+)?\s*\n?([\s\S]*?)```'
    matches = re.findall(code_block_pattern, text)
    
    if matches:
        # If preferred_language specified, try to find matching block first
        if preferred_language:
            for lang, code in matches:
                if lang and lang.lower() == preferred_language.lower():
                    return code.strip()
        
        # Get the largest code block (likely the main code)
        largest_code = max((code for _, code in matches), key=len)
        return largest_code.strip()
    
    # Fallback to line-by-line extraction
    lines = text.split("\n")
    code_lines = []
    in_code_block = False
    
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code_block = not in_code_block
            continue
        if in_code_block:
            code_lines.append(line)
    
    if code_lines:
        return "\n".join(code_lines)
    
    return text


def extract_all_code_blocks(text: str) -> List[Tuple[Optional[str], str]]:
    """
    Extract all code blocks from markdown.
    
    Args:
        text: Text containing markdown code blocks
        
    Returns:
        List of (language, code) tuples
    """
    if "```" not in text:
        return []
    
    code_block_pattern = r'```(\w+)?\s*\n?([\s\S]*?)```'
    matches = re.findall(code_block_pattern, text)
    
    return [(lang if lang else None, code.strip()) for lang, code in matches]


def detect_language_from_task(task: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Detect programming language from task description using heuristics.
    Also detects visual/web projects that should use HTML/CSS/JS.
    
    Args:
        task: Task description text
        
    Returns:
        Tuple of (language, matched_alias) or (None, None) if not detected
    """
    text_lower = task.lower()
    
    # First check for explicit visual/web indicators → HTML/CSS/JS
    visual_indicators = [
        "неоновый", "neon", "стиль", "дизайн", "интерфейс", "ui", 
        "веб", "web", "сайт", "site", "страниц", "page", "браузер", "browser",
        "html", "css", "анимац", "animat", "красив", "визуал",
        "кнопк", "button", "форм", "form", "меню", "menu"
    ]
    
    # Games with visual style should be HTML/CSS/JS
    is_visual_game = ("игр" in text_lower or "game" in text_lower) and any(
        ind in text_lower for ind in ["неоновый", "neon", "стиль", "красив", "визуал", "3d", "2d", "график", "graphic"]
    )
    
    if is_visual_game or any(ind in text_lower for ind in visual_indicators):
        # Check it's not explicitly asking for another language
        explicit_langs = ["python", "питон", "py ", "java ", "c++", "c#", "rust", "go ", "golang"]
        if not any(lang in text_lower for lang in explicit_langs):
            return "html", "visual/web project"
    
    # Language detection map
    lang_map = {
        "python": ["python", "питон", "py"],
        "javascript": ["javascript", "js", "жс"],
        "typescript": ["typescript", "ts"],
        "html": ["html", "css", "веб-страниц", "webpage"],
        "go": ["go", "golang", "го", "голанг"],
        "java": ["java", "ява"],
        "c#": ["c#", "c sharp", "c-шарп", "си шарп"],
        "c++": ["c++", "c plus plus", "cpp", "си плюс плюс"],
        "rust": ["rust", "раст"],
        "kotlin": ["kotlin", "котлин"],
        "swift": ["swift", "свифт"],
        "php": ["php"],
        "ruby": ["ruby", "руби"],
        "dart": ["dart"],
        "elixir": ["elixir"],
        "scala": ["scala"],
        "haskell": ["haskell"],
        "lua": ["lua", "луа"],
        "bash": ["bash", "sh", "shell", "bash-скрипт"],
        "r": [" r ", " r\n", " r\t"],
        "matlab": ["matlab"],
        "julia": ["julia"],
        "sql": ["sql"],
    }
    
    text = f" {text_lower} "
    for lang, aliases in lang_map.items():
        for alias in aliases:
            if f" {alias} " in text:
                return lang, alias
    
    return None, None


def truncate_text(text: str, max_length: int, suffix: str = "...") -> str:
    """
    Truncate text to max_length, adding suffix if truncated.
    
    Args:
        text: Text to truncate
        max_length: Maximum length including suffix
        suffix: Suffix to add when truncated
        
    Returns:
        Truncated text
    """
    if len(text) <= max_length:
        return text
    return text[:max_length - len(suffix)] + suffix

