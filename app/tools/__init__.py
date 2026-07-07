from pathlib import Path

from app.events import EventBus
from app.skills import SkillManager
from app.todo import TodoManager
from app.tools.agent import AgentTool
from app.tools.bash import BashTool
from app.tools.edit import EditFileTool
from app.tools.file_glob import GlobTool
from app.tools.grep import GrepTool
from app.tools.read import ReadFileTool
from app.tools.search import SearchTool
from app.tools.skill import ListSkillFilesTool, ReadSkillFileTool, SkillTool
from app.tools.time import TimeTool
from app.tools.todo import TodoTool
from app.tools.write import WriteFileTool


def create_tools(
    skills: SkillManager,
    todo_manager: TodoManager,
    events: EventBus,
    workspace_root: str | Path | None = None,
) -> list:
    return [
        BashTool(workspace_root=workspace_root),
        ReadFileTool(workspace_root=workspace_root),
        WriteFileTool(workspace_root=workspace_root),
        EditFileTool(workspace_root=workspace_root),
        GlobTool(workspace_root=workspace_root),
        GrepTool(workspace_root=workspace_root),
        AgentTool(),
        TimeTool(),
        SearchTool(),
        SkillTool(skills),
        ListSkillFilesTool(skills),
        ReadSkillFileTool(skills),
        TodoTool(todo_manager, events),
    ]
