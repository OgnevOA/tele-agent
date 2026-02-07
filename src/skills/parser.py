"""Markdown skill file parser."""

import re
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional
import frontmatter


@dataclass
class Skill:
    """Represents a parsed skill from a .md file."""
    
    title: str
    description: str
    dependencies: list[str]
    code: str
    file_path: Path
    
    # Metadata from frontmatter
    author: str = "unknown"
    created: str = ""
    
    # Runtime state
    enabled: bool = True
    
    @property
    def name(self) -> str:
        """Get skill name from file path."""
        return self.file_path.stem
    
    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "title": self.title,
            "name": self.name,
            "description": self.description,
            "dependencies": self.dependencies,
            "code": self.code,
            "file_path": str(self.file_path),
            "author": self.author,
            "created": self.created,
            "enabled": self.enabled,
        }


class SkillParser:
    """Parser for skill .md files."""
    
    # Regex patterns for extracting sections
    DESCRIPTION_PATTERN = re.compile(
        r"#\s*Description\s*\n(.*?)(?=\n#|\Z)",
        re.DOTALL | re.IGNORECASE
    )
    DEPENDENCIES_PATTERN = re.compile(
        r"#\s*Dependencies\s*\n(.*?)(?=\n#|\Z)",
        re.DOTALL | re.IGNORECASE
    )
    CODE_PATTERN = re.compile(
        r"```python\s*\n(.*?)```",
        re.DOTALL
    )
    
    def __init__(self, skills_dir: Path):
        self.skills_dir = Path(skills_dir)
        self._skills_cache: dict[str, Skill] = {}
    
    def parse_file(self, file_path: Path) -> Optional[Skill]:
        """Parse a single skill .md file."""
        try:
            # Read and parse frontmatter
            post = frontmatter.load(file_path)
            content = post.content
            metadata = post.metadata
            
            # Extract title from frontmatter or filename
            title = metadata.get("title", file_path.stem.replace("_", " ").title())
            author = metadata.get("author", "unknown")
            created = str(metadata.get("created", ""))
            
            # Extract description section
            description = ""
            desc_match = self.DESCRIPTION_PATTERN.search(content)
            if desc_match:
                description = desc_match.group(1).strip()
            
            # Extract dependencies
            dependencies = []
            deps_match = self.DEPENDENCIES_PATTERN.search(content)
            if deps_match:
                deps_text = deps_match.group(1).strip()
                # Parse as list items (- item or * item)
                for line in deps_text.split("\n"):
                    line = line.strip()
                    if line.startswith(("-", "*")):
                        dep = line.lstrip("-* ").strip()
                        if dep:
                            dependencies.append(dep)
            
            # Extract code block
            code = ""
            code_match = self.CODE_PATTERN.search(content)
            if code_match:
                code = code_match.group(1).strip()
            
            if not code:
                return None  # No valid code block found
            
            return Skill(
                title=title,
                description=description,
                dependencies=dependencies,
                code=code,
                file_path=file_path,
                author=author,
                created=created,
            )
            
        except Exception as e:
            print(f"Error parsing skill file {file_path}: {e}")
            return None
    
    def load_all_skills(self) -> list[Skill]:
        """Load all skills from the skills directory."""
        self._skills_cache.clear()
        skills = []
        
        if not self.skills_dir.exists():
            return skills
        
        for md_file in self.skills_dir.glob("*.md"):
            skill = self.parse_file(md_file)
            if skill:
                self._skills_cache[skill.name] = skill
                skills.append(skill)
        
        return skills
    
    def get_skill(self, name: str) -> Optional[Skill]:
        """Get a skill by name from cache."""
        return self._skills_cache.get(name)
    
    def reload_skill(self, name: str) -> Optional[Skill]:
        """Reload a specific skill from disk."""
        file_path = self.skills_dir / f"{name}.md"
        if file_path.exists():
            skill = self.parse_file(file_path)
            if skill:
                self._skills_cache[name] = skill
                return skill
        return None
    
    def save_skill(self, skill: Skill) -> bool:
        """Save a skill to disk as a .md file."""
        try:
            # Build the markdown content
            content = f"""---
title: {skill.title}
author: {skill.author}
created: {skill.created}
---

# Description
{skill.description}

# Dependencies
{chr(10).join(f'- {dep}' for dep in skill.dependencies) if skill.dependencies else ''}

# Code
```python
{skill.code}
```
"""
            # Write to file
            file_path = self.skills_dir / f"{skill.name}.md"
            file_path.write_text(content, encoding="utf-8")
            
            # Update cache
            self._skills_cache[skill.name] = skill
            
            return True
            
        except Exception as e:
            print(f"Error saving skill {skill.name}: {e}")
            return False
    
    @property
    def skills(self) -> dict[str, Skill]:
        """Get all cached skills."""
        return self._skills_cache
