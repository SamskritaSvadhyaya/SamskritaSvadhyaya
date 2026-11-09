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

  // ---- Reader accounts (optional sign-in) ----
  // Every page stays open to everyone. This adds a "Sign in" link, and on chapter pages a
  // bar for bookmarks / progress / notes. The Firebase code (account.js) is only loaded on
  // the account page or for readers who have signed in on this device before.
  const AUTH_FLAG = 'ss-signed-in';
  // Bump when account.js changes so browsers fetch the new copy instead of a cached one.
  const ACCOUNT_JS_VERSION = 'c65cf0ca86';
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
    try { localStorage.removeItem(AUTH_FLAG); localStorage.removeItem(NAME_KEY); } catch {}
    location.reload();
  });
  if (controls) { acctLink.after(whoEl); whoEl.after(outBtn); }

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
  if (foot) foot.insertAdjacentHTML('beforeend', ' · <a href="' + base + 'privacy/">Privacy</a>');

  const renderSignedOut = () => {
    if (!studyBar) return;
    studyBar.innerHTML = '<a class="sb-signin" href="' + acctLink.href + '">☆ Sign in to bookmark this page, mark it as studied and keep your own notes</a>';
  };

  window.ssUI = {
    base, path, pathOf, isAccountPage, studyBar, pageInfo, renderSignedOut,
    setSignedIn(user) {
      try { user ? localStorage.setItem(AUTH_FLAG, '1') : localStorage.removeItem(AUTH_FLAG); } catch {}
      acctLink.textContent = user ? 'Account' : 'Sign in';
      if (user) acctLink.href = base + 'account/';
      outBtn.hidden = whoEl.hidden = !user;
      const name = user ? (user.displayName || user.email || '') : '';
      try { name ? localStorage.setItem(NAME_KEY, name) : localStorage.removeItem(NAME_KEY); } catch {}
      showWho(name);
    },
  };

  if (isAccountPage || flagged()) {
    if (studyBar) studyBar.innerHTML = '<span class="sb-loading">Loading your bookmarks…</span>';
    import(base + 'account.js?v=' + ACCOUNT_JS_VERSION).catch(() => { renderSignedOut(); });
  } else {
    renderSignedOut();
  }
})();
