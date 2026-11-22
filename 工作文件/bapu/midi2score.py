"""MIDI（转写模型输出的音符事件）→ 可读的钢琴谱（MusicXML）。

步骤：
  1. 节拍跟踪：用音符起点构造 onset 包络，librosa 动态规划找拍点；速度稳定时拉直成匀速网格。
  2. 时间 → 拍位置：按拍点插值，每拍内在 16 分（4 等分）与三连音（3 等分）中选误差小的网格量化。
  3. 拍号与小节线：按每拍的“重音强度”（力度、低音、长音、和声变化）检验 2/3/4 拍周期和强拍相位。
  4. 调号：Krumhansl 调性分析（music21），并按调号拼写升降号。
  5. 左右手：逐个和弦动态切分，跟踪两手的音区中心，限制单手跨度。
  6. 输出：钢琴大谱表（高音/低音谱号 + 花括号），MusicXML。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from fractions import Fraction

import numpy as np
import pretty_midi
import librosa
from scipy.ndimage import gaussian_filter1d
from music21 import (stream, note, chord, meter, key as m21key, tempo, clef,
                     instrument, pitch as m21pitch, layout, metadata, duration)


@dataclass
class QNote:
    onset: Fraction      # 以四分音符为单位
    dur: Fraction
    pitch: int
    vel: int
    hand: int = 0        # 0 = 右手, 1 = 左手


@dataclass
class Analysis:
    bpm: float
    beats_per_bar: int
    downbeat_phase: int
    key_name: str
    key_sharps: int
    single_staff: bool
    beat_regular: bool
    info: dict = field(default_factory=dict)


# ---------------------------------------------------------------- 读取
def load_notes(path: str) -> np.ndarray:
    pm = pretty_midi.PrettyMIDI(path)
    rows = [(n.start, n.end, n.pitch, n.velocity)
            for inst in pm.instruments if not inst.is_drum for n in inst.notes]
    rows.sort()
    return np.array(rows, dtype=float)


# ---------------------------------------------------------------- 1. 节拍
FPS = 100


def onset_envelope(notes: np.ndarray) -> np.ndarray:
    T = notes[:, 1].max() + 2.0
    env = np.zeros(int(T * FPS) + 1)
    for s, e, p, v in notes:
        w = (0.4 + v / 127.0) * (1.6 if p < 55 else 1.0) * (1.0 + min(e - s, 1.0))
        env[int(round(s * FPS))] += w
    return gaussian_filter1d(env, 1.5)


def track_beats(notes: np.ndarray, start_bpm: float = 100.0):
    env = onset_envelope(notes)
    bpm, beats = librosa.beat.beat_track(onset_envelope=env, sr=FPS, hop_length=1,
                                         start_bpm=start_bpm, tightness=200, trim=False,
                                         units="time")
    beats = np.asarray(beats, dtype=float)
    if len(beats) < 4:
        b0 = float(np.atleast_1d(bpm)[0]) or 100.0
        ibi = 60.0 / b0
        beats = np.arange(0, notes[:, 1].max() + ibi, ibi)
    ibis = np.diff(beats)
    regular = bool(np.std(ibis) / np.mean(ibis) < 0.06)
    if regular:
        beats = straighten(beats)
    return extend_beats(beats, notes), regular


def straighten(beats):
    """匀速：用稳健线性拟合把拍点拉直，消除抖动。"""
    idx = np.arange(len(beats))
    a, b = np.polyfit(idx, beats, 1)
    resid = np.abs(beats - (a * idx + b))
    keep = resid < 0.25 * a
    a, b = np.polyfit(idx[keep], beats[keep], 1)
    return a * idx + b


def extend_beats(beats, notes):
    """前后补足拍点，覆盖第一个和最后一个音。"""
    first, last = notes[:, 0].min(), notes[:, 1].max()
    while beats[0] > first + 0.02:
        beats = np.insert(beats, 0, beats[0] - (beats[1] - beats[0]))
    while beats[-1] < last:
        beats = np.append(beats, beats[-1] + (beats[-1] - beats[-2]))
    return beats


def fix_tempo_octave(beats: np.ndarray, notes: np.ndarray) -> np.ndarray:
    """拍点太密（多数音间隔超过 2 拍）或太稀（多数音间隔不到 1/3 拍）时，减半/加倍。"""
    for _ in range(2):
        ibi = np.median(np.diff(beats))
        ioi = np.diff(np.unique(np.round(notes[:, 0], 2)))
        ioi = ioi[ioi > 0.03]
        if len(ioi) == 0:
            break
        med = np.median(ioi) / ibi
        bpm = 60 / ibi
        if (med < 0.3 and bpm < 160) or (bpm < 60 and med <= 0.6):   # 拍点太稀：插入中点
            mids = (beats[:-1] + beats[1:]) / 2
            beats = np.sort(np.concatenate([beats, mids]))
        elif (med > 1.6 and bpm > 50) or (bpm > 180 and med >= 0.9):  # 拍点太密：隔一取一
            beats = beats[::2]
        else:
            break
    return extend_beats(beats, notes)


# ---------------------------------------------------------------- 2. 量化
def to_beat_pos(t: np.ndarray, beats: np.ndarray) -> np.ndarray:
    idx = np.arange(len(beats), dtype=float)
    pos = np.interp(t, beats, idx)
    lo, hi = t < beats[0], t > beats[-1]
    pos[lo] = (t[lo] - beats[0]) / (beats[1] - beats[0])
    pos[hi] = len(beats) - 1 + (t[hi] - beats[-1]) / (beats[-1] - beats[-2])
    return pos


def quantize_onsets(pos: np.ndarray, triplets: bool = True) -> list:
    out = [None] * len(pos)
    beat_of = np.floor(pos + 1 / 8).astype(int)
    for b in np.unique(beat_of):
        sel = np.where(beat_of == b)[0]
        frac = pos[sel] - b
        q4 = np.round(frac * 4) / 4
        e4 = np.abs(frac - q4).mean()
        q3 = np.round(frac * 3) / 3
        e3 = np.abs(frac - q3).mean()
        has_mid3 = np.any(np.isin(np.round(q3 * 3) % 3, [1, 2]))
        use3 = triplets and len(sel) >= 2 and has_mid3 and e3 < 0.55 * e4
        for i, f in zip(sel, frac):
            if use3:
                out[i] = Fraction(int(b)) + Fraction(int(round(f * 3)), 3)
            else:
                out[i] = Fraction(int(b)) + Fraction(int(round(f * 4)), 4)
    return out


def quantize_dur(on_q: Fraction, end_pos: float) -> Fraction:
    grid = 3 if on_q.denominator == 3 else 4
    end_q = Fraction(int(round(end_pos * grid)), grid)
    d = end_q - on_q
    if d <= 0:
        d = Fraction(1, grid)
    return d


# ---------------------------------------------------------------- 3. 拍号
def _z(x):
    sd = x.std()
    return (x - x.mean()) / sd if sd > 1e-9 else x * 0


def beat_features(qnotes, nbeats: int) -> dict:
    """每拍的几种“强拍线索”。"""
    L = nbeats + 8
    onset = np.zeros(L)      # 该拍上的起音数量（带力度）
    bass = np.zeros(L)       # 低音换音
    land = np.zeros(L)       # 长音之后落下的音（长音通常在小节末结束）
    harm = np.zeros(L)       # 和声变化
    pcs = [set() for _ in range(L)]
    lowest = np.full(L, 999)
    for n in qnotes:
        b = int(np.floor(float(n.onset)))
        if not (0 <= b < L):
            continue
        pcs[b].add(n.pitch % 12)
        if n.onset.denominator == 1:
            onset[b] += 0.3 + n.vel / 127
            lowest[b] = min(lowest[b], n.pitch)
    ons = sorted({n.onset for n in qnotes})
    maxdur = {}
    for n in qnotes:
        maxdur[n.onset] = max(maxdur.get(n.onset, 0), n.dur)
    for i in range(len(ons) - 1):
        gap = ons[i + 1] - ons[i]
        nxt = ons[i + 1]
        if gap >= Fraction(3, 2) and nxt.denominator == 1 and int(nxt) < L:
            land[int(nxt)] += float(min(gap, 4))
    prev_low = None
    for b in range(L):
        if lowest[b] < 999:
            if prev_low is None or lowest[b] != prev_low:
                bass[b] += 1.0 if lowest[b] < 60 else 0.3
            prev_low = lowest[b]
    for b in range(1, L):
        if pcs[b] and pcs[b - 1]:
            harm[b] = len(pcs[b] ^ pcs[b - 1]) / max(len(pcs[b] | pcs[b - 1]), 1)
    return {"onset": onset, "bass": bass, "land": land, "harm": harm}


def detect_meter(feats: dict, first_beat: int):
    W = {"onset": 0.5, "bass": 1.0, "land": 1.2, "harm": 1.0}
    strength = sum(W[k] * _z(v) for k, v in feats.items())
    scores = {}
    for M in (2, 3, 4):
        for ph in range(M):
            on = strength[ph::M]
            off = np.delete(strength, np.arange(ph, len(strength), M))
            c = (on.mean() - off.mean()) / (strength.std() + 1e-9)
            # 先验：乐曲多从强拍开始（或弱起），给“第一个音在强拍”的相位加一点分
            if (first_beat - ph) % M == 0:
                c += 0.15
            scores[(M, ph)] = float(c)
    # 2/4 与 4/4 难分：统一按 4 拍比较，再看前后半小节是否一样强
    c3 = max((scores[(3, p)], p) for p in range(3))
    c4 = max((scores[(4, p)], p) for p in range(4))
    c2 = max((scores[(2, p)], p) for p in range(2))
    if c3[0] > max(c4[0], c2[0]) * 1.1:
        return 3, c3[1], scores
    if c2[0] > c4[0] * 1.15:
        # 4 拍里取与 2 拍相位一致、且更强的那个
        cands = [p for p in range(4) if p % 2 == c2[1]]
        # 两个候选只差半小节，证据通常很弱：再偏向“第一个音落在强拍”的那个
        p = max(cands, key=lambda q: scores[(4, q)] + 0.25 * ((first_beat - q) % 4 == 0))
        return 4, p, scores
    return 4, c4[1], scores


# ---------------------------------------------------------------- 4. 调号
def detect_key(qnotes):
    s = stream.Stream()
    for n in qnotes:
        x = note.Note(n.pitch)
        x.quarterLength = float(min(n.dur, 4))
        s.insert(float(n.onset), x)
    return s.analyze("key")


def _set_name(midi: int, name: str) -> m21pitch.Pitch:
    p = m21pitch.Pitch(name)
    p.octave = 4
    p.octave = 4 + (midi - p.midi) // 12
    if p.midi != midi:  # 舍入误差兜底
        p = m21pitch.Pitch(midi=midi)
    return p


def spell(midi: int, k) -> m21pitch.Pitch:
    scale = {pp.pitchClass: pp.name for pp in k.getScale(k.mode).getPitches("C4", "C5")}
    pc = midi % 12
    if pc in scale:
        return _set_name(midi, scale[pc])
    if k.mode == "minor" and pc == (k.tonic.pitchClass + 11) % 12:
        return _set_name(midi, k.tonic.transpose(-1).name)     # 小调导音
    p = m21pitch.Pitch(midi=midi)
    if k.sharps < 0 and p.accidental is not None and p.accidental.name == "sharp":
        p = p.getEnharmonic()
    elif k.sharps > 0 and p.accidental is not None and p.accidental.name == "flat":
        p = p.getEnharmonic()
    return p


# ---------------------------------------------------------------- 5. 左右手
def is_monophonic(qnotes) -> bool:
    by_on = {}
    for n in qnotes:
        by_on.setdefault(n.onset, []).append(n)
    multi = sum(1 for v in by_on.values() if len(v) > 1)
    return multi / max(len(by_on), 1) < 0.1


def split_hands(qnotes):
    groups = {}
    for n in qnotes:
        groups.setdefault(n.onset, []).append(n)
    rh_c, lh_c = 67.0, 48.0
    active = []                                  # 仍在发声的已分配音
    for on in sorted(groups):
        active = [n for n in active if n.onset + n.dur > on]
        held_l = [n.pitch for n in active if n.hand == 1]
        held_r = [n.pitch for n in active if n.hand == 0]
        g = sorted(groups[on], key=lambda n: n.pitch)
        ps = [n.pitch for n in g]
        best = None
        for j in range(len(g) + 1):
            lo, hi = ps[:j], ps[j:]
            L, R = lo + held_l, hi + held_r       # 同一时刻两手实际要按的音
            cost = 0.0
            if lo:
                cost += abs(np.mean(lo) - lh_c) + 0.5 * max(0, max(lo) - 64)
            if hi:
                cost += abs(np.mean(hi) - rh_c) + 0.5 * max(0, 55 - min(hi))
            for H in (L, R):
                if H:
                    cost += 30 * (max(H) - min(H) > 14) + 30 * (len(H) > 5) + 3 * max(0, len(H) - 3)
            # 优先在音程空隙最大的地方分手（旋律与伴奏之间通常隔得最开）
            if lo and hi:
                cost -= 0.6 * (hi[0] - lo[-1])
            # 整组都给左手时，最高音若明显高于左手音区，多半是右手旋律
            if lo and not hi:
                cost += 0.8 * max(0, max(lo) - lh_c - 5)
            if hi and not lo:
                cost += 0.8 * max(0, rh_c - min(hi) - 5)
            # 声部交叉：新给左手的音高于右手正在按的音，或反之
            if lo and held_r:
                cost += 4 * sum(1 for p in lo if p > min(held_r))
            if hi and held_l:
                cost += 4 * sum(1 for p in hi if p < max(held_l))
            if best is None or cost < best[0]:
                best = (cost, j)
        j = best[1]
        for i, n in enumerate(g):
            n.hand = 1 if i < j else 0
        active += g
        if j > 0:
            lh_c = 0.7 * lh_c + 0.3 * np.mean(ps[:j])
        if j < len(g):
            rh_c = 0.7 * rh_c + 0.3 * np.mean(ps[j:])
        if rh_c - lh_c < 7:
            mid = (rh_c + lh_c) / 2
            rh_c, lh_c = mid + 3.5, mid - 3.5


# ---------------------------------------------------------------- 6. 生成谱面
def hand_to_events(notes):
    """同一手内：同起点的音合成和弦；时值截到下一个起点，避免声部重叠。"""
    groups = {}
    for n in notes:
        groups.setdefault(n.onset, []).append(n)
    ons = sorted(groups)
    ev = []
    for i, on in enumerate(ons):
        g = groups[on]
        d = max(n.dur for n in g)
        if i + 1 < len(ons):
            ioi = ons[i + 1] - on
            d = min(d, ioi)
            # 连奏假设：与下一个音之间的小空隙（< 半拍且 < 间隔的一半）补满，避免满屏碎休止符
            if ioi - d <= Fraction(1, 2) and (ioi - d) * 2 <= ioi:
                d = ioi
        ev.append((on, d, sorted({n.pitch for n in g})))
    return ev


def build_part(events, k, ts_num, total_len, part_clef, name, mark_bpm=None):
    p = stream.PartStaff()
    p.partName = name
    p.insert(0, part_clef)
    p.insert(0, m21key.KeySignature(k.sharps))
    p.insert(0, meter.TimeSignature(f"{ts_num}/4"))
    if mark_bpm:
        p.insert(0, tempo.MetronomeMark(number=round(mark_bpm)))
    for on, d, ps in events:
        if len(ps) == 1:
            x = note.Note(spell(ps[0], k))
        else:
            x = chord.Chord([spell(q, k) for q in ps])
        x.duration = duration.Duration(d)
        p.insert(on, x)
    # 用休止符补满所有空隙（含开头和结尾），否则谱面上会“缺拍”
    t = Fraction(0)
    for on, d, _ in sorted(events) + [(total_len, Fraction(0), None)]:
        if on > t:
            r = note.Rest()
            r.duration = duration.Duration(on - t)
            p.insert(t, r)
        t = max(t, on + d)
    return p


def choose_clef(events):
    ps = [q for _, _, g in events for q in g]
    return clef.TrebleClef() if not ps or np.median(ps) >= 57 else clef.BassClef()


def meter_from_downbeats(beats: np.ndarray, downbeats: np.ndarray):
    """用音频模型给的强拍时间推出每小节几拍、强拍落在第几拍。"""
    if downbeats is None or len(downbeats) < 3:
        return None
    idx = np.array([int(np.argmin(np.abs(beats - d))) for d in downbeats])
    idx = np.unique(idx)
    gaps = np.diff(idx)
    gaps = gaps[(gaps >= 2) & (gaps <= 6)]
    if len(gaps) == 0:
        return None
    M = int(np.bincount(gaps).argmax())
    if M not in (2, 3, 4, 6):
        return None
    if M == 6:              # 6 拍一小节多半是 6/8 或 2 个 3 拍，记成 3 拍、相位不变
        M = 3
    ph = int(np.bincount(idx % M, minlength=M).argmax())
    return M, ph


def transcribe_to_score(midi_path: str, title: str = "", triplets: bool = True,
                        beats_ext=None, downbeats_ext=None):
    """beats_ext / downbeats_ext：音频节拍模型（beat_this）给出的节拍、强拍时间（秒）。
    给了就用它们定节拍网格和小节线；不给就从音符本身推断（适合速度稳定的曲子）。"""
    notes = load_notes(midi_path)
    if beats_ext is not None and len(beats_ext) >= 8:
        beats = np.asarray(beats_ext, dtype=float)
        ibis = np.diff(beats)
        regular = bool(np.std(ibis) / np.mean(ibis) < 0.06)
        beats = extend_beats(beats, notes)
    else:
        beats, regular = track_beats(notes)
        beats = fix_tempo_octave(beats, notes)
    pos_on = to_beat_pos(notes[:, 0], beats)
    pos_off = to_beat_pos(notes[:, 1], beats)
    on_q = quantize_onsets(pos_on, triplets=triplets)
    qnotes = [QNote(o, quantize_dur(o, e), int(p), int(v))
              for o, e, p, v in zip(on_q, pos_off, notes[:, 2], notes[:, 3])]
    seen, uniq = set(), []
    for n in qnotes:                       # 去重（同起点同音高）
        if (n.onset, n.pitch) not in seen:
            seen.add((n.onset, n.pitch))
            uniq.append(n)
    qnotes = uniq

    nbeats = int(max(n.onset for n in qnotes)) + 1
    first_beat = int(np.floor(float(min(n.onset for n in qnotes))))
    M, ph, mscores = detect_meter(beat_features(qnotes, nbeats), first_beat)
    meter_src = "notes"
    ext = meter_from_downbeats(beats, np.asarray(downbeats_ext, float)) if downbeats_ext is not None else None
    if ext:
        M, ph = ext
        meter_src = "audio_downbeats"
    # 小节线在原音频里的时间（测评用）
    bar_times = [float(beats[b]) for b in range(len(beats)) if (b - ph) % M == 0]
    # 让检测到的强拍落在小节线上，再去掉开头整小节的空白
    shift = Fraction((M - ph) % M)
    first = min(n.onset for n in qnotes)
    shift -= int((first + shift) // M) * M
    for n in qnotes:
        n.onset += shift

    k = detect_key(qnotes)
    single = is_monophonic(qnotes)
    if not single:
        split_hands(qnotes)

    total = max(n.onset + n.dur for n in qnotes)
    total_len = Fraction(int(np.ceil(float(total) / M)) * M)
    bpm = 60.0 / float(np.median(np.diff(beats)))

    sc = stream.Score()
    sc.insert(0, metadata.Metadata())
    sc.metadata.title = title or "Transcription"
    sc.metadata.composer = "auto-transcribed (bapu)"
    if single:
        ev = hand_to_events(qnotes)
        part = build_part(ev, k, M, total_len, choose_clef(ev), "Melody", bpm)
        part.insert(0, instrument.Piano())
        sc.insert(0, part)
    else:
        rh = [n for n in qnotes if n.hand == 0]
        lh = [n for n in qnotes if n.hand == 1]
        p1 = build_part(hand_to_events(rh), k, M, total_len, clef.TrebleClef(), "Piano", bpm)
        p2 = build_part(hand_to_events(lh), k, M, total_len, clef.BassClef(), "")
        p1.insert(0, instrument.Piano())
        sc.insert(0, p1)
        sc.insert(0, p2)
        sc.insert(0, layout.StaffGroup([p1, p2], name="Piano", abbreviation="Pno.",
                                       symbol="brace", barTogether=True))
    ana = Analysis(bpm=bpm, beats_per_bar=M, downbeat_phase=ph,
                   key_name=f"{k.tonic.name} {k.mode}", key_sharps=k.sharps,
                   single_staff=single, beat_regular=regular,
                   info={"meter_scores": {f"{a}/{b}": round(c, 3) for (a, b), c in mscores.items()},
                         "n_notes": len(qnotes), "n_beats": int(len(beats)), "meter_source": meter_src,
                         "beat_times": [round(float(b), 3) for b in beats],
                         "bar_times": [round(t, 3) for t in bar_times]})
    return sc, qnotes, ana
