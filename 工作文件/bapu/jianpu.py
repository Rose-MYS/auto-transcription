"""MusicXML（music21 Score）→ 简谱（主旋律）。

输出 jianpu-ly 语法的文本（https://github.com/ssb22/jianpu-ly），装了 jianpu-ly + LilyPond 即可排出 PDF；
同时文本本身也能直接看。只取右手（或单旋律谱）每个时刻的最高音作为旋律。

jianpu-ly 时值写法：四分 `1`，八分 `q1`，十六分 `s1`，附点 `1.`，二分 `1 -`，全音符 `1 - - -`，休止 `0`；
高八度 `1'`，低八度 `1,`。
"""
from __future__ import annotations

from music21 import key as m21key, note, chord, stream

DEG_SHARP = ["1", "#1", "2", "#2", "3", "4", "#4", "5", "#5", "6", "#6", "7"]
DEG_FLAT = ["1", "b2", "2", "b3", "3", "4", "#4", "5", "b6", "6", "b7", "7"]


def _degree(midi: int, tonic_midi: int, flats: bool) -> str:
    d = midi - tonic_midi
    octv, step = divmod(d, 12)
    s = (DEG_FLAT if flats else DEG_SHARP)[step]
    return s + ("'" * octv if octv > 0 else "," * (-octv))


def _dur_tokens(sym: str, ql: float) -> list[str]:
    table = {4.0: [sym, "-", "-", "-"], 3.0: [sym, "-", "-"], 2.0: [sym, "-"],
             1.5: [sym + "."], 1.0: [sym], 0.75: ["q" + sym + "."], 0.5: ["q" + sym],
             0.25: ["s" + sym]}
    ql = round(ql * 4) / 4
    if ql in table:
        return table[ql]
    out, rest = [], ql
    first = True
    for v in (4.0, 2.0, 1.0, 0.5, 0.25):        # 拆成可写的时值，后续部分用延音线 ~ 连接
        while rest >= v - 1e-6:
            toks = table[v] if first or sym == "0" else table[v]
            out += toks if first else (["~"] + toks if sym != "0" else toks)
            first = False
            rest -= v
    return out or [("s" + sym)]


def score_to_jianpu(sc: stream.Score, title: str = "") -> str:
    parts = list(sc.parts)
    mel = parts[0]
    ks = mel.recurse().getElementsByClass(m21key.KeySignature).first()
    sharps = ks.sharps if ks else 0
    tonic = m21key.KeySignature(sharps).asKey("major").tonic
    tonic_midi = 60 + (tonic.pitchClass if tonic.pitchClass <= 6 else tonic.pitchClass - 12)
    flats = sharps < 0
    ts = mel.recurse().getElementsByClass("TimeSignature").first()
    lines = [f"title={title}" if title else "", f"1={tonic.name.replace('-', 'b')}",
             f"{ts.numerator}/{ts.denominator}" if ts else "4/4"]
    measures = mel.getElementsByClass(stream.Measure)
    if not measures:
        mel = mel.makeMeasures()
        measures = mel.getElementsByClass(stream.Measure)
    bars = []
    for m in measures:
        toks = []
        for el in m.flatten().notesAndRests:
            if isinstance(el, note.Rest):
                sym = "0"
            elif isinstance(el, chord.Chord):
                sym = _degree(max(p.midi for p in el.pitches), tonic_midi, flats)
            else:
                sym = _degree(el.pitch.midi, tonic_midi, flats)
            if el.tie is not None and el.tie.type in ("stop", "continue") and sym != "0":
                toks += ["~"]
            if el.duration.tuplets:
                toks += ["3[", "q" + sym, "]"] if False else ["q" + sym]  # 三连音简化为八分
            else:
                toks += _dur_tokens(sym, float(el.quarterLength))
        bars.append(" ".join(toks))
    body = []
    for i in range(0, len(bars), 4):
        body.append(" | ".join(bars[i:i + 4]) + " |")
    return "\n".join([l for l in lines if l] + [""] + body) + "\n"
