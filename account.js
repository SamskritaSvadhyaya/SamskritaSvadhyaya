// Reader accounts: sign-in (email/password or Google), bookmarks, "studied" progress,
// "continue where you left off", private notes, and the announcements opt-in.
// Loaded by script.js only on the account page or when the reader has signed in before,
// so visitors who never sign in don't download Firebase at all.
//
// Data (Firestore; security rules in the Firebase console let each reader touch only their own):
//   users/{uid}               { name, email, announcements, lastPage:{path,title,sub,scroll,at} }
//   users/{uid}/pages/{key}   { path, title, sub, bookmarked, studied, note, updated }
//   subscribers/{uid}         { email, name, at }   — exists only while opted in to announcements

import { initializeApp } from 'https://www.gstatic.com/firebasejs/11.10.0/firebase-app.js';
import {
  getAuth, onAuthStateChanged, signInWithEmailAndPassword, createUserWithEmailAndPassword,
  GoogleAuthProvider, signInWithPopup, signOut, sendPasswordResetEmail, sendEmailVerification,
  updateProfile, deleteUser,
} from 'https://www.gstatic.com/firebasejs/11.10.0/firebase-auth.js';
import {
  getFirestore, doc, getDoc, setDoc, deleteDoc, collection, getDocs, serverTimestamp, writeBatch,
} from 'https://www.gstatic.com/firebasejs/11.10.0/firebase-firestore-lite.js';

const app = initializeApp({
  apiKey: 'AIzaSyAT8e0SjNixG7o3S9jsmZpoH6WSF7OVhQA',
  authDomain: 'samskrita-svadhyaya.firebaseapp.com',
  projectId: 'samskrita-svadhyaya',
  storageBucket: 'samskrita-svadhyaya.firebasestorage.app',
  messagingSenderId: '664969392299',
  appId: '1:664969392299:web:0c0bcedd7c7fcb0a7a87ee',
});
const auth = getAuth(app);
const db = getFirestore(app);

const UI = window.ssUI;            // helpers from script.js
const BASE = UI.base;              // site root URL, ends with "/"
const PATH = UI.path;              // this page's path from the site root ("" = home)

const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const keyOf = path => path.replace(/\/+$/, '').replace(/\//g, '|') || 'home';
const pageRef = (uid, path) => doc(db, 'users', uid, 'pages', keyOf(path));
const userRef = uid => doc(db, 'users', uid);

const MESSAGES = {
  'auth/invalid-credential': 'That email and password don’t match. Please try again, or use “Forgot password?”.',
  'auth/wrong-password': 'That email and password don’t match.',
  'auth/user-not-found': 'No account with that email yet — create one below.',
  'auth/email-already-in-use': 'An account with this email already exists — sign in instead (or use “Forgot password?”).',
  'auth/weak-password': 'Please choose a password of at least 6 characters.',
  'auth/invalid-email': 'Please enter a valid email address.',
  'auth/missing-password': 'Please enter your password.',
  'auth/too-many-requests': 'Too many attempts. Please wait a few minutes and try again.',
  'auth/popup-blocked': 'Your browser blocked the Google sign-in window. Please allow pop-ups for this site and try again.',
  'auth/popup-closed-by-user': 'The Google sign-in window was closed before finishing.',
  'auth/cancelled-popup-request': 'The Google sign-in window was closed before finishing.',
  'auth/network-request-failed': 'Network problem — please check your connection and try again.',
  'auth/requires-recent-login': 'For your security, please sign out, sign in again, and then delete the account.',
  'auth/account-exists-with-different-credential': 'This email is already registered with a password — sign in with email and password.',
};
const friendly = e => MESSAGES[e?.code] || (e?.message || 'Something went wrong.').replace(/^Firebase:\s*/, '');

function nextUrl() {
  const n = new URLSearchParams(location.search).get('next');
  // Only same-site relative paths.
  return n && !/^[a-z]+:|^\/\//i.test(n) ? BASE + n.replace(/^\/+/, '') : null;
}

// ---------------------------------------------------------------- chapter pages
function readingPage(user) {
  const bar = UI.studyBar;
  if (!bar) return;
  const info = UI.pageInfo();
  const ref = pageRef(user.uid, PATH);
  let state = { bookmarked: false, studied: false, note: '' };

  bar.innerHTML = `
    <button type="button" class="sb-btn sb-bookmark" aria-pressed="false" disabled>☆ Bookmark</button>
    <button type="button" class="sb-btn sb-studied" aria-pressed="false" disabled>○ Mark as studied</button>
    <a class="sb-btn sb-notes-link" href="#my-notes">✎ My notes</a>`;
  const bBtn = bar.querySelector('.sb-bookmark');
  const sBtn = bar.querySelector('.sb-studied');

  const notes = document.createElement('section');
  notes.className = 'my-notes';
  notes.id = 'my-notes';
  notes.innerHTML = `
    <h2>My notes on this page</h2>
    <p class="my-notes-hint">Private — only you can see these. Saved automatically.</p>
    <textarea rows="6" maxlength="20000" placeholder="Your notes on this page…" disabled></textarea>
    <div class="my-notes-status" aria-live="polite"></div>`;
  (document.getElementById('content') || bar).after(notes);
  const ta = notes.querySelector('textarea');
  const status = notes.querySelector('.my-notes-status');

  function paint() {
    bBtn.setAttribute('aria-pressed', String(!!state.bookmarked));
    bBtn.textContent = state.bookmarked ? '★ Bookmarked' : '☆ Bookmark';
    sBtn.setAttribute('aria-pressed', String(!!state.studied));
    sBtn.textContent = state.studied ? '✓ Studied' : '○ Mark as studied';
  }

  async function save(fields) {
    Object.assign(state, fields);
    await setDoc(ref, { ...fields, path: PATH, title: info.title, sub: info.sub, updated: serverTimestamp() }, { merge: true });
  }

  const uref = userRef(user.uid);
  let shlokas = [];
  const loaded = getDoc(ref).then(snap => {
    if (snap.exists()) state = { ...state, ...snap.data() };
    ta.value = state.note || '';
    bBtn.disabled = sBtn.disabled = ta.disabled = false;
    paint();
    verseNotes(user, ref, info, state.verses || {});
    shlokas = findShlokas();
    placeMarks();
    if (location.hash === '#mark') {
      const go = () => goToMark();
      if (document.readyState === 'complete') go(); else addEventListener('load', go, { once: true });
    }
    return state;
  }).catch(err => { status.textContent = 'Couldn’t load your notes: ' + friendly(err); return state; });

  // ---- "I stopped here" ribbon beside each shloka (one per chapter) ----
  const RIBBON = '<svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><path d="M6 3h12v18l-6-4.5L6 21z"/></svg>';
  const markIndex = () => matchShloka(shlokas, state.mark);
  function paintMarks() {
    const mi = markIndex();
    shlokas.forEach((sh, i) => {
      const on = i === mi;
      sh.el.classList.toggle('is-mark', on);
      const b = sh.el.querySelector('.verse-mark');
      b.setAttribute('aria-pressed', String(on));
      b.title = on ? 'You stopped here — tap to remove' : 'I stopped here (bookmark this shloka)';
      b.setAttribute('aria-label', b.title);
    });
    let resume = bar.querySelector('.sb-resume');
    if (mi >= 0 && !resume) {
      bar.insertAdjacentHTML('beforeend', '<button type="button" class="sb-btn sb-resume">🔖 Go to where I stopped</button>');
      bar.querySelector('.sb-resume').addEventListener('click', () => goToMark('smooth'));
    } else if (mi < 0 && resume) resume.remove();
  }
  function goToMark(behavior = 'instant') {
    const mi = markIndex();
    if (mi < 0) return false;
    shlokas[mi].el.scrollIntoView({ block: 'start', behavior });
    return true;
  }
  async function setMark(i) {
    const m = i == null ? null : { n: i + 1, t: firstWords(shlokas[i].el) };
    state.mark = m;
    paintMarks();
    await setDoc(ref, { mark: m, markAt: serverTimestamp(), path: PATH, title: info.title, sub: info.sub, updated: serverTimestamp() }, { merge: true });
    // The marked shloka becomes the "continue where you left off" point.
    lastSaved = scrollFrac();
    await setDoc(uref, { lastPage: { path: PATH, title: info.title, sub: info.sub, scroll: lastSaved, mark: m, at: serverTimestamp() } }, { merge: true });
  }
  function placeMarks() {
    shlokas.forEach((sh, i) => {
      const b = document.createElement('button');
      b.type = 'button';
      b.className = 'verse-mark';
      b.innerHTML = RIBBON;
      b.addEventListener('click', () => {
        setMark(markIndex() === i ? null : i).catch(e => alert(friendly(e)));
      });
      sh.el.appendChild(b);
    });
    paintMarks();
  }

  bBtn.addEventListener('click', () => { save({ bookmarked: !state.bookmarked }).catch(e => alert(friendly(e))); paint(); });
  sBtn.addEventListener('click', () => { save({ studied: !state.studied }).catch(e => alert(friendly(e))); paint(); });

  let timer = null;
  const saveNote = () => {
    clearTimeout(timer);
    if (ta.value === (state.note || '')) return;
    status.textContent = 'Saving…';
    save({ note: ta.value })
      .then(() => { status.textContent = 'Saved'; })
      .catch(e => { status.textContent = 'Not saved — ' + friendly(e); });
  };
  ta.addEventListener('input', () => { status.textContent = ''; clearTimeout(timer); timer = setTimeout(saveNote, 1200); });
  ta.addEventListener('blur', saveNote);

  // "Continue where you left off": remember this page and how far down the reader is.
  let lastSaved = -1;
  const scrollFrac = () => {
    const h = document.documentElement;
    const max = h.scrollHeight - h.clientHeight;
    return max > 0 ? Math.round((h.scrollTop / max) * 1000) / 1000 : 0;
  };
  const savePos = () => {
    const f = scrollFrac();
    if (Math.abs(f - lastSaved) < 0.01) return;
    lastSaved = f;
    setDoc(uref, { lastPage: { path: PATH, title: info.title, sub: info.sub, scroll: f, mark: state.mark || null, at: serverTimestamp() } }, { merge: true }).catch(() => {});
  };
  Promise.all([loaded, getDoc(uref)]).then(([, snap]) => {
    const lp = snap.exists() && snap.data().lastPage;
    if (lp && lp.path === PATH) {
      // Same page as last time: keep the saved place until the reader scrolls.
      lastSaved = lp.scroll;
      if (location.hash === '#continue') {
        const go = () => {
          if (goToMark()) return;   // the shloka the reader marked, else how far down they were
          const h = document.documentElement;
          if (lp.scroll > 0) window.scrollTo({ top: lp.scroll * (h.scrollHeight - h.clientHeight), behavior: 'instant' });
        };
        if (document.readyState === 'complete') go(); else addEventListener('load', go, { once: true });
      }
    } else {
      savePos();
    }
  }).catch(() => {});
  // Only after the reader actually scrolls on this visit (so just opening the page again
  // doesn't overwrite the saved place).
  let posTimer = null, moved = false;
  addEventListener('scroll', () => { moved = true; clearTimeout(posTimer); posTimer = setTimeout(savePos, 4000); }, { passive: true });
  document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'hidden' && moved) savePos(); });
}

// ---------------------------------------------------------------- notes on each shloka
// A shloka is a centred Devanagari block directly followed by its (left-aligned) meaning.
// Notes are stored on the page's document as verses: { n: { t: first words, note } } and
// matched back by the shloka's first words (falling back to its position), so they stay
// on the right shloka when the chapter is re-imported.
const verseText = el => (el.innerText || el.textContent).replace(/\s+/g, ' ').trim();
const firstWords = el => verseText(el).slice(0, 40);

function matchShloka(shlokas, ref) {
  if (!ref) return -1;
  const i = shlokas.findIndex(s => firstWords(s.el) === ref.t);
  if (i >= 0) return i;
  return ref.n >= 1 && ref.n <= shlokas.length ? ref.n - 1 : -1;
}

function findShlokas() {
  const main = document.getElementById('content');
  if (!main) return [];
  const els = [...main.children];
  const centred = el => el.tagName === 'P' && /text-align:\s*center/.test(el.getAttribute('style') || '');
  const out = [];
  els.forEach((el, i) => {
    const next = els[i + 1];
    if (centred(el) && /[ऀ-ॿ]/.test(el.textContent) && next && next.tagName === 'P' && !centred(next)) {
      // The note goes at the end of this shloka's explanation (before the <hr> / next shloka).
      let end = next, j = i + 1;
      while (els[j + 1] && els[j + 1].tagName === 'P' && !centred(els[j + 1])) end = els[++j];
      out.push({ el, end });
    }
  });
  return out;
}

function verseNotes(user, ref, info, saved) {
  const shlokas = findShlokas();
  if (!shlokas.length) return;
  // Match saved notes to shlokas: by first words, else by position.
  const byWords = new Map(shlokas.map((s, i) => [firstWords(s.el), i]));
  const notes = new Array(shlokas.length).fill('');
  for (const [n, v] of Object.entries(saved)) {
    if (!v || !(v.note || '').trim()) continue;
    const i = byWords.has(v.t) ? byWords.get(v.t) : Number(n) - 1;
    if (i >= 0 && i < shlokas.length && !notes[i]) notes[i] = v.note;
  }
  shlokas.forEach((s, i) => {
    const n = String(i + 1);
    const box = document.createElement('div');
    box.className = 'verse-note';
    s.end.after(box);
    let current = notes[i];
    const open = () => {
      box.innerHTML = `<label class="verse-note-label">✎ My note on this shloka</label>
        <textarea rows="3" maxlength="5000" placeholder="Your note on this shloka…"></textarea>
        <div class="verse-note-status" aria-live="polite"></div>`;
      const ta = box.querySelector('textarea');
      const st = box.querySelector('.verse-note-status');
      ta.value = current;
      let timer = null;
      const saveIt = () => {
        clearTimeout(timer);
        if (ta.value === current) return;
        const val = ta.value;
        st.textContent = 'Saving…';
        setDoc(ref, { verses: { [n]: { t: firstWords(s.el), note: val } }, path: PATH, title: info.title, sub: info.sub, updated: serverTimestamp() }, { merge: true })
          .then(() => { current = val; st.textContent = 'Saved'; })
          .catch(e => { st.textContent = 'Not saved — ' + friendly(e); });
      };
      ta.addEventListener('input', () => { st.textContent = ''; clearTimeout(timer); timer = setTimeout(saveIt, 1200); });
      ta.addEventListener('blur', () => { saveIt(); if (!ta.value.trim() && !current.trim()) setTimeout(closed, 300); });
      return ta;
    };
    const closed = () => {
      box.innerHTML = '<button type="button" class="verse-note-add">✎ Note on this shloka</button>';
      box.querySelector('button').addEventListener('click', () => open().focus());
    };
    if (current.trim()) open(); else closed();
  });
}

const hasVerseNotes = d => Object.values(d.verses || {}).some(v => (v?.note || '').trim());

// ---------------------------------------------------------------- index pages: ✓ / ★ on chapter cards
async function markIndex(user) {
  const cards = [...document.querySelectorAll('a.chapter-card')];
  if (!cards.length) return;
  const snap = await getDocs(collection(db, 'users', user.uid, 'pages'));
  const byPath = new Map(snap.docs.map(d => [d.data().path, d.data()]));
  let studied = 0;
  for (const a of cards) {
    const p = UI.pathOf(a.href);
    const d = byPath.get(p);
    if (!d) continue;
    if (d.studied) studied++;
    const marks = [d.studied && '<span title="Studied">✓</span>', d.bookmarked && '<span title="Bookmarked">★</span>', (d.note || hasVerseNotes(d)) && '<span title="You have notes here">✎</span>'].filter(Boolean);
    if (marks.length) a.insertAdjacentHTML('beforeend', `<span class="card-marks">${marks.join('')}</span>`);
  }
  const grid = document.querySelector('.chapter-grid');
  if (grid) grid.insertAdjacentHTML('beforebegin',
    `<p class="index-progress">Your progress: <strong>${studied}</strong> of ${cards.length} studied</p>`);
}

const markLine = lp => lp.mark && lp.mark.t
  ? `<span class="continue-mark">🔖 from the shloka <span lang="sa">“${esc(lp.mark.t.split(/[।॥|]/)[0].trim())}…”</span></span>` : '';

const COLLECTIONS = {
  'thestoryofhanuman': 'The Story of Hanuman',
  'narayaneeyam': 'Narayaneeyam',
  'shrimad-bhagavatam-canto-10': 'Shrimad Bhagavatam',
  'raghuvamsha': 'Raghuvamsha',
  'ganapati-atharvashirsha': 'Ganapati Atharvashirsha',
  'eclectic-collection': 'Eclectic Collection',
};
const collectionOf = path => path.split('/')[0];

// The latest marked shloka in each text, most recent first.
function stoppedPlaces(pages) {
  const best = new Map();
  const when = p => (p.markAt || p.updated)?.seconds || 0;
  for (const p of pages) {
    if (!p.mark || !p.mark.t) continue;
    const c = collectionOf(p.path);
    if (!best.has(c) || when(p) > when(best.get(c))) best.set(c, p);
  }
  return [...best.values()].sort((a, b) => when(b) - when(a));
}

function stoppedItem(p) {
  const col = COLLECTIONS[collectionOf(p.path)] || '';
  const title = p.title || p.path;
  const label = col && !title.startsWith(col) ? `${col} — ${title}` : title;
  const first = p.mark.t.split(/[।॥|]/)[0].trim();
  return `<li><a href="${esc(BASE + p.path)}#mark">${esc(label)}</a>${p.sub ? ` <span class="acct-sub">${esc(p.sub)}</span>` : ''}
    <div class="stopped-shloka">🔖 <span lang="sa">“${esc(first)}…”</span></div></li>`;
}

// ---------------------------------------------------------------- home page: continue reading
async function homeContinue(user) {
  const grid = document.querySelector('.home-grid');
  if (!grid || PATH !== '') return;
  const [snap, pagesSnap] = await Promise.all([
    getDoc(userRef(user.uid)),
    getDocs(collection(db, 'users', user.uid, 'pages')),
  ]);
  const lp = snap.exists() && snap.data().lastPage;
  const others = stoppedPlaces(pagesSnap.docs.map(d => d.data()))
    .filter(p => !lp || collectionOf(p.path) !== collectionOf(lp.path));
  const first = esc((user.displayName || '').split(' ')[0]);
  const box = document.createElement('div');
  box.className = 'continue-box';
  box.innerHTML = (lp ? `
    <span class="continue-label">${first ? `Namaste ${first} — c` : 'C'}ontinue where you left off</span>
    <a class="continue-link" href="${esc(BASE + lp.path)}#continue">${esc(lp.title)}${lp.sub ? ` <span class="continue-sub">${esc(lp.sub)}</span>` : ''} →</a>${markLine(lp)}`
    : `<span class="continue-label">${first ? `Namaste ${first}! ` : ''}Pick a text below to begin.</span>`)
    + (others.length ? `<div class="stopped-box"><span class="continue-label">Where I stopped in my other texts</span>
        <ul class="stopped-list">${others.map(stoppedItem).join('')}</ul></div>` : '')
    + `<a class="continue-account" href="${BASE}account/">My bookmarks, progress &amp; notes</a>`;
  grid.before(box);
}

// ---------------------------------------------------------------- home page: sign-out line at the bottom
function homeSignOut(user) {
  const main = document.querySelector('main.home');
  if (!main || PATH !== '' || document.querySelector('.home-signout')) return;
  const who = user.displayName || user.email || '';
  const div = document.createElement('div');
  div.className = 'home-signout';
  div.innerHTML = `<span>Signed in${who ? ' as <strong>' + esc(who) + '</strong>' : ''}</span>
    <button type="button" class="acct-secondary">Sign out</button>`;
  div.querySelector('button').addEventListener('click', async () => {
    await signOut(auth);
    location.reload();
  });
  main.after(div);
}

// ---------------------------------------------------------------- account page
function accountPage() {
  const root = document.getElementById('account-app');
  let mode = new URLSearchParams(location.search).get('mode') === 'signup' ? 'signup' : 'signin';

  function renderSignedOut(msg = '', kind = 'error') {
    root.innerHTML = `
      <div class="acct-card">
        <div class="acct-tabs" role="tablist">
          <button type="button" role="tab" data-mode="signin" aria-selected="${mode === 'signin'}">Sign in</button>
          <button type="button" role="tab" data-mode="signup" aria-selected="${mode === 'signup'}">Create account</button>
        </div>
        <button type="button" class="acct-google"><svg viewBox="0 0 48 48" width="20" height="20" aria-hidden="true"><path fill="#EA4335" d="M24 9.5c3.5 0 6.6 1.2 9.1 3.6l6.8-6.8C35.8 2.4 30.3 0 24 0 14.6 0 6.6 5.4 2.7 13.3l7.9 6.1C12.5 13.6 17.8 9.5 24 9.5z"/><path fill="#4285F4" d="M46.1 24.5c0-1.6-.1-3.1-.4-4.5H24v9h12.4c-.5 2.9-2.2 5.3-4.6 6.9l7.4 5.7c4.3-4 6.9-9.9 6.9-17.1z"/><path fill="#FBBC05" d="M10.6 28.6c-.5-1.4-.8-3-.8-4.6s.3-3.2.8-4.6l-7.9-6.1C1 16.6 0 20.2 0 24s1 7.4 2.7 10.7l7.9-6.1z"/><path fill="#34A853" d="M24 48c6.5 0 11.9-2.1 15.9-5.8l-7.4-5.7c-2.1 1.4-4.8 2.2-8.5 2.2-6.2 0-11.5-4.1-13.4-9.9l-7.9 6.1C6.6 42.6 14.6 48 24 48z"/></svg>Continue with Google</button>
        <div class="acct-or"><span>or with email</span></div>
        <form class="acct-form" novalidate>
          ${mode === 'signup' ? `<label>Your name <span class="opt">(optional)</span><input name="name" autocomplete="name" maxlength="80"></label>` : ''}
          <label>Email<input name="email" type="email" autocomplete="email" required></label>
          <label>Password${mode === 'signup' ? ' <span class="opt">(at least 6 characters)</span>' : ''}<input name="password" type="password" autocomplete="${mode === 'signup' ? 'new-password' : 'current-password'}" required minlength="6"></label>
          ${mode === 'signup' ? `<label class="acct-check"><input type="checkbox" name="announce" checked> Email me when new chapters are released</label>` : ''}
          <button type="submit" class="acct-primary">${mode === 'signup' ? 'Create account' : 'Sign in'}</button>
          ${mode === 'signin' ? '<button type="button" class="acct-link acct-forgot">Forgot password?</button>' : ''}
          <p class="acct-msg ${kind}" aria-live="polite">${esc(msg)}</p>
        </form>
        <p class="acct-fine">Signing in is optional — every page stays free to read without an account.
          See our <a href="${BASE}privacy/">privacy policy</a>.</p>
      </div>`;
    const form = root.querySelector('form');
    const msgEl = root.querySelector('.acct-msg');
    const say = (t, k = 'error') => { msgEl.textContent = t; msgEl.className = 'acct-msg ' + k; };
    root.querySelectorAll('[data-mode]').forEach(b => b.addEventListener('click', () => { mode = b.dataset.mode; renderSignedOut(); }));
    root.querySelector('.acct-google').addEventListener('click', async () => {
      say('');
      try { await signInWithPopup(auth, new GoogleAuthProvider()); } catch (e) { say(friendly(e)); }
    });
    root.querySelector('.acct-forgot')?.addEventListener('click', async () => {
      const email = form.email.value.trim();
      if (!email) return say('Type your email above, then click “Forgot password?” again.');
      try { await sendPasswordResetEmail(auth, email); say('If an account exists for ' + email + ', a password-reset email is on its way. Check your inbox (and spam folder).', 'ok'); }
      catch (e) { say(friendly(e)); }
    });
    form.addEventListener('submit', async ev => {
      ev.preventDefault();
      const email = form.email.value.trim(), pw = form.password.value;
      const btn = form.querySelector('.acct-primary');
      btn.disabled = true; say('');
      try {
        if (mode === 'signup') {
          pendingAnnounce = form.announce.checked;
          signingUp = true;
          const cred = await createUserWithEmailAndPassword(auth, email, pw);
          const name = form.name.value.trim();
          if (name) await updateProfile(cred.user, { displayName: name });
          sendEmailVerification(cred.user).catch(() => {});
          await ensureUser(cred.user);
          signingUp = false;
          renderSignedIn(cred.user);
        } else {
          await signInWithEmailAndPassword(auth, email, pw);
        }
      } catch (e) { signingUp = false; say(friendly(e)); btn.disabled = false; }
    });
  }

  async function renderSignedIn(user) {
    const go = nextUrl();
    if (go && !root.dataset.redirected) { root.dataset.redirected = '1'; location.replace(go); return; }
    root.innerHTML = '<p class="acct-loading">Loading your library…</p>';
    let profile = {}, pages = [];
    try {
      profile = (await ensureUser(user)) || {};
      pages = (await getDocs(collection(db, 'users', user.uid, 'pages'))).docs.map(d => d.data());
    } catch (e) {
      root.innerHTML = `<p class="acct-msg error">Couldn’t load your account: ${esc(friendly(e))}</p>`;
      return;
    }
    const byTime = (a, b) => (b.updated?.seconds || 0) - (a.updated?.seconds || 0);
    const link = p => `<a href="${esc(BASE + p.path)}">${esc(p.title || p.path)}</a>${p.sub ? ` <span class="acct-sub">${esc(p.sub)}</span>` : ''}`;
    const bookmarks = pages.filter(p => p.bookmarked).sort(byTime);
    const stopped = stoppedPlaces(pages);
    const studied = pages.filter(p => p.studied);
    const notes = pages.filter(p => (p.note || '').trim() || hasVerseNotes(p)).sort(byTime);
    const verseList = p => Object.entries(p.verses || {}).filter(([, v]) => (v?.note || '').trim())
      .sort((a, b) => a[0] - b[0])
      .map(([, v]) => `<div class="acct-snippet"><span class="acct-verse" lang="sa">${esc(v.t)}…</span> — ${esc(v.note.slice(0, 160))}${v.note.length > 160 ? '…' : ''}</div>`).join('');
    const lp = profile.lastPage;

    // Studied count per collection (first path segment).
    const groups = {};
    for (const p of studied) {
      const parts = p.path.split('/').filter(Boolean);
      const g = (p.title || '').split(' · ')[0] || parts[0];
      groups[g] = (groups[g] || 0) + 1;
    }

    const unverified = user.providerData.some(p => p.providerId === 'password') && !user.emailVerified;
    root.innerHTML = `
      <div class="acct-card acct-me">
        <div>
          <div class="acct-hello">Namaste${user.displayName ? ', ' + esc(user.displayName) : ''}</div>
          <div class="acct-email">${esc(user.email || '')}</div>
          ${unverified ? `<div class="acct-note">Please confirm your email address — we sent you a link. <button type="button" class="acct-link acct-resend">Send it again</button></div>` : ''}
        </div>
      </div>

      ${lp ? `<section class="acct-section"><h2>Continue where you left off</h2>
        <p><a class="continue-link" href="${esc(BASE + lp.path)}#continue">${esc(lp.title)}${lp.sub ? ` <span class="continue-sub">${esc(lp.sub)}</span>` : ''} →</a>${markLine(lp)}</p></section>` : ''}

      ${stopped.length ? `<section class="acct-section"><h2>🔖 Where I stopped <span class="acct-count">one per text</span></h2>
        <ul class="acct-list stopped-list">${stopped.map(stoppedItem).join('')}</ul></section>` : ''}

      <section class="acct-section"><h2>★ Bookmarks <span class="acct-count">${bookmarks.length}</span></h2>
        ${bookmarks.length ? `<ul class="acct-list">${bookmarks.map(p => `<li>${link(p)}</li>`).join('')}</ul>`
          : '<p class="acct-empty">No bookmarks yet. Use “☆ Bookmark” at the top of any chapter.</p>'}</section>

      <section class="acct-section"><h2>✓ Progress <span class="acct-count">${studied.length} studied</span></h2>
        ${studied.length ? `<ul class="acct-list">${Object.entries(groups).map(([g, n]) => `<li>${esc(g)}: <strong>${n}</strong> studied</li>`).join('')}</ul>`
          : '<p class="acct-empty">Nothing marked yet. Use “○ Mark as studied” at the top of a chapter when you finish it.</p>'}</section>

      <section class="acct-section"><h2>✎ My notes <span class="acct-count">${notes.length}</span></h2>
        ${notes.length ? `<ul class="acct-list acct-notes">${notes.map(p => `<li>${link(p)}${(p.note || '').trim() ? `<div class="acct-snippet">${esc(p.note.slice(0, 220))}${p.note.length > 220 ? '…' : ''}</div>` : ''}${verseList(p)}</li>`).join('')}</ul>`
          : '<p class="acct-empty">No notes yet. Every shloka has a “✎ Note on this shloka” button, and each chapter a “My notes” box at the end.</p>'}</section>

      <section class="acct-section"><h2>Settings</h2>
        <label class="acct-check"><input type="checkbox" class="acct-announce" ${profile.announcements ? 'checked' : ''}> Email me when new chapters are released</label>
        <span class="acct-saved" aria-live="polite"></span>
        <p class="acct-fine"><a href="${BASE}privacy/">Privacy policy</a> ·
          <button type="button" class="acct-link acct-danger acct-delete">Delete my account</button></p>
      </section>
      <div class="acct-admin"></div>
      <div class="home-signout acct-bottom-signout"><span>Signed in as <strong>${esc(user.displayName || user.email || '')}</strong></span>
        <button type="button" class="acct-secondary acct-signout">Sign out</button></div>`;

    root.querySelector('.acct-signout').addEventListener('click', () => signOut(auth));
    root.querySelector('.acct-resend')?.addEventListener('click', e => {
      sendEmailVerification(user).then(() => { e.target.outerHTML = '<em>Sent — check your inbox.</em>'; }).catch(err => alert(friendly(err)));
    });
    const ann = root.querySelector('.acct-announce');
    ann.addEventListener('change', async () => {
      const saved = root.querySelector('.acct-saved');
      try { await setAnnouncements(user, ann.checked); saved.textContent = 'Saved'; }
      catch (e) { ann.checked = !ann.checked; saved.textContent = friendly(e); }
    });
    root.querySelector('.acct-delete').addEventListener('click', () => deleteAccount(user, pages));
    adminPanel(root.querySelector('.acct-admin'));
  }

  onAuthStateChanged(auth, user => {
    UI.setSignedIn(user);
    if (user && signingUp) return;   // the sign-up form finishes setting up the account itself
    if (user) renderSignedIn(user); else renderSignedOut();
  });
}

let signingUp = false;        // true while the sign-up form creates the account
let pendingAnnounce = null;   // chosen on the sign-up form, applied when the user record is created

async function ensureUser(user) {
  const ref = userRef(user.uid);
  const snap = await getDoc(ref);
  if (snap.exists()) return snap.data();
  const data = { name: user.displayName || '', email: user.email || '', announcements: !!pendingAnnounce, created: serverTimestamp() };
  await setDoc(ref, data);
  if (pendingAnnounce) await setAnnouncements(user, true);
  pendingAnnounce = null;
  return data;
}

async function setAnnouncements(user, on) {
  await setDoc(userRef(user.uid), { announcements: on }, { merge: true });
  const sref = doc(db, 'subscribers', user.uid);
  if (on) await setDoc(sref, { email: user.email || '', name: user.displayName || '', at: serverTimestamp() });
  else await deleteDoc(sref);
}

async function deleteAccount(user, pages) {
  if (!confirm('Delete your account? Your bookmarks, progress and notes will be erased permanently. This cannot be undone.')) return;
  try {
    const batch = writeBatch(db);
    for (const p of pages) batch.delete(pageRef(user.uid, p.path));
    batch.delete(doc(db, 'subscribers', user.uid));
    batch.delete(userRef(user.uid));
    await batch.commit();
    await deleteUser(user);
    alert('Your account has been deleted.');
  } catch (e) {
    alert(friendly(e));
  }
}

// Site owner only (Firestore rules allow just the owner to list subscribers): download the
// announcements list as a spreadsheet (CSV).
async function adminPanel(el) {
  let snap;
  try { snap = await getDocs(collection(db, 'subscribers')); } catch { return; }
  const rows = snap.docs.map(d => d.data()).sort((a, b) => (a.at?.seconds || 0) - (b.at?.seconds || 0));
  el.innerHTML = `<section class="acct-section"><h2>Site owner</h2>
    <p>Announcements list: <strong>${rows.length}</strong> reader${rows.length === 1 ? '' : 's'} opted in.</p>
    <button type="button" class="acct-secondary">Download list (CSV for Excel / Google Sheets)</button></section>`;
  el.querySelector('button').addEventListener('click', () => {
    const q = v => '"' + String(v ?? '').replace(/"/g, '""') + '"';
    const csv = 'Name,Email,Joined\r\n' + rows.map(r => [r.name, r.email, r.at ? new Date(r.at.seconds * 1000).toISOString().slice(0, 10) : ''].map(q).join(',')).join('\r\n');
    const a = Object.assign(document.createElement('a'), {
      href: URL.createObjectURL(new Blob(['﻿' + csv], { type: 'text/csv' })),
      download: 'samskrita-svadhyaya-announcements.csv',
    });
    a.click();
  });
}

// ---------------------------------------------------------------- start
if (UI.isAccountPage) {
  accountPage();
} else {
  let started = false;
  onAuthStateChanged(auth, user => {
    UI.setSignedIn(user);
    if (!user) { UI.renderSignedOut(); return; }
    if (started) return;
    started = true;
    if (UI.studyBar) readingPage(user);
    markIndex(user).catch(() => {});
    homeContinue(user).catch(() => {});
    homeSignOut(user);
  });
}
