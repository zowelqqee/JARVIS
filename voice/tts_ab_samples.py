"""A/B sample generation helpers for local TTS model selection."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import shutil
import subprocess
from typing import Iterable


DEFAULT_RU_SAMPLE_PHRASES: tuple[str, ...] = (
    "Не понял, что ты имел в виду.",
    "Сейчас проверю состояние системы и вернусь с коротким ответом.",
    "Открой, пожалуйста, папку с проектом и покажи последние изменения.",
    "Если хочешь, я могу объяснить это проще и без технических деталей.",
    "Я вижу проблему: русский голос звучит натурально, но с заметным акцентом.",
    "Команда выполнена, но для следующего шага нужно подтвердить разрешения.",
    "Сравним несколько голосов на одних и тех же фразах, чтобы выбрать лучший.",
    "JARVIS готов продолжать работу, когда ты скажешь следующую команду.",
)


@dataclass(frozen=True)
class PiperABCandidate:
    """One local Piper model candidate for voice A/B listening."""

    key: str
    display_name: str
    model_path: Path
    config_path: Path | None


@dataclass(frozen=True)
class PiperABSampleResult:
    """One rendered sample result."""

    candidate_key: str
    phrase_index: int
    phrase: str
    output_path: Path
    command: tuple[str, ...]
    ok: bool
    error: str = ""


@dataclass(frozen=True)
class PiperABRunResult:
    """Summary for one A/B sample rendering run."""

    output_dir: Path
    manifest_path: Path
    candidates: tuple[PiperABCandidate, ...]
    results: tuple[PiperABSampleResult, ...]

    @property
    def ok(self) -> bool:
        return all(result.ok for result in self.results)


def repo_root_from_path(path: Path | None = None) -> Path:
    """Return the repository root relative to this module or an explicit path."""

    if path is not None:
        return path.resolve()
    return Path(__file__).resolve().parents[1]


def default_piper_runtime_root(repo_root: Path | None = None) -> Path:
    """Return the repo-local Piper runtime root."""

    return repo_root_from_path(repo_root) / "tmp" / "runtime" / "piper"


def default_ab_output_dir(repo_root: Path | None = None) -> Path:
    """Return the default output directory for generated A/B samples."""

    return repo_root_from_path(repo_root) / "tmp" / "qa" / "tts_ru_ab_samples" / "latest"


def discover_ru_piper_candidates(runtime_root: Path) -> tuple[PiperABCandidate, ...]:
    """Find configured local Russian Piper models available for A/B listening."""

    model_dir = runtime_root / "models"
    if not model_dir.exists():
        return ()
    candidates: list[PiperABCandidate] = []
    for model_path in sorted(model_dir.glob("ru*.onnx")):
        key = _candidate_key(model_path)
        candidates.append(
            PiperABCandidate(
                key=key,
                display_name=_candidate_display_name(model_path, key),
                model_path=model_path,
                config_path=_model_config_path(model_path),
            )
        )
    return tuple(sorted(candidates, key=lambda candidate: candidate.key))


def resolve_piper_binary(runtime_root: Path, explicit_binary: str | None = None) -> Path | None:
    """Resolve a Piper executable from an override, repo-local runtime, or PATH."""

    if explicit_binary:
        candidate = Path(explicit_binary).expanduser()
        if candidate.exists():
            return candidate
    for relative_path in (Path("venv/bin/piper"), Path("bin/piper"), Path("piper")):
        candidate = runtime_root / relative_path
        if candidate.exists():
            return candidate
    path_candidate = shutil.which("piper")
    if path_candidate:
        return Path(path_candidate)
    return None


def render_ru_ab_samples(
    *,
    runtime_root: Path,
    output_dir: Path,
    phrases: Iterable[str] = DEFAULT_RU_SAMPLE_PHRASES,
    candidate_keys: Iterable[str] | None = None,
    piper_binary: str | None = None,
    timeout_seconds: float = 45.0,
) -> PiperABRunResult:
    """Render raw Russian WAV samples for model A/B listening."""

    binary_path = resolve_piper_binary(runtime_root, piper_binary)
    if binary_path is None:
        raise RuntimeError(f"Piper binary was not found for runtime root: {runtime_root}")

    candidates = discover_ru_piper_candidates(runtime_root)
    selected_candidates = _filter_candidates(candidates, candidate_keys)
    if not selected_candidates:
        raise RuntimeError(f"No Russian Piper candidates were found in: {runtime_root / 'models'}")

    phrase_list = tuple(phrase.strip() for phrase in phrases if phrase.strip())
    if not phrase_list:
        raise RuntimeError("No sample phrases were provided.")

    output_dir.mkdir(parents=True, exist_ok=True)
    results: list[PiperABSampleResult] = []
    for candidate in selected_candidates:
        candidate_dir = output_dir / candidate.key
        candidate_dir.mkdir(parents=True, exist_ok=True)
        for index, phrase in enumerate(phrase_list, start=1):
            output_path = candidate_dir / f"{index:02d}.wav"
            command = [str(binary_path), "--model", str(candidate.model_path)]
            if candidate.config_path is not None:
                command.extend(["--config", str(candidate.config_path)])
            command.extend(["--output_file", str(output_path)])
            completed = subprocess.run(
                command,
                input=phrase,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=timeout_seconds,
                check=False,
            )
            results.append(
                PiperABSampleResult(
                    candidate_key=candidate.key,
                    phrase_index=index,
                    phrase=phrase,
                    output_path=output_path,
                    command=tuple(command),
                    ok=completed.returncode == 0,
                    error=_first_meaningful_line(completed.stderr or completed.stdout),
                )
            )

    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            _manifest_payload(
                runtime_root=runtime_root,
                piper_binary=binary_path,
                candidates=selected_candidates,
                results=tuple(results),
            ),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return PiperABRunResult(
        output_dir=output_dir,
        manifest_path=manifest_path,
        candidates=selected_candidates,
        results=tuple(results),
    )


def _filter_candidates(
    candidates: tuple[PiperABCandidate, ...],
    candidate_keys: Iterable[str] | None,
) -> tuple[PiperABCandidate, ...]:
    requested = tuple(str(key or "").strip().lower() for key in candidate_keys or () if str(key or "").strip())
    if not requested:
        return candidates
    by_key = {candidate.key: candidate for candidate in candidates}
    missing = [key for key in requested if key not in by_key]
    if missing:
        known = ", ".join(sorted(by_key)) or "none"
        raise RuntimeError(f"Unknown candidate key(s): {', '.join(missing)}. Known candidates: {known}")
    return tuple(by_key[key] for key in requested)


def _candidate_key(model_path: Path) -> str:
    stem = model_path.stem.lower()
    if stem == "ru_male":
        return "dmitri"
    for prefix in ("ru_male_", "ru_"):
        if stem.startswith(prefix):
            return stem.removeprefix(prefix)
    return stem


def _candidate_display_name(model_path: Path, key: str) -> str:
    manifest_name = _sidecar_display_name(model_path)
    if manifest_name:
        return manifest_name
    if key == "dmitri":
        return "Russian Male (Dmitri)"
    return f"Russian Male ({key.capitalize()})"


def _sidecar_display_name(model_path: Path) -> str:
    sidecar_path = _model_config_path(model_path)
    if sidecar_path is None:
        return ""
    try:
        payload = json.loads(sidecar_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, IsADirectoryError, PermissionError, json.JSONDecodeError, OSError):
        return ""
    for key in ("display_name", "name", "speaker", "speaker_name"):
        value = str(payload.get(key, "") or "").strip()
        if value:
            return value
    return ""


def _model_config_path(model_path: Path) -> Path | None:
    for config_path in (Path(f"{model_path}.json"), model_path.with_suffix(".json")):
        if config_path.exists():
            return config_path
    return None


def _first_meaningful_line(output: str | None) -> str:
    for line in str(output or "").splitlines():
        candidate = line.strip()
        if candidate:
            return candidate
    return ""


def _manifest_payload(
    *,
    runtime_root: Path,
    piper_binary: Path,
    candidates: tuple[PiperABCandidate, ...],
    results: tuple[PiperABSampleResult, ...],
) -> dict[str, object]:
    return {
        "runtime_root": str(runtime_root),
        "piper_binary": str(piper_binary),
        "candidates": [
            {
                "key": candidate.key,
                "display_name": candidate.display_name,
                "model_path": str(candidate.model_path),
                "config_path": str(candidate.config_path) if candidate.config_path else None,
            }
            for candidate in candidates
        ],
        "samples": [
            {
                "candidate_key": result.candidate_key,
                "phrase_index": result.phrase_index,
                "phrase": result.phrase,
                "output_path": str(result.output_path),
                "command": list(result.command),
                "ok": result.ok,
                "error": result.error,
            }
            for result in results
        ],
    }
