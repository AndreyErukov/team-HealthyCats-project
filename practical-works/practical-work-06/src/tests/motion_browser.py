"""Регрессии анимаций и progressive enhancement в настоящем Chromium.

Запустить стенд: PREVIEW_MODE=1 python app.py
Затем: python tests/motion_browser.py
BASE_URL можно переопределить. Никаких внешних CDN / API в тесте нет.
"""
import os
from urllib.error import HTTPError
from urllib.request import Request, HTTPRedirectHandler, build_opener

from playwright.sync_api import sync_playwright, expect

BASE = os.environ.get("BASE_URL", "http://127.0.0.1:5000").rstrip("/")
LOG_URL = "**/habits/*/log*"
TRACK = ".progress-track"
FOCUS = '[data-task-id="1"]'
WALK = '[data-task-id="3"]'
ERRORS = []
INSTRUMENT = """(() => {
  const native = Element.prototype.animate;
  window.__motionCalls = [];
  Element.prototype.animate = function(frames, options) {
    const animation = native.call(this, frames, options);
    window.__motionCalls.push({ element: this, frames, options, animation });
    if (window.__holdProgress && this.matches('.progress-track > span')) {
      animation.pause();
      animation.currentTime = 0;
    }
    return animation;
  };
})();"""


def new_page(browser, **options):
    context = browser.new_context(locale="ru-RU", viewport={"width": 1440, "height": 1000}, **options)
    context.add_init_script(INSTRUMENT)
    page = context.new_page()
    page.on("pageerror", lambda error: ERRORS.append(str(error)))
    return context, page


def settle(page):
    page.evaluate("() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))")
    page.wait_for_function("document.getAnimations().every(a => a.playState === 'finished' || a.playState === 'idle')")


def go(page, path="/today"):
    response = page.goto(BASE + path)
    assert response.status == 200, path
    page.evaluate("document.fonts.ready")
    settle(page)


def count(page, number, total=4):
    expect(page.locator(".plan-counter")).to_have_text(f"{number} из {total} выполнено")
    expect(page.locator(TRACK)).to_have_attribute("aria-valuenow", str(number))
    expect(page.locator(TRACK)).to_have_attribute("aria-valuemax", str(total))


def ratio(page):
    return page.locator(TRACK).evaluate("track => track.firstElementChild.getBoundingClientRect().width / track.clientWidth")


def mark(page, task, status, expected, total=4):
    page.locator(f'{task} button[value="{status}"]').click()
    count(page, expected, total)
    expect(page.locator(".daily-plan")).not_to_have_attribute("aria-busy", "true")


def confirmed_updates(browser):
    context, page = new_page(browser)
    go(page)
    count(page, 2)
    expect(page.locator("html")).to_have_attribute("data-motion", "on")
    assert page.evaluate("__motionCalls.some(c => c.element.matches('.progress-track > span') && c.frames[0].width === '0%' && c.frames[1].width === '50%')")
    page.evaluate("window.__sameDocument = 'confirmed'; window.__holdProgress = true")
    held = []
    page.route(LOG_URL, lambda route: held.append(route))
    page.locator(f'{FOCUS} button[value="done"]').click()
    expect(page.locator(".daily-plan")).to_have_attribute("aria-busy", "true")
    count(page, 2)  # До ответа сервера выполнение НЕ засчитано.
    assert page.locator(".daily-plan button:enabled").count() == 0
    assert page.locator(".is-loading").count() == 1
    page.evaluate("""() => {
      const form = document.querySelector('.focus-card form');
      for (let i = 0; i < 5; i++) form.requestSubmit(form.querySelector('button'));
    }""")
    assert len(held) == 1, "Повторный запрос во время сохранения"
    body = held[0].request.post_data
    assert 'name="csrf_token"' in body and 'name="status"' in body
    held[0].continue_()
    count(page, 3)
    expect(page.locator(f'{FOCUS} button[value="reset"]')).to_be_focused()
    expect(page.locator(FOCUS)).to_have_attribute("data-task-status", "done")
    assert page.evaluate("window.__sameDocument") == "confirmed"
    assert page.evaluate("__motionCalls.some(c => c.frames[0].strokeDashoffset === 32)")
    assert abs(ratio(page) - .5) < .002, "Шкала должна стартовать с прежнего значения"
    page.evaluate("""() => {
      const a = document.querySelector('.progress-track > span').getAnimations()[0];
      a.currentTime = a.effect.getTiming().duration / 2;
    }""")
    page.evaluate("() => new Promise(requestAnimationFrame)")
    assert .5 < ratio(page) < .75, "Должен существовать промежуточный кадр заполнения"
    page.evaluate("""() => {
      window.__holdProgress = false;
      document.querySelector('.progress-track > span').getAnimations().forEach(a => a.finish());
    }""")
    page.unroute(LOG_URL)
    settle(page)
    assert abs(ratio(page) - .75) < .002
    # Уведомление закрывается мягко и возвращает фокус к действию.
    page.locator('.toast [data-dismiss-toast]').last.click()
    expect(page.locator('.toast')).to_have_count(0)
    expect(page.locator(f'{FOCUS} button[value="reset"]')).to_be_focused()
    mark(page, WALK, "minimum", 4)
    expect(page.locator(WALK)).to_have_attribute("data-task-status", "minimum")
    mark(page, WALK, "reset", 3)
    mark(page, FOCUS, "reset", 2)
    for _ in range(3):
        mark(page, FOCUS, "done", 3)
        mark(page, FOCUS, "reset", 2)
    settle(page)
    assert page.locator('.toast').count() <= 3
    assert page.locator('.press-wave, .is-loading').count() == 0
    assert abs(ratio(page) - .5) < .002
    assert page.evaluate("window.__sameDocument") == "confirmed"
    context.close()
    print("OK: реальные промежуточные кадры шкалы, галочка, минимум/отмена, один POST, фокус и уведомления")


def failed_requests(browser):
    context, page = new_page(browser)
    go(page)
    page.evaluate("window.__sameDocument = 'errors'")
    page.route(LOG_URL, lambda route: route.abort("failed"))
    page.locator(f'{FOCUS} button[value="done"]').click()
    expect(page.locator('.toast.error').last).to_contain_text("Не удалось получить ответ")
    count(page, 2)
    expect(page.locator(f'{FOCUS} button[value="done"]')).to_be_enabled()
    page.unroute(LOG_URL)
    page.route(LOG_URL, lambda route: route.fulfill(status=503, content_type="text/html; charset=utf-8", body='<div class="error-page"><p>Сервис временно недоступен.</p></div>'))
    page.locator(f'{FOCUS} button[value="done"]').click()
    expect(page.locator('.toast.error').last).to_contain_text("Сервис временно недоступен")
    count(page, 2)
    page.unroute(LOG_URL)
    page.route(LOG_URL, lambda route: route.fulfill(status=200, content_type="text/html", body='<h1>Not a plan</h1>'))
    page.locator(f'{FOCUS} button[value="done"]').click()
    expect(page.locator('.toast.error').last).to_contain_text("Не удалось обновить план")
    count(page, 2)
    page.unroute(LOG_URL)
    # Настоящий ответ 400 Flask: защита CSRF по-прежнему обязательна.
    page.locator(f'{FOCUS} input[name="csrf_token"]').evaluate("input => input.value = 'wrong-token'")
    page.locator(f'{FOCUS} button[value="done"]').click()
    expect(page.locator('.toast.error').last).to_contain_text("Форма устарела")
    count(page, 2)
    assert page.evaluate("window.__sameDocument") == "errors"
    page.locator('.toast.error .toast-action').last.click()
    count(page, 2)
    page.wait_for_function("window.__sameDocument === undefined")
    settle(page)
    # Тайм-аут проверяется на настоящем отложенном запросе, без автоповтора.
    held = []
    page.route(LOG_URL, lambda route: held.append(route))
    page.locator(f'{FOCUS} button[value="done"]').click()
    expect(page.locator('.toast.error').last).to_contain_text("Не удалось получить ответ", timeout=15000)
    count(page, 2)
    expect(page.locator(f'{FOCUS} button[value="done"]')).to_be_enabled()
    assert len(held) == 1
    held[0].abort()
    assert page.locator('.is-loading').count() == 0
    context.close()
    print("OK: сеть, HTTP 503, некорректный ответ, реальный CSRF 400, тайм-аут 12 с; ложных выполнений нет")


def reduced_motion(browser):
    context, page = new_page(browser, reduced_motion="reduce")
    go(page)
    expect(page.locator("html")).to_have_attribute("data-motion", "off")
    assert page.evaluate("__motionCalls.length") == 0
    assert abs(ratio(page) - .5) < .002
    mark(page, FOCUS, "done", 3)
    assert abs(ratio(page) - .75) < .002
    assert page.evaluate("__motionCalls.length") == 0
    go(page, "/support")
    page.locator('[data-disclosure]').evaluate("button => { button.click(); button.click(); }")
    expect(page.locator('#miss-ai-response')).to_be_hidden()
    page.locator('[data-disclosure]').evaluate("button => { button.click(); button.click(); button.click(); }")
    expect(page.locator('#miss-ai-response')).to_be_visible()
    assert page.evaluate("__motionCalls.length") == 0
    # Смена системного предпочтения на уже открытой странице.
    page.emulate_media(reduced_motion="no-preference")
    go(page)
    page.locator(f'{FOCUS} button[value="reset"]').click()
    count(page, 2)
    page.emulate_media(reduced_motion="reduce")
    expect(page.locator("html")).to_have_attribute("data-motion", "off")
    settle(page)
    assert abs(ratio(page) - .5) < .002
    assert page.evaluate("document.getAnimations().length") == 0
    page.emulate_media(reduced_motion="no-preference")
    expect(page.locator("html")).to_have_attribute("data-motion", "on")
    mark(page, FOCUS, "done", 3)
    assert page.evaluate("__motionCalls.some(c => c.frames[0].strokeDashoffset === 32)")
    context.close()
    print("OK: reduced motion при загрузке и переключении; мгновенные состояния, включая быстрые раскрытия")


def mobile_and_cross_tab(browser):
    context, page = new_page(browser)
    page.set_viewport_size({"width": 320, "height": 720})
    go(page)
    page.evaluate("localStorage.setItem('healthycats.theme', 'dark'); localStorage.setItem('healthycats.font', 'large')")
    page.reload()
    settle(page)
    page.locator(f'{WALK} button[value="minimum"]').scroll_into_view_if_needed()
    settle(page)
    y = page.evaluate("scrollY")
    mark(page, WALK, "minimum", 3)
    settle(page)
    assert abs(page.evaluate("scrollY") - y) <= 2, "Отметка не должна сбрасывать прокрутку"
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
    expect(page.locator(f'{WALK} button[value="reset"]')).to_be_focused()
    # Если человек уже ушёл фокусом за пределы плана, не перехватываем его.
    held = []
    page.route(LOG_URL, lambda route: held.append(route))
    page.locator(f'{WALK} button[value="reset"]').click()
    outside = page.locator('.warm-card a')
    outside.focus()
    held[0].continue_()
    count(page, 2)
    expect(outside).to_be_focused()
    page.unroute(LOG_URL)
    # План устарел в одной вкладке, а в другой включена пауза.
    other = context.new_page()
    schedule_url = page.locator('.aside-button').get_attribute('href')
    other.goto(BASE + schedule_url)
    other.locator('button[name="intent"][value="pause"]').click()
    page.locator(f'{FOCUS} button[value="done"]').click()
    count(page, 2)
    expect(page.locator('.daily-plan')).to_have_attribute('data-plan-paused', 'true')
    expect(page.locator('.pause-notice')).to_be_visible()
    assert page.locator('.daily-plan button:enabled').count() == 0
    expect(page.locator('.plan-counter')).to_be_focused()
    context.close()
    print("OK: 320 px, тёмная тема, крупный шрифт, прокрутка/фокус и пауза из другой вкладки")


def changed_plan(browser):
    context, page = new_page(browser)
    go(page)
    page.evaluate("window.__sameDocument = 'changed-plan'")
    other = context.new_page()
    query = page.locator('.nav-link[href^="/habits"]').get_attribute('href').partition('?')[2]
    other.goto(BASE + '/habits/new' + ('?' + query if query else ''))
    other.locator('[data-open-dialog]').click()
    other.locator('[data-template-id="reading"]').click()
    expect(other.locator('#habit-name')).to_have_value('Читать каждый день')
    other.locator('#habit-name').fill('Задача из другой вкладки')
    other.get_by_role('button', name='Сохранить привычку').click()
    expect(other.locator('.habit-card')).to_have_count(5)
    count(page, 2)  # Эта вкладка пока показывает прежний план.
    mark(page, FOCUS, 'done', 3, total=5)
    expect(page.locator('[data-task-id]')).to_have_count(5)
    expect(page.locator('.nav-count')).to_have_text('5')
    expect(page.locator(f'{FOCUS} button[value="reset"]')).to_be_focused()
    assert page.evaluate("window.__sameDocument") == 'changed-plan'
    mark(page, '[data-task-id="5"]', 'minimum', 4, total=5)
    mark(page, '[data-task-id="5"]', 'reset', 3, total=5)
    # Изменились данные, но не ID и не статус: текст тоже должен обновиться.
    other.get_by_role('link', name='Изменить привычку: Задача из другой вкладки').click()
    other.locator('#habit-name').fill('Обновлено в другой вкладке')
    other.get_by_role('button', name='Сохранить изменения').click()
    expect(other.locator('.habit-card h2').last).to_have_text('Обновлено в другой вкладке')
    mark(page, WALK, 'minimum', 4, total=5)
    expect(page.locator('[data-task-id="5"] h3')).to_have_text('Обновлено в другой вкладке')
    context.close()
    print("OK: новый состав плана, новые формы и изменённый текст из другой вкладки без перезагрузки")


def other_controls(browser):
    context, page = new_page(browser)
    go(page, "/habits")
    page.evaluate("""() => {
      for (const type of ['replacement', 'all', 'useful', 'all', 'replacement'])
        document.querySelector(`[data-filter="${type}"]`).click();
    }""")
    settle(page)
    expect(page.locator('.habit-card:visible')).to_have_count(1)
    assert page.locator('.habits-grid').evaluate("el => el.style.overflow") == ''
    go(page, "/support")
    toggle = page.locator('[data-disclosure]')
    toggle.evaluate("button => { button.click(); button.click(); }")
    expect(page.locator('#miss-ai-response')).to_be_hidden()
    toggle.evaluate("button => { button.click(); button.click(); button.click(); }")
    settle(page)
    expect(toggle).to_have_attribute('aria-expanded', 'true')
    expect(page.locator('#miss-ai-response')).to_be_visible()
    assert page.locator('#miss-ai-response').evaluate("el => !el.inert && !el.style.overflow")
    go(page, "/habits/new")
    opener = page.locator('[data-open-dialog]')
    opener.focus()
    opener.evaluate("button => button.click()")
    page.keyboard.press('Escape')
    expect(page.locator('#template-dialog')).to_be_hidden()
    expect(opener).to_be_focused()
    opener.click()
    page.locator('[data-template-id="reading"]').click()
    expect(page.locator('#habit-name')).to_have_value('Читать каждый день')
    expect(page.locator('#template-dialog')).to_be_hidden()
    page.locator('#habit-name').fill('После анимации можно печатать')
    expect(page.locator('#habit-name')).to_have_value('После анимации можно печатать')
    # Реальный hover/press: активная кнопка меньше, а волна затем удаляется.
    button = page.locator('button[type="submit"]').first
    button.scroll_into_view_if_needed()
    button.hover()
    page.mouse.down()
    page.wait_for_function("document.querySelector('.press-wave') !== null")
    page.evaluate("() => new Promise(resolve => setTimeout(resolve, 170))")
    scale = button.evaluate("el => new DOMMatrixReadOnly(getComputedStyle(el).transform).a")
    assert .95 < scale < 1
    page.mouse.move(5, 5)
    page.mouse.up()
    settle(page)
    expect(page.locator('.press-wave')).to_have_count(0)
    context.close()
    print("OK: быстрые фильтры/раскрытия, прерывание диалога, шаблон, нажатие кнопки и очистка эффектов")


def fallbacks(browser):
    context = browser.new_context(java_script_enabled=False, locale="ru-RU")
    page = context.new_page()
    page.goto(BASE + '/today')
    count(page, 2)
    page.locator(f'{FOCUS} button[value="done"]').click()
    count(page, 3)
    page.locator(f'{FOCUS} button[value="reset"]').click()
    count(page, 2)
    context.close()
    context, page = new_page(browser)
    context.add_init_script("Element.prototype.animate = undefined")
    go(page)
    expect(page.locator('html')).to_have_attribute('data-motion', 'off')
    mark(page, FOCUS, 'done', 3)
    assert abs(ratio(page) - .75) < .002
    context.close()
    print("OK: обычные POST-формы без JavaScript и работа без Web Animations API")


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, new_url):
        return None


def cookie_free_preview(browser):
    context, page = new_page(browser)
    opener = build_opener(NoRedirect)
    post_bodies = []
    sent_cookies = []
    page.on('request', lambda request: sent_cookies.append(request.all_headers().get('cookie', ''))
            if '/static/' not in request.url else None)

    def no_cookies(route):
        source = route.request
        # Отдельный HTTP-клиент БЕЗ cookie jar. Редирект выполняет браузер.
        # Playwright не перехватывает второй URL в цепочке редиректа, поэтому
        # полученную с финальным GET cookie удаляем до следующего действия.
        headers = {key: value for key, value in source.headers.items()
                   if key in ('content-type', 'accept', 'x-requested-with')}
        request = Request(source.url, data=source.post_data_buffer, headers=headers, method=source.method)
        if source.method == 'POST':
            post_bodies.append(source.post_data)
        try:
            response = opener.open(request, timeout=10)
        except HTTPError as error:
            response = error
        with response:
            headers = {key: value for key, value in response.headers.items()
                       if key.lower() not in ('set-cookie', 'connection', 'transfer-encoding')}
            route.fulfill(status=response.code, headers=headers, body=response.read())

    page.route(BASE + '/**', no_cookies)
    go(page)
    has_preview_token = page.locator('input[name="demo_token"]').count() > 0
    if not has_preview_token:
        context.close()
        print("SKIP: cookie-free режим проверяется при PREVIEW_MODE=1")
        return
    assert context.cookies() == []
    mark(page, FOCUS, 'done', 3)
    context.clear_cookies()
    assert '_demo=' in page.url and '/today?' in page.url
    mark(page, WALK, 'minimum', 4)
    context.clear_cookies()
    assert all('name="demo_token"' in body and 'name="csrf_token"' in body for body in post_bodies)
    page.reload()
    count(page, 4)
    assert context.cookies() == []
    assert sent_cookies and not any(sent_cookies), 'Ни один запрос страницы не должен отправлять cookie'
    context.close()
    print("OK: fetch POST → 303 → GET без cookies, подписанный demo_token / CSRF и состояние после reload")


def main():
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        for scenario in [confirmed_updates, failed_requests, reduced_motion,
                         mobile_and_cross_tab, changed_plan, other_controls, fallbacks, cookie_free_preview]:
            scenario(browser)
        browser.close()
    assert not ERRORS, ERRORS
    print("OK: все motion-регрессии; необработанных ошибок JavaScript нет")


if __name__ == '__main__':
    main()
