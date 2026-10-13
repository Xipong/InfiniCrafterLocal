'use strict';
(() => {
  const {pages} = JSON.parse(document.getElementById('handbook-data').textContent);
  const labels = {user: 'Игроку', development: 'Разработчику', reference: 'Справочники', archive: 'История'};
  const listLabels = {user: 'Главы для игрока', development: 'Главы для разработчика', reference: 'Контракты и каталоги', archive: 'История проекта'};
  const order = ['README_RU.md', 'START_RU.md', 'PROVIDERS_RU.md', 'SETTINGS_RU.md', 'DIAGNOSTICS_RU.md', 'MULTIPLAYER_RU.md', 'UPDATING_RU.md', 'COMMANDS_RU.md', 'OPERATIONS_RU.md', 'OPENROUTER_ROUTING_RU.md', 'CODEX_IMAGE_OAUTH_RU.md'];
  const byPath = new Map(pages.map(page => [page.path, page]));
  const search = document.getElementById('search');
  const sidebar = document.getElementById('sidebar');
  const toggle = document.getElementById('contents-toggle');
  const article = document.getElementById('article');
  const list = document.getElementById('page-list');
  const toc = document.getElementById('toc');
  const tocDetails = document.getElementById('toc-details');
  const mobile = window.matchMedia('(max-width: 760px)');
  let audience = 'user';
  let current = null;
  let anchor = '';
  const normalize = text => text.toLocaleLowerCase('ru').replace(/ё/g, 'е');
  for (const page of pages) page.searchText = normalize(page.title + '\n' + page.text);
  const route = (path, id = '') => '#/' + path.split('/').map(encodeURIComponent).join('/') + (id ? '@' + encodeURIComponent(id) : '');
  const home = group => byPath.get(group === 'user' ? 'docs/user/START_RU.md' : `docs/${group}/README_RU.md`) || pages.find(page => page.audience === group);
  const groupPages = group => pages.filter(page => page.audience === group).sort((a, b) => {
    const rank = page => {
      if (!page.path.startsWith('docs/' + group + '/')) return 1000;
      const filename = page.path.split('/').pop();
      if (group === 'user') return order.includes(filename) ? order.indexOf(filename) : 100;
      return filename === 'README_RU.md' ? -1 : (page.path.includes('/generated/') ? 200 : 100);
    };
    return rank(a) - rank(b) || a.path.localeCompare(b.path, 'ru');
  });
  function setOpen(open) {
    sidebar.classList.toggle('is-open', open);
    toggle.setAttribute('aria-expanded', String(open));
  }
  function textElement(tag, text, className = '') {
    const node = document.createElement(tag);
    node.textContent = text;
    if (className) node.className = className;
    return node;
  }
  function appendSnippet(node, page, terms) {
    const text = page.text.replace(/\s+/g, ' ');
    const lower = normalize(text);
    const positions = terms.map(term => lower.indexOf(term)).filter(pos => pos >= 0);
    const start = Math.max(0, (positions.length ? Math.min(...positions) : 0) - 45);
    const snippet = (start ? '…' : '') + text.slice(start, start + 170) + (start + 170 < text.length ? '…' : '');
    const span = textElement('span', '', 'search-snippet');
    // Highlight with text nodes, never interpret search text as HTML.
    const normalized = normalize(snippet);
    let offset = 0;
    while (offset < snippet.length) {
      const matches = terms.map(term => ({pos: normalized.indexOf(term, offset), length: term.length})).filter(match => match.pos >= 0).sort((a, b) => a.pos - b.pos);
      if (!matches.length) { span.append(document.createTextNode(snippet.slice(offset))); break; }
      const match = matches[0];
      span.append(document.createTextNode(snippet.slice(offset, match.pos)));
      span.append(textElement('mark', snippet.slice(match.pos, match.pos + match.length)));
      offset = match.pos + match.length;
    }
    node.append(span);
  }
  function renderList() {
    const query = normalize(search.value.trim());
    const terms = query.split(/\s+/).filter(Boolean);
    const matches = terms.length ? pages.filter(page => terms.every(term => page.searchText.includes(term))).sort((a, b) => {
      const score = page => terms.filter(term => normalize(page.title).includes(term)).length;
      return score(b) - score(a) || a.path.localeCompare(b.path, 'ru');
    }) : groupPages(audience);
    list.replaceChildren();
    document.getElementById('clear-search').hidden = !query;
    document.getElementById('list-label').textContent = query ? 'По всей книге' : listLabels[audience];
    document.getElementById('page-count').textContent = String(matches.length);
    document.getElementById('result-status').textContent = query ? `Найдено страниц: ${matches.length}` : `Страниц в разделе: ${matches.length}`;
    if (!matches.length) {
      const empty = textElement('div', 'Ничего не найдено', 'empty-state');
      empty.append(textElement('p', 'Попробуй другие слова или очисти поиск. Поиск проверяет названия и полный текст всех разделов.'));
      list.append(empty);
    }
    for (const page of matches) {
      const link = textElement('a', page.title);
      link.href = route(page.path);
      if (current && page.path === current.path) link.setAttribute('aria-current', 'page');
      if (query) {
        link.append(textElement('small', labels[page.audience] + (page.path.includes('/generated/') ? ' · Каталог' : '')));
        appendSnippet(link, page, terms);
      }
      list.append(link);
    }
  }
  function clearSearch() {
    search.value = '';
    renderList();
  }
  function setAudience(group) {
    audience = group;
    document.querySelectorAll('[data-audience]').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.audience === group)));
    renderList();
  }
  function scrollToAnchor() {
    if (!anchor) { window.scrollTo(0, 0); return; }
    const target = [...article.querySelectorAll('[id],a[name]')].find(node => node.id === anchor || node.getAttribute('name') === anchor);
    if (target) target.scrollIntoView({block: 'start'});
    toc.querySelectorAll('a').forEach(link => link.setAttribute('aria-current', link.hash === route(current.path, anchor) ? 'location' : 'false'));
  }
  function renderPage(page) {
    current = page;
    setAudience(page.audience);
    document.title = page.title + ' — Infinicraft';
    document.getElementById('section-label').textContent = labels[page.audience];
    document.getElementById('page-kind').textContent = page.path.includes('/generated/') ? 'Сгенерированный каталог' : (page.audience === 'archive' ? 'Архивная страница' : 'Руководство');
    document.getElementById('history-notice').hidden = page.audience !== 'archive';
    article.innerHTML = page.html;
    article.querySelectorAll('table').forEach(table => {
      const wrapper = document.createElement('div');
      wrapper.className = 'table-scroll';
      wrapper.tabIndex = 0;
      wrapper.setAttribute('role', 'region');
      wrapper.setAttribute('aria-label', 'Таблица: прокручивай горизонтально, если не помещается');
      table.replaceWith(wrapper);
      wrapper.append(table);
      const hint = textElement('p', 'Если таблица не помещается, прокрути её по горизонтали →', 'table-hint');
      wrapper.after(hint);
    });
    article.querySelectorAll('pre').forEach(pre => {
      pre.tabIndex = 0;
      const code = pre.querySelector('code');
      const language = code && [...code.classList].find(name => name.startsWith('language-'));
      if (language) pre.dataset.language = language.slice(9);
    });
    article.querySelectorAll('a[href^="http"]').forEach(link => { link.target = '_blank'; link.rel = 'noopener noreferrer'; });
    toc.replaceChildren();
    for (const section of page.toc) {
      const link = textElement('a', section.title, 'level-' + section.level);
      link.href = route(page.path, section.id);
      toc.append(link);
    }
    if (!page.toc.length) toc.append(textElement('p', 'Короткая страница, без разделов.', 'no-sections'));
    tocDetails.open = window.innerWidth > 1200;
    document.getElementById('source-path').textContent = page.path;
    const source = document.getElementById('source-link');
    source.href = page.path.split('/').map(encodeURIComponent).join('/');
    source.target = '_blank';
    source.rel = 'noopener';
    const turns = document.getElementById('page-turns');
    turns.replaceChildren();
    const siblings = groupPages(page.audience);
    const index = siblings.findIndex(sibling => sibling.path === page.path);
    for (const [offset, label] of [[-1, '← Предыдущая глава'], [1, 'Следующая глава →']]) {
      const sibling = siblings[index + offset];
      if (!sibling) continue;
      const link = document.createElement('a');
      link.href = route(sibling.path);
      link.append(textElement('small', label), document.createTextNode(sibling.title));
      turns.append(link);
    }
  }
  function navigate() {
    const raw = location.hash.startsWith('#/') ? location.hash.slice(2) : '';
    let path;
    try {
      const separator = raw.indexOf('@');
      path = decodeURIComponent(separator >= 0 ? raw.slice(0, separator) : raw);
      anchor = separator >= 0 ? decodeURIComponent(raw.slice(separator + 1)) : '';
    } catch (_) { path = ''; anchor = ''; }
    const page = byPath.get(path) || home('user') || pages[0];
    if (!page) { article.textContent = 'В книге пока нет страниц.'; return; }
    if (!byPath.has(path)) {
      history.replaceState(null, '', route(page.path));
      anchor = '';
    }
    if (!current || current.path !== page.path) renderPage(page);
    setOpen(false);
    scrollToAnchor();
  }
  document.querySelectorAll('[data-audience]').forEach(button => button.addEventListener('click', () => {
    clearSearch();
    const page = home(button.dataset.audience);
    if (page) { location.hash = route(page.path); navigate(); }
  }));
  search.addEventListener('input', renderList);
  document.getElementById('clear-search').addEventListener('click', () => { clearSearch(); search.focus(); });
  toggle.addEventListener('click', () => setOpen(!sidebar.classList.contains('is-open')));
  list.addEventListener('click', event => {
    if (event.target.closest('a')) setOpen(false);
  });
  document.addEventListener('keydown', event => {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
      event.preventDefault(); setOpen(true); search.focus(); search.select();
    }
    if (event.key === 'Escape') { clearSearch(); if (mobile.matches) setOpen(false); }
  });
  document.querySelectorAll('.back-top,.skip-link').forEach(link => link.addEventListener('click', event => {
    event.preventDefault(); window.scrollTo(0, 0); article.focus({preventScroll: true});
  }));
  mobile.addEventListener('change', () => { tocDetails.open = !mobile.matches && window.innerWidth > 1200; setOpen(false); });
  window.addEventListener('hashchange', navigate);
  navigate();
})();
