import re
from pathlib import Path


class SkillManager:
    def __init__(self):
        self.skills_dir = Path(__file__).resolve().parent.parent / ".corecoder" / "skills"
        self.active_skills: set[str] = set()
        self.skills_dir.mkdir(parents=True, exist_ok=True)
        self._skill_names: list[str] | None = None
        self._metadata_cache: dict[str, dict[str, str]] = {}

    # ── path resolution ─────────────────────────────────────────────

    def _skill_dir(self, skill_name: str) -> Path:
        """Return the resolved skill directory, or raise ValueError on traversal."""
        d = (self.skills_dir / skill_name).resolve()
        if not d.is_relative_to(self.skills_dir.resolve()):
            raise ValueError(f"path traversal denied: {skill_name!r}")
        return d

    def _resolve_skill_file(self, skill_name: str, relative_path: str) -> Path:
        """Return a resolved file path inside a skill dir, or raise ValueError on traversal."""
        root = self._skill_dir(skill_name)
        f = (root / relative_path).resolve()
        if not f.is_relative_to(root):
            raise ValueError(f"path traversal denied: {relative_path!r}")
        return f

    # ── skill discovery ─────────────────────────────────────────────

    def list_skills(self) -> list[str]:
        if self._skill_names is not None:
            return self._skill_names

        skills = []
        for path in self.skills_dir.iterdir():
            if not path.is_dir():
                continue
            if (path / "SKILL.md").exists():
                skills.append(path.name)
        result = sorted(skills)
        self._skill_names = result
        return result

    def list_skill_files(self, skill_name: str) -> list[str]:
        if skill_name not in self.list_skills():
            return []
        root = self._skill_dir(skill_name)
        return sorted(
            str(f.relative_to(root))
            for f in root.rglob("*")
            if f.is_file() and not f.name.startswith(".")
        )

    # ── reading content ─────────────────────────────────────────────

    def read_skill(self, skill_name: str) -> str:
        try:
            d = self._skill_dir(skill_name)
        except ValueError as e:
            return f"Error: {e}"
        skill_file = d / "SKILL.md"
        if not skill_file.exists():
            return f"skill '{skill_name}' not found"
        return skill_file.read_text(encoding="utf-8")

    def read_skill_file(self, skill_name: str, relative_path: str) -> str:
        try:
            f = self._resolve_skill_file(skill_name, relative_path)
        except ValueError as e:
            return f"Error: {e}"
        if not f.exists():
            return f"File not found: {relative_path}"
        if not f.is_file():
            return f"Not a file: {relative_path}"
        return f.read_text(encoding="utf-8")

    # ── metadata ────────────────────────────────────────────────────

    def read_skill_metadata(self, skill_name: str) -> dict[str, str]:
        if skill_name in self._metadata_cache:
            return self._metadata_cache[skill_name]

        content = self.read_skill(skill_name)
        frontmatter, _ = self._split_frontmatter(content)
        meta = self._parse_simple_metadata(frontmatter)
        self._metadata_cache[skill_name] = meta
        return meta

    # ── active skills ───────────────────────────────────────────────

    def load_all_skills(self):
        for skill_name in self.list_skills():
            self.enable_skill(skill_name)

    def enable_skill(self, skill_name: str) -> str:
        if skill_name not in self.list_skills():
            return f"Skill not found: {skill_name}"
        self.active_skills.add(skill_name)
        return f"Skill enabled: {skill_name}"

    def list_active_skills(self) -> list[str]:
        return sorted(self.active_skills)

    def clear(self) -> str:
        self.active_skills.clear()
        self._metadata_cache.clear()
        self._skill_names = None
        return "All skills cleared."

    # ── rendering ───────────────────────────────────────────────────

    def render_active_skills(self) -> str:
        if not self.active_skills:
            return ""

        chunks = [
            "# Active Skills",
            "The following skills are available. This information IS authoritative — "
            "answer questions about available skills directly from this list without reading any files. "
            "Only use read_skill / list_skill_files / read_skill_file when you need the FULL instruction content to execute a skill.",
        ]

        for skill_name in sorted(self.active_skills):
            chunks.append(self.render_skill_card(skill_name))
        return "\n\n".join(chunks)

    def render_skill_card(self, skill_name: str) -> str:
        skill = self.read_skill_metadata(skill_name)
        return f"""### {skill["name"]}
{skill["description"]}
(Call `read_skill("{skill_name}")` to get full instructions when you need to use this skill.)""".strip()

    # ── frontmatter parsing ─────────────────────────────────────────

    @staticmethod
    def _split_frontmatter(text: str) -> tuple[str, str]:
        if text.startswith("---"):
            parts = text.split("---", 2)
            if len(parts) == 3:
                return parts[1].strip(), parts[2].strip()
        return "", text

    @staticmethod
    def _parse_simple_metadata(frontmatter: str) -> dict[str, str]:
        result: dict[str, str] = {}
        pattern = re.compile(r"^(\w[\w-]*):\s*(.+)$")

        for line in frontmatter.splitlines():
            match = pattern.match(line.strip())
            if match:
                key, value = match.group(1), match.group(2).strip()
                result[key] = value

        if not result:
            return {"name": "unknown skill name", "description": "unknown skill description"}

        return {
            "name": result.get("name", "unknown skill name"),
            "description": result.get("description", "unknown skill description"),
        }
