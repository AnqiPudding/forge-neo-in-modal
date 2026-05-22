#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import os
import signal
import subprocess
import sys
from collections.abc import AsyncIterator
from contextlib import suppress

from aiohttp import ClientSession, WSMsgType, web
from aiohttp.client_exceptions import ClientConnectionResetError


HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
}
NORMAL_WEBSOCKET_CLOSE_ERRORS = (
    BrokenPipeError,
    ClientConnectionResetError,
    ConnectionResetError,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--listen", default="0.0.0.0")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--webui-url", required=True)
    parser.add_argument("--filebrowser-url", required=True)
    parser.add_argument("--filebrowser-prefix", default="/files")
    parser.add_argument("--filebrowser-command", required=True)
    parser.add_argument("--filebrowser-auth-header", default="X-Modal-Filebrowser-User")
    parser.add_argument("--filebrowser-auth-user", default="admin")
    parser.add_argument("webui_command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.webui_command[:1] == ["--"]:
        args.webui_command = args.webui_command[1:]
    if not args.webui_command:
        parser.error("WebUI command is required after --")
    args.filebrowser_prefix = "/" + args.filebrowser_prefix.strip("/")
    return args


async def stream_request(request: web.Request) -> AsyncIterator[bytes]:
    async for chunk in request.content.iter_chunked(1024 * 1024):
        yield chunk


class ProcessProxy:
    def __init__(
        self,
        webui_url: str,
        filebrowser_url: str,
        filebrowser_prefix: str,
        filebrowser_command: str,
        filebrowser_auth_header: str,
        filebrowser_auth_user: str,
        webui_command: list[str],
    ) -> None:
        self.webui_url = webui_url.rstrip("/")
        self.filebrowser_url = filebrowser_url.rstrip("/")
        self.filebrowser_prefix = filebrowser_prefix.rstrip("/")
        self.filebrowser_command = filebrowser_command
        self.filebrowser_auth_header = filebrowser_auth_header
        self.filebrowser_auth_user = filebrowser_auth_user
        self.webui_command = webui_command
        self.session: ClientSession | None = None
        self.processes: list[subprocess.Popen[str]] = []
        self.startup_grace_seconds = int(os.environ.get("FORGE_PROXY_STARTUP_GRACE_SECONDS", "1200"))

    async def start(self, app: web.Application) -> None:
        self.session = ClientSession(auto_decompress=False)
        self.processes = [
            subprocess.Popen(
                self.webui_command,
                cwd=os.environ.get("FORGE_DIR") or None,
                text=True,
                stdout=sys.stdout,
                stderr=sys.stderr,
                start_new_session=True,
            ),
            subprocess.Popen(
                self.filebrowser_command,
                shell=True,
                text=True,
                stdout=sys.stdout,
                stderr=sys.stderr,
                start_new_session=True,
            ),
        ]

    async def stop(self, app: web.Application) -> None:
        if self.session:
            await self.session.close()
        for process in self.processes:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
        for process in self.processes:
            if process.poll() is None:
                try:
                    process.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=30)

    def is_filebrowser_request(self, request: web.Request) -> bool:
        return request.path.startswith(self.filebrowser_prefix + "/") or request.path == self.filebrowser_prefix

    def forward_headers(self, request: web.Request) -> dict[str, str]:
        headers = {
            key: value
            for key, value in request.headers.items()
            if key.lower() not in HOP_BY_HOP_HEADERS and key.lower() != self.filebrowser_auth_header.lower()
        }
        if self.is_filebrowser_request(request):
            headers[self.filebrowser_auth_header] = self.filebrowser_auth_user
        return headers

    def pick_target(self, request: web.Request) -> str:
        raw_path = request.rel_url.raw_path_qs
        if request.path == self.filebrowser_prefix:
            raw_path = f"{self.filebrowser_prefix}/"
        if self.is_filebrowser_request(request):
            if request.method == "POST" and request.path == f"{self.filebrowser_prefix}/api/renew":
                raw_path = f"{self.filebrowser_prefix}/api/login"
            return self.filebrowser_url + raw_path
        return self.webui_url + raw_path

    async def handle_websocket(self, request: web.Request) -> web.StreamResponse:
        if self.session is None:
            raise web.HTTPServiceUnavailable(text="Proxy client is not ready.")
        ws_server = web.WebSocketResponse()
        await ws_server.prepare(request)

        target = self.pick_target(request).replace("http://", "ws://", 1)
        async with self.session.ws_connect(target, headers=self.forward_headers(request)) as ws_client:
            async def client_to_backend() -> None:
                async for message in ws_server:
                    if message.type == WSMsgType.TEXT:
                        try:
                            await ws_client.send_str(message.data)
                        except NORMAL_WEBSOCKET_CLOSE_ERRORS:
                            break
                    elif message.type == WSMsgType.BINARY:
                        try:
                            await ws_client.send_bytes(message.data)
                        except NORMAL_WEBSOCKET_CLOSE_ERRORS:
                            break
                    elif message.type == WSMsgType.CLOSE:
                        with suppress(*NORMAL_WEBSOCKET_CLOSE_ERRORS):
                            await ws_client.close()
                        break

            async def backend_to_client() -> None:
                async for message in ws_client:
                    if message.type == WSMsgType.TEXT:
                        try:
                            await ws_server.send_str(message.data)
                        except NORMAL_WEBSOCKET_CLOSE_ERRORS:
                            break
                    elif message.type == WSMsgType.BINARY:
                        try:
                            await ws_server.send_bytes(message.data)
                        except NORMAL_WEBSOCKET_CLOSE_ERRORS:
                            break
                    elif message.type == WSMsgType.CLOSE:
                        with suppress(*NORMAL_WEBSOCKET_CLOSE_ERRORS):
                            await ws_server.close()
                        break

            tasks = [
                asyncio.create_task(client_to_backend()),
                asyncio.create_task(backend_to_client()),
            ]
            try:
                done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_EXCEPTION)
                for task in done:
                    try:
                        exc = task.exception()
                    except asyncio.CancelledError:
                        continue
                    if exc and not isinstance(exc, NORMAL_WEBSOCKET_CLOSE_ERRORS):
                        raise exc
                for task in pending:
                    task.cancel()
                if pending:
                    await asyncio.gather(*pending, return_exceptions=True)
            finally:
                for task in tasks:
                    if not task.done():
                        task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
                with suppress(*NORMAL_WEBSOCKET_CLOSE_ERRORS):
                    await ws_server.close()
                with suppress(*NORMAL_WEBSOCKET_CLOSE_ERRORS):
                    await ws_client.close()
        return ws_server

    def starting_response(self) -> web.Response:
        body = (
            "<!doctype html><meta charset='utf-8'>"
            "<title>Forge Neo is starting</title>"
            "<body style='font-family: Arial, sans-serif; padding: 24px; background: #111317; color: #e9edf3'>"
            "<h1>Forge Neo is starting</h1>"
            "<p>File Browser is available at <a style='color:#8ac7ff' href='/files/'>/files/</a>.</p>"
            "<script>setTimeout(() => location.reload(), 5000)</script>"
            "</body>"
        )
        return web.Response(status=503, text=body, content_type="text/html")

    async def forward_http(self, request: web.Request) -> web.StreamResponse:
        assert self.session is not None
        async with self.session.request(
            request.method,
            self.pick_target(request),
            data=stream_request(request) if request.can_read_body else None,
            headers=self.forward_headers(request),
            allow_redirects=False,
        ) as response:
            headers = {
                key: value
                for key, value in response.headers.items()
                if key.lower() not in HOP_BY_HOP_HEADERS
            }
            stream = web.StreamResponse(status=response.status, reason=response.reason, headers=headers)
            await stream.prepare(request)
            async for chunk in response.content.iter_chunked(1024 * 1024):
                await stream.write(chunk)
            await stream.write_eof()
            return stream

    async def handle_proxy(self, request: web.Request) -> web.StreamResponse:
        if self.session is None:
            raise web.HTTPServiceUnavailable(text="Proxy client is not ready.")
        if request.headers.get("upgrade", "").lower() == "websocket":
            return await self.handle_websocket(request)

        if self.is_filebrowser_request(request) or request.method not in {"GET", "HEAD"}:
            try:
                return await self.forward_http(request)
            except Exception:
                return self.starting_response()

        deadline = asyncio.get_running_loop().time() + self.startup_grace_seconds
        while True:
            try:
                return await self.forward_http(request)
            except asyncio.CancelledError:
                raise
            except Exception:
                if asyncio.get_running_loop().time() >= deadline:
                    return self.starting_response()
                await asyncio.sleep(2)


def main() -> None:
    args = parse_args()
    proxy = ProcessProxy(
        webui_url=args.webui_url,
        filebrowser_url=args.filebrowser_url,
        filebrowser_prefix=args.filebrowser_prefix,
        filebrowser_command=args.filebrowser_command,
        filebrowser_auth_header=args.filebrowser_auth_header,
        filebrowser_auth_user=args.filebrowser_auth_user,
        webui_command=args.webui_command,
    )
    app = web.Application(client_max_size=1024**4)
    app.on_startup.append(proxy.start)
    app.on_cleanup.append(proxy.stop)
    app.router.add_route("*", "/{tail:.*}", proxy.handle_proxy)
    web.run_app(app, host=args.listen, port=args.port, print=None)


if __name__ == "__main__":
    main()
