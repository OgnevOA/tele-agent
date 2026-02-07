"""System prompt builder from behavior documents."""

import re
from pathlib import Path
from typing import Optional


class PromptBuilder:
    """Builds system prompts from SOUL.md, IDENTITY.md, USER.md, TOOLS.md."""
    
    def __init__(self, paths_config):
        """Initialize with paths configuration."""
        self.paths = paths_config
        self._cached_prompt: Optional[str] = None
        self._identity_cache: Optional[dict] = None
    
    def _read_file(self, path: Path) -> Optional[str]:
        """Read a file if it exists."""
        if path.exists():
            try:
                return path.read_text(encoding="utf-8")
            except Exception:
                return None
        return None
    
    def _parse_identity(self, content: str) -> dict:
        """Parse IDENTITY.md to extract structured info."""
        identity = {}
        
        # Parse key-value pairs like "- **Name:** value"
        patterns = {
            "name": r"\*\*Name:\*\*\s*(.+)",
            "creature": r"\*\*Creature:\*\*\s*(.+)",
            "vibe": r"\*\*Vibe:\*\*\s*(.+)",
            "emoji": r"\*\*Emoji:\*\*\s*(.+)",
            "avatar": r"\*\*Avatar:\*\*\s*(.+)",
        }
        
        for key, pattern in patterns.items():
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                value = match.group(1).strip()
                # Skip placeholder text
                if not value.startswith("(") and value:
                    identity[key] = value
        
        return identity
    
    def build_system_prompt(self) -> str:
        """Build the complete system prompt from behavior documents."""
        if self._cached_prompt:
            return self._cached_prompt
        
        sections = []
        
        # Load SOUL.md - core personality
        soul = self._read_file(self.paths.soul_file)
        if soul:
            sections.append(f"# Your Soul\n{soul}")
        
        # Load IDENTITY.md - who you are
        identity = self._read_file(self.paths.identity_file)
        if identity:
            sections.append(f"# Your Identity\n{identity}")
            self._identity_cache = self._parse_identity(identity)
        
        # Load USER.md - about the user
        user = self._read_file(self.paths.user_file)
        if user:
            sections.append(f"# About Your Human\n{user}")
        
        # Load TOOLS.md - environment config
        tools = self._read_file(self.paths.tools_file)
        if tools:
            sections.append(f"# Your Environment\n{tools}")
        
        # Add skill execution context
        sections.append("""
# Your Capabilities

You have access to tools/skills that let you perform tasks. The tools are called automatically
when you decide to use them - just describe what you want to do.

**Important:** You have an `update_memory` tool to save information:
- Update IDENTITY.md with your chosen name, vibe, emoji
- Update USER.md with info you learn about your human
- Update TOOLS.md with environment-specific notes
- Create memory/YYYY-MM-DD.md files for daily notes
- Use action="append" with file="today" for quick timestamped notes

When you learn something worth remembering, USE the update_memory tool to save it!
Don't just say you'll remember - actually write it down.

Be helpful, be yourself, and remember: actions speak louder than words.
""")
        
        self._cached_prompt = "\n\n---\n\n".join(sections)
        return self._cached_prompt
    
    def get_identity(self) -> Optional[dict]:
        """Get parsed identity information."""
        if self._identity_cache is None:
            # Force build to populate cache
            self.build_system_prompt()
        return self._identity_cache
    
    def reload(self) -> str:
        """Clear cache and rebuild prompt."""
        self._cached_prompt = None
        self._identity_cache = None
        return self.build_system_prompt()
