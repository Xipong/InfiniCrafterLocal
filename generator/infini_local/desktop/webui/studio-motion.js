/* Presentation-only motion. Configuration and generator actions stay in studio.js. */
'use strict';
(() => {
  const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)');
  const finePointer = matchMedia('(hover: hover) and (pointer: fine)');
  let userPaused = false, activeCard = null;
  let frame = 0, lastFrame = 0, navigationFrame = 0;
  let x = 0, y = 0, targetX = 0, targetY = 0;

  function motionAllowed() {
    return finePointer.matches && !reducedMotion.matches && !userPaused && !document.hidden;
  }

  function clearPointer() {
    cancelAnimationFrame(frame);
    cardObserver.disconnect();
    if (activeCard) activeCard.dataset.pointerActive = 'false';
    activeCard = null;
    frame = lastFrame = 0;
    x = y = targetX = targetY = 0;
  }

  function paintPointer() {
    activeCard.style.setProperty('--pointer-x', x.toFixed(4));
    activeCard.style.setProperty('--pointer-y', y.toFixed(4));
  }

  function animatePointer(time) {
    frame = 0;
    if (!activeCard?.isConnected || !motionAllowed()) return clearPointer();
    const elapsed = lastFrame ? Math.min(time - lastFrame, 40) : 16;
    const easing = 1 - Math.exp(-elapsed / 65);
    lastFrame = time;
    x += (targetX - x) * easing;
    y += (targetY - y) * easing;
    const settled = Math.abs(targetX - x) + Math.abs(targetY - y) < 0.001;
    if (settled) { x = targetX; y = targetY; lastFrame = 0; }
    paintPointer();
    // Only pointer movement schedules frames; a settled highlight does no work.
    if (!settled) frame = requestAnimationFrame(animatePointer);
  }

  function flowCard(element) {
    return element instanceof Element ? element.closest('[data-flow-card]') : null;
  }

  function movePointer(event) {
    if (event.pointerType === 'touch') return;
    if (!motionAllowed()) return clearPointer();
    const card = flowCard(event.target);
    if (!card) return clearPointer();
    const rect = card.getBoundingClientRect();
    if (!rect.width || !rect.height) return;
    const clamp = value => Math.max(-1, Math.min(1, value));
    const nextX = clamp((event.clientX - rect.left) / rect.width * 2 - 1);
    const nextY = clamp((event.clientY - rect.top) / rect.height * 2 - 1);
    if (card !== activeCard) {
      clearPointer();
      activeCard = card;
      x = targetX = nextX;
      y = targetY = nextY;
      paintPointer();
      card.dataset.pointerActive = 'true';
      cardObserver.observe(card);
      return;
    }
    targetX = nextX;
    targetY = nextY;
    if (!frame) frame = requestAnimationFrame(animatePointer);
  }

  const cardObserver = new IntersectionObserver(entries => {
    if (entries.some(entry => entry.target === activeCard && !entry.isIntersecting)) clearPointer();
  });

  function syncMotion() {
    const paused = userPaused || reducedMotion.matches;
    document.body.dataset.motion = paused ? 'paused' : 'running';
    document.querySelectorAll('[data-motion-toggle]').forEach(button => {
      button.disabled = reducedMotion.matches;
      button.setAttribute('aria-pressed', String(paused));
      button.setAttribute('aria-label', 'Пауза анимации');
      button.title = reducedMotion.matches ? 'Движение отключено системной настройкой' :
        userPaused ? 'Возобновить движение' : 'Приостановить движение';
      const label = button.querySelector('[data-motion-label]');
      if (label) label.textContent = reducedMotion.matches ? 'Без движения' : userPaused ? 'На паузе' : 'Движение';
    });
    if (!motionAllowed()) clearPointer();
  }

  function positionNavigation() {
    const nav = document.getElementById('navigation');
    const active = nav?.querySelector('.nav-link.active');
    if (!active) return;
    let marker = nav.querySelector('.nav-active-marker');
    const firstPosition = !marker;
    if (!marker) {
      marker = document.createElement('span');
      marker.className = 'nav-active-marker';
      marker.setAttribute('aria-hidden', 'true');
      nav.append(marker);
      if (!nav.dataset.input) nav.dataset.input = 'keyboard';
    }
    const bounds = {top: active.offsetTop, left: active.offsetLeft,
      width: active.offsetWidth, height: active.offsetHeight};
    Object.entries(bounds).forEach(([property, value]) => {
      const pixels = String(value) + 'px';
      if (marker.style[property] !== pixels) marker.style[property] = pixels;
    });
    if (firstPosition) {
      // Establish the initial position before enabling the travelling highlight.
      void marker.offsetWidth;
      requestAnimationFrame(() => {
        if (marker.isConnected) marker.classList.add('marker-ready');
      });
    }
  }

  function scheduleNavigation() {
    if (navigationFrame) return;
    navigationFrame = requestAnimationFrame(() => {
      navigationFrame = 0;
      positionNavigation();
    });
  }

  function bind() {
    if (activeCard && !activeCard.isConnected) clearPointer();
    syncMotion();
    positionNavigation();
  }

  document.addEventListener('keydown', () => {
    const nav = document.getElementById('navigation');
    if (nav) nav.dataset.input = 'keyboard';
    clearPointer();
  });
  document.addEventListener('pointerdown', event => {
    const nav = document.getElementById('navigation');
    const route = event.target instanceof Element ?
      event.target.closest('.nav-link, [data-flow-card]') : null;
    if (route && nav) nav.dataset.input = 'pointer';
  }, {passive: true});
  document.addEventListener('pointerover', movePointer, {passive: true});
  document.addEventListener('pointermove', movePointer, {passive: true});
  document.addEventListener('pointerout', event => {
    if (activeCard && flowCard(event.relatedTarget) !== activeCard) clearPointer();
  }, {passive: true});
  document.addEventListener('pointercancel', clearPointer, {passive: true});
  document.addEventListener('click', event => {
    const button = event.target instanceof Element ? event.target.closest('[data-motion-toggle]') : null;
    if (!button || button.disabled || reducedMotion.matches) return;
    event.preventDefault();
    userPaused = !userPaused;
    syncMotion();
  });

  reducedMotion.addEventListener('change', syncMotion);
  finePointer.addEventListener('change', syncMotion);
  document.addEventListener('visibilitychange', syncMotion);
  document.addEventListener('studio:render', bind);
  document.addEventListener('studio:route', () => { clearPointer(); bind(); });
  window.addEventListener('hashchange', scheduleNavigation);
  window.addEventListener('resize', () => { clearPointer(); scheduleNavigation(); }, {passive: true});
  bind();
})();
