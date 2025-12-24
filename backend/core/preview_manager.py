"""
PreviewManager: запускает пользовательские веб-приложения на локальных портах
и управляет их жизненным циклом (TTL, остановка, логи).
"""

import asyncio
import os
import socket
import time
import secrets
from typing import Dict, Any, Optional, Set

from .logger import get_logger
logger = get_logger(__name__)


class PreviewState:
    def __init__(
        self,
        preview_id: str,
        token: str,
        port: int,
        process: asyncio.subprocess.Process,
        command: str,
        workdir: Optional[str],
        ttl_seconds: int,
        started_at: float,
    ):
        self.id = preview_id
        self.token = token
        self.port = port
        self.process = process
        self.command = command
        self.workdir = workdir
        self.ttl_seconds = ttl_seconds
        self.started_at = started_at
        self.expires_at = started_at + ttl_seconds if ttl_seconds else None
        self.stdout: str = ""
        self.stderr: str = ""
        self.returncode: Optional[int] = None
        self._stdout_task: Optional[asyncio.Task] = None
        self._stderr_task: Optional[asyncio.Task] = None
        self._reaper_task: Optional[asyncio.Task] = None


class PreviewManager:
    def __init__(
        self,
        port_pool: Set[int],
        default_ttl: int = 900,
        log_limit: int = 20000,
    ):
        self.port_pool = set(port_pool)
        self.default_ttl = default_ttl
        self.log_limit = log_limit
        self._by_id: Dict[str, PreviewState] = {}
        self._lock = asyncio.Lock()

    async def start_preview(
        self,
        command: str,
        workdir: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
        port_hint: Optional[int] = None,
        ttl: Optional[int] = None,
    ) -> PreviewState:
        ttl_seconds = ttl or self.default_ttl
        async with self._lock:
            port = port_hint or await self._find_free_port()
            if port not in self.port_pool:
                raise ValueError("Port not allowed")
            if not self._is_port_free(port):
                port = await self._find_free_port()

            preview_id = secrets.token_urlsafe(12)
            token = secrets.token_urlsafe(16)

            proc_env = os.environ.copy()
            if env:
                proc_env.update(env)

            # Подставляем порт в окружение (часто нужно для dev-серверов)
            proc_env.setdefault("PORT", str(port))
            proc_env.setdefault("HOST", "127.0.0.1")

            process = await asyncio.create_subprocess_shell(
                command,
                cwd=workdir,
                env=proc_env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            state = PreviewState(
                preview_id=preview_id,
                token=token,
                port=port,
                process=process,
                command=command,
                workdir=workdir,
                ttl_seconds=ttl_seconds,
                started_at=time.time(),
            )
            self._by_id[preview_id] = state

            state._stdout_task = asyncio.create_task(self._drain_stream(process.stdout, state, "stdout"))
            state._stderr_task = asyncio.create_task(self._drain_stream(process.stderr, state, "stderr"))
            state._reaper_task = asyncio.create_task(self._auto_stop(preview_id, ttl_seconds))

            logger.info(f"Preview started id={preview_id} port={port} cmd='{command}' ttl={ttl_seconds}s")
            return state

    async def stop_preview(self, preview_id: str) -> bool:
        async with self._lock:
            state = self._by_id.get(preview_id)
            if not state:
                return False

            proc = state.process
            if proc and proc.returncode is None:
                proc.terminate()
                try:
                    await asyncio.wait_for(proc.wait(), timeout=5)
                except asyncio.TimeoutError:
                    proc.kill()
                    await proc.wait()

            state.returncode = proc.returncode if proc else state.returncode
            self._by_id.pop(preview_id, None)
            return True

    async def get_status(self, preview_id: str) -> Optional[Dict[str, Any]]:
        state = self._by_id.get(preview_id)
        if not state:
            return None
        proc = state.process
        running = proc.returncode is None if proc else False
        return {
            "id": state.id,
            "token": state.token,
            "port": state.port,
            "command": state.command,
            "workdir": state.workdir,
            "started_at": state.started_at,
            "expires_at": state.expires_at,
            "running": running,
            "returncode": proc.returncode if proc else state.returncode,
            "stdout": state.stdout,
            "stderr": state.stderr,
        }

    async def _drain_stream(self, stream: asyncio.StreamReader, state: PreviewState, field: str):
        try:
            while not stream.at_eof():
                chunk = await stream.read(1024)
                if not chunk:
                    break
                text = chunk.decode("utf-8", errors="ignore")
                current = getattr(state, field)
                new_value = (current + text)[-self.log_limit :]
                setattr(state, field, new_value)
        except Exception as e:
            logger.warning(f"Error reading {field} for preview {state.id}: {e}")

    async def _auto_stop(self, preview_id: str, ttl: int):
        await asyncio.sleep(ttl)
        await self.stop_preview(preview_id)
        logger.info(f"Preview {preview_id} stopped by TTL")

    async def _find_free_port(self) -> int:
        for port in sorted(self.port_pool):
            if self._is_port_free(port) and not any(s.port == port for s in self._by_id.values()):
                return port
        raise RuntimeError("No free preview ports available")

    def _is_port_free(self, port: int) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            return s.connect_ex(("127.0.0.1", port)) != 0

