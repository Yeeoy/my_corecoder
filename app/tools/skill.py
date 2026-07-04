import time

from app.skills import SkillManager
from app.tools.base import Tool, ToolResult


class SkillTool(Tool):
    """Read the full SKILL.md file for a named skill."""

    name = "read_skill"
    description = "Read the full SKILL.md instruction file for a specific skill."
    parameters = {
        "type": "object",
        "properties": {
            "skill_name": {
                "type": "string",
                "description": "need to get the specific skill content",
            },
        },
        "required": ["skill_name"],
    }

    def __init__(self, skill_manager: SkillManager):
        self.skill_manager = skill_manager

    def execute(self, skill_name: str) -> ToolResult:
        start = time.perf_counter()
        try:
            result = self.skill_manager.read_skill(skill_name)
            return ToolResult(
                ok=True,
                content=result,
                error=None,
                metadata={
                    "tool": self.name,
                    "skill_name": skill_name,
                    "duration_ms": int((time.perf_counter() - start) * 1000),
                },
            )
        except Exception as e:
            return ToolResult(
                ok=False,
                content="",
                error=f"Error reading skill file, {type(e).__name__}: {e}",
                metadata={
                    "tool": self.name,
                    "skill_name": skill_name,
                    "duration_ms": int((time.perf_counter() - start) * 1000),
                },
            )


class ListSkillFilesTool(Tool):
    """List files inside a skill's directory."""

    name = "list_skill_files"
    description = "List files inside a specific skill directory."
    parameters = {
        "type": "object",
        "properties": {
            "skill_name": {
                "type": "string",
            },
        },
        "required": ["skill_name"],
    }

    def __init__(self, skill_manager: SkillManager):
        self.skill_manager = skill_manager

    def execute(self, skill_name: str) -> ToolResult:
        start = time.perf_counter()
        try:
            files = self.skill_manager.list_skill_files(skill_name)
            return ToolResult(
                ok=True,
                content="\n".join(files) or "No files found.",
                error=None,
                metadata={
                    "tool": self.name,
                    "skill_name": skill_name,
                    "duration_ms": int((time.perf_counter() - start) * 1000),
                },
            )
        except Exception as e:
            return ToolResult(
                ok=False,
                content="",
                error=f"Error listing skill files, {type(e).__name__}: {e}",
                metadata={
                    "tool": self.name,
                    "skill_name": skill_name,
                    "duration_ms": int((time.perf_counter() - start) * 1000),
                },
            )


class ReadSkillFileTool(Tool):
    """Read a specific file from within a skill's directory."""

    name = "read_skill_file"
    description = "Read a file inside a specific skill directory by relative path."
    parameters = {
        "type": "object",
        "properties": {
            "skill_name": {
                "type": "string",
            },
            "relative_path": {
                "type": "string",
            },
        },
        "required": ["skill_name", "relative_path"],
    }

    def __init__(self, skill_manager: SkillManager):
        self.skill_manager = skill_manager

    def execute(self, skill_name: str, relative_path: str) -> ToolResult:
        start = time.perf_counter()
        try:
            result = self.skill_manager.read_skill_file(skill_name, relative_path)
            return ToolResult(
                ok=True,
                content=result,
                error=None,
                metadata={
                    "tool": self.name,
                    "skill_name": skill_name,
                    "relative_path": relative_path,
                    "duration_ms": int((time.perf_counter() - start) * 1000),
                },
            )
        except Exception as e:
            return ToolResult(
                ok=False,
                content="",
                error=f"Error reading skill file, {type(e).__name__}: {e}",
                metadata={
                    "tool": self.name,
                    "skill_name": skill_name,
                    "relative_path": relative_path,
                    "duration_ms": int((time.perf_counter() - start) * 1000),
                },
            )
