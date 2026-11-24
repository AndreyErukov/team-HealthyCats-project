/* HealthyCats · vanilla JavaScript, без CDN и сборщика.
 * Рабочая UI-логика: тема/шрифт, меню, фильтры, дни, формы, шаблоны.
 * ИИ-блоки — только явно подписанные демонстрационные раскрытия.
 */
(() => {
  'use strict';
  const root = document.documentElement;
  const motion = window.BerezhnoMotion;
  const $ = (selector, scope = document) => scope.querySelector(selector);
  const $$ = (selector, scope = document) => [...scope.querySelectorAll(selector)];

  // Создаём текст через textContent, а не через HTML из пользовательских полей.
  function makeIcon(name) {
    const ns = 'http://www.w3.org/2000/svg';
    const svg = document.createElementNS(ns, 'svg');
    const use = document.createElementNS(ns, 'use');
    svg.setAttribute('class', 'icon');
    svg.setAttribute('viewBox', '0 0 24 24');
    svg.setAttribute('fill', 'none');
    svg.setAttribute('stroke', 'currentColor');
    svg.setAttribute('stroke-width', '1.7');
    svg.setAttribute('stroke-linecap', 'round');
    svg.setAttribute('stroke-linejoin', 'round');
    svg.setAttribute('aria-hidden', 'true');
    use.setAttribute('href', `#icon-${name}`);
    svg.append(use);
    return svg;
  }

  const toastTimers = new WeakMap();
  const toastReturnFocus = new WeakMap();
  function dismissToast(toast, immediate = false) {
    if (!toast || toast.hasAttribute('data-closing')) return;
    clearTimeout(toastTimers.get(toast));
    if (toast.contains(document.activeElement)) {
      const origin = toastReturnFocus.get(toast);
      const destination = origin?.isConnected && !origin.disabled ? origin : $('#main-content');
      destination?.focus({ preventScroll: true });
    }
    toast.dataset.closing = '';
    toast.inert = true;
    toast.setAttribute('aria-hidden', 'true');
    const style = getComputedStyle(toast);
    const animation = !immediate && motion?.animate(toast,
      [{ opacity: style.opacity, transform: style.transform }, { opacity: 0, transform: 'translateY(6px)' }],
      { duration: 160 });
    if (animation) animation.finished.catch(() => {}).then(() => toast.remove());
    else toast.remove();
  }
  function trimToasts(stack) {
    while (stack.children.length > 3) {
      const oldest = [...stack.children].find(toast => !toast.contains(document.activeElement));
      if (!oldest) break;
      dismissToast(oldest, true);
      // Уже закрывающееся уведомление можно убрать сразу.
      if (oldest.isConnected) oldest.remove();
    }
  }
  function armToast(toast) {
    clearTimeout(toastTimers.get(toast));
    if (!toast.isConnected || toast.hasAttribute('data-closing')) return;
    toastTimers.set(toast, setTimeout(() => {
      if (!toast.matches(':hover') && !toast.contains(document.activeElement)) dismissToast(toast);
      else armToast(toast);
    }, 9000));
  }
  function prepareToast(toast) {
    if (document.activeElement !== document.body) toastReturnFocus.set(toast, document.activeElement);
    armToast(toast);
    ['mouseenter', 'focusin'].forEach(name => toast.addEventListener(name, () => clearTimeout(toastTimers.get(toast))));
    ['mouseleave', 'focusout'].forEach(name => toast.addEventListener(name, () => armToast(toast)));
  }
  function notify(message, options = {}) {
    const stack = $('#toast-stack');
    if (!stack) return;
    const toast = document.createElement('div');
    toast.className = `toast ${options.type || 'success'}`;
    const text = document.createElement('p');
    text.textContent = message;
    const close = document.createElement('button');
    close.type = 'button';
    close.className = 'icon-button';
    close.dataset.dismissToast = '';
    close.setAttribute('aria-label', 'Закрыть уведомление');
    close.append(makeIcon('x'));
    toast.append(makeIcon(options.type === 'error' ? 'info' : 'circle-check'), text);
    if (options.actionLabel && options.action) {
      const action = document.createElement('button');
      action.type = 'button';
      action.className = 'text-button toast-action';
      action.textContent = options.actionLabel;
      action.addEventListener('click', options.action);
      toast.append(action);
    }
    toast.append(close);
    stack.append(toast);
    // Не накапливаем уведомления при быстрых переключениях настроек.
    trimToasts(stack);
    prepareToast(toast);
  }
  // Общий безопасный вывод уведомлений для обновлений без перезагрузки.
  function appendServerToasts(responseDocument) {
    const stack = $('#toast-stack');
    if (!stack) return;
    $$('#toast-stack .toast', responseDocument).forEach(source => {
      const toast = document.importNode(source, true);
      stack.append(toast);
      prepareToast(toast);
    });
    trimToasts(stack);
  }
  window.BerezhnoUI = Object.freeze({ notify, appendServerToasts });
  $$('.toast').forEach(prepareToast);
  document.addEventListener('click', event => {
    const close = event.target.closest('[data-dismiss-toast]');
    if (close) dismissToast(close.closest('.toast'));
  });

  // 1. Настройки внешнего вида. Начальная установка также есть в head.html.
  const preferenceKeys = { theme: 'healthycats.theme', font: 'healthycats.font' };
  function syncPreferenceControls() {
    $$('[data-theme-choice]').forEach(input => { input.checked = input.value === root.dataset.theme; });
    $$('[data-font-choice]').forEach(input => { input.checked = input.value === root.dataset.font; });
  }
  function setPreference(kind, value) {
    root.dataset[kind] = value;
    syncPreferenceControls();
    try {
      localStorage.setItem(preferenceKeys[kind], value);
      notify(kind === 'theme'
        ? `${value === 'dark' ? 'Тёмная' : 'Светлая'} тема включена и сохранена.`
        : `${value === 'large' ? 'Крупный' : 'Обычный'} шрифт включён и сохранён.`);
    } catch (_) {
      notify('Настройка применена. Браузер запретил сохранение, поэтому после перезагрузки она может сброситься.');
    }
  }
  $$('[data-theme-choice]').forEach(input => input.addEventListener('change', () => setPreference('theme', input.value)));
  $$('[data-font-choice]').forEach(input => input.addEventListener('change', () => setPreference('font', input.value)));
  syncPreferenceControls();
  window.addEventListener('storage', event => {
    if (event.key === preferenceKeys.theme || event.key === null) {
      try { root.dataset.theme = localStorage.getItem(preferenceKeys.theme) === 'dark' ? 'dark' : 'light'; } catch (_) { /* Без хранилища оставляем текущую тему. */ }
    }
    if (event.key === preferenceKeys.font || event.key === null) {
      try { root.dataset.font = localStorage.getItem(preferenceKeys.font) === 'large' ? 'large' : 'normal'; } catch (_) { /* Аналогично для шрифта. */ }
    }
    syncPreferenceControls();
  });

  // 2. Мобильное меню: Esc, возврат фокуса и focus trap.
  const menuButton = $('#menu-toggle');
  const menuClose = $('#menu-close');
  const sidebar = $('#sidebar');
  const overlay = $('#sidebar-overlay');
  const main = $('#main-content');
  const mobileHeader = $('#mobile-header');
  const mobileQuery = window.matchMedia('(max-width: 860px)');
  function toggleMenu(open, restoreFocus = true) {
    if (!sidebar) return;
    document.body.classList.toggle('menu-open', open);
    menuButton.setAttribute('aria-expanded', String(open));
    menuButton.setAttribute('aria-label', open ? 'Закрыть меню' : 'Открыть меню');
    overlay.hidden = !open;
    main.inert = open;
    mobileHeader.inert = open;
    if (open) {
      sidebar.setAttribute('role', 'dialog');
      sidebar.setAttribute('aria-modal', 'true');
      menuClose.focus();
    } else {
      sidebar.removeAttribute('role');
      sidebar.removeAttribute('aria-modal');
      if (restoreFocus && mobileQuery.matches) menuButton.focus();
    }
  }
  menuButton?.addEventListener('click', () => toggleMenu(!document.body.classList.contains('menu-open')));
  menuClose?.addEventListener('click', () => toggleMenu(false));
  overlay?.addEventListener('click', () => toggleMenu(false));
  mobileQuery.addEventListener('change', event => { if (!event.matches) toggleMenu(false, false); });
  document.addEventListener('keydown', event => {
    if (!document.body.classList.contains('menu-open')) return;
    if (event.key === 'Escape') { event.preventDefault(); toggleMenu(false); }
    if (event.key === 'Tab') {
      const focusable = $$('a[href], button:not(:disabled)', sidebar).filter(el => el.getClientRects().length);
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    }
  });
  $$('[data-demo-logout]').forEach(link => link.addEventListener('click', event => {
    event.preventDefault();
    if (document.body.classList.contains('menu-open')) toggleMenu(false);
    notify('Выход из профиля пока не подключён. Экран входа можно открыть кнопкой «Выйти» в настройках.');
  }));

  // 3. Фильтры по демонстрационным карточкам. Без JS работают GET-ссылки.
  const filterBar = $('[data-habit-filters]');
  if (filterBar) {
    const cards = $$('[data-habit-type]');
    function applyFilter(value) {
      const selected = ['all', 'useful', 'replacement'].includes(value) ? value : 'all';
      const grid = $('.habits-grid');
      const previousHeight = grid.getBoundingClientRect().height;
      let count = 0;
      cards.forEach(card => {
        card.hidden = selected !== 'all' && card.dataset.habitType !== selected;
        if (!card.hidden) count += 1;
      });
      $$('[data-filter]', filterBar).forEach(link => {
        const active = link.dataset.filter === selected;
        link.classList.toggle('is-active', active);
        if (active) link.setAttribute('aria-current', 'true');
        else link.removeAttribute('aria-current');
      });
      $('[data-filter-empty]').hidden = count !== 0;
      $('[data-filter-summary]').textContent = `Показано привычек: ${count}`;
      motion?.resize(grid, previousHeight);
      cards.filter(card => !card.hidden).forEach((card, index) => motion?.reveal(card, index * 30));
    }
    filterBar.addEventListener('click', event => {
      const link = event.target.closest('[data-filter]');
      if (!link || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey || event.button !== 0) return;
      event.preventDefault();
      applyFilter(link.dataset.filter);
      history.pushState({}, '', link.href);
    });
    window.addEventListener('popstate', () => applyFilter(new URL(location.href).searchParams.get('type') || 'all'));
  }

  // 4. Нативные checkbox дней: отправляются с одинаковым name="days".
  $$('[data-days-group]').forEach((group, index) => {
    const inputs = $$('input[type="checkbox"]', group);
    const error = group.nextElementSibling;
    error.id ||= `days-error-${index}`;
    inputs.forEach(input => input.setAttribute('aria-describedby', error.id));
    function validateDays(showError) {
      const valid = inputs.some(input => input.checked);
      inputs[0].setCustomValidity(valid ? '' : 'Выбери хотя бы один день недели.');
      error.hidden = valid || !showError;
      inputs[0].setAttribute('aria-invalid', String(!valid));
      return valid;
    }
    group.addEventListener('change', () => validateDays(true));
    inputs[0].addEventListener('invalid', () => validateDays(true));
    validateDays(false);
  });

  // 5. Конструктор: живой просмотр, план замены, каталог из 3 фикстур.
  const habitForm = $('#habit-form');
  function updateHabitPreview() {
    if (!habitForm) return;
    const value = name => $(`[name="${name}"]`, habitForm)?.value.trim() || '';
    const isReplacement = $('[name="type"]:checked', habitForm)?.value === 'replacement';
    $('[data-replacement-field]', habitForm).hidden = !isReplacement;
    $('#replacement-plan').required = isReplacement;
    $('[data-preview-name]').textContent = value('name') || 'Одна привычка за раз';
    $('[data-preview-formula]').textContent = value('trigger') && value('action')
      ? `После ${value('trigger')} я ${value('action')}.`
      : 'Твой маленький план появится здесь, когда ты заполнишь форму.';
    const selectedDays = $$('[name="days"]:checked', habitForm).map(input => Number(input.value));
    const names = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'];
    $('[data-preview-days]').textContent = selectedDays.length === 7 ? 'Каждый день'
      : selectedDays.length ? selectedDays.map(day => names[day]).join(', ') : 'Выбери дни недели';
    $('[data-preview-minimum]').textContent = value('minimum') || 'Комфортный минимум';
  }
  habitForm?.addEventListener('input', updateHabitPreview);
  habitForm?.addEventListener('change', updateHabitPreview);
  updateHabitPreview();

  function closeDialog(dialog) {
    if (motion) return motion.closeDialog(dialog);
    dialog?.close();
    return Promise.resolve();
  }
  $$('[data-open-dialog]').forEach(button => button.addEventListener('click', () => {
    const dialog = document.getElementById(button.dataset.openDialog);
    if (motion) motion.openDialog(dialog);
    else dialog?.showModal();
  }));
  $$('[data-close-dialog]').forEach(button => button.addEventListener('click', () => closeDialog(button.closest('dialog'))));
  $$('dialog').forEach(dialog => {
    dialog.addEventListener('cancel', event => { event.preventDefault(); closeDialog(dialog); });
    dialog.addEventListener('click', event => {
      if (event.target !== dialog) return;
      const box = dialog.getBoundingClientRect();
      if (event.clientX < box.left || event.clientX > box.right || event.clientY < box.top || event.clientY > box.bottom) closeDialog(dialog);
    });
  });
  const catalogElement = $('#habit-templates');
  if (catalogElement && habitForm) {
    let catalog = [];
    try { catalog = JSON.parse(catalogElement.textContent); } catch (_) { notify('Не удалось загрузить шаблоны. Можно заполнить форму вручную.'); }
    let choosingTemplate = false;
    $$('[data-template-id]').forEach(button => button.addEventListener('click', async () => {
      const template = catalog.find(item => item.id === button.dataset.templateId);
      if (!template || choosingTemplate) return;
      choosingTemplate = true;
      // Сначала снимаем modal/inert, затем показываем готовые для ввода поля.
      await closeDialog(button.closest('dialog'));
      Object.entries(template.fields).forEach(([key, value]) => {
        const controls = $$(`[name="${key}"]`, habitForm);
        if (key === 'days') controls.forEach(input => { input.checked = value.includes(Number(input.value)); });
        else if (controls[0]?.type === 'radio') controls.forEach(input => { input.checked = input.value === value; });
        else if (controls[0]) controls[0].value = value;
      });
      $('#replacement-plan').value = '';
      $('[name="days"]', habitForm).dispatchEvent(new Event('change', { bubbles: true }));
      updateHabitPreview();
      choosingTemplate = false;
      $('#habit-name').focus({ preventScroll: true });
      notify('Шаблон подставлен в форму. Измени детали под себя и нажми «Сохранить привычку».');
    }));
  }

  // 6. Причины пропуска. На сервер уходят только при явной отправке формы.
  $$('[data-reason-label]').forEach(input => input.addEventListener('change', () => {
    const summary = $('[data-reason-summary]');
    if (summary) summary.textContent = input.dataset.reasonLabel;
  }));

  // Разворачиваем подготовленные блоки. Здесь намеренно нет вызова AI API.
  $$('[data-disclosure]').forEach(button => button.addEventListener('click', () => {
    const panel = document.getElementById(button.dataset.disclosure);
    if (!panel) return;
    const expanded = button.getAttribute('aria-expanded') !== 'true';
    button.setAttribute('aria-expanded', String(expanded));
    if (!expanded && panel.contains(document.activeElement)) button.focus({ preventScroll: true });
    if (motion) motion.disclose(panel, expanded);
    else { panel.hidden = !expanded; if (expanded) panel.scrollIntoView({ block: 'nearest' }); }
  }));

  // 7. Пауза: управление полями дат и валидация диапазона.
  const scheduleForm = $('#schedule-form');
  if (scheduleForm) {
    const start = $('#pause-start');
    const end = $('#pause-end');
    const dateError = $('[data-date-error]');
    function syncDates() {
      const useDates = $('[name="duration"]:checked', scheduleForm).value === 'dates';
      [start, end].forEach(input => { input.disabled = !useDates; input.required = useDates; });
      let invalid = false;
      if (useDates && start.value) {
        const next = new Date(`${start.value}T12:00:00Z`);
        next.setUTCDate(next.getUTCDate() + 1);
        if (!Number.isNaN(next.getTime())) end.min = next.toISOString().slice(0, 10);
        invalid = Boolean(end.value && end.value <= start.value);
      } else end.removeAttribute('min');
      end.setCustomValidity(invalid ? 'Дата возобновления должна быть позже даты начала.' : '');
      end.setAttribute('aria-invalid', String(invalid));
      dateError.hidden = !invalid;
    }
    $$('[name="duration"]', scheduleForm).forEach(input => input.addEventListener('change', syncDates));
    [start, end].forEach(input => input.addEventListener('input', syncDates));
    syncDates();
    const recommendation = $('[data-remove-day]');
    recommendation?.addEventListener('click', () => {
      const day = $(`[name="days"][value="${recommendation.dataset.removeDay}"]`, scheduleForm);
      if (day.checked && $$('[name="days"]:checked', scheduleForm).length === 1) {
        notify('Оставь хотя бы один рабочий день. Для полного отдыха можно включить паузу.');
        return;
      }
      day.checked = false;
      day.dispatchEvent(new Event('change', { bubbles: true }));
      $('[data-recommendation-feedback]').hidden = false;
      recommendation.textContent = 'Применено';
      recommendation.disabled = true;
    });
    $$('[name="days"]', scheduleForm).forEach(input => input.addEventListener('change', () => {
      if (input.value === recommendation?.dataset.removeDay && input.checked) {
        recommendation.disabled = false;
        recommendation.textContent = 'Применить';
        $('[data-recommendation-feedback]').hidden = true;
      }
    }));
  }

  // 8. Календарь: информация доступна по клику, касанию и с клавиатуры.
  const heatCells = $$('[data-heat-day]');
  heatCells.forEach((cell, index) => {
    cell.addEventListener('click', () => {
      heatCells.forEach(item => item.setAttribute('aria-pressed', String(item === cell)));
      $('[data-heat-summary]').textContent = `${cell.dataset.heatDay} ноября: ${cell.dataset.heatLevel} из 4 привычек выполнено · демо`;
    });
    cell.addEventListener('keydown', event => {
      const moves = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -7, ArrowDown: 7 };
      if (event.key in moves) {
        event.preventDefault();
        const next = Math.max(0, Math.min(heatCells.length - 1, index + moves[event.key]));
        heatCells[next].focus();
      }
    });
  });

  // 9. Вход/регистрация: доступные tabs и показ тестового пароля.
  const authTabs = $$('[data-auth-tab]');
  function selectAuthTab(tab, moveFocus = false) {
    authTabs.forEach(button => {
      const active = button.dataset.authTab === tab;
      button.setAttribute('aria-selected', String(active));
      button.tabIndex = active ? 0 : -1;
      button.classList.toggle('is-active', active);
      const panel = document.getElementById(button.getAttribute('aria-controls'));
      const wasHidden = panel.hidden;
      panel.hidden = !active;
      if (active && wasHidden) motion?.reveal(panel);
      if (active && moveFocus) button.focus();
    });
    document.title = `${tab === 'register' ? 'Регистрация' : 'Вход'} · бережно`;
    const url = new URL(location.href);
    url.searchParams.set('tab', tab);
    history.replaceState({}, '', url);
  }
  authTabs.forEach((button, index) => {
    button.addEventListener('click', () => selectAuthTab(button.dataset.authTab));
    button.addEventListener('keydown', event => {
      if (['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) {
        event.preventDefault();
        const next = event.key === 'Home' ? 0 : event.key === 'End' ? authTabs.length - 1 : (index + 1) % authTabs.length;
        selectAuthTab(authTabs[next].dataset.authTab, true);
      }
    });
  });
  $$('[data-toggle-password]').forEach(button => button.addEventListener('click', () => {
    const input = document.getElementById(button.dataset.togglePassword);
    const show = input.type === 'password';
    input.type = show ? 'text' : 'password';
    button.setAttribute('aria-label', show ? 'Скрыть пароль' : 'Показать пароль');
    button.setAttribute('aria-pressed', String(show));
    $('use', button).setAttribute('href', `#icon-${show ? 'eye-off' : 'eye'}`);
  }));

  $('[data-form-errors]')?.focus();
})();
