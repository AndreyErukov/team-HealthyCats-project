"""Дополнительный аудит axe. Нужны запущенный app.py и интернет для тестовой библиотеки.
Не является сертификацией WCAG и не заменяет ручные проверки.
"""
import json
import os
from urllib.request import urlopen
from playwright.sync_api import sync_playwright

BASE_URL = os.environ.get("BASE_URL", "http://127.0.0.1:5000").rstrip("/")
AXE_URL = "https://cdnjs.cloudflare.com/ajax/libs/axe-core/4.10.3/axe.min.js"
PAGES = ["/today", "/habits", "/habits/new", "/support", "/statistics", "/schedule", "/settings", "/auth"]


def main():
    with urlopen(AXE_URL, timeout=30) as response:
        axe_source = response.read().decode("utf-8")
    failures = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1000}, locale="ru-RU")
        page.goto(BASE_URL + "/today")
        for theme in ["light", "dark"]:
            page.evaluate('(theme) => localStorage.setItem("healthycats.theme", theme)', theme)
            for path in PAGES:
                page.goto(BASE_URL + path)
                page.evaluate("document.fonts.ready")
                # Проверяем готовое состояние, а не случайный полупрозрачный кадр.
                page.evaluate("() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))")
                page.wait_for_function("document.getAnimations().every(a => a.playState === 'finished' || a.playState === 'idle')")
                page.add_script_tag(content=axe_source)
                violations = page.evaluate('''async () => (await axe.run(document, {
                    runOnly: {type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21aa']}
                })).violations''')
                print(f"{theme:5} {path:14} нарушений: {len(violations)}")
                if violations:
                    failures.append({"theme": theme, "path": path, "violations": violations})
        browser.close()
    if failures:
        print(json.dumps(failures, ensure_ascii=False, indent=2))
        raise SystemExit(1)
    print("OK: выбранные правила axe, 16 состояний экранов. Ручная проверка всё равно необходима.")


if __name__ == "__main__":
    main()
