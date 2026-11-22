"""开发用：用 beat_this 对测试曲找节拍和强拍，结果存成 json（runs/beats-<ckpt>/<曲>.json），便于复用。
python -m bapu.dev_beats final0 L2-01 L3
"""
import json
import sys
import time
from pathlib import Path

import numpy as np
import librosa

ROOT = Path(__file__).resolve().parent.parent


def main():
    ckpt = sys.argv[1]
    pref = sys.argv[2:] or [""]
    from beat_this.inference import Audio2Beats
    f = Audio2Beats(checkpoint_path=ckpt, device="cpu", dbn=False)
    out = ROOT / "runs" / f"beats-{ckpt}"
    out.mkdir(parents=True, exist_ok=True)
    for s in sorted((ROOT / "test-songs").iterdir()):
        if not s.is_dir() or not any(s.name.startswith(p) for p in pref):
            continue
        t = time.time()
        y, sr = librosa.load(str(s / "audio.mp3"), sr=22050, mono=True)
        b, d = f(y, sr)
        b, d = np.asarray(b, float), np.asarray(d, float)
        idx = np.searchsorted(b, d - 0.03)
        bars = np.diff(idx)
        res = {"beats": b.tolist(), "downbeats": d.tolist(), "seconds": round(time.time() - t, 1),
               "bpm": round(60 / float(np.median(np.diff(b))), 1) if len(b) > 1 else None,
               "beats_per_bar_hist": np.bincount(bars).tolist() if len(bars) else []}
        (out / f"{s.name}.json").write_text(json.dumps(res), encoding="utf-8")
        print(s.name, res["bpm"], res["beats_per_bar_hist"], res["seconds"], flush=True)


if __name__ == "__main__":
    main()
