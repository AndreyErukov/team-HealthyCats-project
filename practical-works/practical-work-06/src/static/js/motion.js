/* «бережно» · анимации без сторонних библиотек (Web Animations API).
 * Модуль отвечает только за представление, не записывает выполнения.
 */
(() => {
  'use strict';
  const preference = window.matchMedia('(prefers-reduced-motion: reduce)');
  const ease = 'cubic-bezier(.22, 1, .36, 1)';
  const active = new Set();
  const progressAnimations = new WeakMap();
  const heightAnimations = new WeakMap();
  const disclosureAnimations = new WeakMap();
  const closingDialogs = new WeakMap();
  const openingDialogs = new WeakMap();
  const revealAnimations = new WeakMap();
  const enabled = () => !preference.matches && typeof Element.prototype.animate === 'function';

  function animate(element, frames, options = {}) {
    if (!element || !enabled()) return null;
    const animation = element.animate(frames, { duration: 300, easing: ease, ...options });
    active.add(animation);
    // Отмена — нормальная ситуация при быстром повторном действии.
    animation.finished.then(() => active.delete(animation), () => active.delete(animation));
    return animation;
  }
  const finished = animation => animation ? animation.finished.catch(() => {}) : Promise.resolve();

  function reveal(element, delay = 0) {
    if (!element) return null;
    revealAnimations.get(element)?.cancel();
    const animation = animate(element, [{ opacity: .3, transform: 'translateY(9px)' }, { opacity: 1, transform: 'translateY(0)' }], { duration: 370, delay, fill: 'backwards' });
    if (animation) revealAnimations.set(element, animation);
    return animation;
  }

  function progress(track, percentage, fromZero = false) {
    const fill = track?.firstElementChild;
    if (!fill) return;
    const target = Math.max(0, Math.min(100, Number(percentage) || 0));
    const width = track.getBoundingClientRect().width;
    const start = fromZero ? 0 : (width ? fill.getBoundingClientRect().width / width * 100 : target);
    progressAnimations.get(fill)?.cancel();
    fill.style.width = `${target}%`;
    const animation = animate(fill, [{ width: `${start}%` }, { width: `${target}%` }], { duration: 680 });
    if (animation) progressAnimations.set(fill, animation);
  }

  function resize(element, previousHeight) {
    if (!element) return;
    const previous = heightAnimations.get(element);
    const overflow = previous ? previous.overflow : element.style.overflow;
    previous?.animation?.cancel();
    const height = element.getBoundingClientRect().height;
    if (!enabled() || Math.abs(height - previousHeight) < 1) {
      element.style.overflow = overflow;
      heightAnimations.delete(element);
      return;
    }
    element.style.overflow = 'hidden';
    const animation = animate(element, [{ height: `${previousHeight}px` }, { height: `${height}px` }], { duration: 340 });
    const entry = { animation, overflow };
    heightAnimations.set(element, entry);
    finished(animation).then(() => {
      if (heightAnimations.get(element) === entry) {
        element.style.overflow = overflow;
        heightAnimations.delete(element);
      }
    });
  }

  function markTask(element, complete) {
    if (!element || !enabled()) return;
    const style = getComputedStyle(element);
    const mint = getComputedStyle(document.documentElement).getPropertyValue('--mint-strong').trim();
    animate(element, [{ backgroundColor: mint }, { backgroundColor: style.backgroundColor }], { duration: 680 });
    const mark = element.querySelector('.task-check') || element.querySelector('.focus-done');
    if (mark) animate(mark, [
      { transform: 'scale(.76)', opacity: .4 },
      { transform: 'scale(1.1)', opacity: 1, offset: .6 },
      { transform: 'scale(1)', opacity: 1 },
    ], { duration: 380 });
    if (complete) {
      const check = element.querySelector('.task-check .icon, .focus-done .icon');
      if (check) {
        check.style.strokeDasharray = '32';
        const draw = animate(check, [{ strokeDashoffset: 32 }, { strokeDashoffset: 0 }], { duration: 420, delay: 60, fill: 'backwards' });
        finished(draw).then(() => { check.style.strokeDasharray = ''; });
      }
    }
    const text = element.querySelector('.task-description, .focus-copy');
    animate(text, [{ opacity: .55, transform: 'translateX(-3px)' }, { opacity: 1, transform: 'translateX(0)' }], { duration: 280 });
  }

  function counter(element) {
    animate(element, [{ opacity: .45, transform: 'translateY(3px)' }, { opacity: 1, transform: 'translateY(0)' }], { duration: 300 });
  }

  function openDialog(dialog) {
    if (!dialog || dialog.open) return;
    dialog.showModal();
    const animation = animate(dialog, [{ opacity: 0, transform: 'translateY(12px) scale(.98)' }, { opacity: 1, transform: 'translateY(0) scale(1)' }], { duration: 260 });
    if (animation) openingDialogs.set(dialog, animation);
  }
  function closeDialog(dialog) {
    if (!dialog?.open) return Promise.resolve();
    if (closingDialogs.has(dialog)) return closingDialogs.get(dialog);
    const style = getComputedStyle(dialog);
    const before = { opacity: style.opacity, transform: style.transform };
    openingDialogs.get(dialog)?.cancel();
    openingDialogs.delete(dialog);
    if (!enabled()) { dialog.close(); return Promise.resolve(); }
    const animation = animate(dialog, [before, { opacity: 0, transform: 'translateY(7px)' }], { duration: 140 });
    const promise = finished(animation).then(() => {
      if (dialog.open) dialog.close();
      closingDialogs.delete(dialog);
    });
    closingDialogs.set(dialog, promise);
    return promise;
  }

  async function disclose(panel, expanded) {
    const wasHidden = panel.hidden;
    const style = getComputedStyle(panel);
    const before = wasHidden ? null : {
      height: `${panel.getBoundingClientRect().height}px`, opacity: style.opacity,
      paddingTop: style.paddingTop, paddingBottom: style.paddingBottom,
      marginTop: style.marginTop, marginBottom: style.marginBottom,
      borderTopWidth: style.borderTopWidth, borderBottomWidth: style.borderBottomWidth,
    };
    const previous = disclosureAnimations.get(panel);
    const overflow = previous ? previous.overflow : panel.style.overflow;
    previous?.animation?.cancel();
    panel.hidden = false;
    panel.inert = !expanded;
    const fullStyle = getComputedStyle(panel);
    const full = {
      height: `${panel.getBoundingClientRect().height}px`, opacity: 1,
      paddingTop: fullStyle.paddingTop, paddingBottom: fullStyle.paddingBottom,
      marginTop: fullStyle.marginTop, marginBottom: fullStyle.marginBottom,
      borderTopWidth: fullStyle.borderTopWidth, borderBottomWidth: fullStyle.borderBottomWidth,
    };
    const empty = { height: '0px', opacity: 0, paddingTop: '0px', paddingBottom: '0px', marginTop: '0px', marginBottom: '0px', borderTopWidth: '0px', borderBottomWidth: '0px' };
    panel.style.overflow = 'hidden';
    const animation = animate(panel, [before || empty, expanded ? full : empty], { duration: expanded ? 300 : 180 });
    // Уникальная запись нужна и без анимации (например, при reduced motion).
    const entry = { animation, overflow };
    disclosureAnimations.set(panel, entry);
    await finished(animation);
    if (disclosureAnimations.get(panel) !== entry) return;
    panel.hidden = !expanded;
    panel.inert = false;
    panel.style.overflow = overflow;
    disclosureAnimations.delete(panel);
    if (expanded) panel.scrollIntoView({ behavior: enabled() ? 'smooth' : 'auto', block: 'nearest' });
  }

  function pressWave(element, clientX, clientY) {
    if (!enabled() || element.disabled || element.getAttribute('aria-disabled') === 'true') return;
    const rect = element.getBoundingClientRect();
    const size = Math.hypot(rect.width, rect.height) * 2;
    const wave = document.createElement('span');
    wave.className = 'press-wave';
    wave.setAttribute('aria-hidden', 'true');
    Object.assign(wave.style, {
      width: `${size}px`, height: `${size}px`,
      left: `${(clientX ?? rect.left + rect.width / 2) - rect.left - size / 2}px`,
      top: `${(clientY ?? rect.top + rect.height / 2) - rect.top - size / 2}px`,
    });
    element.append(wave);
    const animation = animate(wave, [{ transform: 'scale(0)', opacity: .16 }, { transform: 'scale(1)', opacity: 0 }], { duration: 450, easing: 'ease-out' });
    finished(animation).then(() => wave.remove());
  }
  document.addEventListener('pointerdown', event => {
    if (event.button !== 0) return;
    const button = event.target.closest('.button, .icon-button, .nav-link, .filter-tab');
    if (button) pressWave(button, event.clientX, event.clientY);
  });
  document.addEventListener('keydown', event => {
    if (event.repeat || !['Enter', ' '].includes(event.key)) return;
    const button = event.target.closest('.button, .icon-button, .nav-link, .filter-tab');
    if (button) pressWave(button);
  });
  document.addEventListener('change', event => {
    const input = event.target;
    if (!input.matches('input[type="checkbox"], input[type="radio"]')) return;
    const label = input.closest('.day-option, .reason-option, .segmented label, .theme-option');
    const face = label?.querySelector(':scope > span');
    if (face) animate(face, [{ transform: 'scale(.96)' }, { transform: 'scale(1.035)', offset: .6 }, { transform: 'scale(1)' }], { duration: 230 });
  });
  document.addEventListener('click', event => {
    const cell = event.target.closest('.heat-cell');
    if (cell) animate(cell, [{ transform: 'scale(.96)' }, { transform: 'scale(1.035)', offset: .6 }, { transform: 'scale(1)' }], { duration: 240 });
  });

  function setMode() {
    document.documentElement.dataset.motion = enabled() ? 'on' : 'off';
    if (!enabled()) active.forEach(animation => { try { animation.finish(); } catch (_) { animation.cancel(); } });
  }
  preference.addEventListener('change', setMode);
  setMode();

  function initialize() {
    document.querySelectorAll('.progress-track, .stat-progress').forEach(track => {
      progress(track, parseFloat(track.firstElementChild?.style.width) || 0, true);
    });
    if (!enabled()) return;
    const selectors = '.page-header, .focus-card, .period-card, .today-aside > .card, .habit-card, .care-banner, .template-banner, .habit-form, .form-aside > .card, .reason-card, .soft-step-card, .ai-support-card, .stat-card, .heatmap-card, .schedule-card, .schedule-recommendation, .settings-card, .profile-settings, .auth-card';
    const elements = [...document.querySelectorAll(selectors)].filter(el => !el.hidden);
    if (!('IntersectionObserver' in window)) return;
    const observer = new IntersectionObserver(entries => {
      let delay = 0;
      entries.forEach(entry => {
        if (!entry.isIntersecting) return;
        observer.unobserve(entry.target);
        reveal(entry.target, Math.min(delay++ * 35, 140));
      });
    }, { threshold: .04 });
    elements.forEach(element => observer.observe(element));
  }
  window.BerezhnoMotion = Object.freeze({
    get enabled() { return enabled(); }, animate, reveal, progress, resize,
    markTask, counter, openDialog, closeDialog, disclose,
  });
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', initialize, { once: true });
  else initialize();
})();
