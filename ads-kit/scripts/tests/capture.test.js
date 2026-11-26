// Run from the repo root: node --test "ads-kit/scripts/tests/*.test.js"
// Tests capture.js against a small fake document. No browser, no network.
'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const SRC = path.join(__dirname, '..', 'capture.js');
const AdsCapture = require(SRC);

// ---- fakes ---------------------------------------------------------------

function fakeJar() {
  const store = new Map();
  const writes = [];
  return {
    store,
    writes,
    get cookie() {
      return Array.from(store.entries()).map(([k, v]) => `${k}=${v}`).join('; ');
    },
    set cookie(str) {
      writes.push(str);
      const [pair, ...attrs] = str.split(';').map((s) => s.trim());
      const eq = pair.indexOf('=');
      const name = pair.slice(0, eq);
      const value = pair.slice(eq + 1);
      const maxAge = attrs.find((a) => a.toLowerCase().startsWith('max-age='));
      if (maxAge && Number(maxAge.split('=')[1]) <= 0) store.delete(name);
      else store.set(name, value);
    },
  };
}

function fakeInput() {
  return { type: 'text', name: '', value: '' };
}

function fakeForm(id) {
  const inputs = [];
  return {
    id,
    inputs,
    querySelector(sel) {
      const m = /^input\[name="([^"]+)"\]$/.exec(sel);
      if (!m) throw new Error('unexpected selector ' + sel);
      return inputs.find((i) => i.name === m[1]) || null;
    },
    appendChild(el) {
      inputs.push(el);
      return el;
    },
    matches(sel) {
      return sel === 'form';
    },
    value(name) {
      const el = inputs.find((i) => i.name === name);
      return el ? el.value : undefined;
    },
  };
}

function fakeDocument({ jar, forms = [], referrer = '' }) {
  return {
    referrer,
    readyState: 'complete',
    get cookie() { return jar.cookie; },
    set cookie(v) { jar.cookie = v; },
    createElement(tag) {
      assert.equal(tag, 'input');
      return fakeInput();
    },
    querySelectorAll(sel) {
      assert.equal(sel, 'form');
      return forms;
    },
    addEventListener() {},
  };
}

function loc(url) {
  const u = new URL(url);
  return { href: u.href, search: u.search, host: u.host, protocol: u.protocol };
}

function visit({ jar, url, referrer = '', forms = [], at = '2026-12-01T10:00:00.000Z', options = {} }) {
  const document = fakeDocument({ jar, forms, referrer });
  const cap = AdsCapture.create({ document, location: loc(url), now: () => new Date(at) }, options);
  return { cap, result: cap.run(), document };
}

const SITE = 'https://www.acme-plumbing.example';

// ---- tests ---------------------------------------------------------------

test('captures click ids, UTMs, landing page, referrer and first-seen into hidden fields', () => {
  const jar = fakeJar();
  const form = fakeForm('quote');
  const url = `${SITE}/drain-cleaning?gclid=TeSt.gclid-123&utm_source=google&utm_medium=paid&utm_campaign=drains&utm_content=AP-20261201-03&utm_term=drain+cleaning#top`;
  const { result } = visit({ jar, url, referrer: 'https://www.google.com/', forms: [form] });

  assert.equal(result.ran, true);
  assert.equal(result.forms, 1);
  assert.equal(form.value('gclid'), 'TeSt.gclid-123');
  assert.equal(form.value('utm_source'), 'google');
  assert.equal(form.value('utm_content'), 'AP-20261201-03');
  assert.equal(form.value('utm_term'), 'drain cleaning');
  assert.equal(form.value('landing_page'), `${SITE}/drain-cleaning?gclid=TeSt.gclid-123&utm_source=google&utm_medium=paid&utm_campaign=drains&utm_content=AP-20261201-03&utm_term=drain+cleaning`);
  assert.equal(form.value('referrer'), 'https://www.google.com/');
  assert.equal(form.value('first_seen'), '2026-12-01T10:00:00.000Z');
  assert.equal(form.value('last_gclid'), 'TeSt.gclid-123');
  assert.equal(form.value('last_seen'), '2026-12-01T10:00:00.000Z');
  // every field is a hidden input
  assert.ok(form.inputs.every((i) => i.type === 'hidden'));
  for (const k of ['gbraid', 'wbraid', 'fbclid', 'msclkid', 'ttclid', 'li_fat_id', 'fbc', 'fbp']) {
    assert.equal(form.value(k), '', `empty field present for ${k}`);
  }
});

test('first touch is kept; last touch moves to the newest ad visit', () => {
  const jar = fakeJar();
  visit({ jar, url: `${SITE}/?gclid=first-click&utm_source=google`, at: '2026-12-01T10:00:00.000Z' });
  // internal page view without signals: nothing changes
  visit({ jar, url: `${SITE}/about`, referrer: `${SITE}/`, at: '2026-12-02T10:00:00.000Z' });
  const form = fakeForm('contact');
  visit({ jar, url: `${SITE}/contact?fbclid=IwAR-meta-click&utm_source=meta&utm_medium=paid`, forms: [form], at: '2026-12-05T09:30:00.000Z' });

  assert.equal(form.value('gclid'), 'first-click');
  assert.equal(form.value('utm_source'), 'google');
  assert.equal(form.value('first_seen'), '2026-12-01T10:00:00.000Z');
  assert.equal(form.value('last_gclid'), '');
  assert.equal(form.value('last_fbclid'), 'IwAR-meta-click');
  assert.equal(form.value('last_utm_source'), 'meta');
  assert.equal(form.value('last_seen'), '2026-12-05T09:30:00.000Z');
});

test('own-site referrer is not stored as a source', () => {
  const jar = fakeJar();
  const form = fakeForm('f');
  visit({ jar, url: `${SITE}/services?utm_source=newsletter`, referrer: `${SITE}/`, forms: [form] });
  assert.equal(form.value('referrer'), '');
});

test('reads Meta _fbc/_fbp cookies; builds fbc from fbclid when the pixel has not set it', () => {
  const jar = fakeJar();
  const form = fakeForm('f');
  visit({ jar, url: `${SITE}/?fbclid=AbC123`, forms: [form], at: '2026-12-01T10:00:00.000Z' });
  assert.equal(form.value('fbc'), `fb.1.${Date.parse('2026-12-01T10:00:00.000Z')}.AbC123`);
  assert.equal(form.value('fbp'), '');

  jar.store.set('_fbc', 'fb.1.1700000000000.FromPixel');
  jar.store.set('_fbp', 'fb.1.1700000000000.123456789');
  const form2 = fakeForm('g');
  visit({ jar, url: `${SITE}/contact`, forms: [form2] });
  assert.equal(form2.value('fbc'), 'fb.1.1700000000000.FromPixel');
  assert.equal(form2.value('fbp'), 'fb.1.1700000000000.123456789');
});

test('reads li_fat_id from its cookie when it is not in the URL', () => {
  const jar = fakeJar();
  jar.store.set('li_fat_id', 'li-cookie-id');
  const form = fakeForm('f');
  visit({ jar, url: `${SITE}/?utm_source=linkedin`, forms: [form] });
  assert.equal(form.value('li_fat_id'), 'li-cookie-id');
});

test('consent hook false: no cookies, no fields', () => {
  const jar = fakeJar();
  const form = fakeForm('f');
  const { result } = visit({ jar, url: `${SITE}/?gclid=x`, forms: [form], options: { consent: () => false } });
  assert.equal(result.ran, false);
  assert.equal(jar.writes.length, 0);
  assert.equal(form.inputs.length, 0);
});

test('a consent hook that throws counts as no consent', () => {
  const jar = fakeJar();
  const { result } = visit({ jar, url: `${SITE}/?gclid=x`, options: { consent: () => { throw new Error('cmp not ready'); } } });
  assert.equal(result.ran, false);
  assert.equal(jar.writes.length, 0);
});

test('consent granted later: run() captures then', () => {
  const jar = fakeJar();
  let granted = false;
  const form = fakeForm('f');
  const document = fakeDocument({ jar, forms: [form] });
  const cap = AdsCapture.create({ document, location: loc(`${SITE}/?gclid=later`), now: () => new Date('2026-12-01T00:00:00Z') }, { consent: () => (granted ? 'granted' : 'denied') });
  assert.equal(cap.run().ran, false);
  granted = true;
  assert.equal(cap.run().ran, true);
  assert.equal(form.value('gclid'), 'later');
});

test('cookies are first-party, path=/, SameSite=Lax, Secure on https, 90-day max-age, optional domain', () => {
  const jar = fakeJar();
  visit({ jar, url: `${SITE}/?gclid=x`, options: { cookieDomain: '.acme-plumbing.example' } });
  assert.equal(jar.writes.length, 2);
  for (const w of jar.writes) {
    assert.match(w, /^_adsc_(ft|lt)=/);
    assert.match(w, /; path=\//);
    assert.match(w, /; max-age=7776000/);
    assert.match(w, /; SameSite=Lax/);
    assert.match(w, /; domain=\.acme-plumbing\.example/);
    assert.match(w, /; Secure/);
  }
});

test('existing hidden fields are filled, not duplicated; createFields false only fills existing', () => {
  const jar = fakeJar();
  const form = fakeForm('f');
  form.appendChild({ type: 'hidden', name: 'gclid', value: 'old' });
  visit({ jar, url: `${SITE}/?gclid=new`, forms: [form] });
  assert.equal(form.inputs.filter((i) => i.name === 'gclid').length, 1);
  assert.equal(form.value('gclid'), 'new');

  const form2 = fakeForm('g');
  form2.appendChild({ type: 'hidden', name: 'utm_source', value: '' });
  visit({ jar: fakeJar(), url: `${SITE}/?utm_source=google&gclid=y`, forms: [form2], options: { createFields: false } });
  assert.equal(form2.inputs.length, 1);
  assert.equal(form2.value('utm_source'), 'google');
});

test('submit handler fills a form that was added after page load', () => {
  const jar = fakeJar();
  const { cap } = visit({ jar, url: `${SITE}/?gclid=sub`, forms: [] });
  const late = fakeForm('late');
  cap.onSubmit({ target: late });
  assert.equal(late.value('gclid'), 'sub');
});

test('bad input: control characters stripped, long values capped, bad encoding skipped', () => {
  const jar = fakeJar();
  const form = fakeForm('f');
  const long = 'a'.repeat(600);
  visit({ jar, url: `${SITE}/?utm_campaign=%0Aspring%00&utm_term=${long}&gclid=%E0%A4%A&utm_source=ok`, forms: [form] });
  assert.equal(form.value('utm_campaign'), 'spring');
  assert.equal(form.value('utm_term').length, 255);
  assert.equal(form.value('gclid'), '');
  assert.equal(form.value('utm_source'), 'ok');
});

test('a broken cookie value is ignored, not thrown', () => {
  const jar = fakeJar();
  jar.store.set('_adsc_ft', '%7Bnot-json');
  const form = fakeForm('f');
  const { result } = visit({ jar, url: `${SITE}/?gclid=fresh`, forms: [form] });
  assert.equal(result.ran, true);
  assert.equal(form.value('gclid'), 'fresh');
});

test('very long URLs keep the cookie under the size cap', () => {
  const jar = fakeJar();
  const params = ['gclid', 'gbraid', 'wbraid', 'fbclid', 'msclkid', 'ttclid', 'li_fat_id', 'utm_source', 'utm_medium', 'utm_campaign', 'utm_content', 'utm_term']
    .map((k) => `${k}=${'x'.repeat(250)}`).join('&');
  visit({ jar, url: `${SITE}/p?${params}&pad=${'y'.repeat(900)}`, referrer: `https://ref.example/?q=${'z'.repeat(900)}` });
  for (const v of jar.store.values()) assert.ok(v.length <= 3500, `cookie length ${v.length}`);
});

test('custom last-touch prefix', () => {
  const jar = fakeJar();
  const form = fakeForm('f');
  visit({ jar, url: `${SITE}/?gclid=p`, forms: [form], options: { lastPrefix: 'lt_' } });
  assert.equal(form.value('lt_gclid'), 'p');
  assert.equal(form.value('lt_seen'), '2026-12-01T10:00:00.000Z');
});

test('the script makes no network calls and loads in a plain browser-like global', () => {
  const src = fs.readFileSync(SRC, 'utf8');
  for (const banned of ['fetch(', 'XMLHttpRequest', 'sendBeacon', 'WebSocket', 'import(', 'new Image', '.src =']) {
    assert.ok(!src.includes(banned), `capture.js must not contain ${banned}`);
  }
  // Load as a classic <script>: no module, a window global, autoStart runs.
  const jar = fakeJar();
  const form = fakeForm('f');
  const document = fakeDocument({ jar, forms: [form] });
  const window = { document, location: loc(`${SITE}/?gclid=global`), adsCaptureOptions: {} };
  window.window = window;
  vm.runInNewContext(src, { window, Date, JSON, Object, String, Math, encodeURIComponent, decodeURIComponent });
  assert.equal(typeof window.AdsCapture.run, 'function');
  assert.equal(form.value('gclid'), 'global');
});

test('cookie writes blocked: submit keeps the values run() filled', () => {
  // A jar that silently drops every write, like a browser with cookies blocked.
  const blocked = { writes: [], get cookie() { return ''; }, set cookie(v) { this.writes.push(v); } };
  const form = fakeForm('f');
  const document = fakeDocument({ jar: blocked, forms: [form] });
  const cap = AdsCapture.create({ document, location: loc(`${SITE}/?gclid=kept&utm_source=google`), now: () => new Date('2026-12-01T10:00:00.000Z') });
  assert.equal(cap.run().ran, true);
  assert.equal(form.value('gclid'), 'kept');
  cap.onSubmit({ target: form });
  assert.equal(form.value('gclid'), 'kept');
  assert.equal(form.value('last_gclid'), 'kept');
  assert.equal(form.value('utm_source'), 'google');
  assert.equal(form.value('first_seen'), '2026-12-01T10:00:00.000Z');
});

test('tampered cookie: unknown keys, non-strings and control characters are dropped', () => {
  const jar = fakeJar();
  const evil = {
    gclid: 'ok-id\u0000\n',
    utm_source: { nested: true },
    utm_medium: 42,
    utm_campaign: 'x'.repeat(900),
    __proto__evil: 'no',
    onload: 'alert(1)',
    first_seen: '2026-11-01T00:00:00.000Z',
  };
  jar.store.set('_adsc_ft', encodeURIComponent(JSON.stringify(evil)));
  const document = fakeDocument({ jar });
  const cap = AdsCapture.create({ document, location: loc(`${SITE}/about`), now: () => new Date('2026-12-01T10:00:00.000Z') });
  const { first } = cap.read();
  assert.deepEqual(Object.keys(first).sort(), ['first_seen', 'gclid', 'utm_campaign']);
  assert.equal(first.gclid, 'ok-id');
  assert.equal(first.utm_campaign.length, 255);

  jar.store.set('_adsc_ft', encodeURIComponent(JSON.stringify(['gclid', 'x'])));
  assert.equal(cap.read().first, null);
  jar.store.set('_adsc_ft', encodeURIComponent(JSON.stringify({ junk: 'only' })));
  assert.equal(cap.read().first, null);
});

test('clear() deletes host-only and cookieDomain cookies', () => {
  const jar = fakeJar();
  const { cap } = visit({ jar, url: `${SITE}/?gclid=x`, options: { cookieDomain: '.acme-plumbing.example' } });
  assert.equal(jar.store.size, 2);
  jar.writes.length = 0;
  cap.clear();
  assert.equal(jar.store.size, 0);
  assert.equal(jar.writes.length, 4);
  assert.ok(jar.writes.every((w) => /max-age=0/.test(w)));
  assert.equal(jar.writes.filter((w) => /domain=\.acme-plumbing\.example/.test(w)).length, 2);
});
