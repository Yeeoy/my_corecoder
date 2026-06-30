from app.tools.agent import AgentTool
from app.tools.bash import BashTool
from app.tools.edit import EditFileTool
from app.tools.glob_tool import GlobTool
from app.tools.grep import GrepTool
from app.tools.now import NowTool
from app.tools.read import ReadFileTool
from app.tools.write import WriteFileTool

ALL_TOOLS = [
    BashTool(),
    ReadFileTool(),
    WriteFileTool(),
    EditFileTool(),
    GlobTool(),
    GrepTool(),
    AgentTool(),
    NowTool(),
]


def get_tool(name: str):
    """Look up a tool by name."""
    for t in ALL_TOOLS:
        if t.name == name:
            return t
    return None
