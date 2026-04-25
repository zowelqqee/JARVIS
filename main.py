import asyncio
import threading
import json
import re
import sys
import traceback
import os
from pathlib import Path
from typing import Callable

from dotenv import load_dotenv
import pyaudio
from google import genai
from google.genai import types
import time
from ui import VectorUI
from memory.memory_manager import load_memory, update_memory, format_memory_for_prompt

from agent.task_queue import get_queue
from actions.registry import TOOL_REGISTRY, TOOL_DECLARATIONS


def get_base_dir():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent


BASE_DIR = get_base_dir()
load_dotenv(BASE_DIR / ".env")

PROMPT_PATH         = BASE_DIR / "core" / "prompt.txt"
LIVE_MODEL          = "models/gemini-2.5-flash-native-audio-preview-12-2025"
FORMAT              = pyaudio.paInt16
CHANNELS            = 1
SEND_SAMPLE_RATE    = 16000
RECEIVE_SAMPLE_RATE = 24000
CHUNK_SIZE          = 1024

pya = pyaudio.PyAudio()

# Global reference to the active VectorLive instance (set during run())
_active_vector: "VectorLive | None" = None


def get_vector_loop() -> asyncio.AbstractEventLoop | None:
    """Return the running event loop of the active VectorLive instance."""
    return _active_vector.vector_loop if _active_vector else None


def _get_api_key() -> str:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not found in .env")
    return api_key


def _load_system_prompt() -> str:
    try:
        return PROMPT_PATH.read_text(encoding="utf-8")
    except Exception:
        return (
            "You are V.E.C.T.O.R., a personal AI assistant. "
            "Be concise, direct, and always use the provided tools to complete tasks. "
            "Never simulate or guess results — always call the appropriate tool."
        )


_memory_turn_counter  = 0
_memory_turn_lock     = threading.Lock()
_MEMORY_EVERY_N_TURNS = 5
_last_memory_input    = ""


def _update_memory_async(user_text: str, vector_text: str) -> None:
    """
    Multilingual memory updater.
    Stage 1: Quick YES/NO check  → ~5 tokens output
    Stage 2: Full extraction     → only if Stage 1 says YES
    Result : ~80% fewer API calls vs original
    """
    global _memory_turn_counter, _last_memory_input

    with _memory_turn_lock:
        _memory_turn_counter += 1
        current_count = _memory_turn_counter

    if current_count % _MEMORY_EVERY_N_TURNS != 0:
        return

    text = user_text.strip()
    if len(text) < 10:
        return
    if text == _last_memory_input:
        return
    _last_memory_input = text

    try:
        from google import genai as genai_new
        client = genai_new.Client(api_key=_get_api_key())

        check = client.models.generate_content(
            model="gemini-2.5-flash-lite",
            contents=(
                f"Does this message contain personal facts about the user "
                f"(name, age, city, job, hobby, relationship, birthday, preference)? "
                f"Reply only YES or NO.\n\nMessage: {text[:300]}"
            )
        )
        if "YES" not in check.text.upper():
            return

        raw = client.models.generate_content(
            model="gemini-2.5-flash-lite",
            contents=(
                f"Extract personal facts from this message. Any language.\n"
                f"Return ONLY valid JSON or {{}} if nothing found.\n"
                f"Extract: name, age, birthday, city, job, hobbies, preferences, relationships, language.\n"
                f"Skip: weather, reminders, search results, commands.\n\n"
                f"Format:\n"
                f'{{"identity":{{"name":{{"value":"..."}}}}}}, '
                f'"preferences":{{"hobby":{{"value":"..."}}}}, '
                f'"notes":{{"job":{{"value":"..."}}}}}}\n\n'
                f"Message: {text[:500]}\n\nJSON:"
            )
        ).text.strip()

        raw = re.sub(r"```(?:json)?", "", raw).strip().rstrip("`").strip()
        if not raw or raw == "{}":
            return

        data = json.loads(raw)
        if data:
            update_memory(data)
            print(f"[Memory] ✅ Updated: {list(data.keys())}")

    except json.JSONDecodeError:
        pass
    except Exception as e:
        if "429" not in str(e):
            print(f"[Memory] ⚠️ {e}")


class VectorLive:

    def __init__(self, ui: VectorUI):
        self.ui               = ui
        self.session          = None
        self.audio_in_queue   = None  # audio received FROM Gemini → speakers
        self.out_queue        = None  # audio to SEND to Gemini
        self._loop            = None
        self.vector_loop: asyncio.AbstractEventLoop | None = None

        # ARIA callbacks — set by ARIAOutputAdapter after construction
        self.on_text_response: Callable[[str], None] | None = None
        self.on_status_change: Callable[[str], None] | None = None

        # Set True while a tool call is being executed; _send_realtime discards
        # audio chunks during this window so the Live API isn't fed audio while
        # waiting for a tool response (the primary cause of error 1011).
        self.tool_call_in_progress: bool = False

        # Disconnect signalling: set by _receive_audio on clean disconnect so the
        # outer CancelledError (raised by TaskGroup after we cancel siblings) is
        # recognised as a reconnect event rather than a real cancellation.
        self._session_failed: bool = False
        self._session_tasks: list[asyncio.Task] = []

    def speak(self, text: str):
        """Thread-safe speak — any thread can call this."""
        if not self.vector_loop or not self.session:
            return
        asyncio.run_coroutine_threadsafe(
            self.session.send_client_content(
                turns={"parts": [{"text": text}]},
                turn_complete=True
            ),
            self.vector_loop
        )

    @staticmethod
    def _tool_response_payload(result):
        if isinstance(result, dict):
            return result
        return {"result": result}

    def _build_config(self) -> types.LiveConnectConfig:
        from datetime import datetime
        from actions.computer_settings import get_desktop_context

        memory  = load_memory()
        mem_str = format_memory_for_prompt(memory)

        sys_prompt = _load_system_prompt()

        now      = datetime.now()
        time_str = now.strftime("%A, %B %d, %Y — %I:%M %p")
        time_ctx = (
            f"[CURRENT DATE & TIME]\n"
            f"Right now it is: {time_str}\n"
            f"Use this to calculate exact times for reminders. "
            f"If user says 'in 2 minutes', add 2 minutes to this time.\n\n"
        )

        try:
            desktop_ctx = (
                f"[DESKTOP CONTEXT — snapshot at session start]\n"
                f"{get_desktop_context()}\n"
                f"Use this to understand references like 'this window', 'the open app', "
                f"'what I'm working on'. For live state, call computer_settings active_window or list_windows.\n\n"
            )
        except Exception:
            desktop_ctx = ""

        blocks = [time_ctx, desktop_ctx, mem_str + "\n\n" if mem_str else "", sys_prompt]
        sys_prompt = "".join(blocks)

        return types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            output_audio_transcription={},
            input_audio_transcription={},
            system_instruction=sys_prompt,
            tools=[{"function_declarations": TOOL_DECLARATIONS}],
            session_resumption=types.SessionResumptionConfig(),
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name="Charon"
                    )
                )
            ),
        )

    async def _execute_tool(self, fc) -> types.FunctionResponse:
        name = fc.name
        args = dict(fc.args or {})

        print(f"[VECTOR] 🔧 TOOL: {name}  ARGS: {args}")

        # Clear stale interrupt before any new command (stop_execution sets it, not clears it)
        if name != "stop_execution":
            try:
                from agent.task_queue import clear_interrupt
                clear_interrupt()
            except ImportError:
                pass

        self.tool_call_in_progress = True
        print("[VECTOR] ⏸️  Audio sending paused (tool_call_in_progress=True)")

        if hasattr(self.ui, 'set_executing'):
            self.ui.set_executing(name, args)

        if self.on_status_change:
            try:
                self.on_status_change("thinking")
            except Exception:
                pass

        loop   = asyncio.get_running_loop()
        result = "Done."

        try:
            handler = TOOL_REGISTRY.get(name)
            if handler is None:
                result = (
                    f"Unknown tool: '{name}'. "
                    f"Available: {', '.join(sorted(TOOL_REGISTRY.keys()))}"
                )
                print(f"[VECTOR] ⚠️  {result}")
            else:
                try:
                    result = await loop.run_in_executor(
                        None, lambda: handler(args, self.ui, self.speak)
                    )
                    result = result or "Done."
                except Exception as e:
                    result = f"Tool '{name}' failed: {e}"
                    traceback.print_exc()
        finally:
            self.tool_call_in_progress = False
            print("[VECTOR] ▶️  Audio sending resumed (tool_call_in_progress=False)")

        if hasattr(self.ui, 'set_idle'):
            self.ui.set_idle()

        print(f"[VECTOR] 📤 {name} → {str(result)[:80]}")

        return types.FunctionResponse(
            id=fc.id,
            name=name,
            response=self._tool_response_payload(result)
        )

    async def _send_realtime(self):
        while True:
            msg = await self.out_queue.get()
            if self.tool_call_in_progress:
                # Discard audio while waiting for tool-response handshake.
                # Sending audio here triggers server-side error 1011.
                continue
            await self.session.send_realtime_input(media=msg)

    async def _listen_audio(self):
        print("[VECTOR] 🎤 Mic started")
        stream = await asyncio.to_thread(
            pya.open,
            format=FORMAT,
            channels=CHANNELS,
            rate=SEND_SAMPLE_RATE,
            input=True,
            frames_per_buffer=CHUNK_SIZE,
        )
        try:
            while True:
                data = await asyncio.to_thread(
                    stream.read, CHUNK_SIZE, exception_on_overflow=False
                )
                await self.out_queue.put({"data": data, "mime_type": "audio/pcm"})
        except Exception as e:
            print(f"[VECTOR] ❌ Mic error: {e}")
            raise
        finally:
            stream.close()

    async def _receive_audio(self):
        print("[VECTOR] 👂 Recv started")
        out_buf = []
        in_buf  = []

        try:
            while True:
                turn = self.session.receive()
                async for response in turn:

                    if response.data:
                        self.audio_in_queue.put_nowait(response.data)

                    if response.server_content:
                        sc = response.server_content

                        if sc.input_transcription and sc.input_transcription.text:
                            txt = sc.input_transcription.text.strip()
                            if txt:
                                in_buf.append(txt)
                                if self.on_status_change:
                                    try:
                                        self.on_status_change("thinking")
                                    except Exception:
                                        pass

                        if sc.output_transcription and sc.output_transcription.text:
                            txt = sc.output_transcription.text.strip()
                            if txt:
                                out_buf.append(txt)
                                # Notify ARIA display BEFORE audio plays
                                if self.on_text_response:
                                    try:
                                        self.on_text_response(txt)
                                    except Exception:
                                        pass
                                if self.on_status_change:
                                    try:
                                        self.on_status_change("responding")
                                    except Exception:
                                        pass

                        if sc.turn_complete:
                            full_in  = ""
                            full_out = ""

                            if in_buf:
                                full_in = " ".join(in_buf).strip()
                                if full_in:
                                    self.ui.write_log(f"You: {full_in}")
                            in_buf = []

                            if out_buf:
                                full_out = " ".join(out_buf).strip()
                                if full_out:
                                    self.ui.write_log(f"V.E.C.T.O.R.: {full_out}")
                            out_buf = []

                            if self.on_status_change:
                                try:
                                    self.on_status_change("listening")
                                except Exception:
                                    pass

                            if full_in and len(full_in) > 5:
                                threading.Thread(
                                    target=_update_memory_async,
                                    args=(full_in, full_out),
                                    daemon=True
                                ).start()

                    if response.tool_call:
                        fn_responses = []
                        for fc in response.tool_call.function_calls:
                            print(
                                f"[VECTOR] 📞 Tool call: {fc.name}  "
                                f"ARGS: {dict(fc.args or {})}"
                            )
                            fr = await self._execute_tool(fc)
                            fn_responses.append(fr)
                        try:
                            await self.session.send_tool_response(
                                function_responses=fn_responses
                            )
                        except Exception as e:
                            print(f"[VECTOR] ⚠️  send_tool_response failed: {e}")
                            raise

        except asyncio.CancelledError:
            raise
        except Exception as e:
            err_str = str(e)
            _is_conn = (
                "1011" in err_str
                or "connection closed" in err_str.lower()
                or "going away" in err_str.lower()
                or "websocket" in type(e).__name__.lower()
                or "connectionclosed" in type(e).__name__.lower()
            )
            if _is_conn:
                # Mark disconnect and cancel siblings so the TaskGroup shuts
                # down cleanly.  Do NOT re-raise: that would create an
                # ExceptionGroup whose str() does not contain "1011", breaking
                # the outer reconnect check.
                self._session_failed = True
                print(f"[VECTOR] 🔌 Session closed (code 1011 / connection lost): {e}")
                for t in self._session_tasks:
                    if not t.done():
                        t.cancel()
                return
            print(f"[VECTOR] ❌ Recv error: {e}")
            traceback.print_exc()
            raise

    async def _play_audio(self):
        print("[VECTOR] 🔊 Play started")
        stream = await asyncio.to_thread(
            pya.open,
            format=FORMAT,
            channels=CHANNELS,
            rate=RECEIVE_SAMPLE_RATE,
            output=True,
        )
        try:
            while True:
                chunk = await self.audio_in_queue.get()
                await asyncio.to_thread(stream.write, chunk)
        except Exception as e:
            print(f"[VECTOR] ❌ Play error: {e}")
            raise
        finally:
            stream.close()

    async def run(self):
        global _active_vector
        _active_vector = self

        client = genai.Client(
            api_key=_get_api_key(),
            http_options={"api_version": "v1beta"}
        )

        _reconnect_count = 0
        _MAX_BACKOFF     = 30.0

        while True:
            try:
                print(
                    f"[VECTOR] 🔌 Connecting..."
                    + (f" (attempt {_reconnect_count + 1})" if _reconnect_count else "")
                )
                if hasattr(self.ui, 'set_connecting'):
                    self.ui.set_connecting()
                config = self._build_config()

                async with (
                    client.aio.live.connect(model=LIVE_MODEL, config=config) as session,
                    asyncio.TaskGroup() as tg,
                ):
                    self.session        = session
                    self.vector_loop    = asyncio.get_running_loop()
                    self._loop          = self.vector_loop  # backwards compat
                    self.audio_in_queue = asyncio.Queue()
                    self.out_queue      = asyncio.Queue(maxsize=10)
                    self.tool_call_in_progress = False
                    self._session_failed = False

                    print("[VECTOR] ✅ Connected.")
                    self.ui.write_log("V.E.C.T.O.R. online.")
                    _reconnect_count = 0  # reset on successful connection

                    if self.on_status_change:
                        try:
                            self.on_status_change("listening")
                        except Exception:
                            pass

                    self._session_tasks = [
                        tg.create_task(self._send_realtime()),
                        tg.create_task(self._listen_audio()),
                        tg.create_task(self._receive_audio()),
                        tg.create_task(self._play_audio()),
                    ]

            except asyncio.CancelledError:
                if not self._session_failed:
                    raise
                # _receive_audio detected a disconnect, cancelled the sibling
                # tasks, and returned cleanly.  The TaskGroup then cancelled the
                # parent task (us), delivering this CancelledError.  Absorb it
                # and reconnect instead of dying.
                asyncio.current_task().uncancel()
                _reconnect_count += 1
                backoff = min(2 ** (_reconnect_count - 1), _MAX_BACKOFF)
                print(
                    f"[VECTOR] 🔄 Connection lost — "
                    f"reconnect attempt {_reconnect_count} in {backoff:.0f}s"
                )
                if hasattr(self.ui, 'set_failed'):
                    self.ui.set_failed("Connection lost, reconnecting...")
                print(f"[VECTOR] 🔄 Reconnecting in {backoff:.0f}s...")
                await asyncio.sleep(backoff)

            except (KeyboardInterrupt, SystemExit):
                raise

            except BaseException as e:
                err_str = str(e)
                _is_1011 = (
                    self._session_failed   # our disconnect path
                    or "1011" in err_str
                    or "connection closed" in err_str.lower()
                    or "going away" in err_str.lower()
                )
                _reconnect_count += 1
                if _is_1011:
                    backoff = min(2 ** (_reconnect_count - 1), _MAX_BACKOFF)
                    print(
                        f"[VECTOR] 🔄 Connection lost (1011) — "
                        f"reconnect attempt {_reconnect_count} in {backoff:.0f}s"
                    )
                else:
                    backoff = 3.0
                    print(f"[VECTOR] ⚠️  Error: {e}")
                    traceback.print_exc()

                if hasattr(self.ui, 'set_failed'):
                    self.ui.set_failed(str(e)[:120])

                print(f"[VECTOR] 🔄 Reconnecting in {backoff:.0f}s...")
                await asyncio.sleep(backoff)


def main():
    ui = VectorUI("face.png")

    def runner():
        ui.wait_for_api_key()

        vector = VectorLive(ui)
        try:
            asyncio.run(vector.run())
        except KeyboardInterrupt:
            print("\n🔴 Shutting down...")

    threading.Thread(target=runner, daemon=True).start()
    ui.root.mainloop()


if __name__ == "__main__":
    main()
