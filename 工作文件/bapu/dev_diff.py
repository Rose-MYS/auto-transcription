"""开发用：列出谱面与答案不一致的音（左右手、时值）。python -m bapu.dev_diff <answer.musicxml> <est.musicxml>"""
import sys
from fractions import Fraction
from music21 import converter
from bapu.evaluate import score_notes

ref = converter.parse(sys.argv[1])
est = converter.parse(sys.argv[2])
rn, *_r = score_notes(ref)
en, *_e = score_notes(est)
rparts, eparts = _r[2], _e[2]
if rparts == 4:
    rn = [(o, p, s // 2, d) for o, p, s, d in rn]
rset = {(o, p) for o, p, _, _ in rn}
best = max(((sum((o + Fraction(k, 4), p) in rset for o, p, _, _ in en), Fraction(k, 4)) for k in range(-32, 33)))
sh = best[1]
rinfo = {(o, p): (s, d) for o, p, s, d in rn}
print("shift", sh)
for o, p, s, d in sorted(en):
    k = (o + sh, p)
    if k in rinfo and rinfo[k] != (s, d):
        print(f"beat {float(o+sh):6.2f} pitch {p:3d}  est hand {s} dur {d}  ref hand {rinfo[k][0]} dur {rinfo[k][1]}")
