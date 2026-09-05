"""Ephemeral loopback bridge for the runtime's explicitly registered business tools."""
from __future__ import annotations

import asyncio
import concurrent.futures
import hmac
import json
import secrets
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Awaitable, Callable


class ToolBridge:
    MAX_BODY_BYTES = 16384
    MAX_RESPONSE_BYTES = 512 * 1024
    MAX_CONNECTIONS = 8

    def __init__(
        self, session_id: str,
        dispatch: Callable[[str, dict], Awaitable[dict]],
        *, timeout: float = 180, request_timeout: float = 5,
    ):
        if timeout <= 0 or request_timeout <= 0:
            raise ValueError('Bridge timeouts must be positive')
        self.session_id = session_id
        self.token = secrets.token_urlsafe(32)
        self.loop = asyncio.get_running_loop()
        self.dispatch = dispatch
        self.timeout = timeout
        self.closed = threading.Event()
        self.pending: set[concurrent.futures.Future] = set()
        self.tasks: set[asyncio.Task] = set()
        self.connections: set[socket.socket] = set()
        self.handlers: set[threading.Thread] = set()
        self.lock = threading.Lock()
        self.close_lock = threading.Lock()
        self.slots = threading.BoundedSemaphore(self.MAX_CONNECTIONS)
        owner = self

        class Server(ThreadingHTTPServer):
            daemon_threads = True

            def get_request(self):
                connection, address = super().get_request()
                if owner.closed.is_set() or not owner.slots.acquire(blocking=False):
                    connection.close()
                    raise OSError('Bridge connection capacity exceeded')
                connection.settimeout(request_timeout)
                with owner.lock:
                    owner.connections.add(connection)
                return connection, address

            def process_request(self, request, client_address):
                worker = threading.Thread(
                    target=self.process_request_thread, args=(request, client_address),
                    name='vinote-tool-request', daemon=True,
                )
                with owner.lock:
                    owner.handlers.add(worker)
                try:
                    worker.start()
                except BaseException:
                    with owner.lock:
                        owner.handlers.discard(worker)
                    self.shutdown_request(request)
                    raise

            def process_request_thread(self, request, client_address):
                try:
                    super().process_request_thread(request, client_address)
                finally:
                    with owner.lock:
                        owner.handlers.discard(threading.current_thread())

            def shutdown_request(self, request):
                with owner.lock:
                    owned = request in owner.connections
                    owner.connections.discard(request)
                try:
                    super().shutdown_request(request)
                finally:
                    if owned:
                        owner.slots.release()

            def handle_error(self, *_args):
                # Protocol failures never print user input, credentials or tracebacks.
                pass

        class Handler(BaseHTTPRequestHandler):
            def setup(self):
                super().setup()
                # A total header/body deadline also bounds slow byte-at-a-time clients.
                self.read_deadline = threading.Timer(request_timeout, self.expire_request)
                self.read_deadline.daemon = True
                self.read_deadline.start()

            def expire_request(self):
                try:
                    self.connection.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass

            def finish(self):
                self.read_deadline.cancel()
                try:
                    super().finish()
                except OSError:
                    pass

            def log_message(self, *_args):
                pass

            def reply(self, status, payload):
                self.close_connection = True
                try:
                    encoded = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode('utf-8')
                    if len(encoded) > owner.MAX_RESPONSE_BYTES:
                        raise ValueError('Result too large')
                except (TypeError, ValueError):
                    status, encoded = 500, b'{"error":"invalid_tool_result"}'
                try:
                    self.send_response(status)
                    self.send_header('Content-Type', 'application/json; charset=utf-8')
                    self.send_header('Content-Length', str(len(encoded)))
                    self.send_header('Connection', 'close')
                    self.end_headers()
                    self.wfile.write(encoded)
                except OSError:
                    pass

            def do_POST(self):
                if owner.closed.is_set():
                    return self.reply(503, {'error': 'tool_bridge_closed'})
                auth = self.headers.get_all('Authorization', [])
                expected = ('Bearer ' + owner.token).encode('ascii')
                if len(auth) != 1 or not hmac.compare_digest(auth[0].encode('utf-8'), expected):
                    return self.reply(401, {'error': 'unauthorized'})
                if self.path not in {'/tools/video_search', '/tools/generate_notes'}:
                    return self.reply(404, {'error': 'unknown_tool'})
                try:
                    lengths = self.headers.get_all('Content-Length', [])
                    if len(lengths) != 1 or not lengths[0].isascii() or not lengths[0].isdigit():
                        raise ValueError()
                    size = int(lengths[0])
                    if not 0 < size <= owner.MAX_BODY_BYTES or self.headers.get('Transfer-Encoding'):
                        raise ValueError()
                    raw = self.rfile.read(size)
                    if len(raw) != size:
                        raise ValueError()
                    data = json.loads(raw)
                    if not isinstance(data, dict) or set(data) != {'session_id', 'arguments'}:
                        raise ValueError()
                    if data['session_id'] != owner.session_id or not isinstance(data['arguments'], dict):
                        raise ValueError()
                except (ValueError, OSError):
                    return self.reply(400, {'error': 'invalid_tool_request'})
                self.read_deadline.cancel()
                with owner.lock:
                    if owner.closed.is_set():
                        return self.reply(503, {'error': 'tool_bridge_closed'})
                    operation = owner._invoke(self.path.rsplit('/', 1)[-1], data['arguments'])
                    try:
                        future = asyncio.run_coroutine_threadsafe(operation, owner.loop)
                    except RuntimeError:
                        operation.close()
                        return self.reply(503, {'error': 'tool_bridge_closed'})
                    owner.pending.add(future)
                try:
                    result = future.result(timeout=owner.timeout)
                    if not isinstance(result, dict):
                        return self.reply(500, {'error': 'invalid_tool_result'})
                    self.reply(200, result)
                except concurrent.futures.TimeoutError:
                    future.cancel()
                    self.reply(504, {'error': 'tool_timeout'})
                except concurrent.futures.CancelledError:
                    self.reply(503, {'error': 'tool_cancelled'})
                except Exception:
                    self.reply(500, {'error': 'tool_execution_failed'})
                finally:
                    with owner.lock:
                        owner.pending.discard(future)

            def do_GET(self):
                self.reply(405, {'error': 'method_not_allowed'})

        self.server = Server(('127.0.0.1', 0), Handler)
        self.url = f'http://127.0.0.1:{self.server.server_port}'
        self.thread = threading.Thread(
            target=self.server.serve_forever, kwargs={'poll_interval': 0.05},
            name='vinote-tool-bridge', daemon=True,
        )
        try:
            self.thread.start()
        except BaseException:
            self.server.server_close()
            raise

    async def _invoke(self, tool: str, arguments: dict) -> dict:
        task = asyncio.current_task()
        self.tasks.add(task)
        try:
            if self.closed.is_set():
                raise asyncio.CancelledError()
            return await self.dispatch(tool, arguments)
        finally:
            self.tasks.discard(task)

    def close(self):
        """Stop network admission; async owners should use aclose to drain tools."""
        with self.close_lock:
            self.closed.set()
            with self.lock:
                pending = list(self.pending)
                connections = list(self.connections)
            for future in pending:
                future.cancel()
            for connection in connections:
                try:
                    connection.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
            self.server.shutdown()
            self.server.server_close()
            self.thread.join(timeout=2)
            with self.lock:
                handlers = list(self.handlers)
            deadline = time.monotonic() + 2
            for handler in handlers:
                handler.join(timeout=max(0, deadline - time.monotonic()))

    async def aclose(self):
        """Stop listeners and await cooperative cancellation of every tool task."""
        await asyncio.to_thread(self.close)
        # Let already-admitted run_coroutine_threadsafe callbacks start and observe closed.
        await asyncio.sleep(0)
        tasks = set(self.tasks)
        # close() already cancelled every admitted concurrent future. A second
        # Task.cancel here could interrupt the dispatch coroutine's finally block.
        if tasks:
            _, pending = await asyncio.wait(tasks, timeout=3)
            if pending:
                raise RuntimeError('Business tool did not stop after cancellation')
