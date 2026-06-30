import time

from app.tools.base import Tool


class NowTool(Tool):
    name = "Now"
    description = "Get the current time"
    parameters = {
        "type": "object",
        "properties": {},
        "required": [],
    }

    def execute(self, **kwargs) -> str:
        return time.strftime("%Y-%m-%d %H:%M:%S")
