from app.skills import SkillManager
from app.tools.base import Tool


class SkillTool(Tool):
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

    def execute(self, skill_name: str) -> str:
        try:
            return self.skill_manager.read_skill(skill_name)
        except Exception as e:
            return f"Error: {e}"


class ListSkillFilesTool(Tool):
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

    def execute(self, skill_name: str) -> list[str] | str:
        try:
            files = self.skill_manager.list_skill_files(skill_name)
            return "\n".join(files)
        except Exception as e:
            return f"Error: {e}"


class ReadSkillFileTool(Tool):
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

    def execute(self, skill_name: str, relative_path: str) -> str:
        try:
            return self.skill_manager.read_skill_file(skill_name, relative_path)
        except Exception as e:
            return f"Error: {e}"
