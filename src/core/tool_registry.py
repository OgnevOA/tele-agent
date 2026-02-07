"""Tool registry for converting skills to LLM tool definitions."""

import re
import ast
import logging
from typing import Optional, Any
from dataclasses import dataclass

from src.skills.parser import Skill, SkillParser
from src.llm.base import ToolDefinition

logger = logging.getLogger(__name__)


@dataclass
class ParameterInfo:
    """Information about a function parameter."""
    name: str
    type_hint: str
    default: Any
    has_default: bool
    description: str = ""


class ToolRegistry:
    """Converts skills to tool definitions for LLM function calling."""
    
    # Python type to JSON Schema type mapping
    TYPE_MAP = {
        "str": "string",
        "int": "integer",
        "float": "number",
        "bool": "boolean",
        "list": "array",
        "dict": "object",
        "None": "null",
    }
    
    def __init__(self, skill_parser: SkillParser):
        """Initialize tool registry.
        
        Args:
            skill_parser: Parser for loading skills.
        """
        self.skill_parser = skill_parser
        self._tools_cache: dict[str, ToolDefinition] = {}
    
    def _parse_function_signature(self, code: str) -> list[ParameterInfo]:
        """Parse the execute() function signature to extract parameters."""
        params = []
        
        try:
            # Parse the code as AST
            tree = ast.parse(code)
            
            # Find the execute function
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef) and node.name == "execute":
                    # Process arguments
                    args = node.args
                    
                    # Calculate defaults offset
                    num_defaults = len(args.defaults)
                    num_args = len(args.args)
                    defaults_start = num_args - num_defaults
                    
                    for i, arg in enumerate(args.args):
                        # Skip 'self' if present
                        if arg.arg == "self":
                            continue
                        
                        # Get type hint
                        type_hint = "str"  # Default to string
                        if arg.annotation:
                            type_hint = ast.unparse(arg.annotation)
                        
                        # Check for default value
                        has_default = i >= defaults_start
                        default = None
                        if has_default:
                            default_node = args.defaults[i - defaults_start]
                            try:
                                default = ast.literal_eval(ast.unparse(default_node))
                            except:
                                default = ast.unparse(default_node)
                        
                        params.append(ParameterInfo(
                            name=arg.arg,
                            type_hint=type_hint,
                            default=default,
                            has_default=has_default,
                        ))
                    break
                    
        except Exception as e:
            logger.warning(f"Failed to parse function signature: {e}")
        
        return params
    
    def _python_type_to_json_schema(self, python_type: str) -> str:
        """Convert Python type hint to JSON Schema type."""
        # Handle common type hints
        python_type = python_type.strip()
        
        # Check direct mapping
        if python_type in self.TYPE_MAP:
            return self.TYPE_MAP[python_type]
        
        # Handle Optional[X] -> X
        if python_type.startswith("Optional["):
            inner = python_type[9:-1]
            return self._python_type_to_json_schema(inner)
        
        # Handle list[X] -> array
        if python_type.startswith("list[") or python_type.startswith("List["):
            return "array"
        
        # Handle dict types -> object
        if python_type.startswith("dict[") or python_type.startswith("Dict["):
            return "object"
        
        # Default to string
        return "string"
    
    def skill_to_tool_definition(self, skill: Skill) -> ToolDefinition:
        """Convert a skill to a tool definition.
        
        Args:
            skill: The skill to convert.
        
        Returns:
            ToolDefinition for the LLM.
        """
        # Parse function parameters
        params = self._parse_function_signature(skill.code)
        
        # Build JSON Schema for parameters
        properties = {}
        required = []
        
        for param in params:
            json_type = self._python_type_to_json_schema(param.type_hint)
            
            prop = {
                "type": json_type,
                "description": param.description or f"Parameter: {param.name}",
            }
            
            # Add default if present
            if param.has_default and param.default is not None:
                prop["default"] = param.default
            
            properties[param.name] = prop
            
            # Required if no default
            if not param.has_default:
                required.append(param.name)
        
        parameters_schema = {
            "type": "object",
            "properties": properties,
        }
        if required:
            parameters_schema["required"] = required
        
        # Create tool definition
        tool = ToolDefinition(
            name=skill.name,
            description=skill.description or skill.title,
            parameters=parameters_schema,
        )
        
        return tool
    
    def get_all_tool_definitions(self) -> list[ToolDefinition]:
        """Get tool definitions for all enabled skills.
        
        Returns:
            List of ToolDefinition objects.
        """
        tools = []
        
        for name, skill in self.skill_parser.skills.items():
            if not skill.enabled:
                continue
            
            try:
                # Check cache
                if name in self._tools_cache:
                    tools.append(self._tools_cache[name])
                    continue
                
                # Convert skill to tool
                tool = self.skill_to_tool_definition(skill)
                self._tools_cache[name] = tool
                tools.append(tool)
                
            except Exception as e:
                logger.warning(f"Failed to convert skill '{name}' to tool: {e}")
        
        return tools
    
    def get_tool_definition(self, skill_name: str) -> Optional[ToolDefinition]:
        """Get tool definition for a specific skill.
        
        Args:
            skill_name: Name of the skill.
        
        Returns:
            ToolDefinition or None if not found.
        """
        if skill_name in self._tools_cache:
            return self._tools_cache[skill_name]
        
        skill = self.skill_parser.get_skill(skill_name)
        if skill and skill.enabled:
            tool = self.skill_to_tool_definition(skill)
            self._tools_cache[skill_name] = tool
            return tool
        
        return None
    
    def clear_cache(self):
        """Clear the tool definition cache."""
        self._tools_cache.clear()
    
    def refresh(self):
        """Reload skills and rebuild tool definitions."""
        self.clear_cache()
        self.skill_parser.load_all_skills()
