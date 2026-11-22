"""测评：
  A. 音符级（转写准不准）：mir_eval，起点容差 50ms，F1（只看起点+音高）和 F1（含时值，offset_ratio=0.2）。
  B. 谱面级（谱子对不对，仅 L1/L2 有 answer.musicxml）：
     - 调号、拍号是否一致
     - 谱面音符 F1：按（第几拍、音高）匹配。允许整体平移（弱起处理不同）和拍速 2 倍/0.5 倍（记为“拍子层级错”）
     - 强拍对齐：最佳平移是否是整小节（= 小节线位置对不对）
     - 时值准确率、左右手准确率（在匹配上的音符里）
  C. L3 只有 MIDI 答案：调号/拍号对照 META 里的已知信息。
"""
from __future__ import annotations

from fractions import Fraction

import numpy as np
import mir_eval
import pretty_midi
from music21 import converter, key as m21key, meter

# L3 曲目的已知调号/拍号（来自乐谱）
META = {
    "L3-01": {"key_sharps": 0, "ts": "4/4"},     # BWV 846 C 大调
    "L3-02": {"key_sharps": 1, "ts": "3/4"},     # 格里格圆舞曲 e 小调
    "L3-03": {"key_sharps": -1, "ts": "3/8"},    # 斯卡拉蒂 K.525 F 大调
    "L3-04": {"key_sharps": -4, "ts": "2/4"},    # 舒伯特 f 小调
    "L3-05": {"key_sharps": -3, "ts": "12/8"},   # 肖邦 降 E 大调
}


def _notes(path):
    pm = pretty_midi.PrettyMIDI(path)
    rows = [(n.start, max(n.end, n.start + 0.01), n.pitch)
            for i in pm.instruments if not i.is_drum for n in i.notes]
    a = np.array(sorted(rows), dtype=float).reshape(-1, 3)
    return a[:, :2], mir_eval.util.midi_to_hz(a[:, 2])


def note_metrics(ref_mid: str, est_mid: str) -> dict:
    ri, rp = _notes(ref_mid)
    ei, ep = _notes(est_mid)
    if len(ep) == 0:
        return {"P": 0.0, "R": 0.0, "F1": 0.0, "F1_with_offset": 0.0, "n_ref": len(rp), "n_est": 0}
    p, r, f, _ = mir_eval.transcription.precision_recall_f1_overlap(ri, rp, ei, ep, offset_ratio=None)
    p2, r2, f2, _ = mir_eval.transcription.precision_recall_f1_overlap(ri, rp, ei, ep)
    return {"P": round(p, 3), "R": round(r, 3), "F1": round(f, 3), "F1_with_offset": round(f2, 3),
            "n_ref": len(rp), "n_est": len(ep)}


def score_notes(sc):
    sc = sc.stripTies()
    parts = list(sc.parts)
    # 弱起小节：把位置换算成“从一个完整小节开头算起”，这样两份谱的小节线位置可以直接比
    pad = Fraction(0)
    ms = parts[0].getElementsByClass("Measure") if parts else []
    if len(ms) > 1:
        m1 = ms[0]
        short = Fraction(m1.barDuration.quarterLength).limit_denominator(48) - \
            Fraction(ms[1].offset - m1.offset).limit_denominator(48)
        if short > 0:
            pad = short
    out = []
    for si, p in enumerate(parts):
        for n in p.flatten().notes:
            for pp in n.pitches:
                out.append((Fraction(n.offset).limit_denominator(48) + pad, pp.midi, si,
                            Fraction(n.quarterLength).limit_denominator(48)))
    ks = sc.recurse().getElementsByClass(m21key.KeySignature).first()
    ts = sc.recurse().getElementsByClass(meter.TimeSignature).first()
    return out, (ks.sharps if ks else 0), (ts.ratioString if ts else "4/4"), len(parts)


def score_metrics(ref_xml: str, est_sc) -> dict:
    ref = converter.parse(ref_xml)
    rn, rks, rts, rparts = score_notes(ref)
    en, eks, ets, eparts = score_notes(est_sc)
    if rparts == 4 and eparts == 2:          # 四声部合唱谱：S/A → 右手，T/B → 左手
        rn = [(o, p, s // 2, d) for o, p, s, d in rn]
        rparts = 2
    rset = {(o, p) for o, p, _, _ in rn}
    rinfo = {(o, p): (s, d) for o, p, s, d in rn}
    best = (-1, None, None)
    for scale in (Fraction(1), Fraction(1, 2), Fraction(2)):
        for k in range(-64, 65):
            sh = Fraction(k, 4)
            m = sum(1 for o, p, _, _ in en if (o * scale + sh, p) in rset)
            if m > best[0] or (m == best[0] and scale == 1 and best[1] != 1):
                best = (m, scale, sh)
    m, scale, sh = best
    f1 = 2 * m / (len(rn) + len(en)) if rn and en else 0.0
    bar = Fraction(meter.TimeSignature(rts).barDuration.quarterLength).limit_denominator(48)
    dur_ok = hand_ok = 0
    for o, p, s, d in en:
        key = (o * scale + sh, p)
        if key in rinfo:
            rs, rd = rinfo[key]
            dur_ok += (d * scale == rd)
            if rparts == eparts:
                hand_ok += (s == rs)
    return {
        "key_ok": rks == eks, "ref_key_sharps": rks, "est_key_sharps": eks,
        "ts_ok": rts == ets, "ref_ts": rts, "est_ts": ets,
        "score_note_F1": round(f1, 3),
        "beat_level": "ok" if scale == 1 else f"x{scale}",
        "downbeat_ok": bool(scale == 1 and rts == ets and (sh % bar) == 0),
        "dur_acc": round(dur_ok / m, 3) if m else 0.0,
        "hand_acc": (round(hand_ok / m, 3) if m and rparts == eparts else None),
        "staves_ref_est": f"{rparts}/{eparts}",
    }


def meta_metrics(song_id: str, ana) -> dict:
    meta = META.get(song_id[:5])
    if not meta:
        return {}
    num = int(meta["ts"].split("/")[0])
    # 3/8 → 3 拍，12/8 → 4 个附点四分拍，2/4 ↔ 4/4 视为同类
    accept = {num, {12: 4, 6: 2, 9: 3}.get(num, num)}
    if num in (2, 4):
        accept |= {2, 4}
    return {"key_ok": ana.key_sharps == meta["key_sharps"], "ref_key_sharps": meta["key_sharps"],
            "est_key_sharps": ana.key_sharps, "ref_ts": meta["ts"], "est_ts": f"{ana.beats_per_bar}/4",
            "meter_ok": ana.beats_per_bar in accept}
