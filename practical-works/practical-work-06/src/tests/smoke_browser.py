"""Реальный браузерный smoke-тест. Сначала запустите python app.py.

python -m pip install -r requirements-dev.txt
python -m playwright install chromium
python tests/smoke_browser.py
BASE_URL можно переопределить переменной окружения.
"""
import os
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

BASE_URL = os.environ.get("BASE_URL", "http://127.0.0.1:5000").rstrip("/")
PAGES = ["/today", "/habits", "/habits/new", "/support", "/statistics", "/schedule", "/settings", "/auth"]


def main():
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        context = browser.new_context(viewport={"width": 1440, "height": 1000}, locale="ru-RU")
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))

        def go(path):
            response = page.goto(BASE_URL + path)
            assert response.status == 200, path
            page.evaluate("document.fonts.ready")

        def count(text):
            expect(page.locator(".plan-counter")).to_have_text(text)

        go("/today")
        count("2 из 4 выполнено")
        page.locator('.focus-card button[value="done"]').click()
        count("3 из 4 выполнено")
        page.locator('form[action^="/habits/3/log"] button[value="minimum"]').click()
        count("4 из 4 выполнено")
        page.locator('form[action^="/habits/3/log"] button[value="reset"]').click()
        page.locator('.focus-card button[value="reset"]').click()
        count("2 из 4 выполнено")

        go("/support")
        page.get_by_text("Не было сил", exact=True).click()
        expect(page.locator('[data-reason-summary]')).to_have_text("Не было сил")
        page.locator('[data-disclosure="miss-ai-response"]').click()
        expect(page.locator('#miss-ai-response')).to_be_visible()
        expect(page.locator('#miss-ai-response')).to_contain_text("не ответ нейросети")
        page.get_by_role("button", name="Выбрать этот шаг").click()
        count("2 из 4 выполнено")
        expect(page.locator('.focus-card h2')).to_have_text("Прочитать 1 страницу")
        page.locator('.focus-card button[value="minimum"]').click()
        count("3 из 4 выполнено")

        go("/habits")
        page.locator('[data-filter="useful"]').click()
        expect(page.locator('.habit-card:visible')).to_have_count(3)
        page.locator('[data-filter="replacement"]').click()
        expect(page.locator('.habit-card:visible')).to_have_count(1)
        page.locator('[data-filter="all"]').click()
        page.get_by_role("link", name="Новая привычка", exact=True).click()
        page.locator('[data-open-dialog="template-dialog"]').click()
        expect(page.locator('#template-dialog')).to_be_visible()
        page.locator('[data-template-id="reading"]').click()
        expect(page.locator('#habit-name')).to_have_value("Читать каждый день")
        page.locator('#habit-name').fill("Моя тестовая привычка")
        page.locator('label[title="Среда"]').click()
        page.locator('label[title="Суббота"]').click()
        expect(page.locator('[data-preview-days]')).to_have_text("Пн, Вт, Чт, Пт, Сб")
        page.locator('[data-disclosure="ai-plan"]').click()
        expect(page.locator('#ai-plan')).to_contain_text("Здесь появится план от ИИ")
        page.get_by_role("button", name="Сохранить привычку").click()
        expect(page.locator('.habit-card')).to_have_count(5)
        page.get_by_role("link", name="Изменить привычку: Моя тестовая привычка").click()
        expect(page.locator('#habit-name')).to_have_value("Моя тестовая привычка")
        page.locator('label:has(input[name="type"][value="replacement"])').click()
        expect(page.locator('#replacement-plan')).to_be_visible()
        page.locator('#replacement-plan').fill("Отложить телефон и открыть книгу")
        page.get_by_role("button", name="Сохранить изменения").click()
        page.locator('[data-filter="replacement"]').click()
        expect(page.locator('.habit-card:visible')).to_have_count(2)

        go("/settings")
        page.locator('label:has(input[data-theme-choice][value="dark"])').click()
        page.locator('label:has(input[data-font-choice][value="large"])').click()
        expect(page.locator('html')).to_have_attribute('data-theme', 'dark')
        expect(page.locator('html')).to_have_attribute('data-font', 'large')
        assert page.evaluate('getComputedStyle(document.documentElement).fontSize') == '18px'
        page.reload()
        expect(page.locator('html')).to_have_attribute('data-theme', 'dark')
        expect(page.locator('html')).to_have_attribute('data-font', 'large')

        go("/schedule")
        page.locator('input[name="duration"][value="dates"]').check()
        page.locator('#pause-start').fill('2026-11-10')
        page.locator('#pause-end').fill('2026-11-09')
        assert not page.locator('#pause-end').evaluate('(input) => input.checkValidity()')
        expect(page.locator('[data-date-error]')).to_be_visible()
        page.locator('#pause-end').fill('2026-11-12')
        page.locator('[data-remove-day]').click()
        expect(page.locator('#schedule-day-4')).not_to_be_checked()
        page.locator('.toggle-switch').click()
        page.locator('button[name="intent"][value="save"]').click()
        expect(page.locator('#pause-end')).to_have_value('2026-11-12')
        expect(page.locator('#schedule-day-4')).not_to_be_checked()
        expect(page.locator('[name="reminders"]')).not_to_be_checked()
        page.locator('button[name="intent"][value="pause"]').click()
        go('/today')
        expect(page.locator('.pause-notice')).to_be_visible()
        expect(page.locator('.focus-card button')).to_be_disabled()
        go('/schedule')
        page.locator('button[name="intent"][value="resume"]').click()
        go('/today')
        expect(page.locator('.pause-notice')).to_have_count(0)

        go('/statistics')
        page.locator('[data-heat-day="9"]').click()
        expect(page.locator('[data-heat-summary]')).to_contain_text('9 ноября: 3 из 4')
        page.keyboard.press('ArrowRight')
        expect(page.locator('[data-heat-day="10"]')).to_be_focused()

        go('/settings')
        page.locator('.demo-details summary').click()
        page.get_by_role('button', name='Сбросить демо-данные').click()
        page.get_by_role('link', name='Выйти', exact=True).click()
        expect(page.locator('#auth-title')).to_be_visible()
        expect(page.locator('.sidebar')).to_have_count(0)
        expect(page.locator('html')).to_have_attribute('data-theme', 'dark')
        page.locator('#register-tab').click()
        expect(page.locator('#register-panel')).to_be_visible()
        page.keyboard.press('ArrowLeft')
        expect(page.locator('#login-tab')).to_be_focused()
        page.locator('#login-username').fill('demo')
        page.locator('#login-password').fill('not-a-real-password')
        page.locator('[data-toggle-password="login-password"]').click()
        expect(page.locator('#login-password')).to_have_attribute('type', 'text')
        page.get_by_role('button', name='Войти', exact=True).click()
        count('2 из 4 выполнено')
        print('OK: отметки, минимум, поддержка, фильтры, шаблон, создание/редактирование, настройки, пауза, календарь, вход')

        # 8 экранов × 7 ширин × 2 темы × 2 размера шрифта = 224 проверки.
        checks = 0
        for theme in ['light', 'dark']:
            for font in ['normal', 'large']:
                page.evaluate('([theme, font]) => { localStorage.setItem("healthycats.theme", theme); localStorage.setItem("healthycats.font", font); }', [theme, font])
                for width in [1440, 1280, 1024, 860, 768, 390, 320]:
                    page.set_viewport_size({'width': width, 'height': 1000 if width > 600 else 844})
                    for path in PAGES:
                        go(path)
                        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1'), (theme, font, width, path)
                        expect(page.locator('html')).to_have_attribute('data-theme', theme)
                        expect(page.locator('html')).to_have_attribute('data-font', font)
                        checks += 1
        print(f'OK: {checks} проверок адаптивности, темы и шрифта')

        page.set_viewport_size({'width': 390, 'height': 844})
        go('/today')
        page.locator('#menu-toggle').click()
        expect(page.locator('#sidebar')).to_have_attribute('aria-modal', 'true')
        expect(page.locator('#menu-close')).to_be_focused()
        page.keyboard.press('Escape')
        expect(page.locator('#menu-toggle')).to_be_focused()
        expect(page.locator('#menu-toggle')).to_have_attribute('aria-expanded', 'false')
        assert errors == [], errors
        print('OK: мобильное меню, Esc, возврат фокуса; ошибок JavaScript нет')

        if os.environ.get('SCREENSHOTS') == '1':
            folder = Path(__file__).parent / 'screenshots'
            folder.mkdir(exist_ok=True)
            page.wait_for_function("document.getAnimations().every(a => a.playState === 'finished' || a.playState === 'idle')")
            page.screenshot(path=str(folder / 'today-mobile-dark-large.png'), full_page=True)
            page.set_viewport_size({'width': 1440, 'height': 1000})
            go('/today')
            page.wait_for_function("document.getAnimations().every(a => a.playState === 'finished' || a.playState === 'idle')")
            page.screenshot(path=str(folder / 'today-desktop-dark-large.png'), full_page=True)
        context.close()
        browser.close()


if __name__ == '__main__':
    main()
