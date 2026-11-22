"""Rough key estimate per L5-rose song from 30-120s audio (chroma + Krumhansl), to compare with the sheet PDFs."""
import glob, os, sys
import av, numpy as np, librosa

sys.stdout.reconfigure(encoding="utf-8")
MAJ = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
MIN = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])
NAMES = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]


def load(f, t0=20, dur=90, sr=22050):
    c = av.open(f)
    rs = av.AudioResampler(format="flt", layout="mono", rate=sr)
    out = []
    for fr in c.decode(audio=0):
        if fr.time is not None and fr.time < t0:
            continue
        for r in rs.resample(fr):
            out.append(r.to_ndarray().ravel())
        if sum(len(o) for o in out) > dur * sr:
            break
    return np.concatenate(out), sr


root = sys.argv[1]
for f in sorted(glob.glob(os.path.join(root, "*", "音频.m4a"))):
    y, sr = load(f)
    ch = librosa.feature.chroma_cqt(y=y, sr=sr).sum(axis=1)
    sc = []
    for k in range(12):
        sc.append((np.corrcoef(ch, np.roll(MAJ, k))[0, 1], NAMES[k] + " major"))
        sc.append((np.corrcoef(ch, np.roll(MIN, k))[0, 1], NAMES[k] + " minor"))
    sc.sort(reverse=True)
    tempo = librosa.beat.beat_track(y=y, sr=sr)[0]
    print(os.path.basename(os.path.dirname(f)), "|", sc[0][1], round(sc[0][0], 2), "/", sc[1][1], "| tempo", np.round(tempo, 0))
