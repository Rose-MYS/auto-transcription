"""构建 L4 测试集：真人钢琴录音 + 人工标注的节拍/强拍（检查小节线用）。

来源：
  - 音频：MAESTRO v3（CC BY-NC-SA 4.0，非商用），从官方 zip 里按文件远程读取（HTTP Range），不下载整个 100GB 包
  - 节拍/强拍/拍号标注：ASAP 数据集（https://github.com/fosfrancesco/asap-dataset，CC BY-NC-SA 4.0）
每首只截取前 CLIP 秒，标注同步截取。
输出：test-songs/L4-xx_<名>/audio.flac、answer.mid（截取后的演奏 MIDI）、beats.json
python -m bapu.build_asap_set
"""
from __future__ import annotations

import csv
import io
import json
import zipfile
from pathlib import Path

import numpy as np
import requests
import soundfile as sf
import pretty_midi

ROOT = Path(__file__).resolve().parent.parent
MAESTRO_ZIP = "https://storage.googleapis.com/magentadata/datasets/maestro/v3.0.0/maestro-v3.0.0.zip"
ASAP_RAW = "https://raw.githubusercontent.com/fosfrancesco/asap-dataset/master/"
CLIP = 90.0

# (编号, 名称, ASAP 文件夹, 演奏者文件名；None = 取第一个有 MAESTRO 音频的)
PICKS = [
    ("L4-01", "bach_prelude_C_BWV846", "Bach/Prelude/bwv_846", None),
    ("L4-02", "schubert_moment_musical_3", "Schubert/Moment_musical_no_3", None),
    ("L4-03", "schubert_impromptu_op90_2", "Schubert/Impromptu_op.90_D.899/2", None),
    ("L4-04", "mozart_sonata_K332_1", "Mozart/Piano_Sonatas/12-1", None),
    ("L4-05", "chopin_berceuse_op57", "Chopin/Berceuse_op_57", None),
]


class HttpFile(io.RawIOBase):
    """只读、可 seek 的远程文件（HTTP Range），给 zipfile 用。"""

    def __init__(self, url):
        self.url, self.pos = url, 0
        self.s = requests.Session()
        self.size = int(self.s.head(url, allow_redirects=True).headers["Content-Length"])

    def seekable(self):
        return True

    def readable(self):
        return True

    def tell(self):
        return self.pos

    def seek(self, off, whence=0):
        self.pos = off if whence == 0 else (self.pos + off if whence == 1 else self.size + off)
        return self.pos

    def read(self, n=-1):
        if n is None or n < 0:
            n = self.size - self.pos
        if n == 0 or self.pos >= self.size:
            return b""
        end = min(self.pos + n, self.size)
        buf = bytearray()
        while self.pos < end:                      # 分块 + 重试，网络断了也能续上
            stop = min(self.pos + 8 * 2**20, end) - 1
            for k in range(6):
                try:
                    r = self.s.get(self.url, headers={"Range": f"bytes={self.pos}-{stop}"}, timeout=120)
                    r.raise_for_status()
                    break
                except Exception:  # noqa: BLE001
                    if k == 5:
                        raise
                    import time
                    time.sleep(2 ** k)
            buf += r.content
            self.pos += len(r.content)
        return bytes(buf)

    def readinto(self, b):
        d = self.read(len(b))
        b[:len(d)] = d
        return len(d)


def parse_ann(text, clip):
    beats, downs, ts = [], [], []
    for line in text.strip().splitlines():
        t, _, lab = line.split("\t")
        t = float(t)
        if t > clip:
            break
        parts = lab.split(",")
        beats.append(t)
        if parts[0] == "db":
            downs.append(t)
        if len(parts) > 1 and "/" in parts[1]:
            ts.append([t, parts[1]])
    return {"beats": beats, "downbeats": downs, "time_signatures": ts}


def main():
    meta = list(csv.DictReader(io.StringIO(requests.get(ASAP_RAW + "metadata.csv", timeout=60).text)))
    zf = zipfile.ZipFile(HttpFile(MAESTRO_ZIP))
    names = set(zf.namelist())
    for sid, name, folder, perf in PICKS:
        rows = [r for r in meta if r["folder"] == folder and r["maestro_audio_performance"]]
        if perf:
            rows = [r for r in rows if r["midi_performance"].endswith(perf)]
        r = rows[0]
        out = ROOT / "test-songs" / f"{sid}_{name}"
        if (out / "beats.json").exists():
            print(sid, "已存在，跳过")
            continue
        out.mkdir(parents=True, exist_ok=True)
        wav = r["maestro_audio_performance"].replace("{maestro}", "maestro-v3.0.0")
        mid = r["maestro_midi_performance"].replace("{maestro}", "maestro-v3.0.0")
        assert wav in names, wav
        print(sid, folder, Path(wav).name, flush=True)
        ann = parse_ann(requests.get(ASAP_RAW + r["performance_annotations"], timeout=60).text, CLIP)
        # ASAP 的 performance 时间轴与 MAESTRO 文件可能有起点差：用 metadata 里的 start（秒）对齐
        start = float(r["start"] or 0.0)
        y, sr = sf.read(io.BytesIO(zf.read(wav)))
        a0, a1 = int(start * sr), int((start + CLIP) * sr)
        sf.write(str(out / "audio.flac"), y[a0:a1], sr)
        pm = pretty_midi.PrettyMIDI(io.BytesIO(zf.read(mid)))
        pm2 = pretty_midi.PrettyMIDI()
        inst = pretty_midi.Instrument(0)
        for n in pm.instruments[0].notes:
            if start <= n.start < start + CLIP:
                inst.notes.append(pretty_midi.Note(n.velocity, n.pitch, n.start - start,
                                                   min(n.end, start + CLIP) - start))
        pm2.instruments.append(inst)
        pm2.write(str(out / "answer.mid"))
        ann.update({"source_audio": wav, "asap_folder": folder, "asap_performance": r["midi_performance"],
                    "start_offset": start, "clip_seconds": CLIP,
                    "note": "beats/downbeats 已减去 start_offset 吗？见 aligned 字段"})
        # ASAP 标注的时间是相对 ASAP 的 performance MIDI；若该 MIDI 与 MAESTRO 原文件一致，则同一时间轴
        ann["aligned"] = "asap_time_minus_start" if start else "asap_time"
        if start:
            ann["beats"] = [t - start for t in ann["beats"] if t >= start]
            ann["downbeats"] = [t - start for t in ann["downbeats"] if t >= start]
        (out / "beats.json").write_text(json.dumps(ann, ensure_ascii=False, indent=1), encoding="utf-8")
        print("  beats", len(ann["beats"]), "downbeats", len(ann["downbeats"]), "ts", ann["time_signatures"][:2])


if __name__ == "__main__":
    main()
