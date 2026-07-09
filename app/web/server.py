import asyncio
from dataclasses import dataclass

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.web.event_bridge import WebEventBridge
from app.web.session import WebAgentSession


class ChatRequest(BaseModel):
    message: str


class PermissionRequest(BaseModel):
    action: str


class SwitchRequest(BaseModel):
    session_id: str


@dataclass
class WebRuntime:
    bridge: WebEventBridge
    session: WebAgentSession
    tools: list
    skills: object


def create_web_app(runtime: WebRuntime) -> FastAPI:
    app = FastAPI(title="CoreCoder Web")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.on_event("startup")
    async def on_startup():
        runtime.bridge.bind_loop(asyncio.get_running_loop())

    @app.get("/api/health")
    async def health():
        return {
            "ok": True,
            "name": "CoreCoder Web",
        }

    @app.get("/api/tools")
    async def list_tools():
        tools = []
        for tool in runtime.tools:
            tools.append(
                {
                    "name": tool.name,
                    "description": tool.description,
                }
            )
        return {"ok": True, "tools": tools}

    @app.get("/api/skills")
    async def list_skills():
        skills = []
        for skill_name in runtime.skills.list_skills():
            meta = runtime.skills.read_skill_metadata(skill_name)
            skills.append(
                {
                    "name": skill_name,
                    "display_name": meta.get("name", skill_name),
                    "description": meta.get("description", ""),
                }
            )
        return {"ok": True, "skills": skills}

    @app.post("/api/chat")
    async def chat(req: ChatRequest):
        return runtime.session.submit(req.message)

    @app.post("/api/permission/respond")
    async def permission_respond(req: PermissionRequest):
        return runtime.session.respond_permission(req.action)

    @app.post("/api/stop")
    async def stop():
        return runtime.session.stop()

    @app.websocket("/ws/events")
    async def websocket_events(websocket: WebSocket):
        await runtime.bridge.connect(websocket)

        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            runtime.bridge.disconnect(websocket)

    @app.get("/api/sessions")  # 列表
    async def list_sessions():
        return runtime.session.list_sessions()

    @app.get("/api/session")  # 当前会话(id + messages)
    async def get_session():
        return runtime.session.get_current()

    @app.post("/api/session/new")  # 新建
    async def new_session():
        return runtime.session.new_session()

    @app.post("/api/session/switch")  # 切换
    async def switch_session(req: SwitchRequest):
        return runtime.session.switch_session(req.session_id)

    return app
