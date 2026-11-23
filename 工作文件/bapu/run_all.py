"""一键跑完整流程 + 测评。

用法（在 工作文件 目录下）：
  python -m bapu.run_all                      # 全部测试曲，输出到 runs/<时间戳>/
  python -m bapu.run_all --songs L1 L2        # 只跑 L1、L2
  python -m bapu.run_all --midi-cache runs/xxx  # 复用之前一次运行的转写 MIDI（只调谱面整理时用，省时间）

每首曲子输出：
  transcribed.mid          音频 → MIDI（Transkun）
  audio_score.musicxml     由转写 MIDI 整理出的五线谱（主要成品）
  audio_score.mid          量化后的 MIDI（已对齐节拍，导入编曲软件用）
  audio_jianpu.txt         简谱（主旋律，jianpu-ly 语法）
  oracle_*                 用标准答案 MIDI 走同一套整理流程，单独检验“MIDI→谱子”这一步
每次运行都新建文件夹，不覆盖旧结果。
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import shutil
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent          # 工作文件/
sys.path.insert(0, str(ROOT))

from bapu import midi2score, evaluate, jianpu  # noqa: E402

MODE = "auto"
BEATS = "none"


def process_song(song: Path, out: Path, cache: Path | None) -> dict:
    sid = song.name
    out.mkdir(parents=True, exist_ok=True)
    res = {"song": sid}
    audio = next(p for p in (song / "audio.mp3", song / "audio.flac", song / "audio.wav",
                             song / "audio.ogg", song / "audio.oga", song / "audio.m4a") if p.exists())
    est_mid = out / "transcribed.mid"
    cached = cache / sid / "transcribed.mid" if cache else None
    if cached and cached.exists():
        shutil.copy(cached, est_mid)
        res["transcribe"] = {"cached_from": str(cached.parent.parent.name)}
    else:
        from bapu import audio2midi
        res["transcribe"] = audio2midi.transcribe_auto(str(audio), str(est_mid), MODE)
    ans_mid = song / "answer.mid"
    if ans_mid.exists():
        res["note_level"] = evaluate.note_metrics(str(ans_mid), str(est_mid))

    # 节拍/强拍：可选用音频模型（beat_this），结果缓存为 beats_audio.json
    bt = None
    if BEATS != "none":
        ckpt = "final0" if BEATS == "auto" else BEATS
        bj = out / "beats_audio.json"
        cb = cache / sid / "beats_audio.json" if cache else None
        if cb and cb.exists():
            shutil.copy(cb, bj)
        else:
            from bapu.beats import audio_beats
            bj.write_text(json.dumps(audio_beats(str(audio), ckpt)), encoding="utf-8")
        bt = json.loads(bj.read_text(encoding="utf-8"))
        res["beat_model"] = {"model": bt.get("model"), "seconds": bt.get("seconds")}

    ans_xml = song / "answer.musicxml"
    ref_beats = song / "beats.json"
    meta_json = song / "meta.json"
    if ans_xml.exists():
        from music21 import converter
        res["ref_readability"] = evaluate.readability_metrics(converter.parse(str(ans_xml)))
    beats_mode = "none" if BEATS == "none" else ("auto" if BEATS == "auto" else "ext")
    sources = [("audio", est_mid)] + ([("oracle", ans_mid)] if ans_mid.exists() else [])
    for src, mid in sources:
        t0 = time.time()
        sc, qn, ana = midi2score.transcribe_to_score(
            str(mid), title=sid, beats_ext=bt["beats"] if bt else None,
            downbeats_ext=bt["downbeats"] if bt else None, beats_mode=beats_mode)
        sc.write("musicxml", fp=str(out / f"{src}_score.musicxml"))
        sc.write("midi", fp=str(out / f"{src}_score.mid"))
        (out / f"{src}_jianpu.txt").write_text(jianpu.score_to_jianpu(sc, sid), encoding="utf-8")
        if src == "audio":
            try:
                from bapu.render import render_svg
                render_svg(str(out / "audio_score.musicxml"), str(out / "audio_score"))
            except Exception as e:  # noqa: BLE001  预览失败不影响主流程
                res["render_error"] = repr(e)
        r = {"bpm": round(ana.bpm, 1), "meter": getattr(ana, "time_sig", f"{ana.beats_per_bar}/4"),
             "key": ana.key_name, "key_sharps": ana.key_sharps,
             "single_staff": ana.single_staff, "beat_regular": ana.beat_regular,
             "seconds": round(time.time() - t0, 1), **ana.info}
        r["readability"] = evaluate.readability_metrics(sc)
        if ans_xml.exists():
            r["score_level"] = evaluate.score_metrics(str(ans_xml), sc)
        elif ref_beats.exists():
            r["beat_level"] = evaluate.beat_metrics(str(ref_beats), ana)
        else:
            r["meta_level"] = evaluate.meta_metrics(sid, ana, str(meta_json) if meta_json.exists() else None)
        for k in ("beat_times", "bar_times"):      # 太长，不进 results.json
            r.pop(k, None)
        res[src] = r
    return res


def fmt_row(r: dict, src: str) -> str:
    s = r.get(src, {})
    nl = r.get("note_level", {})
    if "score_level" in s:
        m = s["score_level"]
        return (f"| {r['song']} | {nl.get('F1', '')} | {'✓' if m['key_ok'] else '✗'} | "
                f"{m['est_ts']}{'' if m['ts_ok'] else ' ✗(' + m['ref_ts'] + ')'} | "
                f"{m['score_note_F1']} | {'✓' if m['downbeat_ok'] else '✗'} | {m['beat_level']} | "
                f"{m['dur_acc']} | {m['hand_acc'] if m['hand_acc'] is not None else '—'} |")
    if "beat_level" in s:
        m = s["beat_level"]
        kmark = ('✓' if m["key_ok"] else '✗') if "key_ok" in m else '—'
        return (f"| {r['song']} | {nl.get('F1', '')} | {kmark} | "
                f"{m['est_ts']}{' ✓' if m['meter_ok'] else ' ✗(' + m['ref_ts'] + ')'} | "
                f"节拍F {m['beat_F']} | 小节线F {m['bar_F']} | — | — | — |")
    m = s.get("meta_level", {})
    kok = m.get("key_ok")
    kmark = '—' if kok is None else ('✓' if kok else '✗')
    mok = m.get("meter_ok")
    ts_str = m.get("est_ts", "")
    if mok is False:
        ts_str += f" ✗({m.get('ref_ts', '')})"
    return (f"| {r['song']} | {nl.get('F1', '—')} | {kmark} | "
            f"{ts_str} | — | — | — | — | — |")


def fmt_read_row(r: dict) -> str:
    ar = r.get("audio", {}).get("readability", {})
    rr = r.get("ref_readability") or r.get("oracle", {}).get("readability")
    if rr:
        ref_kind = "标准谱" if "ref_readability" in r else "Oracle"
        ref_str = f"{ref_kind}: {rr.get('rests_per_bar', '')} / {rr.get('tuplet_ratio', '')} / {rr.get('short16_ratio', '')}"
    else:
        ref_str = "—"
    return (f"| {r['song']} | {ar.get('rests_per_bar', '')} | {ar.get('tuplet_ratio', '')} | "
            f"{ar.get('short16_ratio', '')} | {'✓' if ar.get('has_pickup') else '—'} | "
            f"{ref_str} |")


def write_report(results: list, out: Path):
    head = ("| 曲目 | 转写音符F1 | 调号 | 拍号 | 谱面音符F1 | 小节线对齐 | 拍子层级 | 时值准确率 | 左右手准确率 |\n"
            "|---|---|---|---|---|---|---|---|---|")
    lines = [f"# 测评结果 {out.name}", "",
             "## A. 完整流程：音频 → 谱子", "", head] + [fmt_row(r, "audio") for r in results if "audio" in r]
    lines += ["", "## B. 只测“MIDI→谱子”：用标准答案 MIDI 作输入", "", head] + \
             [fmt_row(r, "oracle") for r in results if "oracle" in r]
    rhead = ("| 曲目 | 休止符/小节 | 连音占比 | ≤16分音符占比 | 弱起小节 | 参考(休止/连音/≤16分) |\n"
             "|---|---|---|---|---|---|")
    lines += ["", "## C. 谱面可读性（与参考谱 / Oracle 对比）", "", rhead] + \
             [fmt_read_row(r) for r in results if "audio" in r]
    errs = [r for r in results if "error" in r]
    if errs:
        lines += ["", "## 出错", ""] + [f"- {r['song']}: {r['error']}" for r in errs]
    (out / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--songs", nargs="*", default=[], help="曲目编号前缀，如 L1 L2-03")
    ap.add_argument("--songs-dir", default=str(ROOT / "test-songs"))
    ap.add_argument("--out", default="")
    ap.add_argument("--midi-cache", default="")
    ap.add_argument("--mode", default="auto", choices=["auto", "piano", "melody"],
                    help="转写路线：auto 自动判断；piano 钢琴；melody 单旋律（长笛、小提琴、人声等）")
    ap.add_argument("--beats", default="none",
                    help="节拍来源：none = 从音符推断；final0 / small0 = beat_this 音频模型；auto = 自动选择")
    a = ap.parse_args()
    global MODE, BEATS
    MODE = a.mode
    BEATS = a.beats
    out = Path(a.out) if a.out else ROOT / "runs" / dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    out.mkdir(parents=True, exist_ok=True)
    cache = Path(a.midi_cache) if a.midi_cache else None
    audio_names = ("audio.mp3", "audio.flac", "audio.wav", "audio.ogg", "audio.oga", "audio.m4a")
    songs = sorted(p for p in Path(a.songs_dir).iterdir()
                   if p.is_dir() and any((p / f).exists() for f in audio_names))
    if a.songs:
        songs = [s for s in songs if any(s.name.startswith(x) for x in a.songs)]
    results = []
    for s in songs:
        print(f"== {s.name}", flush=True)
        try:
            r = process_song(s, out / s.name, cache)
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            r = {"song": s.name, "error": repr(e)}
        results.append(r)
        print(json.dumps(r, ensure_ascii=False), flush=True)
        (out / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
        write_report(results, out)
    print("报告:", out / "report.md")


if __name__ == "__main__":
    main()
