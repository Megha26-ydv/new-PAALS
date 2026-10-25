/* motion.js — page transitions, ambient hue hand-off, hero word reveal and staggered reveals.
   Works on content the page scripts render later (tables, cards) via a MutationObserver. */
(function () {
  const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const body = document.body;
  const page = body.dataset.page;
  const PREV_KEY = 'paals-prev-page';

  // ── Ambient backdrop: fade from the previous page's hues into this page's ──
  let prev = null;
  try { prev = sessionStorage.getItem(PREV_KEY); } catch (e) {}
  const current = document.querySelector('.ambient.current');
  if (prev && prev !== page && !reduce) {
    const old = document.createElement('div');
    old.className = 'ambient prev';
    applyHues(old, prev);
    current.before(old);
    requestAnimationFrame(() => requestAnimationFrame(() => {
      old.classList.add('out'); current.classList.add('in');
      setTimeout(() => old.remove(), 1000);
    }));
  } else {
    current.classList.add('in');
  }

  // Read another page's hue tokens by briefly switching body[data-page]
  function applyHues(el, name) {
    const saved = body.dataset.page;
    body.dataset.page = name;
    const cs = getComputedStyle(body);
    ['--amb-a', '--amb-b', '--amb-c'].forEach(v => el.style.setProperty(v, cs.getPropertyValue(v)));
    body.dataset.page = saved;
  }

  if (reduce) return;
  body.classList.add('motion-ready', 'page-enter');
  setTimeout(() => body.classList.remove('page-enter'), 800);

  // ── Hero headline: split into words that rise in sequence ──
  const h1 = document.querySelector('.page-hero h1');
  if (h1) {
    h1.innerHTML = h1.textContent.trim().split(/\s+/)
      .map((w, i) => `<span class="w" style="--i:${i}"><span>${w}</span></span>`).join(' ');
  }

  // ── Page transitions: blur-swipe out, then navigate ──
  document.addEventListener('click', e => {
    const a = e.target.closest('a[href]');
    if (!a || e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    if (a.target && a.target !== '_self') return;
    const url = new URL(a.href, location.href);
    if (url.origin !== location.origin || url.hash && url.pathname === location.pathname) return;
    e.preventDefault();
    leaveTo(url.href);
  });
  function leaveTo(href) {
    try { sessionStorage.setItem(PREV_KEY, page); } catch (e) {}
    body.classList.add('page-leave');
    setTimeout(() => { location.href = href; }, 250);
  }
  // Pages that navigate in script (e.g. table row clicks) still record the hue hand-off
  addEventListener('pagehide', () => { try { sessionStorage.setItem(PREV_KEY, page); } catch (e) {} });
  // Coming back via the bfcache: undo the leave state
  addEventListener('pageshow', e => { if (e.persisted) body.classList.remove('page-leave'); });

  // ── Reveals ──
  const io = new IntersectionObserver(entries => {
    entries.forEach(en => {
      if (!en.isIntersecting) return;
      const el = en.target;
      el.classList.add('in');
      io.unobserve(el);
      // Once the entrance is done, drop the reveal classes so hover transitions take over
      const settle = e => {
        if (e && e.target !== el) return;
        el.removeEventListener('transitionend', settle);
        el.classList.remove('reveal', 'in');
      };
      el.addEventListener('transitionend', settle);
      setTimeout(settle, 1600);
    });
  }, { rootMargin: '0px 0px -40px 0px', threshold: 0 });  // any overlap: some cards are taller than the viewport

  const content = document.querySelector('.content');
  function prepCards(root) {
    const els = root.querySelectorAll ? root.querySelectorAll('.card, .metric-card') : [];
    [...(root.matches && root.matches('.card, .metric-card') ? [root] : []), ...els].forEach(el => {
      if (el.dataset.revealed) return;
      el.dataset.revealed = '1';
      // stagger siblings within the same grid/row
      const sibs = el.parentElement ? [...el.parentElement.children].filter(c => c.matches('.card, .metric-card')) : [el];
      el.style.setProperty('--i', Math.min(sibs.indexOf(el), 8));
      el.classList.add('reveal');
      io.observe(el);
    });
  }
  function prepRows(tbody) {
    [...tbody.children].slice(0, 24).forEach((tr, i) => {
      tr.classList.remove('row-in'); void tr.offsetWidth;
      tr.style.setProperty('--i', i); tr.classList.add('row-in');
    });
  }
  prepCards(content);

  // ── Numbers count up to their new value (e.g. "1143", "$74.16M", "54.8%") ──
  const written = new WeakMap();  // last text we wrote, so our own frames don't retrigger
  const lastValue = new WeakMap();
  function countUp(el) {
    if (el.children.length) return;  // leave values with nested markup alone
    const text = el.textContent.trim();
    if (written.get(el) === text) return;
    const m = text.match(/^([^\d-]*)(-?[\d,]*\.?\d+)(.*)$/);
    if (!m) return;
    const [, pre, numStr, post] = m;
    const target = parseFloat(numStr.replace(/,/g, ''));
    const decimals = (numStr.split('.')[1] || '').length;
    const commas = numStr.includes(',');
    const from = lastValue.has(el) ? lastValue.get(el) : 0;
    lastValue.set(el, target);
    if (from === target) return;
    const fmt = v => {
      let s = v.toFixed(decimals);
      if (commas) s = Number(s).toLocaleString('en-US', { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
      return pre + s + post;
    };
    const start = performance.now(), dur = 1100;
    (function step(now) {
      const p = Math.min((now - start) / dur, 1);
      const eased = 1 - Math.pow(1 - p, 4);
      const out = p < 1 ? fmt(from + (target - from) * eased) : text;
      written.set(el, out);
      el.textContent = out;
      if (p < 1) requestAnimationFrame(step);
    })(start);
  }

  // ── Tabs: one ink line that glides to the active tab ──
  function placeInk(tabs) {
    const active = tabs.querySelector('.tab.active');
    let ink = tabs.querySelector('.tab-ink');
    if (!ink) {
      ink = document.createElement('span');
      ink.className = 'tab-ink';
      tabs.appendChild(ink);
      tabs.classList.add('has-ink');
    }
    if (!active) { ink.style.width = '0'; return; }
    ink.style.width = active.offsetWidth + 'px';
    ink.style.transform = `translateX(${active.offsetLeft}px)`;
  }
  const tabLists = [...document.querySelectorAll('.tabs')];
  tabLists.forEach(t => {
    placeInk(t);
    new MutationObserver(() => placeInk(t)).observe(t, { attributes: true, subtree: true, attributeFilter: ['class'] });
  });
  addEventListener('resize', () => tabLists.forEach(placeInk));
  document.fonts && document.fonts.ready.then(() => tabLists.forEach(placeInk));

  new MutationObserver(muts => {
    const bodies = new Set();
    const counters = new Set();
    muts.forEach(m => {
      if (m.target.tagName === 'TBODY') bodies.add(m.target);
      m.addedNodes.forEach(n => {
        if (n.nodeType !== 1) return;
        prepCards(n);
        if (n.tagName === 'TBODY') bodies.add(n);
      });
      const mv = m.target.nodeType === 1 ? m.target.closest('.metric-value') : m.target.parentElement?.closest('.metric-value');
      if (mv) counters.add(mv);
    });
    bodies.forEach(prepRows);
    counters.forEach(countUp);
  }).observe(content, { childList: true, subtree: true, characterData: true });
  document.querySelectorAll('.metric-value').forEach(countUp);
})();
