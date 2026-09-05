"""Run the official SDK with only ViNote's business tools and bounded lifetime."""
from __future__ import annotations

import asyncio
import logging
import math
import subprocess
import tempfile
import threading
from pathlib import Path
from typing import Awaitable, Callable
from uuid import UUID

from backend.agent_runtime.bridge import ToolBridge

logger = logging.getLogger(__name__)


class AgentRuntimeError(RuntimeError):
    """Safe error boundary: upstream diagnostics must not enter user-visible events."""


class AgentCleanupError(AgentRuntimeError):
    """The session must remain blocked because owned work did not stop safely."""


class HarnessRuntime:
    def __init__(
        self, config, home: Path, *, timeout=300, max_steps=8,
        system_prompt='You are ViNote. Only search videos and generate video notes.',
    ):
        if not math.isfinite(timeout) or not 0 < timeout <= 3600:
            raise ValueError('Agent timeout must be between 0 and 3600 seconds')
        if isinstance(max_steps, bool) or not isinstance(max_steps, int) or not 1 <= max_steps <= 32:
            raise ValueError('Agent max_steps must be between 1 and 32')
        if not isinstance(system_prompt, str) or not system_prompt.strip():
            raise ValueError('Agent system prompt must not be empty')
        self.config = config
        self.home = Path(home)
        self.timeout = timeout
        self.max_steps = max_steps
        self.system_prompt = system_prompt

    async def run(
        self, prompt: str, session_id: str,
        dispatch: Callable[[str, dict], Awaitable[dict]],
        emit: Callable[[dict], None],
    ) -> str:
        # Only generated repository ids cross the subprocess/tool boundary.
        session_id = str(UUID(session_id))
        runtime = bridge = work = temporary_home = owned_process = None
        stop = threading.Event()
        lifecycle_lock = threading.Lock()
        loop = asyncio.get_running_loop()

        def publish(text):
            if not stop.is_set():
                emit({'type': 'text_chunk', 'content': text})

        def notify(notification):
            if stop.is_set() or notification.method != 'session.event':
                return
            payload = notification.payload
            if not isinstance(payload, dict) or payload.get('sessionId') != session_id:
                return
            event = payload.get('event')
            if not isinstance(event, dict) or event.get('type') != 'assistant/chunk':
                return
            data = event.get('data')
            chunk = data.get('chunk') if isinstance(data, dict) else None
            if isinstance(chunk, dict) and chunk.get('type') == 'text-delta' and isinstance(chunk.get('text'), str):
                loop.call_soon_threadsafe(publish, chunk['text'])

        def run_sdk():
            nonlocal owned_process
            # Closing an SDK before its lazy run() starts can otherwise spawn a
            # fresh process after cancellation. Prepare Session once under a lock;
            # Session.run never starts/restarts a subprocess on its own.
            with lifecycle_lock:
                if stop.is_set():
                    return None
                client = getattr(runtime, 'client', None)
                start_client = getattr(client, 'start', None)
                if callable(start_client):
                    try:
                        start_client()
                    finally:
                        # SDK initialization failures call close() internally and
                        # clear _proc. Retain the pipes before initialization.
                        owned_process = getattr(client, '_proc', None)
                try:
                    session = runtime.start_session(session_id)
                finally:
                    if owned_process is None:
                        owned_process = getattr(client, '_proc', None)
            if stop.is_set():
                return None
            return session.run(prompt, on_notification=notify)

        def close_sdk():
            if runtime is None:
                return
            with lifecycle_lock:
                # The pinned SDK has no public force-close method. Retain its
                # subprocess handle only as a final fallback if graceful close fails.
                client = getattr(runtime, 'client', None)
                process = owned_process or getattr(client, '_proc', None)
                try:
                    runtime.close()
                except Exception:
                    logger.warning('Agent runtime graceful shutdown failed')
                finally:
                    if process is not None and process.poll() is None:
                        try:
                            process.terminate()
                            process.wait(timeout=1)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.wait(timeout=2)
                        except ProcessLookupError:
                            pass
                    if process is not None:
                        process.wait(timeout=2)
                        # SDK 0.1.2rc1 joins its readers but leaves stdout/stderr
                        # open. Wait for EOF readers before closing TextIOWrapper
                        # objects: closing while a reader holds their lock can hang.
                        for name in ('_reader_thread', '_stderr_thread'):
                            reader = getattr(client, name, None)
                            if reader is not None and reader.is_alive():
                                reader.join(timeout=1)
                                if reader.is_alive():
                                    raise AgentCleanupError('Agent runtime reader did not stop')
                        pipe_failure = False
                        for pipe in (process.stdin, process.stdout, process.stderr):
                            if pipe is not None and not pipe.closed:
                                try:
                                    pipe.close()
                                except OSError:
                                    pipe_failure = pipe_failure or not pipe.closed
                        if pipe_failure:
                            raise AgentCleanupError('Agent runtime pipe cleanup did not complete')

        async def cleanup():
            stop.set()
            failed = False
            if bridge is not None:
                try:
                    await bridge.aclose()
                except Exception:
                    failed = True
                    logger.warning('Agent business tool cleanup did not complete')
            try:
                await asyncio.to_thread(close_sdk)
            except Exception:
                failed = True
                logger.warning('Agent runtime process cleanup did not complete')
            if work is not None:
                done, _ = await asyncio.wait({work}, timeout=5)
                if done:
                    try:
                        work.result()
                    except (Exception, asyncio.CancelledError):
                        pass
                else:
                    failed = True
                    logger.warning('Agent runtime worker did not stop after shutdown')
            if temporary_home is not None:
                try:
                    await asyncio.to_thread(temporary_home.cleanup)
                except OSError:
                    failed = True
                    logger.warning('Agent runtime temporary directory cleanup failed')
            if failed:
                raise AgentCleanupError('Agent 清理未完成，请重启服务后重试')

        try:
            from deepseek_harness import DeepSeekHarness

            self.home.mkdir(parents=True, exist_ok=True, mode=0o700)
            temporary_home = tempfile.TemporaryDirectory(prefix='turn-', dir=self.home)
            home = Path(temporary_home.name)
            bridge = ToolBridge(session_id, dispatch, timeout=self.timeout)
            config = self.config
            base_url = config.base_url.rstrip('/').removesuffix('/chat/completions')
            runtime = DeepSeekHarness(
                dsh_home=str(home), cwd=str(home), profile='sdk-minimal',
                patches=(str(Path(__file__).parent / 'plugin' / 'runtime.patch.yml'),),
                provider='vinote', model=config.model, max_tokens=4096,
                initialize_timeout_seconds=min(30, self.timeout),
                request_timeout_seconds=min(30, self.timeout),
                shutdown_timeout_seconds=1,
                env={
                    'VINOTE_LLM_BASE_URL': base_url,
                    'VINOTE_LLM_API_KEY': config.api_key or '',
                    'VINOTE_LLM_MODEL': config.model,
                    'VINOTE_AGENT_SYSTEM_PROMPT': self.system_prompt,
                    'VINOTE_AGENT_BRIDGE_URL': bridge.url,
                    'VINOTE_AGENT_BRIDGE_TOKEN': bridge.token,
                    'VINOTE_AGENT_MAX_STEPS': str(self.max_steps),
                    'VINOTE_AGENT_TOOL_TIMEOUT_MS': str(max(1, int(self.timeout * 1000))),
                },
            )
            work = asyncio.create_task(asyncio.to_thread(run_sdk))
            result = await asyncio.wait_for(asyncio.shield(work), timeout=self.timeout)
            if result is None or result.finish_reason != 'completed':
                raise AgentRuntimeError('Agent 未完成本轮任务，请缩小检索范围后重试')
            return result.final_response or ''
        except asyncio.TimeoutError:
            raise AgentRuntimeError('Agent 执行超时，请缩小检索范围后重试') from None
        except asyncio.CancelledError:
            raise
        except AgentRuntimeError:
            raise
        except Exception:
            raise AgentRuntimeError('Agent 服务暂时不可用，请检查模型配置或稍后重试') from None
        finally:
            # A second client disconnect/cancel must not cancel cleanup itself.
            finalizer = asyncio.create_task(cleanup())
            cancelled = False
            while not finalizer.done():
                try:
                    await asyncio.shield(finalizer)
                except asyncio.CancelledError:
                    cancelled = True
            finalizer.result()
            if cancelled:
                raise asyncio.CancelledError()
