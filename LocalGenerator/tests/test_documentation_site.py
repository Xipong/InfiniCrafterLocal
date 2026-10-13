from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import re

import pytest

ROOT = Path(__file__).resolve().parents[2]


def generator():
    path = ROOT / "tools/build_documentation.py"
    assert path.exists(), "The offline documentation generator has not been implemented"
    spec = importlib.util.spec_from_file_location("documentation_site", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def source(root: Path, path: str, text: str):
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(text.encode("utf-8"))


def payload(html: str):
    match = re.search(r'<script id="handbook-data" type="application/json">(.*?)</script>', html, re.S)
    assert match, "The book must embed all rendered pages, not link to raw Markdown"
    return json.loads(match.group(1))


def test_book_embeds_full_markdown_for_all_audiences_deterministically(tmp_path):
    source(tmp_path, "docs/user/START_RU.md", "# Первый крафт\r\n\r\nУникальный полный текст.\r\n\r\n## Настройка\r\n\r\n```python\r\nprint('готово')\r\n```\r\n\r\n| Поле | Значение |\r\n| --- | --- |\r\n| api | offline |\r\n")
    for audience in ("development", "reference", "archive"):
        source(tmp_path, f"docs/{audience}/GUIDE.md", f"# {audience}\n\nПолный текст {audience}.")
    source(tmp_path, "docs/reference/generated/CATALOG.md", "# Каталог\n\nВсе строки каталога.")
    module = generator()
    html = module.build(tmp_path)
    assert html == module.build(tmp_path)
    pages = payload(html)["pages"]
    assert len(pages) == 5
    page = next(p for p in pages if p["path"] == "docs/user/START_RU.md")
    assert page["title"] == "Первый крафт"
    assert "Уникальный полный текст" in page["html"]
    assert "Уникальный полный текст" in page["text"]
    assert '<h2 id="настройка">' in page["html"]
    assert "<table>" in page["html"] and '<code class="language-python">' in page["html"]
    assert page["toc"] == [{"id": "настройка", "title": "Настройка", "level": 2}]
    assert '<html lang="ru">' in html
    assert '<script src=' not in html and '<link rel="stylesheet"' not in html


def test_markdown_links_route_to_embedded_pages_and_real_root_relative_files(tmp_path):
    source(tmp_path, "docs/user/START_RU.md", '# Начало\n\n[Раздел](../development/GUIDE.md#custom) · [Заголовок](../development/GUIDE.md#привет-world) · [Дубликат](../development/GUIDE.md#привет-world-1) · [BAT](../../OPEN.bat) · [Лицензия](../../LICENSE) · [Сайт](https://example.com)\n')
    source(tmp_path, "docs/development/GUIDE.md", '# Dev\n\n<a id="custom"></a>\n\n## Привет `world`!\n\n## Привет world!\n\n[Здесь](#custom)')
    source(tmp_path, "OPEN.bat", "@exit /b 0")
    source(tmp_path, "LICENSE", "Source available")
    pages = {p["path"]: p for p in payload(generator().build(tmp_path))["pages"]}
    html = pages["docs/user/START_RU.md"]["html"]
    assert 'href="#/docs/development/GUIDE.md@custom"' in html
    assert 'href="#/docs/development/GUIDE.md@%D0%BF%D1%80%D0%B8%D0%B2%D0%B5%D1%82-world"' in html
    assert 'href="OPEN.bat"' in html and 'href="LICENSE"' in html
    assert 'href="https://example.com"' in html
    assert 'href="#/docs/development/GUIDE.md@custom"' in pages["docs/development/GUIDE.md"]["html"]
    assert 'id="привет-world-1"' in pages["docs/development/GUIDE.md"]["html"]


def test_github_anchor_suffixes_handle_natural_collisions(tmp_path):
    source(tmp_path, "docs/user/START_RU.md", '# Book\n\n## A\n\n## A-1\n\n## A\n\n## X & Y: `code` / !\n\n[All](#a-2)')
    page = payload(generator().build(tmp_path))["pages"][0]
    assert [item["id"] for item in page["toc"]] == ["a", "a-1", "a-2", "x--y-code--"]


def test_generator_self_link_works_before_output_exists(tmp_path):
    source(tmp_path, "README.md", '# Project\n\n[Книга](START_HERE.html)\n\n[Играть](docs/user/START_RU.md)')
    source(tmp_path, "docs/user/START_RU.md", '# Start\n\n[Книга](../../START_HERE.html)')
    pages = payload(generator().build(tmp_path))["pages"]
    assert len(pages) == 2
    assert all('href="#/docs/user/START_RU.md"' in page["html"] for page in pages)


@pytest.mark.parametrize("link", ["MISSING.md", "OTHER.md#absent", "../../MISSING.bat", "../../../outside.md"])
def test_generator_rejects_missing_local_files_or_anchors(tmp_path, link):
    source(tmp_path, "docs/user/START_RU.md", f"# Начало\n\n[Ссылка]({link})")
    source(tmp_path, "docs/user/OTHER.md", "# Other")
    with pytest.raises(ValueError, match="START_RU.md"):
        generator().build(tmp_path)


@pytest.mark.parametrize("kind", ["image", "file", "chapter"])
def test_generator_rejects_symlinks_outside_project_root(tmp_path, kind):
    root = tmp_path / "project"
    source(root, "docs/user/START_RU.md", '# Start\n\nComplete guide.')
    outside = tmp_path / "outside.svg"
    outside.write_text('# External data must not be embedded', encoding='utf-8')
    name = "OUTSIDE.md" if kind == "chapter" else "pixel.svg"
    linked = root / "docs/user" / name
    try:
        linked.symlink_to(outside)
    except OSError:
        pytest.skip('Host cannot create symbolic links')
    if kind != "chapter":
        prefix = "!" if kind == "image" else ""
        source(root, "docs/user/START_RU.md", f'# Start\n\n{prefix}[External]({name})')
    with pytest.raises(ValueError, match="escapes repository"):
        generator().build(root)


def test_agents_canonical_links_are_embedded_without_changing_source(tmp_path):
    source(tmp_path, "AGENTS.md", '# Rules\n\n[README](README.md)\n\n[Lowery](docs/reference/generated/LOWERY_RU.md#boundary)')
    source(tmp_path, "README.md", '# Project\n\nCurrent canonical introduction.')
    source(tmp_path, "docs/reference/generated/LOWERY_RU.md", '# Lowery\n\n<a id="boundary"></a>\n\nContract.')
    before = (tmp_path / 'AGENTS.md').read_bytes()
    pages = {p['path']: p for p in payload(generator().build(tmp_path))['pages']}
    assert 'href="#/README.md"' in pages['AGENTS.md']['html']
    assert 'href="#/docs/reference/generated/LOWERY_RU.md@boundary"' in pages['AGENTS.md']['html']
    assert (tmp_path / 'AGENTS.md').read_bytes() == before
    source(tmp_path, "docs/user/START_RU.md", '# Start\n\n[Stale](../../README_RU.md)')
    with pytest.raises(ValueError, match='START_RU.md'):
        generator().build(tmp_path)


def test_inline_html_links_and_local_images_are_offline(tmp_path):
    import base64
    source(tmp_path, "docs/user/START_RU.md", '# Начало\n\n<a href="OTHER.md#custom">HTML ссылка</a>\n\n![Pixel](pixel.png)')
    source(tmp_path, "docs/user/OTHER.md", '# Другая\n\n<a name="custom"></a>\n\nПолный текст.')
    pixel = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jQZkAAAAASUVORK5CYII=")
    (tmp_path / "docs/user/pixel.png").write_bytes(pixel)
    pages = {p["path"]: p for p in payload(generator().build(tmp_path))["pages"]}
    assert 'href="#/docs/user/OTHER.md@custom"' in pages["docs/user/START_RU.md"]["html"]
    assert 'src="data:image/png;base64,' in pages["docs/user/START_RU.md"]["html"]


def test_raw_html_cannot_execute_code_or_fetch_remote_images(tmp_path):
    source(tmp_path, "docs/user/START_RU.md", '# Начало\n\n<script>alert("bad")</script>\n\n<p onclick="alert(1)">Текст</p>\n\n<iframe src="https://example.com"></iframe>')
    html = payload(generator().build(tmp_path))["pages"][0]["html"]
    assert '<script' not in html and 'onclick' not in html and '<iframe' not in html
    assert 'Текст' in html
    source(tmp_path, "docs/user/START_RU.md", '# Начало\n\n![Внешнее](https://example.com/image.png)')
    with pytest.raises(ValueError, match="remote image"):
        generator().build(tmp_path)


def test_search_text_includes_raw_html_and_decoded_entities(tmp_path):
    source(tmp_path, "docs/user/START_RU.md", '# Book\n\n<div>Найди HTML абзац &amp; entities.</div>\n\n```html\n<tag> & literal\n```')
    page = payload(generator().build(tmp_path))["pages"][0]
    assert 'Найди HTML абзац & entities.' in page["text"]
    assert '<tag> & literal' in page["text"]


def test_json_embedding_cannot_be_terminated_by_source_text(tmp_path):
    source(tmp_path, "docs/user/START_RU.md", '# Security\n\n```html\n</script><script>alert("bad")</script>\n```')
    html = generator().build(tmp_path)
    assert '</script><script>alert("bad")' not in html
    assert '</script><script>alert("bad")' in payload(html)["pages"][0]["text"]


def test_cli_check_detects_drift_without_rewriting_output(tmp_path):
    import subprocess
    import sys
    source(tmp_path, "docs/user/START_RU.md", "# Start\n\nПолный текст.")
    output = tmp_path / "BOOK.html"
    command = [sys.executable, str(ROOT / "tools/build_documentation.py"), "--root", str(tmp_path), "--output", str(output)]
    assert subprocess.run(command + ["--check"], capture_output=True, timeout=20).returncode == 1
    assert not output.exists()
    assert subprocess.run(command, capture_output=True, timeout=20).returncode == 0
    assert output.exists()
    before = output.read_bytes()
    assert subprocess.run(command + ["--check"], capture_output=True, timeout=20).returncode == 0
    source(tmp_path, "docs/user/START_RU.md", "# Start\n\nИзменённый текст.")
    result = subprocess.run(command + ["--check"], capture_output=True, timeout=20)
    assert result.returncode == 1
    assert output.read_bytes() == before


def test_file_browser_reading_search_navigation_and_mobile(tmp_path):
    playwright = pytest.importorskip("playwright.sync_api")
    source(tmp_path, "docs/user/START_RU.md", '# Первый крафт\n\nПолностью встроенное руководство. [Разработка](../development/GUIDE.md#custom)\n\n## Шаги\n\nПоследняя строка user.')
    source(tmp_path, "docs/development/GUIDE.md", '# Архитектура\n\n<a id="custom"></a>\n\n## Контракт\n\nУникальныйтокен в полном тексте.\n\n| Поле | Значение |\n| --- | --- |\n| contract | preserved |\n\n```python\nprint("offline")\n```')
    source(tmp_path, "docs/reference/generated/CATALOG.md", '# Каталог\n\nПолный каталог.\n\n## Строки\n\nВсе поля.')
    source(tmp_path, "docs/archive/HISTORY.md", '# История\n\nИсторический текст.')
    output = tmp_path / "START_HERE.html"
    output.write_text(generator().build(tmp_path), encoding="utf-8")
    with playwright.sync_playwright() as engine:
        if not Path(engine.chromium.executable_path).exists():
            pytest.skip("Chromium not installed; install it for browser acceptance")
        browser = engine.chromium.launch()
        expect = playwright.expect
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        errors, requests = [], []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("request", lambda request: requests.append(request.url))
        page.goto(output.as_uri())
        assert page.locator("#article").inner_text().endswith("Последняя строка user.")
        page.locator("#article a", has_text="Разработка").click()
        expect(page.locator("#article h1")).to_have_text("Архитектура")
        assert page.url.endswith("@custom")
        assert page.locator("#article table td").all_text_contents() == ["contract", "preserved"]
        assert page.locator('#article table').evaluate('table => table.scrollWidth >= 520')
        assert 'print("offline")' in page.locator("#article pre").inner_text()
        page.go_back()
        assert page.locator("#article h1").inner_text() == "Первый крафт"
        page.go_forward()
        expect(page.locator("#article h1")).to_have_text("Архитектура")
        page.reload()
        expect(page.locator("#article h1")).to_have_text("Архитектура")
        page.keyboard.press("Control+k")
        assert page.locator("#search").evaluate("node => node === document.activeElement")
        page.locator("#search").fill("Уникальныйтокен")
        assert page.locator("#page-list a").count() == 1
        assert "Архитектура" in page.locator("#page-list").inner_text()
        page.locator("#search").fill('<img src=x onerror=alert(1)>')
        expect(page.locator("#page-list")).to_contain_text("Ничего не найдено")
        assert page.locator('#page-list img').count() == 0
        page.locator("#search").fill("несуществующийтекст")
        assert "Ничего не найдено" in page.locator("#page-list").inner_text()
        page.keyboard.press("Escape")
        assert page.locator("#search").input_value() == ""
        page.locator('[data-audience="reference"]').click()
        assert page.locator("#article h1").inner_text() == "Каталог"
        page.locator("#toc a").click()
        assert page.url.endswith("@%D1%81%D1%82%D1%80%D0%BE%D0%BA%D0%B8")
        page.locator('[data-audience="archive"]').click()
        assert page.locator("#article").inner_text().endswith("Исторический текст.")
        page.set_viewport_size({"width": 390, "height": 844})
        expect(page.locator('#toc-details')).not_to_have_attribute('open', '')
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        page.locator("#contents-toggle").click()
        assert page.locator("#page-list").is_visible()
        page.set_viewport_size({"width": 900, "height": 900})
        expect(page.locator("#toc-details")).to_be_visible()
        page.locator('[data-audience="development"]').click()
        page.locator("#toc-details summary").click()
        expect(page.locator("#toc a")).to_be_visible()
        page.locator("#toc a").click()
        expect(page).to_have_url(re.compile(r"@%D0%BA%D0%BE%D0%BD%D1%82%D1%80%D0%B0%D0%BA%D1%82$"))
        page.set_viewport_size({"width": 390, "height": 844})
        page.locator('[data-audience="user"]').click()
        page.locator('[data-audience="development"]').click()
        page.wait_for_function("document.querySelector('#article table').scrollWidth >= 520")
        page.locator("#toc-details summary").click()
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        expect(page.locator("#toc a")).to_be_visible()
        assert not errors
        assert all(url.startswith("file:") for url in requests)
        browser.close()
