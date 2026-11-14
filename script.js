(() => {
  const STORAGE = {
    theme: 'ga-theme',
    size: 'ga-size',
  };

  // ---- Theme (dark/light) ----
  const themeBtn = document.getElementById('toggle-theme');
  const root = document.documentElement;

  function applyTheme(theme) {
    if (theme === 'dark') {
      root.setAttribute('data-theme', 'dark');
      themeBtn.setAttribute('aria-pressed', 'true');
      themeBtn.textContent = '☀ Light';
    } else {
      root.removeAttribute('data-theme');
      themeBtn.setAttribute('aria-pressed', 'false');
      themeBtn.textContent = '☾ Dark';
    }
  }

  const savedTheme = localStorage.getItem(STORAGE.theme);
  const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
  applyTheme(savedTheme ?? (prefersDark ? 'dark' : 'light'));

  themeBtn.addEventListener('click', () => {
    const next = root.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
    applyTheme(next);
    localStorage.setItem(STORAGE.theme, next);
  });

  // ---- Font size ----
  const SIZES = [16, 18, 20, 22, 24];
  let sizeIdx = parseInt(localStorage.getItem(STORAGE.size) ?? '1', 10);
  if (isNaN(sizeIdx) || sizeIdx < 0 || sizeIdx >= SIZES.length) sizeIdx = 1;

  function applySize() {
    document.body.style.setProperty('--base-size', SIZES[sizeIdx] + 'px');
    localStorage.setItem(STORAGE.size, String(sizeIdx));
  }
  applySize();

  document.getElementById('size-down').addEventListener('click', () => {
    sizeIdx = Math.max(0, sizeIdx - 1);
    applySize();
  });
  document.getElementById('size-up').addEventListener('click', () => {
    sizeIdx = Math.min(SIZES.length - 1, sizeIdx + 1);
    applySize();
  });

  // ---- Scroll progress + back-to-top ----
  const progress = document.getElementById('progress');
  const toTop = document.getElementById('to-top');

  function onScroll() {
    const h = document.documentElement;
    const scrolled = h.scrollTop;
    const max = h.scrollHeight - h.clientHeight;
    const pct = max > 0 ? (scrolled / max) * 100 : 0;
    progress.style.width = pct + '%';
    toTop.classList.toggle('visible', scrolled > 400);
  }
  document.addEventListener('scroll', onScroll, { passive: true });
  onScroll();

  toTop.addEventListener('click', () => {
    window.scrollTo({ top: 0, behavior: 'smooth' });
  });

  // ---- Clean up Pandoc's inline image dimensions (overridden by CSS but tidier) ----
  document.querySelectorAll('.content img').forEach(img => {
    img.removeAttribute('width');
    img.removeAttribute('height');
    img.style.cssText = '';
    img.loading = 'lazy';
    img.alt = img.alt || 'Shri Ganapati';
  });

  // ---- Tag Devanagari-heavy paragraphs with lang attribute for assistive tech ----
  const devRe = /[ऀ-ॿ]/;
  document.querySelectorAll('.content p, .content li').forEach(el => {
    if (devRe.test(el.textContent)) el.setAttribute('lang', 'sa');
  });

  // ---- Collection introductions: folded to a few lines, "Read more" opens them ----
  document.querySelectorAll('.preamble').forEach((pre, i) => {
    if (pre.scrollHeight < 380) return;               // short enough to show in full
    pre.classList.add('is-folded');
    pre.id = pre.id || 'intro-' + i;
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'preamble-toggle';
    btn.setAttribute('aria-controls', pre.id);
    const set = open => {
      pre.classList.toggle('is-folded', !open);
      btn.setAttribute('aria-expanded', String(open));
      btn.textContent = open ? 'Show less ▴' : 'Read more ▾';
    };
    btn.addEventListener('click', () => {
      const open = pre.classList.contains('is-folded');
      set(open);
      if (!open) pre.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    });
    set(false);
    pre.after(btn);
  });

  // ---- Previous / Next without scrolling to the bottom ----
  // Built from the bottom buttons (build.py chapter_nav), so they always agree:
  // side arrows on wide screens, a small link row under the heading on narrow ones,
  // and the ← / → keys.
  const bottomNav = document.querySelector('.chapter-nav');
  if (bottomNav) {
    const prevA = bottomNav.querySelector('a.cn-prev');
    const nextA = bottomNav.querySelector('a.cn-next');
    const allA = bottomNav.querySelector('a.cn-all');
    const describe = a => {
      const t = a.querySelector('.cn-title')?.textContent || '';
      const s = a.querySelector('.cn-sub')?.textContent || '';
      return s ? `${t} — ${s}` : t;
    };

    // Side arrows (shown by CSS only where the margins are wide enough).
    for (const [a, side, arrow, word] of [[prevA, 'left', '‹', 'Previous'], [nextA, 'right', '›', 'Next']]) {
      if (!a) continue;
      const el = document.createElement('a');
      el.className = `side-nav side-nav-${side}`;
      el.href = a.href;
      el.setAttribute('aria-label', `${word}: ${describe(a)}`);
      el.innerHTML = `<span class="side-nav-arrow" aria-hidden="true">${arrow}</span>`;
      const tip = document.createElement('span');
      tip.className = 'side-nav-tip';
      tip.innerHTML = `<b></b><span></span>`;
      tip.querySelector('b').textContent = `${word}: ${a.querySelector('.cn-title')?.textContent || ''}`;
      tip.querySelector('span').textContent = a.querySelector('.cn-sub')?.textContent || '';
      el.appendChild(tip);
      document.body.appendChild(el);
    }

    // Small row under the heading (narrow screens).
    const hero = document.querySelector('.hero');
    if (hero) {
      const row = document.createElement('nav');
      row.className = 'chapter-nav-top';
      row.setAttribute('aria-label', 'Previous and next');
      const piece = (a, text) => {
        if (!a) return '<span class="cnt-empty"></span>';
        return `<a href="${a.getAttribute('href')}">${text}</a>`;
      };
      row.innerHTML = piece(prevA, '‹ Previous')
        + (allA ? `<a class="cnt-all" href="${allA.getAttribute('href')}">${allA.textContent}</a>` : '')
        + piece(nextA, 'Next ›');
      hero.after(row);
    }

    // Keyboard: ← / → (not while typing, not with modifier keys).
    document.addEventListener('keydown', e => {
      if (e.altKey || e.ctrlKey || e.metaKey || e.shiftKey) return;
      const t = e.target;
      if (t && (t.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName))) return;
      const a = e.key === 'ArrowLeft' ? prevA : e.key === 'ArrowRight' ? nextA : null;
      if (a) location.href = a.href;
    });
  }

  // ---- Shloka links: #shloka-5.13.41 opens the page at that shloka (briefly highlighted) ----
  const findVerse = num => {
    const main = document.getElementById('content');
    if (!main || !num) return null;
    const re = new RegExp('॥\\s*' + num.replace(/\./g, '\\.') + '\\s*॥');
    const ps = [...main.querySelectorAll('p')].filter(p => re.test(p.textContent));
    return ps.find(p => /text-align:\s*center/.test(p.getAttribute('style') || '')) || ps[0] || null;
  };
  const goToHash = () => {
    const h = decodeURIComponent(location.hash.slice(1));
    if (!h.startsWith('shloka-')) return;
    const el = findVerse(h.slice(7));
    if (!el) return;
    const go = () => {
      el.classList.remove('flash'); void el.offsetWidth;
      el.classList.add('flash');
      el.scrollIntoView({ block: 'start', behavior: 'instant' });
      setTimeout(() => el.classList.remove('flash'), 2600);
    };
    if (document.readyState === 'complete') go(); else addEventListener('load', go, { once: true });
  };
  goToHash();
  addEventListener('hashchange', goToHash);

  // ---- Header "Go to shloka": text -> chapter -> shloka ----
  const VERSES_VERSION = 'c584ec4ebd';
  (() => {
    const controls = document.querySelector('.controls');
    const header = document.querySelector('.site-header');
    const textsLink = controls && controls.querySelector('.home-link');
    if (!controls || !header || !textsLink) return;
    const siteBase = textsLink.getAttribute('href');               // "../../../" -> site root
    const here = (() => {
      const root = new URL(siteBase, location.href).pathname;
      return decodeURIComponent(location.pathname.startsWith(root) ? location.pathname.slice(root.length) : '').replace(/index\.html$/, '');
    })();
    const link = document.createElement('a');
    link.className = 'home-link jump-link';
    link.href = '#';
    link.textContent = 'Go to shloka';
    link.setAttribute('aria-expanded', 'false');
    textsLink.after(link);
    const panel = document.createElement('div');
    panel.className = 'jump-panel';
    panel.hidden = true;
    panel.innerHTML = `<form class="jump-inner">
        <label><span>Text</span><select class="j-text"></select></label>
        <label><span>Part</span><select class="j-part"></select></label>
        <label><span>Chapter</span><select class="j-ch"></select></label>
        <label><span>Shloka</span><select class="j-v"></select></label>
        <button type="submit" class="j-go">Go</button>
        <button type="button" class="j-close" aria-label="Close">×</button></form>`;
    header.appendChild(panel);
    const [tSel, pSel, cSel, vSel] = ['.j-text', '.j-part', '.j-ch', '.j-v'].map(q => panel.querySelector(q));
    const esc = x => String(x).replace(/[&<>"]/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[ch]));
    let data = null;
    const unit = l => (l.match(/^(?:.*\s)?(Sarga|Dashaka|Chapter)\s/) || [])[1] || 'Chapter';
    // The Story of Hanuman / Shrimad Bhagavatam: a Part level (Kishkindhakanda…, Book 1…).
    const partsOf = t => [...new Set(t.c.map(c => c.g).filter(Boolean))];
    const fillPart = () => {
      const parts = partsOf(data[+tSel.value]);
      pSel.innerHTML = parts.map(g => `<option value="${esc(g)}">${esc(g)}</option>`).join('');
      pSel.closest('label').hidden = !parts.length;
      pSel.closest('label').querySelector('span').textContent = parts.some(g => /^Book/.test(g)) ? 'Book' : 'Kanda';
    };
    const fillCh = () => {
      const t = data[+tSel.value];
      const g = pSel.closest('label').hidden ? null : pSel.value;
      const list = t.c.map((c, i) => [c, i]).filter(([c]) => !g || c.g === g);
      cSel.innerHTML = list.map(([c, i]) => `<option value="${i}">${esc(c.l)}</option>`).join('');
      cSel.closest('label').hidden = t.c.length === 1 && t.c[0].p === t.k + '/';   // a single-page text
      cSel.closest('label').querySelector('span').textContent = unit(list[0][0].l);
    };
    const fillV = () => {
      const c = data[+tSel.value].c[+cSel.value];
      vSel.innerHTML = '<option value="">Beginning</option>'
        + c.v.map(v => `<option value="${esc(c.pre + v)}">${esc(c.pre + v)}</option>`).join('');
    };
    const go = () => {
      const c = data[+tSel.value].c[+cSel.value];
      const v = vSel.value;
      const target = new URL(siteBase + c.p + (v ? '#shloka-' + encodeURIComponent(v) : ''), location.href);
      panel.hidden = true; link.setAttribute('aria-expanded', 'false');
      if (target.pathname === location.pathname) {
        if (!v) { scrollTo({ top: 0, behavior: 'smooth' }); return; }
        if (location.hash === target.hash) goToHash(); else location.hash = target.hash;
      } else location.href = target.href;
    };
    tSel.addEventListener('change', () => { fillPart(); fillCh(); fillV(); });
    pSel.addEventListener('change', () => { fillCh(); fillV(); });
    cSel.addEventListener('change', fillV);
    vSel.addEventListener('change', () => { if (vSel.value) go(); });
    panel.querySelector('form').addEventListener('submit', e => { e.preventDefault(); go(); });
    panel.querySelector('.j-close').addEventListener('click', () => { panel.hidden = true; link.setAttribute('aria-expanded', 'false'); link.focus(); });
    panel.addEventListener('keydown', e => { if (e.key === 'Escape') panel.querySelector('.j-close').click(); });
    link.addEventListener('click', async e => {
      e.preventDefault();
      if (!panel.hidden) { panel.hidden = true; link.setAttribute('aria-expanded', 'false'); return; }
      panel.hidden = false; link.setAttribute('aria-expanded', 'true');
      if (!data) {
        tSel.innerHTML = '<option>Loading…</option>';
        try { data = await (await fetch(siteBase + 'verses.json?v=' + VERSES_VERSION)).json(); }
        catch { tSel.innerHTML = '<option>Couldn’t load the list — please try again</option>'; data = null; return; }
        tSel.innerHTML = data.map((t, i) => `<option value="${i}">${esc(t.t)}</option>`).join('');
        // Start on the text / chapter being read.
        let ti = data.findIndex(t => t.c.some(c => c.p === here));
        if (ti < 0) ti = data.findIndex(t => here.startsWith(t.k + '/'));
        tSel.value = String(Math.max(0, ti));
        fillPart();
        const t = data[+tSel.value];
        const ci = t.c.findIndex(c => c.p === here);
        const inPart = here && t.c.find(c => c.g && c.p.startsWith(here));        // a part's own page
        if (ci >= 0 && t.c[ci].g) pSel.value = t.c[ci].g; else if (inPart) pSel.value = inPart.g;
        fillCh();
        if (ci >= 0) cSel.value = String(ci);
        fillV();
      }
      (here && data[+tSel.value].c.some(c => c.p === here) ? vSel : tSel).focus();
    });
  })();

  // ---- Reader accounts (optional sign-in) ----
  // Every page stays open to everyone. This adds a "Sign in" link, and on chapter pages a
  // bar for bookmarks / progress / notes. The Firebase code (account.js) is only loaded on
  // the account page or for readers who have signed in on this device before.
  const AUTH_FLAG = 'ss-signed-in';
  // Bump when account.js changes so browsers fetch the new copy instead of a cached one.
  const ACCOUNT_JS_VERSION = '7334a0f0f2';
  const scriptEl = document.currentScript || document.querySelector('script[src$="script.js"]');
  const base = scriptEl.src.replace(/script\.js(\?.*)?$/, '');
  const pathOf = url => {
    const u = new URL(url, location.href);
    const clean = u.origin + u.pathname;
    const rel = clean.startsWith(base) ? clean.slice(base.length) : u.pathname.replace(/^\/+/, '');
    return rel.replace(/index\.html$/, '');
  };
  const path = pathOf(location.href);
  const isAccountPage = !!document.getElementById('account-app');
  const isTrackerPage = !!document.getElementById('tracker-app');
  const flagged = () => { try { return localStorage.getItem(AUTH_FLAG) === '1'; } catch { return false; } };

  const controls = document.querySelector('.controls');
  const acctLink = document.createElement('a');
  acctLink.className = 'home-link account-link';
  acctLink.href = base + 'account/' + (isAccountPage || !path ? '' : '?next=' + encodeURIComponent(path));
  acctLink.textContent = flagged() ? 'Account' : 'Sign in';
  if (controls) controls.insertBefore(acctLink, controls.querySelector('button'));

  // Header "Signed in as <name>" + "Sign out", shown on every page while signed in.
  const NAME_KEY = 'ss-name';
  const savedName = () => { try { return localStorage.getItem(NAME_KEY) || ''; } catch { return ''; } };
  const whoEl = document.createElement('span');
  whoEl.className = 'signed-in-as';
  const showWho = name => {
    whoEl.textContent = '';
    whoEl.append('Signed in' + (name ? ' as ' : ''));
    if (name) { const b = document.createElement('strong'); b.textContent = name; whoEl.append(b); }
    whoEl.title = name ? 'Signed in as ' + name : 'Signed in';
  };
  showWho(savedName());
  whoEl.hidden = !flagged();
  const outBtn = document.createElement('button');
  outBtn.type = 'button';
  outBtn.className = 'signout-btn';
  outBtn.textContent = 'Sign out';
  outBtn.title = 'Sign out';
  outBtn.hidden = !flagged();
  outBtn.addEventListener('click', async () => {
    outBtn.disabled = true;
    try {
      if (!window.ssUI.signOut) await import(base + 'account.js?v=' + ACCOUNT_JS_VERSION);
      await window.ssUI.signOut();
    } catch {}
    try { localStorage.removeItem(AUTH_FLAG); localStorage.removeItem(NAME_KEY); localStorage.removeItem('ss-owner'); } catch {}
    location.reload();
  });
  if (controls) acctLink.after(outBtn);

  // Highlight the header button for the part of the site you're on: Account on the account
  // page, Texts on the home page and every collection / chapter page.
  const textsLink = controls && controls.querySelector('.home-link:not(.account-link)');
  const here = (path.split('/')[0] || '');
  // Site owner only (marked when the owner's account loads): a Tracker button.
  let trackerLink = null;
  const addTrackerLink = () => {
    if (trackerLink || !controls) return trackerLink;
    trackerLink = document.createElement('a');
    trackerLink.className = 'home-link tracker-link';
    trackerLink.href = base + 'tracker/';
    trackerLink.textContent = 'Tracker';
    acctLink.before(trackerLink);
    return trackerLink;
  };
  try { if (flagged() && localStorage.getItem('ss-owner') === '1') addTrackerLink(); } catch {}
  const current = isTrackerPage ? trackerLink : isAccountPage ? acctLink : (['privacy', 'disclaimer'].includes(here) ? null : textsLink);
  if (current) { current.classList.add('is-current'); current.setAttribute('aria-current', 'page'); }   // (no "Signed in as …" in the header, at the owner's request)

  // A readable page (chapter, sarga, dashaka, single text) — not an index or the account page.
  const main = document.querySelector('main.content');
  const readable = main && !isAccountPage && !main.classList.contains('static-page');
  let studyBar = null;
  if (readable) {
    studyBar = document.createElement('div');
    studyBar.className = 'study-bar';
    main.before(studyBar);
  }

  const pageInfo = () => {
    const crumb = (document.querySelector('.hero .crumb')?.textContent || '').replace(/^\s*↩\s*/, '').trim();
    const h1 = (document.querySelector('.hero h1')?.textContent || document.title).trim();
    const sub = (document.querySelector('.hero .subtitle')?.textContent || '').trim();
    return { title: crumb ? crumb + ' · ' + h1 : h1, sub };
  };

  const foot = document.querySelector('.site-footer div');
  if (foot) {
    foot.insertAdjacentHTML('beforeend', ' · <a href="' + base + 'privacy/">Privacy</a>'
      + ' · <a href="' + base + 'disclaimer/">Disclaimer and Credits</a>');
  }

  const renderSignedOut = () => {
    if (!studyBar) return;
    studyBar.innerHTML = '<a class="sb-signin" href="' + acctLink.href + '">☆ Sign in to bookmark this page, mark it as studied and keep your own notes</a>';
  };

  window.ssUI = {
    base, path, pathOf, isAccountPage, isTrackerPage, studyBar, pageInfo, renderSignedOut,
    // Called once the signed-in account is confirmed as the site owner.
    markOwner() { try { localStorage.setItem('ss-owner', '1'); } catch {} addTrackerLink(); },
    setSignedIn(user) {
      try { user ? localStorage.setItem(AUTH_FLAG, '1') : (localStorage.removeItem(AUTH_FLAG), localStorage.removeItem('ss-owner')); } catch {}
      acctLink.textContent = user ? 'Account' : 'Sign in';
      if (user) acctLink.href = base + 'account/';
      outBtn.hidden = whoEl.hidden = !user;
      const name = user ? (user.displayName || user.email || '') : '';
      try { name ? localStorage.setItem(NAME_KEY, name) : localStorage.removeItem(NAME_KEY); } catch {}
      showWho(name);
    },
  };

  if (isAccountPage || isTrackerPage || flagged()) {
    if (studyBar) studyBar.innerHTML = '<span class="sb-loading">Loading your bookmarks…</span>';
    import(base + 'account.js?v=' + ACCOUNT_JS_VERSION).catch(() => { renderSignedOut(); });
  } else {
    renderSignedOut();
  }
})();
