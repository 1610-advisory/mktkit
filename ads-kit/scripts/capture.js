/*!
 * ads-kit capture.js — first-party ad click capture for lead forms.
 * MIT License. Part of ads-kit (https://github.com/1610-advisory/mktkit).
 *
 * What it does:
 *   1. On each page view, reads click ids and UTM tags from the URL.
 *   2. Stores them in two first-party cookies on your own domain:
 *        first touch (written once, kept)  and  last touch (updated on each ad visit).
 *   3. Writes them into hidden fields on your forms, so the form post
 *      carries them to your CRM intake.
 *
 * What it does NOT do: no network calls, no third-party cookies, no
 * fingerprinting, no personal data. It only reads the URL, the referrer and
 * the Meta pixel's own _fbc/_fbp cookies.
 *
 * Install: <script src="/capture.js" defer></script> on every page.
 * Options (set before the script loads):
 *   window.adsCaptureOptions = {
 *     consent: function () { return true; }, // your consent check; false = do nothing
 *     cookieDomain: '.example.com',          // share across subdomains (optional)
 *     days: 90,                               // cookie life (gclid lives 90 days)
 *     formSelector: 'form',                   // which forms get hidden fields
 *     lastPrefix: 'last_',                    // prefix for last-touch field names
 *     autoStart: true                         // false = call AdsCapture.run() yourself
 *   };
 * If your consent tool grants consent later, call window.AdsCapture.run().
 * Plain browser JavaScript (ES5), no dependencies.
 */
(function (root, factory) {
  var api = factory();
  if (typeof module === 'object' && module.exports) {
    module.exports = api;
  } else if (root) {
    root.AdsCapture = api;
    api.autoStart(root);
  }
})(typeof window !== 'undefined' ? window : null, function () {
  'use strict';

  // Click ids, in the order platforms document them.
  var CLICK_IDS = ['gclid', 'gbraid', 'wbraid', 'fbclid', 'msclkid', 'ttclid', 'li_fat_id'];
  var UTMS = ['utm_source', 'utm_medium', 'utm_campaign', 'utm_content', 'utm_term'];
  var URL_KEYS = CLICK_IDS.concat(UTMS);
  // Fields saved per touch (first and last).
  var TOUCH_FIELDS = URL_KEYS.concat(['landing_page', 'referrer']);
  var FIRST_COOKIE = '_adsc_ft';
  var LAST_COOKIE = '_adsc_lt';
  var MAX_LEN = 255;
  var MAX_URL_LEN = 1000;
  var MAX_COOKIE = 3500; // encoded value length; browsers cap a cookie near 4096 bytes

  function clean(value, max) {
    if (value === null || value === undefined) return '';
    // Strip control characters; cap the length.
    var s = String(value).replace(/[\u0000-\u001f\u007f]/g, '').trim();
    return s.length > max ? s.slice(0, max) : s;
  }

  function parseQuery(search) {
    var out = {};
    if (!search) return out;
    var q = search.charAt(0) === '?' ? search.slice(1) : search;
    var parts = q.split('&');
    for (var i = 0; i < parts.length; i++) {
      if (!parts[i]) continue;
      var eq = parts[i].indexOf('=');
      var k = eq < 0 ? parts[i] : parts[i].slice(0, eq);
      var v = eq < 0 ? '' : parts[i].slice(eq + 1);
      try {
        k = decodeURIComponent(k.replace(/\+/g, ' '));
        v = decodeURIComponent(v.replace(/\+/g, ' '));
      } catch (e) {
        continue; // bad encoding: skip this pair
      }
      k = k.toLowerCase();
      if (!(k in out)) out[k] = v; // first value wins
    }
    return out;
  }

  function readCookies(doc) {
    var out = {};
    var raw = '';
    try { raw = doc.cookie || ''; } catch (e) { return out; }
    var parts = raw.split(';');
    for (var i = 0; i < parts.length; i++) {
      var p = parts[i].replace(/^\s+/, '');
      if (!p) continue;
      var eq = p.indexOf('=');
      if (eq < 0) continue;
      var name = p.slice(0, eq);
      if (!(name in out)) out[name] = p.slice(eq + 1);
    }
    return out;
  }

  function decodeTouch(raw) {
    if (!raw) return null;
    try {
      var obj = JSON.parse(decodeURIComponent(raw));
      return obj && typeof obj === 'object' ? obj : null;
    } catch (e) {
      return null;
    }
  }

  function hostOf(url) {
    var m = /^[a-z][a-z0-9+.-]*:\/\/([^\/?#]+)/i.exec(url || '');
    return m ? m[1].toLowerCase() : '';
  }

  function create(env, options) {
    env = env || {};
    options = options || {};
    var doc = env.document;
    var loc = env.location || (doc && doc.location) || { href: '', search: '', host: '', protocol: '' };
    var now = env.now || function () { return new Date(); };
    var days = typeof options.days === 'number' && options.days > 0 ? options.days : 90;
    var lastPrefix = typeof options.lastPrefix === 'string' ? options.lastPrefix : 'last_';
    var formSelector = options.formSelector || 'form';

    function consentGiven() {
      var hook = options.consent;
      if (typeof hook !== 'function' && env.window && typeof env.window.adsCaptureConsent === 'function') {
        hook = env.window.adsCaptureConsent;
      }
      if (typeof hook !== 'function') return true; // no hook: the site owner decided
      try {
        var r = hook();
        return r === true || r === 'granted';
      } catch (e) {
        return false; // a broken hook never counts as consent
      }
    }

    // Keep each cookie under the ~4 KB browser limit: trim URLs first, then long values.
    function fit(obj) {
      var value = encodeURIComponent(JSON.stringify(obj));
      if (value.length <= MAX_COOKIE) return value;
      if (obj.landing_page) obj.landing_page = obj.landing_page.split('?')[0];
      if (obj.referrer) obj.referrer = obj.referrer.split('?')[0];
      value = encodeURIComponent(JSON.stringify(obj));
      if (value.length <= MAX_COOKIE) return value;
      for (var k in obj) {
        if (Object.prototype.hasOwnProperty.call(obj, k) && typeof obj[k] === 'string') obj[k] = obj[k].slice(0, 100);
      }
      return encodeURIComponent(JSON.stringify(obj));
    }

    function writeCookie(name, obj) {
      var value = fit(obj);
      var parts = [name + '=' + value, 'path=/', 'max-age=' + Math.round(days * 86400), 'SameSite=Lax'];
      if (options.cookieDomain) parts.push('domain=' + options.cookieDomain);
      if (loc.protocol === 'https:') parts.push('Secure');
      try { doc.cookie = parts.join('; '); } catch (e) { /* cookies blocked */ }
    }

    // Read this page view's signals from the URL.
    function pageTouch() {
      var q = parseQuery(loc.search || '');
      var touch = {};
      var hasSignal = false;
      for (var i = 0; i < URL_KEYS.length; i++) {
        var k = URL_KEYS[i];
        var v = clean(q[k], MAX_LEN);
        if (v) { touch[k] = v; hasSignal = true; }
      }
      // LinkedIn may keep li_fat_id in its own first-party cookie.
      if (!touch.li_fat_id) {
        var li = clean(readCookies(doc).li_fat_id, MAX_LEN);
        if (li) touch.li_fat_id = li;
      }
      var href = String(loc.href || '').split('#')[0];
      touch.landing_page = clean(href, MAX_URL_LEN);
      var ref = '';
      try { ref = doc.referrer || ''; } catch (e) { ref = ''; }
      // Keep only an outside referrer; our own pages are not a source.
      touch.referrer = ref && hostOf(ref) !== String(loc.host || '').toLowerCase() ? clean(ref.split('#')[0], MAX_URL_LEN) : '';
      return { touch: touch, hasSignal: hasSignal };
    }

    function read() {
      var c = readCookies(doc);
      return { first: decodeTouch(c[FIRST_COOKIE]), last: decodeTouch(c[LAST_COOKIE]) };
    }

    // Store first touch once; update last touch on each visit with a click id or UTM.
    function capture() {
      var stored = read();
      var page = pageTouch();
      var ts = now().toISOString();
      var first = stored.first;
      var last = stored.last;
      if (!first) {
        first = page.touch;
        first.first_seen = ts;
        writeCookie(FIRST_COOKIE, first);
      }
      if (page.hasSignal || !last) {
        last = page.touch === first ? copy(first) : page.touch;
        last.last_seen = ts;
        delete last.first_seen;
        writeCookie(LAST_COOKIE, last);
      }
      return { first: first, last: last };
    }

    function copy(o) {
      var r = {};
      for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) r[k] = o[k];
      return r;
    }

    // Meta browser ids. _fbc is built from the newest fbclid when the pixel has not set it.
    function metaIds(state) {
      var c = readCookies(doc);
      var fbc = clean(c._fbc, MAX_LEN);
      var fbp = clean(c._fbp, MAX_LEN);
      if (!fbc && state.last && state.last.fbclid) {
        var t = Date.parse(state.last.last_seen || '') || now().getTime();
        fbc = 'fb.1.' + t + '.' + state.last.fbclid;
      }
      return { fbc: fbc, fbp: fbp };
    }

    // The flat field map that goes into each form.
    function fields(state) {
      state = state || read();
      var out = {};
      var first = state.first || {};
      var last = state.last || {};
      for (var i = 0; i < TOUCH_FIELDS.length; i++) {
        var k = TOUCH_FIELDS[i];
        out[k] = first[k] || '';
        out[lastPrefix + k] = last[k] || '';
      }
      out.first_seen = first.first_seen || '';
      out[lastPrefix + 'seen'] = last.last_seen || '';
      var meta = metaIds(state);
      out.fbc = meta.fbc;
      out.fbp = meta.fbp;
      return out;
    }

    function setField(form, name, value) {
      var input = form.querySelector('input[name="' + name + '"]');
      if (!input) {
        if (options.createFields === false) return;
        input = doc.createElement('input');
        input.type = 'hidden';
        input.name = name;
        form.appendChild(input);
      }
      input.value = value;
    }

    function fill(form, state) {
      var map = fields(state);
      for (var name in map) {
        if (Object.prototype.hasOwnProperty.call(map, name)) setField(form, name, map[name]);
      }
    }

    function fillAll(state) {
      var forms = doc.querySelectorAll(formSelector);
      for (var i = 0; i < forms.length; i++) fill(forms[i], state);
      return forms.length;
    }

    // One full pass: consent check, capture, fill. Safe to call many times.
    function run() {
      if (!doc || !consentGiven()) return { ran: false };
      var state = capture();
      var filled = fillAll(state);
      return { ran: true, state: state, forms: filled };
    }

    // Fill the submitted form again at submit time (covers forms added later).
    function onSubmit(event) {
      if (!consentGiven()) return;
      var form = event && event.target;
      if (!form || typeof form.querySelector !== 'function') return;
      if (typeof form.matches === 'function' && !form.matches(formSelector)) return;
      fill(form, read());
    }

    return { run: run, read: read, fields: fields, fill: fill, onSubmit: onSubmit, consentGiven: consentGiven };
  }

  var instance = null;

  function autoStart(win) {
    var options = (win && win.adsCaptureOptions) || {};
    instance = create({ window: win, document: win.document, location: win.location }, options);
    if (win.document && typeof win.document.addEventListener === 'function') {
      win.document.addEventListener('submit', instance.onSubmit, true);
    }
    if (options.autoStart === false) return;
    if (win.document && win.document.readyState === 'loading') {
      win.document.addEventListener('DOMContentLoaded', instance.run);
    } else {
      instance.run();
    }
  }

  return {
    create: create,
    autoStart: autoStart,
    run: function () { return instance ? instance.run() : { ran: false }; },
    read: function () { return instance ? instance.read() : null; },
    CLICK_IDS: CLICK_IDS,
    UTMS: UTMS,
    COOKIES: { first: FIRST_COOKIE, last: LAST_COOKIE },
    _parseQuery: parseQuery
  };
});
