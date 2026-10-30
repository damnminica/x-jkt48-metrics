"""Bangun PDF dari laporan Markdown: Markdown -> HTML bergaya cetak -> PDF lewat Chrome headless.

Pakai: uv run --python 3.12 --with markdown python report/build_pdf.py report/laporan_project_x_jkt48.md
Menghasilkan <nama>.html dan <nama>.pdf di folder yang sama (gambar dirujuk relatif).
"""
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import markdown

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
CSS = """
@page { size: A4; margin: 16mm 15mm 18mm 15mm;
  @bottom-right { content: "Halaman " counter(page) " / " counter(pages); font: 8pt 'Helvetica Neue', Arial, sans-serif; color: #8a8985; }
  @bottom-left { content: "Laporan Project Metrik X JKT48"; font: 8pt 'Helvetica Neue', Arial, sans-serif; color: #8a8985; } }
:root { --ink: #0b0b0b; --ink2: #52514e; --rule: #e4e3df; --accent: #1f3864; --soft: #f4f3ef; }
html { background: #ffffff; }
body { font: 10pt/1.5 'Helvetica Neue', Arial, sans-serif; color: var(--ink); margin: 0; }
h1 { font-size: 22pt; line-height: 1.2; color: var(--accent); margin: 0 0 4pt; }
h1 + p { color: var(--ink2); margin-top: 0; }
h2 { font-size: 14pt; color: var(--accent); margin: 18pt 0 6pt; padding-bottom: 3pt; border-bottom: 1.5px solid var(--rule);
     break-after: avoid; }
h3 { font-size: 11.5pt; margin: 12pt 0 4pt; break-after: avoid; }
p, li { orphans: 3; widows: 3; }
ul, ol { padding-left: 16pt; margin: 4pt 0 8pt; }
li { margin: 2pt 0; }
hr { border: 0; border-top: 1px solid var(--rule); margin: 12pt 0; }
table { border-collapse: collapse; width: 100%; margin: 6pt 0 10pt; font-size: 8.8pt; break-inside: auto; }
thead { display: table-header-group; }
tr { break-inside: avoid; }
th { background: var(--accent); color: #fff; text-align: left; padding: 4pt 6pt; font-weight: 600; }
td { padding: 3.5pt 6pt; border-bottom: 1px solid var(--rule); vertical-align: top; }
tbody tr:nth-child(even) td { background: #fafaf8; }
code { font: 8.6pt Menlo, Consolas, monospace; background: var(--soft); padding: 0.5pt 3pt; border-radius: 3px; }
pre { background: var(--soft); padding: 8pt 10pt; border-radius: 4px; white-space: pre; font-size: 8.2pt;
      break-inside: avoid; }
td code { white-space: nowrap; }
blockquote { margin: 8pt 0; padding: 6pt 10pt; background: #fff6ec; border-left: 3px solid #eb6834; color: var(--ink); }
blockquote p { margin: 0; }
pre code { background: none; padding: 0; }
img { width: 100%; margin: 6pt 0 2pt; break-inside: avoid; }
p:has(> img) { break-inside: avoid; }
strong { font-weight: 650; }
a { color: var(--accent); }
"""


def normalize(md):
    """Daftar bertingkat ditulis dengan indentasi 2 spasi dan kadang tanpa baris kosong sebelum daftar;
    python-markdown butuh 4 spasi per tingkat dan baris kosong sebelum daftar."""
    out, prev = [], ""
    for line in md.splitlines():
        m = re.match(r"^( +)([-*]|\d+\.) ", line)
        if m:
            line = " " * (len(m.group(1)) * 2) + line[len(m.group(1)):]
        is_item = bool(re.match(r"^\s*([-*]|\d+\.) ", line))
        prev_item = bool(re.match(r"^\s*([-*]|\d+\.) ", prev))
        if is_item and prev.strip() and not prev_item and not prev.startswith("|"):
            out.append("")
        out.append(line)
        prev = line
    return "\n".join(out)


def main():
    src = Path(sys.argv[1]).resolve()
    body = markdown.markdown(normalize(src.read_text(encoding="utf-8")),
                             extensions=["tables", "fenced_code", "sane_lists"])
    title = re.search(r"^# (.+)$", src.read_text(encoding="utf-8"), re.M).group(1)
    html = src.with_suffix(".html")
    html.write_text(f"<!doctype html><html lang='id'><head><meta charset='utf-8'><title>{title}</title>"
                    f"<style>{CSS}</style></head><body>{body}</body></html>", encoding="utf-8")
    pdf = src.with_suffix(".pdf")
    with tempfile.TemporaryDirectory() as prof:
        subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--no-pdf-header-footer", f"--user-data-dir={prof}",
                        f"--print-to-pdf={pdf}", html.as_uri()], check=True, capture_output=True, timeout=180)
    print(pdf)


if __name__ == "__main__":
    main()
