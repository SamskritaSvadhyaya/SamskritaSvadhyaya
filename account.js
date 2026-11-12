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
  getFirestore, doc, getDoc, setDoc, updateDoc, deleteDoc, collection, getDocs, serverTimestamp, writeBatch, Timestamp,
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
UI.signOut = () => signOut(auth);   // used by the header Sign out button
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

// Saved chapter descriptions may start with the Sanskrit label ("सर्गः १३ · …"); show just the
// description when there is one (Narayaneeyam's "दशकम् २४" stays, as on its page).
const subOf = sub => {
  const parts = String(sub || '').split(' · ');
  while (parts.length > 1 && /[\u0900-\u097F]/.test(parts[0]) && !/[A-Za-z]/.test(parts[0])) parts.shift();
  return parts.join(' · ');
};

// ---------------------------------------------------------------- rich notes
// Notes can have bold, italics, underline and highlight. Stored as cleaned HTML behind a
// marker ("<!--rich-->…"); older notes are plain text and are shown/edited as such.
const RICH = '<!--rich-->';
const HL = '#fff1a8';                       // highlighter yellow (rgb 255, 241, 168)

// Keep only b / i / u / mark / line breaks; everything else becomes plain text.
function cleanNote(html) {
  const tpl = document.createElement('template');
  tpl.innerHTML = html;
  const walk = node => {
    let out = '';
    for (const c of node.childNodes) {
      if (c.nodeType === 3) { out += esc(c.textContent); continue; }
      if (c.nodeType !== 1) continue;
      const tag = c.tagName.toLowerCase();
      if (tag === 'br') { out += '<br>'; continue; }
      if (['script', 'style', 'img', 'iframe', 'object', 'svg', 'video', 'audio'].includes(tag)) continue;
      let inner = walk(c);
      const st = c.getAttribute('style') || '';
      const bg = st.match(/background(?:-color)?\s*:\s*([^;]+)/i);
      const hl = tag === 'mark' || (bg && !/transparent|rgba\(\s*0,\s*0,\s*0,\s*0\s*\)|initial|inherit|none/i.test(bg[1]));
      if (hl) inner = `<mark>${inner}</mark>`;
      if (tag === 'u' || /text-decoration[^;]*underline/i.test(st)) inner = `<u>${inner}</u>`;
      if (tag === 'i' || tag === 'em' || /font-style\s*:\s*italic/i.test(st)) inner = `<i>${inner}</i>`;
      if (tag === 'b' || tag === 'strong' || /font-weight\s*:\s*(bold|[6-9]00)/i.test(st)) inner = `<b>${inner}</b>`;
      if (['div', 'p', 'li'].includes(tag) && out && !out.endsWith('<br>')) inner = '<br>' + inner;
      out += inner;
    }
    return out;
  };
  return walk(tpl.content).replace(/(<br>\s*)+$/, '');
}
// Stored note -> safe HTML for display.
const noteHtml = note => !note ? '' : note.startsWith(RICH) ? cleanNote(note.slice(RICH.length)) : esc(note).replace(/\n/g, '<br>');

// A note box with a formatting toolbar. Saves (after a pause, and on leaving the box) through
// save(value) -> Promise; value is '' when the note is empty.
function noteEditor(host, note, { placeholder, status, save, onBlurEmpty }) {
  host.insertAdjacentHTML('beforeend', `<div class="note-tools" role="toolbar" aria-label="Formatting">
      <button type="button" data-cmd="bold" title="Bold (Ctrl+B)" aria-label="Bold"><b>B</b></button>
      <button type="button" data-cmd="italic" title="Italics (Ctrl+I)" aria-label="Italics"><i>I</i></button>
      <button type="button" data-cmd="underline" title="Underline (Ctrl+U)" aria-label="Underline"><u>U</u></button>
      <button type="button" data-cmd="hl" title="Highlight" aria-label="Highlight"><span class="hl-swatch">ab</span></button>
      <button type="button" data-cmd="clear" title="Clear formatting" aria-label="Clear formatting">clear</button>
    </div>
    <div class="note-editor" contenteditable="true" role="textbox" aria-multiline="true" spellcheck="true" data-placeholder="${esc(placeholder)}"></div>`);
  const tools = host.querySelector('.note-tools');
  const ed = host.querySelector('.note-editor');
  ed.innerHTML = noteHtml(note).replace(/<mark>/g, `<span style="background-color: ${HL};">`).replace(/<\/mark>/g, '</span>');
  let saved = note || '';
  const value = () => ed.textContent.trim() ? RICH + cleanNote(ed.innerHTML) : '';
  let timer = null;
  const flush = () => {
    clearTimeout(timer);
    const v = value();
    if (v === saved) return;
    if (v.length > 19000) { status.textContent = 'This note is too long to save — please shorten it.'; return; }
    status.textContent = 'Saving…';
    save(v).then(() => { saved = v; status.textContent = 'Saved'; })
      .catch(e => { status.textContent = 'Not saved — ' + friendly(e); });
  };
  const schedule = () => { status.textContent = ''; clearTimeout(timer); timer = setTimeout(flush, 1200); };
  const css = on => { try { document.execCommand('styleWithCSS', false, on); } catch {} };
  tools.addEventListener('mousedown', e => e.preventDefault());       // keep the text selection
  tools.addEventListener('click', e => {
    const b = e.target.closest('button');
    if (!b) return;
    ed.focus();
    const cmd = b.dataset.cmd;
    if (cmd === 'hl') {
      css(true);
      const cur = String(document.queryCommandValue('backColor') || '').replace(/\s/g, '');
      document.execCommand('backColor', false, cur === 'rgb(255,241,168)' ? 'transparent' : HL);
      css(false);
    } else if (cmd === 'clear') {
      document.execCommand('removeFormat');
      css(true); document.execCommand('backColor', false, 'transparent'); css(false);
    } else {
      css(false);
      document.execCommand(cmd);
    }
    schedule();
  });
  // Paste as plain words (no fonts, colours, links or scripts from other pages).
  ed.addEventListener('paste', e => {
    e.preventDefault();
    document.execCommand('insertText', false, (e.clipboardData || window.clipboardData).getData('text/plain'));
  });
  ed.addEventListener('drop', e => e.preventDefault());
  ed.addEventListener('input', schedule);
  ed.addEventListener('blur', () => { flush(); if (onBlurEmpty && !value() && !saved) setTimeout(onBlurEmpty, 300); });
  return { ed, flush, focus: () => ed.focus() };
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
    <div class="note-box"><p class="acct-loading">Loading your notes…</p></div>
    <div class="my-notes-status" aria-live="polite"></div>`;
  (document.getElementById('content') || bar).after(notes);
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
    const noteBox = notes.querySelector('.note-box');
    noteBox.innerHTML = '';
    noteEditor(noteBox, state.note || '', { placeholder: 'Your notes on this page…', status, save: v => save({ note: v }) });
    bBtn.disabled = sBtn.disabled = false;
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
    const m = i == null ? null : { n: i + 1, t: firstWords(shlokas[i].el), num: verseNum(shlokas[i].el) };
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
    const mi = markIndex();
    // Re-file the ribbon under its shloka's current position, opening words and number
    // (after a re-import that moved or reworded shlokas, or a mark saved before numbers).
    if (mi >= 0 && state.mark) {
      const fresh = { n: mi + 1, t: firstWords(shlokas[mi].el), num: verseNum(shlokas[mi].el) };
      if (fresh.n !== state.mark.n || fresh.t !== state.mark.t || fresh.num !== (state.mark.num || '')) {
        state.mark = fresh;
        setDoc(ref, { mark: fresh }, { merge: true }).catch(() => {});
      }
    }
  }

  bBtn.addEventListener('click', () => { save({ bookmarked: !state.bookmarked }).catch(e => alert(friendly(e))); paint(); });
  sBtn.addEventListener('click', () => {
    const on = !state.studied;
    save(on ? { studied: true, studiedAt: serverTimestamp() } : { studied: false }).catch(e => alert(friendly(e)));
    paint();
  });


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
    if (lp && lp.path === PATH && lp.mark && state.mark &&
        (lp.mark.n !== state.mark.n || lp.mark.t !== state.mark.t || (lp.mark.num || '') !== state.mark.num))
      setDoc(uref, { lastPage: { mark: state.mark } }, { merge: true }).catch(() => {});
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
// The shloka's own number as printed in the text (॥10.4.19॥, ॥24.1॥); a block holding two
// numbered verses gives a range (5.58.14–15). Empty if the text has no numbers.
function verseNum(el) {
  const ns = [...verseText(el).matchAll(/॥\s*([0-9०-९]+(?:\.[0-9०-९]+)+)\s*॥/g)].map(m => m[1]);
  if (!ns.length) return '';
  if (ns.length === 1) return ns[0];
  const last = ns[ns.length - 1];
  return ns[0] + '–' + last.slice(last.lastIndexOf('.') + 1);
}

// Find a saved shloka ({t: opening words, num: printed number, n: position}) on the page:
// by opening words (follows a shloka that was moved), then by its printed number (follows a
// reworded one), then by position.
function matchShloka(shlokas, ref) {
  if (!ref) return -1;
  let i = ref.t ? shlokas.findIndex(s => firstWords(s.el) === ref.t) : -1;
  if (i >= 0) return i;
  if (ref.num) {
    i = shlokas.findIndex(s => verseNum(s.el) === ref.num);
    if (i >= 0) return i;
  }
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
  // Match saved notes to shlokas (opening words, then printed number, then position), so a
  // note follows its shloka when the chapter is re-imported with shlokas reworded or reordered.
  const notes = new Array(shlokas.length).fill('');
  const placed = {};      // the notes re-filed under each shloka's current position
  let moved = false;
  // Exact opening-words matches first, so a moved shloka can't be claimed by position.
  const entries = Object.entries(saved).filter(([, v]) => v && (v.note || '').trim());
  const order = [...entries].sort(([, a], [, b]) =>
    (shlokas.some(s => firstWords(s.el) === b.t) ? 1 : 0) - (shlokas.some(s => firstWords(s.el) === a.t) ? 1 : 0));
  for (const [n, v] of order) {
    let i = matchShloka(shlokas, { t: v.t, num: v.num, n: Number(n) });
    if (i >= 0 && notes[i]) i = -1;              // that shloka already has its own note
    if (i < 0) { placed[n] = v; continue; }      // keep unmatched notes as they were
    notes[i] = v.note;
    const key = String(i + 1);
    const fresh = { t: firstWords(shlokas[i].el), num: verseNum(shlokas[i].el), note: v.note };
    if (key !== n || fresh.t !== v.t || fresh.num !== (v.num || '')) moved = true;
    placed[key] = fresh;
  }
  // Rewrite the whole map (not a merge) so old keys of moved notes are removed.
  if (moved) updateDoc(ref, { verses: placed }).catch(() => {});
  const byWords = new Map(shlokas.map((s, i) => [firstWords(s.el), i]));

  // Links from the Account page: #shloka-10.4.19 (by printed number) or #note-<key>.
  const hash = decodeURIComponent(location.hash.slice(1));
  let target = -1;
  if (hash.startsWith('shloka-')) target = shlokas.findIndex(s => verseNum(s.el) === hash.slice(7));
  else if (hash.startsWith('note-') && saved[hash.slice(5)]) {
    const v = saved[hash.slice(5)];
    target = matchShloka(shlokas, { t: v.t, num: v.num, n: Number(hash.slice(5)) });
  }
  if (target >= 0 && target < shlokas.length) {
    const el = shlokas[target].el;
    const go = () => {
      el.classList.add('flash');   // first: it also keeps the shloka clear of the sticky header
      el.scrollIntoView({ block: 'start', behavior: 'instant' });
      setTimeout(() => el.classList.remove('flash'), 2600);
    };
    if (document.readyState === 'complete') go(); else addEventListener('load', go, { once: true });
  }

  shlokas.forEach((s, i) => {
    const n = String(i + 1);
    const box = document.createElement('div');
    box.className = 'verse-note';
    s.end.after(box);
    let current = notes[i];
    const num = verseNum(s.el);
    const open = () => {
      box.innerHTML = `<label class="verse-note-label">✎ My note on ${num ? 'shloka ' + esc(num) : 'this shloka'}</label>
        <div class="note-box"></div>
        <div class="verse-note-status" aria-live="polite"></div>`;
      const st = box.querySelector('.verse-note-status');
      return noteEditor(box.querySelector('.note-box'), current, {
        placeholder: 'Your note on this shloka…', status: st, onBlurEmpty: closed,
        save: v => setDoc(ref, { verses: { [n]: { t: firstWords(s.el), num, note: v } }, path: PATH, title: info.title, sub: info.sub, updated: serverTimestamp() }, { merge: true })
          .then(() => { current = v; }),
      });
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

// "shloka 10.4.19", or the opening words for texts without shloka numbers.
const markWhere = mark => mark.num
  ? `shloka <strong>${esc(mark.num)}</strong>`
  : `the shloka <span lang="sa">“${esc(mark.t.split(/[।॥|]/)[0].trim())}…”</span>`;
const markLine = lp => lp.mark && lp.mark.t
  ? `<span class="continue-mark">🔖 from ${markWhere(lp.mark)}</span>` : '';

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

// Saved titles come from the chapter breadcrumb ("Book 1 — पूर्वार्धः · Chapter 4"). Show which
// text a "Book N" belongs to: "Shrimad Bhagavatam Book 1 · Chapter 4".
function displayTitle(p) {
  const title = p.title || p.path || '';
  const col = COLLECTIONS[collectionOf(p.path || '')] || '';
  return title.replace(/^Book (\d+)(?:\s+—\s+[^·]*?)?(?=\s+·|$)/, (_, n) => `${col} Book ${n}`.trim());
}
const workOf = p => displayTitle(p).split(' · ')[0];

function stoppedItem(p) {
  const col = COLLECTIONS[collectionOf(p.path)] || '';
  const title = displayTitle(p);
  const label = col && !title.startsWith(col) ? `${col} — ${title}` : title;
  return `<li><a href="${esc(BASE + p.path)}#mark">${esc(label)}</a>${p.sub ? ` <span class="acct-sub">${esc(subOf(p.sub))}</span>` : ''}
    <div class="stopped-shloka">🔖 from ${markWhere(p.mark)}</div></li>`;
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
    <a class="continue-link" href="${esc(BASE + lp.path)}#continue">${esc(displayTitle(lp))}${lp.sub ? ` <span class="continue-sub">${esc(subOf(lp.sub))}</span>` : ''} →</a>${markLine(lp)}`
    : `<span class="continue-label">${first ? `Namaste ${first}! ` : ''}Pick a text below to begin.</span>`)
    + (others.length ? `<div class="stopped-box"><span class="continue-label">Where I stopped in my other texts</span>
        <ul class="stopped-list">${others.map(stoppedItem).join('')}</ul></div>` : '')
    + `<a class="continue-account" href="${BASE}account/">My bookmarks, progress &amp; notes</a>`;
  grid.before(box);
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
          if (name) { await updateProfile(cred.user, { displayName: name }); UI.setSignedIn(cred.user); }
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
    const link = p => `<a href="${esc(BASE + p.path)}">${esc(displayTitle(p))}</a>${p.sub ? ` <span class="acct-sub">${esc(subOf(p.sub))}</span>` : ''}`;
    const bookmarks = pages.filter(p => p.bookmarked).sort(byTime);
    const stopped = stoppedPlaces(pages);
    const studied = pages.filter(p => p.studied);
    const notes = pages.filter(p => (p.note || '').trim() || hasVerseNotes(p)).sort(byTime);
    // Text names from the build (they say which collection a part belongs to).
    let TEXT_LABELS = {};
    try { TEXT_LABELS = JSON.parse(document.getElementById('text-labels')?.textContent || '{}'); } catch {}
    const textName = (key, p) => TEXT_LABELS[key] || workOf(p) || key;
    // My notes grouped by text (Narayaneeyam, Sundarakanda, Shrimad Bhagavatam Book 1 …);
    // texts with the latest note first, chapters in their own order (Dashaka 1, 2, 3 …).
    // Inside a text's group the heading names the text, so show just "Sarga 2" / "The story of Prahlada".
    // Dropdown labels: "Sarga 13 — Hanuman's soliloquy…", "Dashaka 24 — The story of Prahlada", "Chapter 4 — …".
    const UNIT = { sarga: 'Sarga', dashaka: 'Dashaka', ch: 'Chapter' };
    const slugOf = p => (p.path.split('/').filter(Boolean).pop() || '');
    const unitWord = p => (UNIT[slugOf(p).split('-')[0]] || 'chapter').toLowerCase();
    const noteCount = p => ((p.note || '').trim() ? 1 : 0) + Object.values(p.verses || {}).filter(v => (v?.note || '').trim()).length;
    const chapterLabel = p => {
      const unit = UNIT[slugOf(p).split('-')[0]];
      const no = +((slugOf(p).match(/(\d+)$/) || [])[1] || 0);
      if (!unit || !no) return shortTitle(p);
      // Dashakas saved before 13 Nov 2026 have the name as their title, later ones as the description.
      const subject = unit === 'Dashaka' && !/^Dashaka \d/.test(shortTitle(p)) ? shortTitle(p) : subOf(p.sub).replace(/^[^A-Za-z]*$/, '');
      return `${unit} ${no}` + (subject ? ` — ${subject.length > 60 ? subject.slice(0, 58) + '…' : subject}` : '');
    };
    const shortTitle = p => { const parts = displayTitle(p).split(' · '); return parts.length > 1 ? parts.slice(1).join(' · ') : parts[0]; };
    const shortLink = p => {
      const label = shortTitle(p);
      return `<a href="${esc(BASE + p.path)}">${esc(label)}</a>${p.sub ? ` <span class="acct-sub">${esc(subOf(p.sub))}</span>` : ''}`;
    };
    const chapterNo = p => +((p.path.match(/(\d+)\/?$/) || [])[1] || 0);
    const noteGroups = list => {
      const byText = new Map();
      for (const p of list) {
        const parts = p.path.split('/').filter(Boolean);
        const key = parts.length > 1 ? parts.slice(0, -1).join('/') : parts[0];
        if (!byText.has(key)) byText.set(key, { key, label: textName(key, p), items: [] });
        byText.get(key).items.push(p);
      }
      const groupsOut = [...byText.values()];
      for (const g of groupsOut) g.items.sort((a, b) => chapterNo(a) - chapterNo(b));
      return groupsOut;
    };
    // Each shloka label links to that shloka in its chapter (#shloka-10.4.19, or #note-<key>
    // for texts without shloka numbers).
    const verseList = p => Object.entries(p.verses || {}).filter(([, v]) => (v?.note || '').trim())
      .sort((a, b) => a[0] - b[0])
      .map(([key, v]) => `<div class="acct-snippet">${v.num
        ? `<a class="acct-verse-num" href="${esc(BASE + p.path)}#shloka-${esc(v.num)}" title="Read shloka ${esc(v.num)}">Shloka ${esc(v.num)}</a>`
        : `<a class="acct-verse" lang="sa" href="${esc(BASE + p.path)}#note-${esc(key)}">${esc(v.t)}…</a>`} — <span class="note-text">${noteHtml(v.note)}</span></div>`).join('');
    const lp = profile.lastPage;

    // Studied count per text (the chapter's folder: narayaneeyam, thestoryofhanuman/sundarakanda,
    // shrimad-bhagavatam-canto-10/book-1 …), out of that text's total from the build.
    let totals = {};
    try { totals = JSON.parse(document.getElementById('text-totals')?.textContent || '{}'); } catch {}
    // Progress per text (textKey = the chapter's folder): "N of TOTAL studied", or "completed".
    // (profile.readings from the earlier reading-cycles feature is no longer shown.)
    const readings = profile.readings || {};
    const textKey = p => { const parts = p.path.split('/').filter(Boolean); return parts.length > 1 ? parts.slice(0, -1).join('/') : parts[0]; };
    const groups = new Map();
    const group = (key, label) => {
      if (!groups.has(key)) groups.set(key, { key, label, n: 0, total: totals[key] || 0, pages: [], last: 0, lastTs: null,
        done: readings[key.replace(/\//g, '|')] || [] });
      return groups.get(key);
    };
    for (const p of studied) {
      const g = group(textKey(p), textName(textKey(p), p));
      g.n += 1;
      g.pages.push(p);
      const ts = p.studiedAt || p.updated;
      if (ts && ts.seconds > g.last) { g.last = ts.seconds; g.lastTs = ts; }
    }
    // Texts read before but with nothing studied in the current reading.
    const pastLabels = () => { try { return JSON.parse(document.getElementById('text-labels')?.textContent || '{}'); } catch { return {}; } };
    const fmt = ts => ts ? new Date(ts.seconds * 1000).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' }) : '';
    // One row per text: name · bar across the box · "26 of 100 studied" (or "completed").
    const progressItem = g => {
      const complete = g.total > 0 && g.n >= g.total;
      const pct = complete ? 100 : g.total ? Math.min(100, Math.round((g.n / g.total) * 100)) : 0;
      return `<li class="acct-progress${complete ? ' acct-complete' : ''}">`
        + `<span class="ap-name">${complete ? '✓ <strong>' + esc(g.label) + '</strong>' : esc(g.label)}</span>`
        + (g.total ? `<span class="acct-bar" aria-hidden="true"><span style="width:${pct}%"></span></span>` : '<span></span>')
        + `<span class="ap-count">${complete ? 'completed' : `<strong>${g.n}</strong>${g.total ? ` of ${g.total}` : ''} studied`}</span></li>`;
    };

    const unverified = user.providerData.some(p => p.providerId === 'password') && !user.emailVerified;
    root.innerHTML = `
      <div class="acct-card acct-me">
        <div>
          <div class="acct-hello">Namaste${user.displayName ? ', ' + esc(user.displayName) : ''}</div>
          ${unverified ? `<div class="acct-note">Please confirm your email address — we sent you a link. <button type="button" class="acct-link acct-resend">Send it again</button></div>` : ''}
        </div>
      </div>

      ${lp ? `<section class="acct-section"><h2>Continue where you left off</h2>
        <p><a class="continue-link" href="${esc(BASE + lp.path)}#continue">${esc(displayTitle(lp))}${lp.sub ? ` <span class="continue-sub">${esc(subOf(lp.sub))}</span>` : ''} →</a>${markLine(lp)}</p></section>` : ''}

      ${stopped.length ? `<section class="acct-section"><h2>🔖 Where I stopped <span class="acct-count">one per text</span></h2>
        <ul class="acct-list stopped-list">${stopped.map(stoppedItem).join('')}</ul></section>` : ''}

      <section class="acct-section"><h2>★ Bookmarks <span class="acct-count">${bookmarks.length}</span></h2>
        ${bookmarks.length ? `<ul class="acct-list">${bookmarks.map(p => `<li>${link(p)}</li>`).join('')}</ul>`
          : '<p class="acct-empty">No bookmarks yet. Use “☆ Bookmark” at the top of any chapter.</p>'}</section>

      <section class="acct-section"><h2>✓ Progress <span class="acct-count">${studied.length} studied</span></h2>
        ${groups.size ? `<ul class="acct-progress-list">${[...groups.values()].map(progressItem).join('')}</ul>`
          : '<p class="acct-empty">Nothing marked yet. Use “○ Mark as studied” at the top of a chapter when you finish it.</p>'}</section>

      <section class="acct-section"><h2>✎ My notes</h2>
        ${notes.length ? (() => {
          const gs = noteGroups(notes);
          return `<div class="note-tabs" role="tablist" aria-label="Notes by text">${gs.map((g, i) =>
            `<button type="button" class="note-tab" role="tab" id="note-tab-${i}" aria-controls="note-panel-${i}" aria-selected="false" data-key="${esc(g.key)}">${esc(g.label)}</button>`).join('')}</div>`
            + gs.map((g, i) => `<div class="note-panel" role="tabpanel" id="note-panel-${i}" aria-labelledby="note-tab-${i}" hidden>
              <label class="ch-pick"><span class="sr-only">Chapter</span>
                <select class="ch-select" data-panel="${i}">
                  <option value="">Choose a ${unitWord(g.items[0])}…</option>
                  ${g.items.map((p, j) => `<option value="${j}" data-path="${esc(p.path)}">${esc(chapterLabel(p))}</option>`).join('')}
                </select></label>
              ${g.items.map((p, j) => `<div class="ch-panel" id="ch-panel-${i}-${j}" hidden>
                <ul class="acct-list acct-notes"><li>${shortLink(p)}${(p.note || '').trim() ? `<div class="acct-snippet"><span class="note-text">${noteHtml(p.note)}</span></div>` : ''}${verseList(p)}</li></ul></div>`).join('')}</div>`).join('');
        })()
          : '<p class="acct-empty">No notes yet. Every shloka has a “✎ Note on this shloka” button, and each chapter a “My notes” box at the end.</p>'}</section>

      <div class="acct-small-row">
      <section class="acct-section acct-small">
        <label class="acct-check"><input type="checkbox" class="acct-announce" ${profile.announcements ? 'checked' : ''}> Email me when new chapters are released</label>
        <span class="acct-saved" aria-live="polite"></span>
        <p class="acct-fine"><button type="button" class="acct-link acct-danger acct-delete">Delete my account</button></p>
      </section>
      <div class="acct-admin"></div>
      </div>`;

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
    const tabs = [...root.querySelectorAll('.note-tab')];
    if (tabs.length) {
      const show = (tab, remember = true) => {
        tabs.forEach(t => {
          const on = t === tab;
          t.setAttribute('aria-selected', String(on));
          document.getElementById(t.getAttribute('aria-controls')).hidden = !on;
        });
        if (remember) { try { localStorage.setItem('ss-notes-tab', tab ? tab.dataset.key : ''); } catch {} }
      };
      tabs.forEach(t => t.addEventListener('click', () => show(t.getAttribute('aria-selected') === 'true' ? null : t)));
      let saved = null;
      try { saved = localStorage.getItem('ss-notes-tab'); } catch {}
      show(saved === '' ? null : (tabs.find(t => t.dataset.key === saved) || tabs[0]), false);

      // Chapter dropdown inside a text: shows the chosen chapter's shloka numbers and notes.
      const pick = (select, remember = true) => {
        const i = select.dataset.panel;
        select.closest('.note-panel').querySelectorAll('.ch-panel').forEach((pnl, j) => { pnl.hidden = String(j) !== select.value; });
        if (remember) {
          const opt = select.selectedOptions[0];
          try { localStorage.setItem('ss-notes-ch', opt && opt.dataset.path ? opt.dataset.path : ''); } catch {}
        }
      };
      root.querySelectorAll('.ch-select').forEach(sel => sel.addEventListener('change', () => pick(sel)));
      let savedCh = null;
      try { savedCh = localStorage.getItem('ss-notes-ch'); } catch {}
      const opt = savedCh && [...root.querySelectorAll('.ch-select option')].find(o => o.dataset.path === savedCh);
      if (opt) {
        // Reopen the remembered chapter inside its own text's tab.
        const sel = opt.closest('select');
        const tab = tabs.find(t => t.getAttribute('aria-controls') === sel.closest('.note-panel').id);
        if (tab) show(tab, false);
        sel.value = opt.value;
        pick(sel, false);
      }
    }
    root.querySelectorAll('.acct-again').forEach(btn => btn.addEventListener('click', async () => {
      const g = groups.get(btn.dataset.key);
      if (!g) return;
      const cycle = g.done.length + 1;
      if (!confirm(`Record reading ${cycle} of ${g.label} as finished on ${fmt(g.lastTs) || 'today'}, and start reading ${cycle + 1}?\n\nThe ✓ studied marks for ${g.label} will be cleared. Your bookmarks, notes and ribbons stay.`)) return;
      btn.disabled = true;
      try {
        const done = [...g.done, { cycle, finished: g.lastTs || Timestamp.now() }];
        await setDoc(userRef(user.uid), { readings: { [g.key.replace(/\//g, '|')]: done } }, { merge: true });
        const batch = writeBatch(db);
        for (const p of g.pages) batch.set(pageRef(user.uid, p.path), { studied: false }, { merge: true });
        await batch.commit();
        renderSignedIn(user);
      } catch (e) { btn.disabled = false; alert(friendly(e)); }
    }));
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
  UI.markOwner && UI.markOwner();
  el.innerHTML = `<section class="acct-section acct-small"><h2>Site owner</h2>
    <p>Announcements list: <strong>${rows.length}</strong> reader${rows.length === 1 ? '' : 's'} opted in.</p>
    <button type="button" class="acct-secondary">Download list (CSV)</button></section>`;
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

// ---------------------------------------------------------------- study tracker (site owner only)
// tracker/: one table per text (Sundarakanda with KK 66-67, Narayaneeyam, Shrimad Bhagavatam),
// one column per cycle. Saved in the owner's own user document:
//   users/{uid}.tracker[textKey] = { cycles: N, cells: { "<chapter path>~<cycle>": "YYYY-MM-DD" | "done" | "" } }
// The page is only shown to the site owner (the account that may list the announcements list).
function trackerPage() {
  const root = document.getElementById('tracker-app');
  let texts = [];
  try { texts = JSON.parse(document.getElementById('tracker-data')?.textContent || '[]'); } catch {}
  const today = () => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`; };   // local date
  const nice = v => {
    if (!v || v === 'done') return v === 'done' ? 'Done' : '';
    const d = new Date(v + 'T12:00:00');
    return isNaN(d) ? v : d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
  };

  async function load(user) {
    try { await getDocs(collection(db, 'subscribers')); }            // only the site owner may
    catch { root.innerHTML = '<p class="acct-empty">This page is private.</p>'; return; }
    UI.markOwner && UI.markOwner();
    const snap = await getDoc(userRef(user.uid));
    const tracker = (snap.exists() && snap.data().tracker) || {};
    let active = 0;
    try { active = Math.max(0, texts.findIndex(t => t.key === localStorage.getItem('ss-tracker-tab'))); } catch {}
    const data = k => (tracker[k] = tracker[k] || { cycles: 1, cells: {} });
    const saveCell = (k, cell, value) => {
      data(k).cells[cell] = value;
      return setDoc(userRef(user.uid), { tracker: { [k]: { cells: { [cell]: value } } } }, { merge: true });
    };

    function render() {
      const t = texts[active];
      const d = data(t.key);
      const cyc = [];
      for (let c = d.cycles; c >= 1; c--) cyc.push(c);              // newest first, like the sheet
      const doneIn = c => t.rows.filter(r => d.cells[`${r.id}~${c}`]).length;
      root.innerHTML = `
        <div class="note-tabs tr-tabs" role="tablist">${texts.map((x, i) =>
          `<button type="button" class="note-tab" role="tab" aria-selected="${i === active}" data-i="${i}">${esc(x.title)}</button>`).join('')}</div>
        <div class="tr-actions">
          <button type="button" class="acct-secondary tr-new">+ New cycle</button>
        </div>
        <div class="tr-scroll"><table class="tr-table">
          <thead><tr><th class="tr-no">No.</th><th class="tr-name">Name</th><th class="tr-sh">Shlokas</th>
            ${cyc.map(c => `<th class="tr-cyc">Cycle ${c}<span>${doneIn(c)} / ${t.rows.length}</span></th>`).join('')}</tr></thead>
          <tbody>${t.rows.map(r => `<tr><td class="tr-no">${esc(r.no)}</td>
            <td class="tr-name"><a href="${esc(BASE + r.id + '/')}">${esc(r.name)}</a></td><td class="tr-sh">${esc(String(r.shlokas))}</td>
            ${cyc.map(c => { const v = d.cells[`${r.id}~${c}`] || '';
              return `<td class="tr-cell${v ? ' is-done' : ''}"><button type="button" data-cell="${esc(r.id)}~${c}" title="${v ? 'Done ' + esc(nice(v)) + ' — click to change' : 'Mark done'}">${v ? '✓ ' + esc(nice(v)) : '·'}</button></td>`; }).join('')}
          </tr>`).join('')}</tbody></table></div>
        <div class="tr-editor" hidden><span class="tr-ed-title"></span>
          <input type="date" max="${today()}"> <button type="button" class="acct-secondary tr-ed-save">Save</button>
          <button type="button" class="acct-link tr-ed-done">Done (no date)</button>
          <button type="button" class="acct-link acct-danger tr-ed-clear">Clear</button>
          <button type="button" class="acct-link tr-ed-close">Close</button></div>`;

      root.querySelectorAll('.tr-tabs .note-tab').forEach(b => b.addEventListener('click', () => {
        active = +b.dataset.i; try { localStorage.setItem('ss-tracker-tab', texts[active].key); } catch {}
        render();
      }));
      root.querySelector('.tr-new').addEventListener('click', async () => {
        if (!confirm(`Start cycle ${d.cycles + 1} of ${t.title}?`)) return;
        d.cycles += 1;
        await setDoc(userRef(user.uid), { tracker: { [t.key]: { cycles: d.cycles } } }, { merge: true });
        render();
      });
      // Cell editor: empty cell -> done today; filled cell -> change date / done without date / clear.
      const ed = root.querySelector('.tr-editor');
      let editing = null;
      const closeEd = () => { ed.hidden = true; editing = null; };
      root.querySelectorAll('.tr-cell button').forEach(b => b.addEventListener('click', async () => {
        const cell = b.dataset.cell, v = d.cells[cell] || '';
        if (!v) {
          b.disabled = true;
          try { await saveCell(t.key, cell, today()); } catch (err) { alert(friendly(err)); }
          return render();
        }
        editing = cell;
        const r = t.rows.find(x => cell.startsWith(x.id + '~'));
        ed.querySelector('.tr-ed-title').textContent = `${r ? r.no + ' ' + r.name : ''} — Cycle ${cell.split('~').pop()}:`;
        ed.querySelector('input').value = v === 'done' ? '' : v;
        ed.hidden = false;
        ed.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
      }));
      const editTo = async value => {
        if (!editing) return;
        try { await saveCell(t.key, editing, value); } catch (err) { alert(friendly(err)); }
        closeEd(); render();
      };
      ed.querySelector('.tr-ed-save').addEventListener('click', () => editTo(ed.querySelector('input').value || 'done'));
      ed.querySelector('.tr-ed-done').addEventListener('click', () => editTo('done'));
      ed.querySelector('.tr-ed-clear').addEventListener('click', () => editTo(''));
      ed.querySelector('.tr-ed-close').addEventListener('click', closeEd);
    }
    render();
  }

  onAuthStateChanged(auth, user => {
    UI.setSignedIn(user);
    if (!user) { root.innerHTML = `<p class="acct-empty">This page is private. <a href="${BASE}account/">Sign in</a></p>`; return; }
    load(user).catch(e => { root.innerHTML = `<p class="acct-msg error">${esc(friendly(e))}</p>`; });
  });
}

// ---------------------------------------------------------------- start
if (UI.isTrackerPage) {
  trackerPage();
} else if (UI.isAccountPage) {
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
  });
}
