"""音频 → MIDI（钢琴转写，Transkun v2，CPU）。

不走 transkun 自带命令行：它用 pydub 读音频，需要 ffmpeg。这里用 librosa 直接解码 mp3/wav，
再调用 Transkun 模型。模型权重随 pip 包附带（transkun/pretrained/2.0.pt，约 56MB）。
"""
from __future__ import annotations

import time
from importlib import resources

import numpy as np
import librosa
import torch

_MODEL = None


def _load_model(device: str = "cpu"):
    global _MODEL
    if _MODEL is None:
        import moduleconf
        base = resources.files("transkun") / "pretrained"
        conf_mgr = moduleconf.parseFromFile(str(base / "2.0.conf"))
        TransKun = conf_mgr["Model"].module.TransKun
        model = TransKun(conf=conf_mgr["Model"].config).to(device)
        ckpt = torch.load(str(base / "2.0.pt"), map_location=device)
        model.load_state_dict(ckpt.get("best_state_dict", ckpt.get("state_dict")), strict=False)
        model.eval()
        _MODEL = model
    return _MODEL


def transcribe_melody(audio_path: str, out_mid: str) -> dict:
    """单旋律（长笛、小提琴、人声等非钢琴）：Spotify Basic Pitch（ONNX 模型，CPU），再整理成单声部。"""
    from basic_pitch import ICASSP_2022_MODEL_PATH
    from basic_pitch.inference import predict, Model
    from pathlib import Path
    t0 = time.time()
    onnx = Path(str(ICASSP_2022_MODEL_PATH)).with_suffix(".onnx")
    if not onnx.exists():
        onnx = Path(str(ICASSP_2022_MODEL_PATH)) / "nmp.onnx"
    _, pm, _ = predict(audio_path, Model(str(onnx)), onset_threshold=0.5, frame_threshold=0.3,
                       minimum_note_length=80, multiple_pitch_bends=False, melodia_trick=True)
    notes = sorted((n for i in pm.instruments for n in i.notes), key=lambda n: (n.start, -n.velocity))
    # 单声部：同时发声的音只留最响的；重叠时截断前一个音
    mono = []
    for n in notes:
        if mono and n.start - mono[-1].start < 0.05:
            if n.velocity > mono[-1].velocity:
                mono[-1] = n
            continue
        if mono and mono[-1].end > n.start:
            mono[-1].end = n.start
        mono.append(n)
    out = pretty_midi_from(mono)
    out.write(out_mid)
    return {"model": "basic-pitch", "seconds": round(time.time() - t0, 1), "n_notes": len(mono)}


def transcribe_mono_pyin(audio_path: str, out_mid: str) -> dict:
    """单旋律的经典做法：pYIN 基频跟踪 + 起音检测切分（同音反复靠起音检测分开）。"""
    import pretty_midi
    from scipy.ndimage import median_filter
    t0 = time.time()
    sr, hop = 22050, 256
    y, _ = librosa.load(audio_path, sr=sr, mono=True)
    f0, voiced, _ = librosa.pyin(y, fmin=65.0, fmax=2100.0, sr=sr, frame_length=2048, hop_length=hop)
    midi = np.where(voiced, np.round(librosa.hz_to_midi(np.nan_to_num(f0, nan=1.0))), -1).astype(int)
    midi = median_filter(midi, size=5)
    onset_env = librosa.onset.onset_strength(y=y, sr=sr, hop_length=hop)
    rms = librosa.feature.rms(y=y, frame_length=1024, hop_length=hop)[0]
    raw = librosa.onset.onset_detect(onset_envelope=onset_env, sr=sr, hop_length=hop, delta=0.2, wait=4)
    bt = librosa.onset.onset_backtrack(raw, rms)
    onsets = set(int(o) for o in raw)
    bt_times = np.array(sorted(bt)) * hop / sr
    notes, start, cur = [], None, -1
    for i in range(len(midi) + 1):
        m = midi[i] if i < len(midi) else -1
        boundary = (m != cur) or (i in onsets and m > 0)
        if boundary:
            if cur > 0 and start is not None and i - start >= 5:      # 至少约 58ms
                seg = slice(start, i)
                vel = int(np.clip(40 + 600 * float(rms[seg].mean()), 30, 120))
                notes.append(pretty_midi.Note(velocity=vel, pitch=int(cur),
                                              start=start * hop / sr, end=i * hop / sr))
            elif cur > 0 and notes and start is not None and notes[-1].pitch == cur:
                notes[-1].end = i * hop / sr                            # 太短的碎片并回前一个音
            start, cur = i, m
    # 合并：同音高、几乎无空隙、且中间没有起音的碎片
    merged = []
    for n in notes:
        short = min(n.end - n.start, merged[-1].end - merged[-1].start) < 0.12 if merged else False
        if merged and n.pitch == merged[-1].pitch and n.start - merged[-1].end < 0.03 and (
                short or not any(abs(o * hop / sr - n.start) < 0.03 for o in onsets)):
            merged[-1].end = n.end
        else:
            merged.append(n)
    # 延迟补偿：基频要稳定一会儿才判得出音高，把音头前移到最近的能量起点（最多 150ms）
    for i, n in enumerate(merged):
        cand = bt_times[(bt_times <= n.start + 0.02) & (bt_times >= n.start - 0.15)]
        if len(cand):
            s = float(cand.max())
            if i > 0:
                s = max(s, merged[i - 1].start + 0.05)
                merged[i - 1].end = min(merged[i - 1].end, s)
            n.start = s
    out = pretty_midi_from(merged)
    out.write(out_mid)
    return {"model": "pyin", "seconds": round(time.time() - t0, 1), "n_notes": len(merged)}


def pretty_midi_from(notes):
    import pretty_midi
    pm = pretty_midi.PrettyMIDI()
    inst = pretty_midi.Instrument(program=0)
    inst.notes = [pretty_midi.Note(velocity=int(n.velocity), pitch=int(n.pitch), start=float(n.start),
                                   end=float(n.end)) for n in notes]
    pm.instruments.append(inst)
    return pm


def transcribe_auto(audio_path: str, out_mid: str, mode: str = "auto") -> dict:
    """mode: piano / melody / auto。
    auto：钢琴模型（Transkun）和单旋律音高跟踪（pYIN）都跑。钢琴模型听出的音与 pYIN 吻合、
    或数量相当 → 是钢琴，用 Transkun；钢琴模型几乎没听出东西（长笛、小提琴、人声）→ 用 pYIN。"""
    if mode == "piano":
        return {"model": "transkun", **transcribe(audio_path, out_mid)}
    if mode == "melody":
        return transcribe_mono_pyin(audio_path, out_mid)
    import pretty_midi
    import mir_eval
    tmp_p, tmp_m = out_mid + ".piano.mid", out_mid + ".melody.mid"
    rp = transcribe(audio_path, tmp_p)
    rm = transcribe_mono_pyin(audio_path, tmp_m)

    def arr(path):
        ns = [(n.start, n.end, n.pitch) for i in pretty_midi.PrettyMIDI(path).instruments for n in i.notes]
        a = np.array(sorted(ns), dtype=float).reshape(-1, 3)
        return a[:, :2], mir_eval.util.midi_to_hz(a[:, 2])
    (pi, pp), (mi, mp) = arr(tmp_p), arr(tmp_m)
    if len(pp) == 0 or len(mp) == 0:
        rec = 0.0
    else:   # 旋律模型的音，有多少被钢琴模型也听到了
        _, rec, _, _ = mir_eval.transcription.precision_recall_f1_overlap(mi, mp, pi, pp, offset_ratio=None,
                                                                          onset_tolerance=0.1)
    import shutil
    import os
    choice = "transkun" if (rec >= 0.5 or len(pp) >= 0.6 * len(mp)) else "pyin"
    shutil.copy(tmp_p if choice == "transkun" else tmp_m, out_mid)
    os.remove(tmp_p)
    os.remove(tmp_m)
    return {"model": choice, "agreement": round(float(rec), 3), "piano": rp, "melody": rm}


def transcribe(audio_path: str, out_mid: str, device: str = "cpu") -> dict:
    from transkun.Data import writeMidi
    torch.set_grad_enabled(False)
    torch.set_num_threads(max(1, torch.get_num_threads()))
    model = _load_model(device)
    t0 = time.time()
    y, sr = librosa.load(audio_path, sr=model.fs, mono=False)
    if y.ndim == 1:
        y = np.stack([y, y])
    x = torch.from_numpy(np.ascontiguousarray(y.T, dtype=np.float32)).to(device)
    notes = model.transcribe(x, discardSecondHalf=False)
    writeMidi(notes).write(out_mid)
    return {"seconds": round(time.time() - t0, 1), "audio_seconds": round(y.shape[-1] / sr, 1),
            "n_notes": len(notes)}
