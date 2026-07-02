class RuntimeStateRenderer:
    def __init__(self, skills, permission_manager, todo_manager):
        self.skills = skills
        self.permission_manager = permission_manager
        self.todo_manager = todo_manager

    def render(self) -> str:
        chunks = ["# Runtime State"]

        chunks.append(self._render_skills())
        chunks.append(self._render_permissions())
        chunks.append(self._render_todo())

        chunks.append(
            "## Continuation Rules\n"
            "- Continue from the runtime state above.\n"
            "- Do not assume denied operations succeeded.\n"
            "- Do not repeat completed todo items unless verification requires it.\n"
            "- If a todo item is in progress, continue from that step."
        )

        return "\n\n".join(chunk for chunk in chunks if chunk.strip())

    def _render_skills(self) -> str:
        active = self.skills.list_active_skills()
        if not active:
            return "## Active Skills\n- None"
        lines = ["## Active Skills"]
        for skill in active:
            lines.append(f"- {skill}")

        return "\n".join(lines)

    def _render_permissions(self) -> str:
        lines = ["## Permission", f"- Mode: {self.permission_manager.get_mode()}"]

        allowed_dirs = getattr(self.permission_manager, "allowed_read_dirs", set())

        if allowed_dirs:
            lines.append("- Session read directories:")
            for directory in sorted(allowed_dirs):
                lines.append(f"- {directory}")
        else:
            lines.append("- Session read directories: none")

        return "\n".join(lines)

    def _render_todo(self) -> str:
        return "## Current Todo\n" + self.todo_manager.render_todo()
