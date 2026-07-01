from pathlib import Path

from rich.console import Console

# force_terminal=True 强制输出样式（即使不在终端中）
console = Console(force_terminal=True)
console.print("[bold magenta]Hello[/bold magenta] [green]World[/green] [blink]闪烁[/blink]:sparkles:!")


content = Path(
    "/Users/shimi/WorkSpace/Self-Learning/github/my_corecoder/.corecoder/skills/weather-1.0.0/SKILL.md"
).read_text(encoding="utf-8")

parts = content.split("---", maxsplit=2)
print(len(parts))
print(parts[1])
print(parts[2])
