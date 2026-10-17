/* Presentation-only interactions. The generator and its drafts stay in studio.js. */
'use strict';
(() => {
  const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)');
  const finePointer = matchMedia('(hover: hover) and (pointer: fine)');
  const parts = new Set(['mechanics', 'image', 'sprite']);
  let stage = null, hovered = null, focused = null;
  let userPaused = false, exploded = false, onScreen = false;
  let frame = 0, lastFrame = 0, navigationFrame = 0;
  let x = 0, y = 0, targetX = 0, targetY = 0;

  function setStage(name, value) {
    if (!stage) return;
    if (value === undefined) delete stage.dataset[name];
    else if (stage.dataset[name] !== value) stage.dataset[name] = value;
  }

  function canMove() {
    return stage?.isConnected && onScreen && !document.hidden &&
      finePointer.matches && !reducedMotion.matches && !userPaused;
  }

  function paintPointer() {
    if (!stage) return;
    stage.style.setProperty('--pointer-x', x.toFixed(4));
    stage.style.setProperty('--pointer-y', y.toFixed(4));
  }

  function resetPointer() {
    cancelAnimationFrame(frame);
    frame = lastFrame = 0;
    x = y = targetX = targetY = 0;
    paintPointer();
  }

  function animatePointer(time) {
    frame = 0;
    if (!canMove()) return resetPointer();
    const elapsed = lastFrame ? Math.min(time - lastFrame, 40) : 16;
    const easing = 1 - Math.exp(-elapsed / 75);
    lastFrame = time;
    x += (targetX - x) * easing;
    y += (targetY - y) * easing;
    const settled = Math.abs(targetX - x) + Math.abs(targetY - y) < 0.001;
    if (settled) { x = targetX; y = targetY; lastFrame = 0; }
    paintPointer();
    // A settled pointer never leaves an idle requestAnimationFrame loop running.
    if (!settled) frame = requestAnimationFrame(animatePointer);
  }

  function requestPointerFrame() {
    if (!frame && canMove()) frame = requestAnimationFrame(animatePointer);
  }

  function movePointer(event) {
    if (!canMove() || event.pointerType === 'touch') return;
    const rect = stage.getBoundingClientRect();
    if (!rect.width || !rect.height) return;
    const clamp = value => Math.max(-1, Math.min(1, value));
    targetX = clamp((event.clientX - rect.left) / rect.width * 2 - 1);
    targetY = clamp((event.clientY - rect.top) / rect.height * 2 - 1);
    requestPointerFrame();
  }

  function leavePointer() {
    targetX = targetY = 0;
    if (canMove()) requestPointerFrame();
    else resetPointer();
  }

  function partControl(element) {
    const control = element instanceof Element ? element.closest('[data-craft-part]') : null;
    return control?.isConnected && parts.has(control.dataset.craftPart) ? control : null;
  }

  function syncPart() {
    const focus = partControl(focused);
    const control = focus?.matches(':focus-visible') ? focus : partControl(hovered) || focus;
    setStage('part', control?.dataset.craftPart);
  }

  function sync() {
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
    document.querySelectorAll('[data-craft-toggle]').forEach(button => {
      button.setAttribute('aria-pressed', String(exploded));
      button.setAttribute('aria-label', 'Разобрать объект по слоям');
      button.title = exploded ? 'Собрать объект' : 'Разобрать объект по слоям';
      const label = button.querySelector('[data-craft-label]');
      if (label) label.textContent = exploded ? 'Собрать объект' : 'Разобрать по слоям';
    });
    setStage('exploded', String(exploded));
    setStage('dormant', String(document.hidden || !onScreen));
    syncPart();
    if (!canMove()) resetPointer();
  }

  const observer = new IntersectionObserver(entries => {
    const entry = entries.find(item => item.target === stage);
    if (!entry) return;
    onScreen = entry.isIntersecting;
    sync();
  });

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
      const pixels = `${value}px`;
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
    const nextStage = document.querySelector('.craft-stage');
    if (nextStage !== stage) {
      observer.disconnect();
      stage?.removeEventListener('pointermove', movePointer);
      stage?.removeEventListener('pointerleave', leavePointer);
      stage = nextStage;
      resetPointer();
      const rect = stage?.getBoundingClientRect();
      onScreen = !!rect && rect.width > 0 && rect.height > 0 &&
        rect.bottom > 0 && rect.right > 0 && rect.top < innerHeight && rect.left < innerWidth;
      if (stage) {
        stage.addEventListener('pointermove', movePointer, {passive: true});
        stage.addEventListener('pointerleave', leavePointer, {passive: true});
        observer.observe(stage);
      }
    }
    // Preserve animation phase when a render keeps the same stage node.
    hovered = finePointer.matches ? document.querySelector('[data-craft-part]:hover') : null;
    focused = document.activeElement;
    sync();
    positionNavigation();
  }

  document.addEventListener('keydown', () => {
    const nav = document.getElementById('navigation');
    if (nav) nav.dataset.input = 'keyboard';
  });
  document.addEventListener('pointerdown', event => {
    const nav = document.getElementById('navigation');
    const link = event.target instanceof Element ? event.target.closest('.nav-link') : null;
    if (link && nav?.contains(link)) nav.dataset.input = 'pointer';
  }, {passive: true});
  document.addEventListener('pointerover', event => {
    if (!finePointer.matches || event.pointerType === 'touch') return;
    hovered = partControl(event.target);
    syncPart();
  });
  document.addEventListener('pointerout', event => {
    if (!finePointer.matches || event.pointerType === 'touch') return;
    hovered = partControl(event.relatedTarget);
    syncPart();
  });
  document.addEventListener('focusin', event => { focused = event.target; syncPart(); });
  document.addEventListener('focusout', event => { focused = event.relatedTarget; syncPart(); });
  document.addEventListener('click', event => {
    const button = event.target instanceof Element ?
      event.target.closest('[data-craft-toggle], [data-motion-toggle]') : null;
    if (!button || button.disabled) return;
    event.preventDefault();
    if (button.hasAttribute('data-motion-toggle')) {
      if (reducedMotion.matches) return;
      userPaused = !userPaused;
    } else exploded = !exploded;
    sync();
  });

  reducedMotion.addEventListener('change', sync);
  finePointer.addEventListener('change', () => {
    if (!finePointer.matches) hovered = null;
    sync();
  });
  document.addEventListener('visibilitychange', sync);
  document.addEventListener('studio:render', bind);
  document.addEventListener('studio:route', () => { resetPointer(); bind(); });
  window.addEventListener('hashchange', scheduleNavigation);
  window.addEventListener('resize', scheduleNavigation, {passive: true});
  bind();
})();
