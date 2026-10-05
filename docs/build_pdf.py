"""Builds docs/ФСП-Талант-документация.pdf from the markdown docs.

    cd backend && uv run python ../docs/build_pdf.py

Markdown -> one HTML (brand styles, mermaid diagrams rendered in the browser) -> PDF via headless Chromium/Edge.
"""

import re
import shutil
import subprocess
import sys
from pathlib import Path

import markdown

DOCS = Path(__file__).resolve().parent
ORDER = ["00-summary.md", "../README.md", "01-architecture.md", "02-testing.md", "03-matching.md", "validation/report.md",
         "04-fsp-integration.md", "05-api.md", "06-antifraud-ats.md", "07-libraries.md", "08-deploy.md"]

CSS = """
@page { size: A4; margin: 16mm 14mm; }
body { font-family: 'Segoe UI', 'PT Sans', Arial, sans-serif; color: #1B1C21; font-size: 10.5pt; line-height: 1.45; }
h1 { color: #402FFF; font-size: 20pt; margin: 0 0 8pt; page-break-before: always; }
h1:first-of-type { page-break-before: avoid; }
h2 { font-size: 14pt; margin: 16pt 0 6pt; border-bottom: 1px solid #E6E6EB; padding-bottom: 3pt; }
h3 { font-size: 11.5pt; margin: 12pt 0 4pt; }
table { border-collapse: collapse; width: 100%; margin: 6pt 0 10pt; font-size: 9pt; page-break-inside: avoid; }
th, td { border: 1px solid #DADAE0; padding: 4pt 6pt; vertical-align: top; text-align: left; }
th { background: #F1EFFF; }
code { font-family: Consolas, 'JetBrains Mono', monospace; font-size: 9pt; background: #F6F6F9; padding: 0 2pt; }
pre { background: #F6F6F9; padding: 8pt; border-radius: 6pt; white-space: pre-wrap; font-size: 8.5pt; }
pre code { background: none; padding: 0; }
img { max-width: 100%; page-break-inside: avoid; }
.mermaid { text-align: center; page-break-inside: avoid; margin: 8pt 0; }
.cover { height: 250mm; display: flex; flex-direction: column; justify-content: center; }
.cover .label { font-family: Consolas, monospace; letter-spacing: .1em; color: #402FFF; font-size: 10pt; }
.cover h1 { page-break-before: avoid; font-size: 34pt; color: #1B1C21; margin: 10pt 0; }
.cover p { font-size: 13pt; color: #66676E; max-width: 150mm; }
a { color: #402FFF; text-decoration: none; }
"""


def md_to_html(text: str, base: Path) -> str:
    # mermaid fences -> <div class="mermaid">, images -> absolute file URIs
    text = re.sub(r"```mermaid\n(.*?)```", lambda m: f'<div class="mermaid">\n{m.group(1)}</div>', text, flags=re.S)
    text = re.sub(r"!\[(.*?)\]\((?!http)(.*?)\)",
                  lambda m: f"![{m.group(1)}]({(base / m.group(2)).resolve().as_uri()})", text)
    return markdown.markdown(text, extensions=["tables", "fenced_code"])


def browser() -> str:
    for name in ("msedge", "chrome", "chromium", "google-chrome", "chromium-browser"):
        if path := shutil.which(name):
            return path
    for path in (r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                 r"C:\Program Files\Google\Chrome\Application\chrome.exe"):
        if Path(path).exists():
            return path
    sys.exit("Chromium/Edge not found")


def main() -> None:
    parts = ['<div class="cover"><div class="label">ЛЦТ-2026 · СПЕЦИАЛЬНЫЙ ТРЕК ФСП</div><h1>ФСП Талант</h1>'
             "<p>Платформа подбора ИТ-специалистов с обратной механикой, адаптивным тестированием на грейд "
             "и верифицированным профилем достижений ФСП. Сопроводительная документация.</p></div>"]
    for name in ORDER:
        path = (DOCS / name).resolve()
        parts.append(md_to_html(path.read_text(encoding="utf-8"), path.parent))
    html = f"""<!doctype html><html lang="ru"><head><meta charset="utf-8"><title>ФСП Талант — документация</title>
<style>{CSS}</style>
<script src="https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js"></script>
<script>mermaid.initialize({{startOnLoad: true, theme: 'neutral', themeVariables: {{primaryColor: '#F1EFFF'}}}});</script>
</head><body>{''.join(parts)}</body></html>"""
    out_html = DOCS / "_build.html"
    out_html.write_text(html, encoding="utf-8")
    out_pdf = DOCS / "ФСП-Талант-документация.pdf"
    subprocess.run([browser(), "--headless", "--disable-gpu", "--no-pdf-header-footer", "--virtual-time-budget=15000",
                    f"--print-to-pdf={out_pdf}", out_html.resolve().as_uri()], check=True, capture_output=True)
    out_html.unlink()
    print(f"written {out_pdf} ({out_pdf.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
