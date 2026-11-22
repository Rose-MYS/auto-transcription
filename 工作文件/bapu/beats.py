"""音频 → 节拍 + 强拍（beat_this，CPJKU，MIT 许可，CPU）。真人演奏速度会变，靠音频模型跟拍比从音符硬推更稳。"""
from __future__ import annotations

import time

import numpy as np
import librosa

_MODEL = {}


def audio_beats(audio_path: str, ckpt: str = "final0") -> dict:
    from beat_this.inference import Audio2Beats
    if ckpt not in _MODEL:
        _MODEL[ckpt] = Audio2Beats(checkpoint_path=ckpt, device="cpu", dbn=False)
    t0 = time.time()
    y, sr = librosa.load(audio_path, sr=22050, mono=True)
    b, d = _MODEL[ckpt](y, sr)
    return {"beats": np.asarray(b, float).tolist(), "downbeats": np.asarray(d, float).tolist(),
            "model": f"beat_this-{ckpt}", "seconds": round(time.time() - t0, 1)}
