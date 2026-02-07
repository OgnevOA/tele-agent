"""LLM-based skill file generator."""

import logging
import re
from datetime import datetime
from typing import Optional

from src.llm.manager import ProviderManager
from .parser import Skill
from .executor import SkillExecutor

logger = logging.getLogger(__name__)


class SkillGenerator:
    """Generate skill files using LLM based on user instructions."""
    
    GENERATION_PROMPT = """You are a Python skill generator. Create a skill based on the user's request.

CRITICAL REQUIREMENTS:
1. Include ALL necessary imports at the TOP of the code (os, sys, json, datetime, requests, etc.)
2. Have a main function called `execute()` with optional parameters that have defaults
3. Return a string result (always return a string, never None)
4. Handle errors gracefully with try/except
5. Be completely self-contained

Original request: {original_request}

User's teaching:
{teaching_context}

Generate ONLY the Python code. Start with imports, then define the execute function.
Do NOT include markdown code fences or explanations.

Common imports you might need:
- import os (for file/path operations)
- import subprocess (for shell commands)
- import json (for JSON parsing)
- import requests (for HTTP requests)
- from datetime import datetime (for dates/times)

Example format:
import os
import json

def execute(param1="default"):
    try:
        # implementation
        return "result string"
    except Exception as e:
        return f"Error: {{e}}"

Your code (start with imports):"""

    SKILL_NAME_PROMPT = """Given this task description, generate a short snake_case skill name (2-4 words).

Task: {task}

Reply with only the skill name, like: check_weather or get_crypto_price"""

    def __init__(self, provider_manager: ProviderManager):
        """Initialize skill generator.
        
        Args:
            provider_manager: LLM provider manager.
        """
        self.provider_manager = provider_manager
        self.executor = SkillExecutor(timeout=30)
    
    async def generate_skill(
        self,
        original_request: str,
        teaching_context: list[dict],
    ) -> Optional[Skill]:
        """Generate a new skill from user instructions.
        
        Args:
            original_request: The original user request.
            teaching_context: List of teaching messages.
        
        Returns:
            Generated Skill object or None if generation failed.
        """
        provider = self.provider_manager.get_active()
        
        # Format teaching context
        context_text = ""
        for msg in teaching_context:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            context_text += f"{role.title()}: {content}\n"
        
        # Generate code
        prompt = self.GENERATION_PROMPT.format(
            original_request=original_request,
            teaching_context=context_text,
        )
        
        try:
            response = await provider.generate([
                {"role": "system", "content": "You are an expert Python developer. Generate clean, working code."},
                {"role": "user", "content": prompt},
            ])
            
            # Extract code from response
            code = self._extract_code(response)
            
            if not code:
                logger.error("No code extracted from response")
                return None
            
            # Validate code
            is_valid, error = self.executor.validate_code(code)
            if not is_valid:
                logger.error(f"Generated code validation failed: {error}")
                return None
            
            # Generate skill name
            skill_name = await self._generate_skill_name(original_request)
            
            # Extract dependencies from imports
            dependencies = self._extract_dependencies(code)
            
            # Create skill object
            from pathlib import Path
            skill = Skill(
                title=skill_name.replace("_", " ").title(),
                description=original_request,
                dependencies=dependencies,
                code=code,
                file_path=Path(f"skills/{skill_name}.md"),
                author="user",
                created=datetime.now().strftime("%Y-%m-%d"),
            )
            
            return skill
            
        except Exception as e:
            logger.error(f"Skill generation error: {e}")
            return None
    
    async def improve_skill(
        self,
        skill: Skill,
        error: str,
        user_feedback: str,
    ) -> Optional[Skill]:
        """Improve a skill based on error and user feedback.
        
        Args:
            skill: The skill to improve.
            error: The error that occurred.
            user_feedback: User's feedback/suggestions.
        
        Returns:
            Improved Skill object or None.
        """
        provider = self.provider_manager.get_active()
        
        prompt = f"""The following Python skill code has an error. Fix it based on the error and user feedback.

Current code:
```python
{skill.code}
```

Error:
{error}

User feedback:
{user_feedback}

Generate the corrected code only, no explanation."""

        try:
            response = await provider.generate([
                {"role": "system", "content": "You are an expert Python developer. Fix the code."},
                {"role": "user", "content": prompt},
            ])
            
            code = self._extract_code(response)
            
            if not code:
                return None
            
            # Validate
            is_valid, error = self.executor.validate_code(code)
            if not is_valid:
                return None
            
            # Create improved skill
            improved = Skill(
                title=skill.title,
                description=skill.description,
                dependencies=self._extract_dependencies(code),
                code=code,
                file_path=skill.file_path,
                author=skill.author,
                created=skill.created,
            )
            
            return improved
            
        except Exception as e:
            logger.error(f"Skill improvement error: {e}")
            return None
    
    async def _generate_skill_name(self, task: str) -> str:
        """Generate a skill name from task description."""
        provider = self.provider_manager.get_active()
        
        prompt = self.SKILL_NAME_PROMPT.format(task=task)
        
        try:
            response = await provider.generate([
                {"role": "system", "content": "Reply with only the skill name."},
                {"role": "user", "content": prompt},
            ])
            
            # Clean and validate the name
            name = response.strip().lower()
            name = re.sub(r'[^a-z0-9_]', '_', name)
            name = re.sub(r'_+', '_', name).strip('_')
            
            if not name:
                name = "new_skill"
            
            return name
            
        except Exception:
            return "new_skill"
    
    def _extract_code(self, response: str) -> Optional[str]:
        """Extract Python code from LLM response."""
        # Try to find code block
        code_pattern = re.compile(r'```(?:python)?\s*\n(.*?)```', re.DOTALL)
        match = code_pattern.search(response)
        
        if match:
            return match.group(1).strip()
        
        # If no code block, try to find the code directly
        # Look for import or def statements
        lines = response.strip().split('\n')
        code_lines = []
        in_code = False
        
        for line in lines:
            if line.strip().startswith(('import ', 'from ', 'def ')):
                in_code = True
            if in_code:
                code_lines.append(line)
        
        if code_lines:
            return '\n'.join(code_lines)
        
        return None
    
    def _extract_dependencies(self, code: str) -> list[str]:
        """Extract pip package dependencies from code imports."""
        dependencies = []
        
        # Common import patterns
        import_pattern = re.compile(r'^(?:import|from)\s+(\w+)', re.MULTILINE)
        
        # Standard library modules to exclude
        stdlib = {
            'os', 'sys', 'json', 'datetime', 'time', 're', 'math',
            'random', 'urllib', 'base64', 'hashlib', 'io', 'pathlib',
            'typing', 'collections', 'itertools', 'functools',
            'subprocess', 'shutil', 'glob', 'tempfile', 'shlex',
            'platform', 'socket', 'http', 'email', 'html', 'xml',
        }
        
        for match in import_pattern.finditer(code):
            module = match.group(1)
            if module not in stdlib:
                dependencies.append(module)
        
        return list(set(dependencies))
