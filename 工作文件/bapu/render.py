"""MusicXML → SVG 谱面预览（verovio，不需要装 MuseScore）。"""
from __future__ import annotations


def render_svg(xml_path: str, out_prefix: str, max_pages: int = 2) -> list[str]:
    import verovio
    tk = verovio.toolkit()
    tk.setOptions({"pageWidth": 2100, "pageHeight": 2970, "scale": 45, "adjustPageHeight": True,
                   "footer": "none", "breaks": "auto"})
    if not tk.loadFile(xml_path):
        return []
    out = []
    for i in range(1, min(tk.getPageCount(), max_pages) + 1):
        p = f"{out_prefix}-p{i}.svg"
        with open(p, "w", encoding="utf-8") as f:
            f.write(tk.renderToSVG(i))
        out.append(p)
    return out
