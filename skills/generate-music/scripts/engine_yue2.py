"""YuE2 engine worker. Run only by generate_music.py, with the engine venv's python.

    <YUE2_HOME>/.venv/bin/python engine_yue2.py <out>/job.json

Reads the validated job, renders the song, optionally splits stems with Demucs,
writes audio in the requested formats and report.json. On any error it writes
failure.json and exits 1.
"""
from __future__ import annotations

import json
import sys
import time
import traceback
from pathlib import Path

import numpy as np
import soundfile as sf
import torch

SR = 48000
WRITE = {"flac": dict(format="FLAC", subtype="PCM_24"),
         "wav": dict(format="WAV", subtype="PCM_24"),
         "mp3": dict(format="MP3", subtype="MPEG_LAYER_III")}


def write_audio(base: Path, audio: np.ndarray, formats) -> dict:
    """audio: [samples, channels] float32. Returns {format: filename}."""
    audio = np.clip(audio, -1.0, 1.0).astype(np.float32)
    files = {}
    for fmt in formats:
        path = base.with_suffix("." + fmt)
        sf.write(path, audio, SR, **WRITE[fmt])
        files[fmt] = path.name
    return files


def level(audio: np.ndarray) -> dict:
    rms = float(np.sqrt(np.mean(np.square(audio, dtype=np.float64))))
    return {"rms_dbfs": round(20 * np.log10(max(rms, 1e-10)), 1),
            "peak_dbfs": round(20 * np.log10(max(float(np.abs(audio).max()), 1e-10)), 1)}


def separate(mix: np.ndarray, model_name: str) -> dict:
    """Demucs split of a [samples, 2] 48 kHz mix into vocals and accompaniment."""
    import julius
    from demucs.apply import apply_model
    from demucs.pretrained import get_model

    model = get_model(model_name).eval().cuda()
    wav = torch.from_numpy(mix.T.copy()).float()                    # [2, T]
    wav = julius.resample_frac(wav, SR, model.samplerate)
    ref = wav.mean(0)
    mean, std = ref.mean(), ref.std() + 1e-8
    with torch.inference_mode():
        out = apply_model(model, ((wav - mean) / std)[None].cuda(), device="cuda",
                          shifts=1, split=True, overlap=0.25, progress=False)[0]
    out = (out * std + mean).cpu()                                 # [sources, 2, T]
    sources = dict(zip(model.sources, out))
    vocals = sources.pop("vocals")
    accompaniment = sum(sources.values())
    stems = {}
    for name, wave in (("vocals", vocals), ("accompaniment", accompaniment)):
        wave = julius.resample_frac(wave, model.samplerate, SR)
        wave = torch.nn.functional.pad(wave, (0, max(0, mix.shape[0] - wave.shape[-1])))[..., :mix.shape[0]]
        stems[name] = wave.T.numpy()
    del model
    torch.cuda.empty_cache()
    return stems


def main(job_path: str) -> int:
    job = json.loads(Path(job_path).read_text(encoding="utf-8"))
    out = Path(job["out_dir"])
    home = Path(job["engine_home"])
    engine = json.loads((home / "engine.json").read_text())
    installed = json.loads((home / "INSTALLED.json").read_text())
    report = {"status": "running", "id": job["id"], "title": job.get("title"), "profile": job["profile"],
              "output": str(out), "style": job["style"], "cot": job["cot"], "seed": job["seed"],
              "score_supplied": bool(job["abc"]), "engine": {"name": "yue2", **engine,
              "yue_commit": installed["yue_commit"], "model_revision": installed["model"]["revision"],
              "vae_revision": installed["vae"]["revision"], "packages": installed["packages"]}}
    stage = "load"
    try:
        from yue2 import YuE2Pipeline
        t0 = time.perf_counter()
        torch.cuda.reset_peak_memory_stats()
        with YuE2Pipeline.from_pretrained(
                installed["model"]["path"], vae=installed["vae"]["path"], device="cuda",
                local_files_only=True, memory_budget_gib=engine["memory_budget_gib"],
                offload_ar=engine["offload_ar"], quantization=engine["quantization"],
                backend=engine.get("backend", "torch"),
                vae_core_frames=512 if engine["memory_budget_gib"] <= 12 else 1024) as pipe:
            stage = "generate"
            kwargs = dict(id=job["id"], style=job["style"], lyrics=job["lyrics"], cot=job["cot"], seed=job["seed"])
            if job["abc"]:
                kwargs["abc"] = job["abc"]
            song = pipe(**kwargs)
            stage = "save"
            receipt = song.save_artifacts(out / "yue2")
        report["peak_vram_gib"] = {"yue2": round(torch.cuda.max_memory_allocated() / 2**30, 2),
                                   "yue2_reserved": round(torch.cuda.max_memory_reserved() / 2**30, 2)}
        report["timing_seconds"] = {"yue2_total": round(time.perf_counter() - t0, 1),
                                    **{k: v for k, v in song.timing.items() if isinstance(v, (int, float))}}
        report["request_id"] = receipt["identity"]
        report["truncated_parts"] = song.truncated          # {"abc": bool, "semantic": bool}
        report["truncated"] = any(song.truncated.values())
        torch.cuda.empty_cache()

        mix = np.asarray(song.audio, dtype=np.float32)
        if mix.ndim == 1:
            mix = np.stack([mix, mix], axis=1)
        elif mix.shape[0] == 2 and mix.shape[1] != 2:
            mix = mix.T
        score = out / "yue2" / "score.abc"
        if score.is_file():
            (out / "score.abc").write_text(score.read_text(encoding="utf-8"), encoding="utf-8")
        files = {"mix": write_audio(out / "mix", mix, job["formats"])}
        levels = {"mix": level(mix)}

        if job["stems"]:
            stage = "stems"
            t1 = time.perf_counter()
            torch.cuda.reset_peak_memory_stats()
            for name, wave in separate(mix, engine.get("demucs_model", "htdemucs")).items():
                files[name] = write_audio(out / name, wave, job["formats"])
                levels[name] = level(wave)
            report["timing_seconds"]["stems"] = round(time.perf_counter() - t1, 1)
            report["peak_vram_gib"]["demucs"] = round(torch.cuda.max_memory_allocated() / 2**30, 2)

        report.update(status="complete", audio_seconds=round(mix.shape[0] / SR, 2),
                      score_nominal_seconds=job.get("score_nominal_seconds"),
                      files=files, levels=levels, has_score=(out / "score.abc").is_file())
        (out / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return 0
    except BaseException as exc:
        oom = isinstance(exc, torch.OutOfMemoryError)
        failure = {"status": "failed", "stage": stage, "type": type(exc).__name__, "reason": str(exc)[:2000],
                   "out_of_memory": oom, "engine": report["engine"],
                   "hint": ("out of GPU memory: close other GPU apps, or change engine.json "
                            "(offload_ar true, then quantization fp8) and record the change") if oom else None}
        (out / "failure.json").write_text(json.dumps(failure, indent=2) + "\n", encoding="utf-8")
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
