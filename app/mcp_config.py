import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class MCPServerConfig:
    name: str
    command: str
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    # Environment variable name that holds the API key for auth retry on 429.
    # If set and the env var exists, the client will reconnect with the key on rate limit.
    auth_key: str | None = None


def load_mcp_config(path: str | Path) -> list[MCPServerConfig]:
    path = Path(path)

    if not path.exists():
        return []

    data = json.loads(path.read_text(encoding="utf-8"))
    servers = data.get("servers", [])

    result: list[MCPServerConfig] = []

    for name, cfg in servers.items():
        if "command" not in cfg:
            print(f"[MCP] Skipping server '{name}': no 'command' (transport type not supported)")
            continue
        result.append(
            MCPServerConfig(
                name=name,
                command=cfg["command"],
                args=cfg.get("args", []),
                env=cfg.get("env", {}),
                auth_key=cfg.get("auth_key"),
            )
        )

    return result


@dataclass
class MCPPermissionPolicy:
    allow: set[str] = field(default_factory=set)
    confirm: set[str] = field(default_factory=set)
    deny: set[str] = field(default_factory=set)


def load_mcp_permission_policy(path: str | Path) -> MCPPermissionPolicy:
    path = Path(path)

    if not path.exists():
        return MCPPermissionPolicy()

    data = json.loads(path.read_text(encoding="utf-8"))
    permissions = data.get("permissions", {})

    return MCPPermissionPolicy(
        allow=set(permissions.get("allow", [])),
        confirm=set(permissions.get("confirm", [])),
        deny=set(permissions.get("deny", [])),
    )
