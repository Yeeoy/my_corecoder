from rich.console import Console

# force_terminal=True 强制输出样式（即使不在终端中）
console = Console(force_terminal=True)
console.print("[bold magenta]Hello[/bold magenta] [green]World[/green] [blink]闪烁[/blink]:sparkles:!")


dic = {"name": "zhangsan", "age": 18}

dic.update({"name": "lisi"})
print(dic)
