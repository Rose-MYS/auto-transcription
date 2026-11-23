"""构建 L5 训练集外真人录音测试集（15 首：A 类 SMD 4 首 + B 类公版古典 4 首 + C 类 Rose 流行翻弹 7 首）。

每首输出到 test-songs/L5-xx_<名>/：
  - audio.flac（22050Hz，截取 75 秒）
  - meta.json（来源 URL、许可、演奏者、曲名、参考调号/拍号、弱起/rubato/音质标注、是否与 MAESTRO 重叠）
  - answer.mid（仅 A 类 SMD 有对齐 MIDI，保留 CC64 延音踏板事件）

用法（在 工作文件 目录下）：
  python -m bapu.build_l5_set
"""
from __future__ import annotations

import io
import json
import time
import zipfile
from pathlib import Path

import av
import numpy as np
import pretty_midi
import requests
import soundfile as sf

from bapu.build_asap_set import HttpFile

ROOT = Path(__file__).resolve().parent.parent
CLIP_SEC = 75.0
TARGET_SR = 22050
UA = {"User-Agent": "bapu-heldout-eval/1.0 (non-commercial research)"}

SMD_ZIP = "https://zenodo.org/api/records/13753319/files/SMD-piano_v2.zip/content"
SMD_URL = "https://zenodo.org/records/10847280"

# A 类：Saarland Music Data v2（Yamaha Disklavier 真人演奏 + 对齐 MIDI，CC BY-NC-SA 3.0）
CAT_A = [
    ("L5-A01", "brahms_ballade_op10_1", "Brahms_Op010No1_003_20090916-SMD",
     "Ballade Op. 10 No. 1 (Edward)", "Johannes Brahms", "SMD Performer 003",
     -1, "D minor", "4/4", True, True, "studio"),
    ("L5-A02", "mozart_var_K265", "Mozart_KV265_006_20110315-SMD",
     "12 Variations KV 265 (Ah! vous dirai-je, Maman)", "W. A. Mozart", "SMD Performer 006",
     0, "C major", "2/4", False, False, "studio"),
    ("L5-A03", "haydn_fantasia_Hob17_4", "Haydn_Hob017No4_003_20090916-SMD",
     "Fantasia in C major, Hob. XVII:4", "Joseph Haydn", "SMD Performer 003",
     0, "C major", "3/8", True, True, "studio"),
    ("L5-A04", "brahms_ballade_op10_2", "Brahms_Op010No2_003_20090916-SMD",
     "Ballade Op. 10 No. 2", "Johannes Brahms", "SMD Performer 003",
     2, "D major", "4/4", True, True, "studio"),
]

# B 类：Internet Archive 公版/历史非 Disklavier 真人钢琴录音
CAT_B = [
    ("L5-B01", "satie_gymnopedie_1",
     "https://archive.org/download/SatieGymnopedieNo.1./Satie-Gymnopedie%20No.%201..flac",
     "https://archive.org/details/SatieGymnopedieNo.1.",
     "Public Domain / Archive.org", "Gymnopédie No. 1", "Erik Satie", "Archive.org",
     2, "D major", "3/4", False, True, "studio"),
    ("L5-B02", "beethoven_fur_elise",
     "https://archive.org/download/FurElise_656/FurElise.mp3",
     "https://archive.org/details/FurElise_656",
     "Public Domain / Archive.org", "Für Elise, WoO 59", "L. van Beethoven", "Archive.org",
     0, "A minor", "3/8", True, True, "room"),
    ("L5-B03", "schumann_traumerei",
     "https://archive.org/download/schumann-op-15-vii-schnabel-1947/schumann%20op15-vii%20(schnabel%201947).mp3",
     "https://archive.org/details/schumann-op-15-vii-schnabel-1947",
     "Public Domain (1947)", "Kinderszenen Op. 15 No. 7 (Träumerei)", "Robert Schumann", "Artur Schnabel (1947)",
     -1, "F major", "4/4", True, True, "historical_noisy"),
    ("L5-B04", "chopin_waltz_op64_2",
     "https://archive.org/download/78_waltz-in-c-sharp-minor-op-64-no-2_jose-iturbi-chopin_gbia0124709a/WALTZ%20IN%20C%20SHARP%20MINOR,%20OP.%2064.%20NO.%202%20-%20JOSE%20ITURBI.flac",
     "https://archive.org/details/78_waltz-in-c-sharp-minor-op-64-no-2_jose-iturbi-chopin_gbia0124709a",
     "Public Domain (78rpm)", "Waltz in C# minor, Op. 64 No. 2", "Frédéric Chopin", "José Iturbi",
     4, "C# minor", "3/4", False, True, "historical_noisy"),
]

# C 类：Rose 提供的 B 站钢琴翻弹合集（截取主旋律段 75s；音频不进 git）
CAT_C = [
    ("L5-C01", "always_with_me", "03_千与千寻·永远同在", 0.0,
     "永远同在 (Always With Me)", "木村弓", -1, "F major", "3/4", True, True),
    ("L5-C02", "sparkle", "04_你的名字·Sparkle", 15.0,
     "Sparkle (你的名字)", "RADWIMPS", 5, "B major", "12/8", False, False),
    ("L5-C03", "night_piano_5", "06_夜的钢琴曲五", 0.0,
     "夜的钢琴曲五", "石进", -3, "Eb major", "4/4", False, True),
    ("L5-C04", "river_flows_in_you", "07_River Flows in You", 0.0,
     "River Flows in You (含混合拍子)", "Yiruma", 3, "A major", "4/4", False, True),
    ("L5-C05", "croatian_rhapsody", "09_克罗地亚狂想曲", 0.0,
     "克罗地亚狂想曲", "Tonči Huljić", -3, "C minor", "4/4", False, False),
    ("L5-C06", "mcml", "13_Merry Christmas Mr. Lawrence", 10.0,
     "Merry Christmas Mr. Lawrence", "坂本龙一", -5, "Db major", "12/8", False, True),
    ("L5-C07", "flower_dance", "15_Flower Dance·花之舞", 15.0,
     "Flower Dance (花之舞)", "DJ Okawari", 4, "C# minor", "4/4", False, False),
]


def decode_and_clip(src, start_sec: float = 0.0, dur_sec: float = CLIP_SEC, target_sr: int = TARGET_SR) -> np.ndarray:
    """使用 PyAV 解码任意音频（wav/ogg/oga/m4a）并重采样到 22050Hz 立体声/单声道浮点数组。"""
    c = av.open(src)
    rs = av.AudioResampler(format="flt", layout="mono", rate=target_sr)
    chunks = []
    started = False
    for fr in c.decode(audio=0):
        t = float(fr.time) if fr.time is not None else 0.0
        if not started and t + (fr.samples / max(fr.sample_rate, 1)) < start_sec:
            continue
        started = True
        for r in rs.resample(fr):
            chunks.append(r.to_ndarray().ravel())
        if sum(len(x) for x in chunks) >= (dur_sec + 2.0) * target_sr:
            break
    c.close()
    if not chunks:
        return np.zeros(0, dtype=np.float32)
    y = np.concatenate(chunks)
    # 精确对齐起点（若 fr.time 略早于 start_sec，则多取的部分基本可忽略；这里直接截取 dur_sec）
    n_keep = int(dur_sec * target_sr)
    return y[:n_keep]


def clip_midi(raw_bytes: bytes, dur_sec: float = CLIP_SEC) -> pretty_midi.PrettyMIDI:
    pm = pretty_midi.PrettyMIDI(io.BytesIO(raw_bytes))
    out = pretty_midi.PrettyMIDI()
    for inst in pm.instruments:
        if inst.is_drum:
            continue
        ni = pretty_midi.Instrument(program=inst.program)
        for n in inst.notes:
            if n.start < dur_sec:
                ni.notes.append(pretty_midi.Note(n.velocity, n.pitch, n.start, min(n.end, dur_sec)))
        for cc in inst.control_changes:
            if cc.time < dur_sec:
                ni.control_changes.append(pretty_midi.ControlChange(cc.number, cc.value, cc.time))
        if ni.notes:
            out.instruments.append(ni)
    return out


def download_bytes(url: str) -> bytes:
    for k in range(4):
        try:
            r = requests.get(url, headers=UA, timeout=90)
            r.raise_for_status()
            return r.content
        except Exception as e:
            if k == 3:
                raise
            print(f"  重试 {k + 1}/3 ({e})...", flush=True)
            time.sleep(2 ** k)
    return b""


def write_meta(out_dir: Path, meta: dict):
    (out_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    songs_root = ROOT / "test-songs"

    # --- A 类：SMD ---
    need_a = [row for row in CAT_A if not (songs_root / f"{row[0]}_{row[1]}" / "meta.json").exists()]
    if need_a:
        print("打开 SMD Zenodo zip（HTTP Range）...", flush=True)
        try:
            zf = zipfile.ZipFile(HttpFile(SMD_ZIP))
        except Exception as e:
            print(f"SMD zip 打开失败，跳过 A 类: {e}", flush=True)
            zf = None
        if zf is not None:
            for sid, slug, stem, title, comp, perf, ks, kn, ts, pickup, rubato, qual in need_a:
                out = songs_root / f"{sid}_{slug}"
                out.mkdir(parents=True, exist_ok=True)
                try:
                    print(f"[{sid}] {stem}...", flush=True)
                    wav_bytes = zf.read(f"wav_22050_mono/{stem}.wav")
                    mid_bytes = zf.read(f"midi/{stem}.mid")
                    y, sr = sf.read(io.BytesIO(wav_bytes), dtype="float32")
                    y = y[:int(CLIP_SEC * sr)]
                    sf.write(str(out / "audio.flac"), y, sr)
                    pm = clip_midi(mid_bytes, CLIP_SEC)
                    pm.write(str(out / "answer.mid"))
                    write_meta(out, {
                        "id": sid, "category": "A_SMD_Disklavier", "title": title, "composer": comp,
                        "performer": perf, "source_url": SMD_URL, "license": "CC BY-NC-SA 3.0",
                        "ref_key_sharps": ks, "ref_key_name": kn, "ref_ts": ts,
                        "pickup": pickup, "rubato": rubato, "audio_quality": qual,
                        "clip_start": 0.0, "clip_end": round(len(y) / sr, 2), "maestro_overlap": False,
                    })
                    print(f"  OK: {round(len(y)/sr,1)}s, notes={sum(len(i.notes) for i in pm.instruments)}", flush=True)
                except Exception as e:
                    print(f"  跳过 {sid}: {e}", flush=True)

    # --- B 类：Wikimedia Commons ---
    for sid, slug, dl_url, page_url, lic, title, comp, perf, ks, kn, ts, pickup, rubato, qual in CAT_B:
        out = songs_root / f"{sid}_{slug}"
        if (out / "meta.json").exists():
            continue
        out.mkdir(parents=True, exist_ok=True)
        try:
            print(f"[{sid}] {title}...", flush=True)
            raw = download_bytes(dl_url)
            y = decode_and_clip(io.BytesIO(raw), 0.0, CLIP_SEC, TARGET_SR)
            sf.write(str(out / "audio.flac"), y, TARGET_SR)
            write_meta(out, {
                "id": sid, "category": "B_PublicDomain_Classical", "title": title, "composer": comp,
                "performer": perf, "source_url": page_url, "download_url": dl_url, "license": lic,
                "ref_key_sharps": ks, "ref_key_name": kn, "ref_ts": ts,
                "pickup": pickup, "rubato": rubato, "audio_quality": qual,
                "clip_start": 0.0, "clip_end": round(len(y) / TARGET_SR, 2), "maestro_overlap": False,
            })
            print(f"  OK: {round(len(y)/TARGET_SR,1)}s", flush=True)
        except Exception as e:
            print(f"  跳过 {sid}: {e}", flush=True)

    # --- C 类：L5-rose ---
    rose_root = songs_root / "L5-rose" / "钢琴翻弹合集"
    for sid, slug, folder, start_s, title, comp, ks, kn, ts, pickup, rubato in CAT_C:
        out = songs_root / f"{sid}_{slug}"
        if (out / "meta.json").exists():
            continue
        src_dir = rose_root / folder
        m4a = src_dir / "音频.m4a"
        if not m4a.exists():
            print(f"  跳过 {sid}：未找到 {m4a}", flush=True)
            continue
        out.mkdir(parents=True, exist_ok=True)
        print(f"[{sid}] {folder} ({start_s}-{start_s + CLIP_SEC}s)...", flush=True)
        y = decode_and_clip(str(m4a), start_s, CLIP_SEC, TARGET_SR)
        sf.write(str(out / "audio.flac"), y, TARGET_SR)
        info_txt = (src_dir / "曲目信息.md").read_text(encoding="utf-8") if (src_dir / "曲目信息.md").exists() else ""
        src_url = ""
        for line in info_txt.splitlines():
            if "http" in line:
                src_url = line.split("http", 1)[1].strip()
                src_url = "http" + src_url.rstrip(")")
                break
        write_meta(out, {
            "id": sid, "category": "C_Rose_PopCover", "title": title, "composer": comp,
            "performer": "B站翻弹 UP 主（Rose 合集）", "source_url": src_url or "L5-rose/钢琴翻弹合集",
            "license": "个人学习测试（有版权，音频不进 git）",
            "ref_key_sharps": ks, "ref_key_name": kn, "ref_ts": ts,
            "pickup": pickup, "rubato": rubato, "audio_quality": "bilibili_aac",
            "clip_start": start_s, "clip_end": round(start_s + len(y) / TARGET_SR, 2), "maestro_overlap": False,
        })
        print(f"  OK: {round(len(y)/TARGET_SR,1)}s", flush=True)


if __name__ == "__main__":
    main()
