# Slide Type Reference

Each slide type is a self-contained HTML block. Drop into `slides.html` inside a `<div class="slide-wrap"><span class="slide-label">NN · Name</span>...</div>`. The `id` on the inner `<section class="slide">` must be `s1`, `s2`, ..., `sN` matching its position — `render.js` screenshots by id.

Replace `__PLACEHOLDERS__`. Comments inside each block tell you what each placeholder is for. Choose `tighter` on `.quote` for longer quotes (>20 words).

**Photo path requirement:** absolute `file:///` URL. Relative paths break in headless Chromium.

---

## Type: title

Used as the opening cover. One short title with an italic accent word, plus a one-sentence subtitle.

```html
<section class="slide" id="sN">
  <div class="bg" style="background-image: url('file:///abs/path/photo.jpg');"></div>
  <div class="overlay"></div>
  <div class="vignette"></div>
  <div class="content">
    <div><div class="eyebrow">__EYEBROW__</div></div>
    <div class="center">
      <h1 class="title">__LINE_1__<br/><em>__ACCENT__</em> __LINE_2__</h1>
      <p class="subtitle">__SUBTITLE__</p>
    </div>
    <div>
      <div class="footer-row">
        <span class="pagetag">__DOMAIN__</span>
        <span class="handle">@__HANDLE__</span>
      </div>
    </div>
  </div>
</section>
```

---

## Type: pull-quote

The workhorse slide. One quote, 1-3 italic accent phrases. Use `tighter` (`<p class="quote tighter">`) when the quote runs long.

```html
<section class="slide" id="sN">
  <div class="bg" style="background-image: url('file:///abs/path/photo.jpg');"></div>
  <div class="overlay"></div>
  <div class="vignette"></div>
  <div class="content">
    <div><div class="eyebrow">__EYEBROW__</div></div>
    <div class="center">
      <span class="quote-mark">&ldquo;</span>
      <p class="quote">__QUOTE_BEFORE_ACCENT__ <span class="accent">__ACCENT_PHRASE__</span> __QUOTE_AFTER_ACCENT__</p>
    </div>
    <div>
      <div class="footer-row">
        <span class="pagetag">__INDEX__&nbsp;·&nbsp;__CAROUSEL_NAME__</span>
        <span class="handle">@__HANDLE__</span>
      </div>
    </div>
  </div>
</section>
```

---

## Type: numbered-list

Roman-numeral list of 3-5 items. Each item: name + right-aligned italic note.

```html
<section class="slide" id="sN">
  <div class="bg" style="background-image: url('file:///abs/path/photo.jpg');"></div>
  <div class="overlay"></div>
  <div class="vignette"></div>
  <div class="content">
    <div><div class="eyebrow">__EYEBROW__</div></div>
    <div class="center">
      <h2 class="vent-headline">__HEADLINE_BEFORE__ <em>__ACCENT__</em>__HEADLINE_AFTER__</h2>
      <div class="vent-list">
        <div class="vent-item">
          <span class="vent-num">i.</span>
          <span class="vent-name">__ITEM_1__</span>
          <span class="vent-note">__NOTE_1__</span>
        </div>
        <div class="vent-item">
          <span class="vent-num">ii.</span>
          <span class="vent-name">__ITEM_2__</span>
          <span class="vent-note">__NOTE_2__</span>
        </div>
        <div class="vent-item">
          <span class="vent-num">iii.</span>
          <span class="vent-name">__ITEM_3__</span>
          <span class="vent-note">__NOTE_3__</span>
        </div>
        <div class="vent-item">
          <span class="vent-num">iv.</span>
          <span class="vent-name">__ITEM_4__</span>
          <span class="vent-note">__NOTE_4__</span>
        </div>
      </div>
    </div>
    <div>
      <div class="footer-row">
        <span class="pagetag">__INDEX__&nbsp;·&nbsp;__CAROUSEL_NAME__</span>
        <span class="handle">@__HANDLE__</span>
      </div>
    </div>
  </div>
</section>
```

---

## Type: stat

One huge number, one short caption underneath. Good for proof-point slides.

```html
<section class="slide" id="sN">
  <div class="bg" style="background-image: url('file:///abs/path/photo.jpg');"></div>
  <div class="overlay"></div>
  <div class="vignette"></div>
  <div class="content">
    <div><div class="eyebrow">__EYEBROW__</div></div>
    <div class="center">
      <div class="stat-number">__NUMBER__<em>__UNIT__</em></div>
      <p class="stat-caption">__CAPTION__</p>
    </div>
    <div>
      <div class="footer-row">
        <span class="pagetag">__INDEX__&nbsp;·&nbsp;__CAROUSEL_NAME__</span>
        <span class="handle">@__HANDLE__</span>
      </div>
    </div>
  </div>
</section>
```

---

## Type: cta

Closing slide with a call-to-action and a URL.

```html
<section class="slide" id="sN">
  <div class="bg" style="background-image: url('file:///abs/path/photo.jpg');"></div>
  <div class="overlay"></div>
  <div class="vignette"></div>
  <div class="content">
    <div><div class="eyebrow">__EYEBROW__</div></div>
    <div class="center">
      <h2 class="cta-headline">__HEADLINE_LINE_1__<br/><em>__ACCENT__</em></h2>
      <div class="cta-divider"></div>
      <p class="cta-link"><span class="domain">__DOMAIN__</span>&nbsp;/&nbsp;__PATH__</p>
    </div>
    <div>
      <div class="footer-row">
        <span class="pagetag">__INDEX__&nbsp;·&nbsp;__BRAND_FOOTER__</span>
        <span class="handle">@__HANDLE__</span>
      </div>
    </div>
  </div>
</section>
```

---

## Type: text-only

No photo. Solid brand-background slide for transitions, single punchy lines, or section dividers.

```html
<section class="slide text-only" id="sN">
  <div class="content">
    <div><div class="eyebrow">__EYEBROW__</div></div>
    <div class="center">
      <p class="quote">__LINE__ <span class="accent">__ACCENT_PHRASE__</span></p>
    </div>
    <div>
      <div class="footer-row">
        <span class="pagetag">__INDEX__&nbsp;·&nbsp;__CAROUSEL_NAME__</span>
        <span class="handle">@__HANDLE__</span>
      </div>
    </div>
  </div>
</section>
```

---

## Per-slide overlay tweaks

Override the default vertical gradient on slides where the photo needs different treatment:

```html
<!-- Slightly heavier than default (for bright photos) -->
<div class="overlay" style="background: linear-gradient(180deg, rgba(20,15,12,0.62) 0%, rgba(20,15,12,0.85) 100%);"></div>

<!-- Lighter than default (for already-dark photos) -->
<div class="overlay" style="background: linear-gradient(180deg, rgba(20,15,12,0.40) 0%, rgba(20,15,12,0.65) 100%);"></div>
```

## Sizing budget per slide-type

| Type | Max copy width | Notes |
|------|----------------|-------|
| title | ~720px subtitle | Two-line title max; subtitle one sentence |
| pull-quote | full width | ≤30 words on default `.quote`; ≤45 on `.quote.tighter` |
| numbered-list | ~760px headline | 3-5 items; each name ≤3 words; each note ≤6 words |
| stat | ~760px caption | Number ≤6 chars; caption one sentence |
| cta | ~900px URL | URL ≤45 chars; if longer split on `/` |
| text-only | full width | Same budget as pull-quote |
