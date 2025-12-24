"""
Preview management endpoints:
- create preview (start user web app on local port)
- status
- stop
- proxy HTTP GET/HEAD to the preview (localhost port) with token check
"""

import time
from typing import Dict, Any, Optional

import httpx
import websockets
from fastapi import APIRouter, HTTPException, Request, Response, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from ...core.preview_manager import PreviewManager

router = APIRouter()

# Proxy constraints
PROXY_REQUEST_TIMEOUT = 8.0
PROXY_MAX_BODY = 2_000_000  # bytes
WS_TIMEOUT = 30.0


class PreviewCreateRequest(BaseModel):
    command: str = Field(..., description="Shell command to start the web app")
    workdir: Optional[str] = Field(None, description="Working directory")
    env: Optional[Dict[str, str]] = Field(None, description="Extra env variables")
    port_hint: Optional[int] = Field(None, description="Preferred port (must be in pool)")
    ttl: Optional[int] = Field(None, description="TTL seconds; default manager setting")


@router.post("/previews")
async def create_preview(request: Request, payload: PreviewCreateRequest):
    mgr: PreviewManager = request.app.state.preview_manager
    if not mgr:
        raise HTTPException(status_code=503, detail="Preview manager unavailable")
    try:
        state = await mgr.start_preview(
            command=payload.command,
            workdir=payload.workdir,
            env=payload.env,
            port_hint=payload.port_hint,
            ttl=payload.ttl,
        )
        proxy_url = f"/api/v1/previews/{state.id}/proxy/"
        return {
            "id": state.id,
            "token": state.token,
            "port": state.port,
            "proxy_url": proxy_url + f"?token={state.token}",
            "expires_at": state.expires_at,
            "started_at": state.started_at,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/previews/{preview_id}")
async def get_preview_status(preview_id: str, request: Request):
    mgr: PreviewManager = request.app.state.preview_manager
    state = await mgr.get_status(preview_id) if mgr else None
    if not state:
        raise HTTPException(status_code=404, detail="Preview not found")
    return state


@router.delete("/previews/{preview_id}")
async def stop_preview(preview_id: str, request: Request):
    mgr: PreviewManager = request.app.state.preview_manager
    if not mgr:
        raise HTTPException(status_code=503, detail="Preview manager unavailable")
    ok = await mgr.stop_preview(preview_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Preview not found")
    return {"stopped": True}


@router.api_route("/previews/{preview_id}/proxy/{path:path}", methods=["GET", "HEAD"])
async def proxy_preview(preview_id: str, path: str, request: Request, token: Optional[str] = None):
    mgr: PreviewManager = request.app.state.preview_manager
    state = await mgr.get_status(preview_id) if mgr else None
    if not state:
        raise HTTPException(status_code=404, detail="Preview not found")
    if token != state["token"]:
        raise HTTPException(status_code=403, detail="Invalid token")

    method = request.method.upper()
    if method not in ("GET", "HEAD"):
        raise HTTPException(status_code=405, detail="Method not allowed")

    target_url = f"http://127.0.0.1:{state['port']}/{path}"

    # Forward selected headers
    headers = {}
    for name, value in request.headers.items():
        lname = name.lower()
        if lname in ("accept", "accept-language", "user-agent", "cache-control"):
            headers[name] = value

    try:
        async with httpx.AsyncClient(timeout=PROXY_REQUEST_TIMEOUT, follow_redirects=False) as client:
            upstream = await client.request(method, target_url, headers=headers)
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail=f"Proxy request failed: {exc}")

    content = upstream.content
    if len(content) > PROXY_MAX_BODY:
        content = content[:PROXY_MAX_BODY]

    resp_headers = {}
    for name, value in upstream.headers.items():
        lname = name.lower()
        if lname in ("content-type", "cache-control"):
            resp_headers[name] = value

    return Response(
        content=content if method != "HEAD" else b"",
        status_code=upstream.status_code,
        headers=resp_headers,
        media_type=upstream.headers.get("content-type"),
    )


@router.websocket("/previews/{preview_id}/ws/{path:path}")
async def proxy_preview_ws(websocket: WebSocket, preview_id: str, path: str):
    await websocket.accept()
    token = websocket.query_params.get("token")

    mgr: PreviewManager = websocket.app.state.preview_manager
    state = await mgr.get_status(preview_id) if mgr else None
    if not state:
        await websocket.close(code=4404)
        return
    if token != state["token"]:
        await websocket.close(code=4403)
        return

    target_url = f"ws://127.0.0.1:{state['port']}/{path}"

    try:
        async with websockets.connect(
            target_url,
            open_timeout=WS_TIMEOUT,
            close_timeout=WS_TIMEOUT,
        ) as upstream:

            async def client_to_upstream():
                try:
                    while True:
                        msg = await websocket.receive_text()
                        await upstream.send(msg)
                except WebSocketDisconnect:
                    await upstream.close()
                except Exception:
                    await upstream.close()

            async def upstream_to_client():
                try:
                    async for msg in upstream:
                        await websocket.send_text(msg)
                except Exception:
                    await websocket.close()

            t1 = asyncio.create_task(client_to_upstream())
            t2 = asyncio.create_task(upstream_to_client())
            await asyncio.wait([t1, t2], return_when=asyncio.FIRST_COMPLETED)
    except Exception:
        await websocket.close(code=4500)

