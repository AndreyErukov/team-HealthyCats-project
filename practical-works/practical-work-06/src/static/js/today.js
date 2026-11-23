/* Отметки без перезагрузки страницы.
 * Использует те же POST-формы и серверный HTML, без нового API и без оптимистичного
 * засчитывания. Если JS выключен, формы продолжают работать обычным способом.
 */
(() => {
  'use strict';
  if (!document.querySelector('.daily-plan') || !window.fetch || !window.DOMParser ||
      !window.AbortController || !window.BerezhnoUI || window.origin === 'null') return;
  const motion = window.BerezhnoMotion;
  document.documentElement.classList.add('has-live-plan');
  let busy = false;
  let controller = null;
  const all = (selector, scope = document) => [...scope.querySelectorAll(selector)];
  const completed = status => status === 'done' || status === 'minimum';

  function notifyError(message) {
    window.BerezhnoUI?.notify(message, {
      type: 'error', actionLabel: 'Обновить', action: () => window.location.reload(),
    });
  }

  function syncPlan(plan, incoming, taskId, shouldFocus) {
    const previousRow = plan.querySelector(`[data-task-id="${taskId}"]`);
    const previousStatus = previousRow?.dataset.taskStatus;
    const block = previousRow?.closest('.period-card, .focus-card');
    const blockHeight = block?.getBoundingClientRect().height;
    const countBefore = plan.querySelector('.plan-counter')?.textContent;
    const trackBefore = plan.querySelector('.progress-track');
    const oldPercentage = trackBefore?.clientWidth ? trackBefore.firstElementChild.getBoundingClientRect().width / trackBefore.clientWidth * 100 : 0;
    const freshPlan = incoming.querySelector('.daily-plan');
    const structure = scope => all('[data-task-id]', scope).map(el =>
      `${el.dataset.taskId}:${el.closest('.period-card')?.getAttribute('aria-labelledby') || 'focus'}`).join(',');
    const oldIds = structure(plan);
    const newIds = structure(freshPlan);
    const pauseChanged = plan.dataset.planPaused !== freshPlan.dataset.planPaused;

    if (oldIds === newIds) {
      all('[data-task-id]', freshPlan).forEach(fresh => {
        const old = plan.querySelector(`[data-task-id="${fresh.dataset.taskId}"]`);
        if (fresh.dataset.taskId === taskId || old.outerHTML !== fresh.outerHTML || pauseChanged) {
          old.replaceWith(document.importNode(fresh, true));
        }
      });
      const freshCount = freshPlan.querySelector('.plan-counter');
      plan.querySelector('.plan-counter').replaceChildren(...[...freshCount.childNodes].map(node => document.importNode(node, true)));
      plan.dataset.planPaused = freshPlan.dataset.planPaused;
    } else {
      // Например, план изменился в другой вкладке. Берём полный серверный план.
      const replacement = document.importNode(freshPlan, true);
      replacement.querySelector('.progress-track').firstElementChild.style.width = `${oldPercentage}%`;
      plan.replaceWith(replacement);
      plan = replacement;
    }
    plan.removeAttribute('aria-busy');
    const freshTrack = freshPlan.querySelector('.progress-track');
    const track = plan.querySelector('.progress-track');
    ['aria-valuenow', 'aria-valuemin', 'aria-valuemax'].forEach(name => track.setAttribute(name, freshTrack.getAttribute(name)));
    const percentage = parseFloat(freshTrack.firstElementChild.style.width) || 0;
    if (motion) motion.progress(track, percentage);
    else track.firstElementChild.style.width = `${percentage}%`;
    if (countBefore !== plan.querySelector('.plan-counter').textContent) motion?.counter(plan.querySelector('.plan-counter'));

    // Обновляем защитные поля из ответа, а не обходим серверную проверку.
    ['csrf_token', 'demo_token'].forEach(name => {
      const freshValue = incoming.querySelector(`input[name="${name}"]`)?.value;
      if (freshValue) all(`input[name="${name}"]`).forEach(input => { input.value = freshValue; });
    });
    const oldNotice = document.querySelector('.pause-notice');
    const newNotice = incoming.querySelector('.pause-notice');
    if (newNotice) {
      const notice = document.importNode(newNotice, true);
      if (oldNotice) oldNotice.replaceWith(notice);
      else document.querySelector('.today-layout').before(notice);
    } else oldNotice?.remove();
    const navCount = incoming.querySelector('.nav-count')?.textContent;
    if (navCount) all('.nav-count').forEach(node => { node.textContent = navCount; });

    const updated = plan.querySelector(`[data-task-id="${taskId}"]`);
    if (updated && blockHeight) motion?.resize(updated.closest('.period-card, .focus-card'), blockHeight);
    if (updated && previousStatus !== updated.dataset.taskStatus) motion?.markTask(updated, completed(updated.dataset.taskStatus));
    if (shouldFocus) {
      const nextButton = updated?.querySelector('button:not(:disabled)');
      if (nextButton) nextButton.focus({ preventScroll: true });
      else {
        const counter = plan.querySelector('.plan-counter');
        counter.tabIndex = -1;
        counter.focus({ preventScroll: true });
      }
    }
    window.BerezhnoUI?.appendServerToasts(incoming);
  }

  document.addEventListener('submit', async event => {
    const form = event.target;
    if (!form.matches('form[data-habit-log]')) return;
    const submitter = event.submitter;
    // Не вмешиваемся в неизвестный сценарий: остаётся нативная отправка.
    if (submitter?.name !== 'status' || !['done', 'minimum', 'reset'].includes(submitter.value)) return;
    const plan = form.closest('.daily-plan');
    const row = form.closest('[data-task-id]');
    if (!plan || !row) return;
    event.preventDefault();
    if (busy) return;
    const taskId = row.dataset.taskId;
    const data = new FormData(form);
    data.set(submitter.name, submitter.value);
    const hadFocus = plan.contains(document.activeElement);
    const buttons = all('button', plan).map(button => [button, button.disabled]);
    const restore = () => buttons.forEach(([button, disabled]) => {
      if (button.isConnected) button.disabled = disabled;
      button.classList.remove('is-loading');
    });
    busy = true;
    plan.setAttribute('aria-busy', 'true');
    buttons.forEach(([button]) => { button.disabled = true; });
    submitter.classList.add('is-loading');
    controller = new AbortController();
    const timeout = setTimeout(() => controller?.abort(), 12000);
    try {
      const response = await fetch(form.action, {
        method: 'POST', body: data, credentials: 'same-origin',
        headers: { Accept: 'text/html', 'X-Requested-With': 'XMLHttpRequest' },
        signal: controller.signal,
      });
      const incoming = new DOMParser().parseFromString(await response.text(), 'text/html');
      if (!response.ok) {
        const message = incoming.querySelector('.error-page p:not(.eyebrow)')?.textContent.trim();
        throw new Error(message || 'Сервер не принял отметку. Попробуй обновить страницу.');
      }
      const url = new URL(response.url);
      if (url.origin !== location.origin || !incoming.querySelector('.daily-plan .progress-track > span') || !incoming.querySelector('.daily-plan .plan-counter')) {
        throw new Error('Не удалось обновить план. Обнови страницу, чтобы проверить отметку.');
      }
      if (!plan.isConnected) return;
      const shouldFocus = hadFocus && (document.activeElement === document.body || plan.contains(document.activeElement));
      restore();
      syncPlan(plan, incoming, taskId, shouldFocus);
      // Сохраняем подписанную демо-сессию в URL, как при обычном Redirect.
      history.replaceState(history.state, '', url.pathname + url.search + location.hash);
    } catch (error) {
      if (!plan.isConnected) return;
      restore();
      const message = error.name === 'AbortError' || error instanceof TypeError
        ? 'Не удалось получить ответ. Обнови страницу, чтобы проверить, сохранилась ли отметка.'
        : error.message;
      notifyError(message);
      if (hadFocus && document.activeElement === document.body && !submitter.disabled) submitter.focus({ preventScroll: true });
    } finally {
      clearTimeout(timeout);
      restore();
      plan.removeAttribute('aria-busy');
      busy = false;
      controller = null;
    }
  });
  window.addEventListener('pagehide', () => controller?.abort());
})();
