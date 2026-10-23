"""Build the lab's static portal: reports, rendered guides and reference PDFs."""

import argparse
import html
import json
import os
import shutil
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit

from markdown_it import MarkdownIt

ROOT = Path(__file__).resolve().parents[2]
GUIDES = {"DEFENSE.md": "defense.html", "FILE_GUIDE.md": "file-guide.html"}
PDFS = {"ТИОПО, ЛР №1.pdf": "lab-1.pdf", "ТИОПО, ЛР №2.pdf": "lab-2.pdf"}
STYLE = """
:root{font-family:system-ui,sans-serif;color:#17233c;background:#f3f6fc}
*{box-sizing:border-box}body{margin:0}main,nav{max-width:1120px;margin:auto;padding:24px}
nav{display:flex;gap:20px;flex-wrap:wrap}a{color:#2456b5;text-underline-offset:3px}
h1{font-size:clamp(28px,4vw,42px);line-height:1.15}h2{margin-top:36px}
p,li{line-height:1.65}.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:16px}
.card,article,.notice{background:white;border:1px solid #d9e1ef;
border-radius:14px;padding:22px}
.card h2{margin:0 0 12px;font-size:21px}.muted{color:#52617c}
.pill{display:inline-block;padding:5px 12px;background:#e8eefb;
border-radius:20px;margin:4px}
table{display:block;overflow:auto;border-collapse:collapse;width:100%;margin:18px 0}
th,td{border:1px solid #d9e1ef;padding:10px;text-align:left;vertical-align:top}
pre{background:#edf2fa;padding:16px;overflow:auto;border-radius:8px}code{font-size:13px}
article{overflow-wrap:anywhere}article img{max-width:100%}details{margin:20px 0}
@media(max-width:600px){main,nav{padding:16px}.card,article{padding:16px}}
"""


def page(title, content, *, prefix=""):
    nav = " · ".join(
        f'<a href="{prefix}{path}">{label}</a>'
        for path, label in (
            ("index.html", "Главная"),
            ("allure-report/index.html", "Allure"),
            ("coverage/index.html", "Coverage"),
            ("reference/defense.html", "Защита"),
            ("reference/file-guide.html", "Карта файлов"),
        )
    )
    return f"""<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)} · CMB</title><style>{STYLE}</style></head>
<body><nav>{nav}</nav><main>{content}</main></body></html>"""


def render_guide(source, *, repository, commit):
    renderer = MarkdownIt("commonmark", {"html": False}).enable("table")
    tokens = renderer.parse(source.read_text())
    contents = []
    for index, token in enumerate(tokens):
        if token.type == "heading_open":
            anchor = f"section-{len(contents) + 1}"
            token.attrSet("id", anchor)
            heading = tokens[index + 1].content
            contents.append(f'<li><a href="#{anchor}">{html.escape(heading)}</a></li>')
        for child in token.children or []:
            if child.type != "link_open":
                continue
            href = child.attrGet("href") or ""
            parts = urlsplit(href)
            if parts.scheme or parts.netloc or not parts.path:
                continue
            name = unquote(parts.path)
            if name in GUIDES:
                target = GUIDES[name]
            elif name in PDFS:
                target = PDFS[name]
            else:
                resolved = (source.parent / name).resolve()
                try:
                    relative = resolved.relative_to(ROOT).as_posix()
                except ValueError:
                    continue
                target = (
                    f"https://github.com/{repository}/blob/"
                    f"{quote(commit, safe='')}/{quote(relative)}"
                )
            if parts.fragment:
                target += "#" + parts.fragment
            child.attrSet("href", target)
    toc = (
        "<details><summary>Оглавление</summary><ul>"
        + "".join(contents)
        + "</ul></details>"
    )
    return (
        toc
        + "<article>"
        + renderer.renderer.render(tokens, renderer.options, {})
        + "</article>"
    )


def prepare(source: Path, destination: Path):
    destination.mkdir(parents=True, exist_ok=False)
    summary = json.loads((source / "summary.json").read_text())
    repository = os.environ.get("GITHUB_REPOSITORY", "just-rudy/ppo-labs")
    commit = summary.get("commit", "regular")
    shutil.copy2(source / "index.html", destination / "run-report.html")
    for name in (
        "summary.json",
        "coverage.xml",
        "unit.xml",
        "integration.xml",
        "e2e.xml",
        "capture-verification.json",
    ):
        if (source / name).is_file():
            shutil.copy2(source / name, destination / name)
    for name in ("allure-report", "coverage"):
        if (source / name).is_dir():
            shutil.copytree(source / name, destination / name)
        else:
            # An early failure still publishes documentation and an explanation.
            folder = destination / name
            folder.mkdir()
            (folder / "index.html").write_text(
                page(
                    name,
                    "<h1>Отчёт не сформирован</h1><p>Проверьте ошибки запуска в "
                    '<a href="../run-report.html">подробной сводке</a>.</p>',
                    prefix="../",
                )
            )
    reference = destination / "reference"
    reference.mkdir()
    for name, target in GUIDES.items():
        content = render_guide(
            ROOT / "labs/testing" / name, repository=repository, commit=commit
        )
        (reference / target).write_text(page(name, content, prefix="../"))
        shutil.copy2(ROOT / "labs/testing" / name, reference / name)
    for name, target in PDFS.items():
        shutil.copy2(ROOT / "labs/testing" / name, reference / target)
    cards = []
    for title, target, description in (
        (
            "Allure report",
            "allure-report/index.html",
            "Результаты, шаги тестов, ошибки и история запусков.",
        ),
        (
            "Coverage",
            "coverage/index.html",
            "Покрытие строк и ветвлений unit-тестами, просмотр исходного кода.",
        ),
        (
            "Как защищать лабораторную",
            "reference/defense.html",
            "Команды запуска, порядок демонстрации и работа с Wireshark.",
        ),
        (
            "Где что лежит",
            "reference/file-guide.html",
            "Карта файлов, связи компонентов и разбор тестового стенда.",
        ),
        (
            "Сводка и тренды",
            "run-report.html",
            "Статусы этапов, восстановление baseline и сравнение запусков.",
        ),
    ):
        cards.append(
            f'<section class="card"><h2><a href="{target}">{title}</a></h2>'
            f"<p>{description}</p></section>"
        )
    badges = "".join(
        f'<span class="pill">{html.escape(stage)}: '
        f'{html.escape(info.get("status", "unknown"))}</span>'
        for stage, info in summary.get("stages", {}).items()
    )
    downloads = "".join(
        f'<li><a href="{name}">{name}</a></li>'
        for name in (
            "summary.json",
            "coverage.xml",
            "unit.xml",
            "integration.xml",
            "e2e.xml",
            "capture-verification.json",
        )
        if (destination / name).exists()
    )
    actions = f"https://github.com/{repository}/actions"
    if os.environ.get("GITHUB_RUN_ID"):
        actions += f'/runs/{os.environ["GITHUB_RUN_ID"]}'
    body = f"""<p class="muted">Лабораторная работа №2 · тестирование</p>
<h1>Cool Magic Battles</h1><p>Отчёты и материалы для защиты в одном месте.</p>
<p class="muted">Запуск: {html.escape(summary.get("run_id", "unknown"))}<br>
Commit: {html.escape(commit)} ·
восстановление: {html.escape(summary.get("cleanup", "unknown"))}</p>
<div>{badges}</div><h2>Отчёты и инструкции</h2><div class="cards">{"".join(cards)}</div>
<h2>Задания лабораторных</h2><p><a href="reference/lab-1.pdf">ЛР №1 — PDF</a> ·
<a href="reference/lab-2.pdf">ЛР №2 — PDF</a></p>
<h2>Данные для проверки</h2><ul>{downloads}</ul>
<div class="notice"><h2>Логи и захват Wireshark</h2>
<p>Полные логи и <code>demo.pcap</code>
находятся в артефактах
<a href="{html.escape(actions, quote=True)}">запуска GitHub Actions</a>.
Скачайте архив <code>lab2-ci-…</code>.
Данные тестового трафика доступны в этом архиве.</p></div>"""
    (destination / "index.html").write_text(page("Лабораторная №2", body))
    (destination / ".nojekyll").touch()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    prepare(args.source, args.destination)
