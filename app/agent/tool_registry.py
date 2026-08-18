"""
DevPilot Tool Registry and Tool Definition.

Manages tool registration, input schema validation, and safe tool execution.
"""

from dataclasses import dataclass, field
import inspect
from typing import Any, Callable, Dict, List, Optional


class ToolValidationError(Exception):
    """Raised when tool arguments fail schema validation."""
    pass


@dataclass
class Tool:
    """
    Representation of a registered read-only codebase tool.
    """
    name: str
    description: str
    parameters: Dict[str, Any]
    func: Callable[..., Any]
    safety_level: str = "read_only"

    def to_tool_spec(self) -> Dict[str, Any]:
        """Returns the OpenAI/Groq function calling JSON definition."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class ToolRegistry:
    """
    Central registry for available AI agent tools.
    Enforces validation and prevents execution of unregistered or unsafe code.
    """

    def __init__(self):
        self._tools: Dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """Registers a tool with the registry."""
        if not isinstance(tool, Tool):
            raise TypeError(f"Expected Tool instance, got {type(tool).__name__}")
        if not tool.name or not tool.name.strip():
            raise ValueError("Tool name cannot be empty.")
        if tool.safety_level != "read_only":
            raise ValueError(f"Only read_only tools are permitted, got {tool.safety_level}")
        self._tools[tool.name] = tool

    def get(self, name: str) -> Optional[Tool]:
        """Retrieves a registered tool by name."""
        return self._tools.get(name)

    def list_tools(self) -> List[Tool]:
        """Returns list of all registered tools."""
        return list(self._tools.values())

    def get_tool_specs(self) -> List[Dict[str, Any]]:
        """Returns tool specs formatted for LLM function calling."""
        return [tool.to_tool_spec() for tool in self._tools.values()]

    def validate_arguments(self, tool: Tool, arguments: Dict[str, Any]) -> None:
        """
        Validates arguments against the tool's JSON schema parameter definition.
        """
        if not isinstance(arguments, dict):
            raise ToolValidationError(f"Tool arguments must be a dictionary, got {type(arguments).__name__}")

        schema = tool.parameters
        required_fields = schema.get("required", [])
        properties = schema.get("properties", {})

        # Check required fields
        for field_name in required_fields:
            if field_name not in arguments:
                raise ToolValidationError(f"Missing required parameter '{field_name}' for tool '{tool.name}'")

        # Type validation where specified in schema
        for key, value in arguments.items():
            if key not in properties:
                continue
            prop_def = properties[key]
            prop_type = prop_def.get("type")

            if prop_type == "string" and not isinstance(value, str):
                raise ToolValidationError(f"Parameter '{key}' must be a string, got {type(value).__name__}")
            elif prop_type == "integer" and (not isinstance(value, int) or isinstance(value, bool)):
                raise ToolValidationError(f"Parameter '{key}' must be an integer, got {type(value).__name__}")
            elif prop_type == "number" and not isinstance(value, (int, float)):
                raise ToolValidationError(f"Parameter '{key}' must be a number, got {type(value).__name__}")
            elif prop_type == "boolean" and not isinstance(value, bool):
                raise ToolValidationError(f"Parameter '{key}' must be a boolean, got {type(value).__name__}")
            elif prop_type == "array" and not isinstance(value, list):
                raise ToolValidationError(f"Parameter '{key}' must be a list, got {type(value).__name__}")

            # Specific numeric constraints
            if prop_type == "integer" and "minimum" in prop_def:
                if value < prop_def["minimum"]:
                    raise ToolValidationError(
                        f"Parameter '{key}' must be >= {prop_def['minimum']}, got {value}"
                    )

    def execute(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Safely executes a registered tool with argument validation.

        Returns a dictionary:
            {
                "success": bool,
                "tool": name,
                "data": ...,
                "sources": List[Dict[str, Any]],
                "error": Optional[str]
            }
        """
        tool = self.get(name)
        if not tool:
            return {
                "success": False,
                "tool": name,
                "data": None,
                "sources": [],
                "error": f"Unknown tool '{name}'. Available tools: {list(self._tools.keys())}",
            }

        try:
            self.validate_arguments(tool, arguments)
            result = tool.func(**arguments)

            if isinstance(result, dict) and "sources" in result:
                sources = result.get("sources", [])
                data = result.get("data", result)
            else:
                sources = []
                data = result

            return {
                "success": True,
                "tool": name,
                "data": data,
                "sources": sources,
                "error": None,
            }
        except ToolValidationError as e:
            return {
                "success": False,
                "tool": name,
                "data": None,
                "sources": [],
                "error": f"Validation error for '{name}': {e}",
            }
        except Exception as e:
            return {
                "success": False,
                "tool": name,
                "data": None,
                "sources": [],
                "error": f"Error executing tool '{name}': {str(e)}",
            }
