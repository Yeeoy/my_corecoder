from app.skills import SkillManager
from app.tools.agent import AgentTool
from app.tools.bash import BashTool
from app.tools.edit import EditFileTool
from app.tools.glob_tool import GlobTool
from app.tools.grep import GrepTool
from app.tools.now import NowTool
from app.tools.read import ReadFileTool
from app.tools.skill import ListSkillFilesTool, ReadSkillFileTool, SkillTool
from app.tools.write import WriteFileTool


def create_tools(skills: SkillManager) -> list:
    return [
        BashTool(),
        ReadFileTool(),
        WriteFileTool(),
        EditFileTool(),
        GlobTool(),
        GrepTool(),
        AgentTool(),
        NowTool(),
        SkillTool(skills),
        ListSkillFilesTool(skills),
        ReadSkillFileTool(skills),
    ]
