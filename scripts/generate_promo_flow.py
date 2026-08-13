"""Generate the looping promotional pipeline GIF used by the docs.

This script intentionally uses only the standard library plus ImageMagick so the
animation remains editable and reproducible without introducing a runtime dependency.
"""

from __future__ import annotations

import html
import shutil
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs/assets/loop-apidoc-flow-demo.gif"
WIDTH, HEIGHT = 1200, 675
STAGES = (
    ("SOURCE PACKAGE", "PDF · DOCX · HTML · OpenAPI", "#7c6df2", "#eeeafe"),
    ("PRE-AGENT GATE", "manifest · source-risk · quality", "#d95757", "#ffe7e5"),
    ("AGENT PROPOSAL", "claims + exact evidence", "#f5a524", "#fff1d2"),
    ("DETERMINISTIC CORE", "verify · assemble · validate", "#15a39a", "#ddf6f2"),
)
OUTPUTS = ("OpenAPI 3.1", "繁中 guide", "provenance", "validation")


def esc(value: str) -> str:
    return html.escape(value, quote=True)


def frame_svg(active: int, *, success: bool, correction: bool) -> str:
    cards = []
    arrows = []
    start_x, card_w, gap, y = 54, 236, 42, 210
    for index, (title, subtitle, color, soft) in enumerate(STAGES):
        x = start_x + index * (card_w + gap)
        is_active = index == active
        stroke = color if is_active else "#d9d5cc"
        width = 5 if is_active else 2
        glow = f'<rect x="{x - 10}" y="{y - 10}" width="{card_w + 20}" height="170" rx="26" fill="{soft}" opacity=".8"/>' if is_active else ""
        cards.append(
            f'''{glow}<g>
              <rect x="{x}" y="{y}" width="{card_w}" height="150" rx="20" fill="#fff" stroke="{stroke}" stroke-width="{width}"/>
              <circle cx="{x + 32}" cy="{y + 34}" r="13" fill="{color}"/>
              <text x="{x + 56}" y="{y + 42}" class="stage">{esc(title)}</text>
              <text x="{x + 24}" y="{y + 83}" class="detail">{esc(subtitle)}</text>
              <rect x="{x + 24}" y="{y + 108}" width="{card_w - 48}" height="12" rx="6" fill="{soft}"/>
              <rect x="{x + 24}" y="{y + 108}" width="{(card_w - 48) if is_active else 42}" height="12" rx="6" fill="{color}" opacity="{'.88' if is_active else '.24'}"/>
            </g>'''
        )
        if index < len(STAGES) - 1:
            x1 = x + card_w + 8
            x2 = x + card_w + gap - 8
            lit = active > index
            arrows.append(
                f'<path d="M{x1} {y + 75}H{x2}" stroke="{"#15a39a" if lit else "#c8c5bd"}" stroke-width="5" marker-end="url(#arrow)"/>'
            )

    output_opacity = "1" if success else ".28"
    output_chips = "".join(
        f'<rect x="{220 + i * 198}" y="442" width="174" height="48" rx="24" fill="#fff" stroke="#15a39a" stroke-width="2"/>'
        f'<text x="{307 + i * 198}" y="473" class="chip" text-anchor="middle">{esc(label)}</text>'
        for i, label in enumerate(OUTPUTS)
    )
    status = (
        '<circle cx="1018" cy="466" r="29" fill="#2bb673"/><path d="M1004 466l10 10 20-23" stroke="#fff" stroke-width="6" fill="none" stroke-linecap="round" stroke-linejoin="round"/>'
        if success
        else '<circle cx="1018" cy="466" r="29" fill="#e8e4da"/><path d="M1007 455l22 22m0-22l-22 22" stroke="#a29d91" stroke-width="5" stroke-linecap="round"/>'
    )
    correction_path = (
        '<path d="M1018 405C1018 560 733 579 576 579C414 579 258 555 258 398" stroke="#d95757" stroke-width="4" stroke-dasharray="9 10" fill="none" marker-end="url(#arrow-red)"/>'
        '<rect x="420" y="548" width="360" height="42" rx="21" fill="#ffe7e5" stroke="#d95757"/><text x="600" y="575" class="retry" text-anchor="middle">evidence gap → re-read source → correct</text>'
        if correction
        else ""
    )
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}">
      <defs>
        <marker id="arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0 0L10 5L0 10z" fill="#15a39a"/></marker>
        <marker id="arrow-red" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0 0L10 5L0 10z" fill="#d95757"/></marker>
        <style>
          text{{font-family:"Noto Sans TC","PingFang TC","Microsoft JhengHei",Arial,sans-serif}}
          .kicker{{font-size:17px;font-weight:800;letter-spacing:3px;fill:#0f7a73}}
          .title{{font-size:40px;font-weight:900;fill:#2c3043}}
          .sub{{font-size:19px;fill:#5d6478}}
          .stage{{font-size:16px;font-weight:900;fill:#2c3043}}
          .detail{{font-size:15px;fill:#5d6478}}
          .chip{{font-size:15px;font-weight:800;fill:#0f7a73}}
          .retry{{font-size:16px;font-weight:800;fill:#a13d3d}}
        </style>
      </defs>
      <rect width="1200" height="675" fill="#fffdf8"/>
      <circle cx="1100" cy="40" r="220" fill="#ddf6f2" opacity=".72"/>
      <circle cx="50" cy="670" r="210" fill="#ffe7e5" opacity=".62"/>
      <text x="54" y="64" class="kicker">LOOP-APIDOC</text>
      <text x="54" y="116" class="title">From messy docs to a contract you can trust.</text>
      <text x="54" y="154" class="sub">The model reads. Deterministic gates decide what is supported.</text>
      {''.join(arrows)}{''.join(cards)}
      <g opacity="{output_opacity}">
        <text x="54" y="414" class="kicker">REVIEWABLE OUTPUTS</text>{output_chips}{status}
      </g>
      {correction_path}
      <text x="1146" y="640" class="sub" text-anchor="end">source-grounded · fail-closed · reproducible</text>
    </svg>'''


def main() -> None:
    magick = shutil.which("magick")
    if not magick:
        raise SystemExit("ImageMagick's `magick` command is required")
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    sequence = [0, 0, 1, 1, 2, 2, 3, 3]
    with tempfile.TemporaryDirectory(prefix="loop-apidoc-promo-") as tmp:
        directory = Path(tmp)
        frames: list[Path] = []
        for number, active in enumerate(sequence):
            path = directory / f"frame-{number:02d}.svg"
            path.write_text(frame_svg(active, success=False, correction=False), encoding="utf-8")
            frames.append(path)
        for number in range(3):
            path = directory / f"frame-{len(frames):02d}.svg"
            path.write_text(frame_svg(3, success=True, correction=False), encoding="utf-8")
            frames.append(path)
        for number in range(2):
            path = directory / f"frame-{len(frames):02d}.svg"
            path.write_text(frame_svg(3, success=False, correction=True), encoding="utf-8")
            frames.append(path)
        subprocess.run(
            [magick, "-density", "96", *map(str, frames), "-resize", "1000x563", "-layers", "Optimize", "-delay", "42", "-loop", "0", str(OUTPUT)],
            check=True,
        )
    print(OUTPUT.relative_to(ROOT))


if __name__ == "__main__":
    main()
