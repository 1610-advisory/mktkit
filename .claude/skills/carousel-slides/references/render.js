// Universal Playwright renderer for the ai-cmo:carousel-slides skill.
// Iterates every <section class="slide" id="sN"> in slides.html and writes slide-N.png.
// Auto-detects slide count, so works for any carousel length.

const { chromium } = require('playwright');
const path = require('path');
const fs = require('fs');

(async () => {
  const browser = await chromium.launch();
  const context = await browser.newContext({
    viewport: { width: 1080, height: 1350 },
    deviceScaleFactor: 2,
  });
  const page = await context.newPage();

  const fileUrl = 'file://' + path.resolve(__dirname, 'slides.html');
  await page.goto(fileUrl, { waitUntil: 'networkidle' });

  await page.evaluate(() => document.fonts.ready);
  await page.evaluate(() => document.body.classList.add('rendering'));
  await page.waitForTimeout(400);

  const ids = await page.$$eval(
    'section.slide[id]',
    (els) => els.map((e) => e.id).filter((id) => /^s\d+$/.test(id))
  );
  ids.sort((a, b) => parseInt(a.slice(1), 10) - parseInt(b.slice(1), 10));

  if (ids.length === 0) {
    console.error('No <section class="slide" id="sN"> elements found in slides.html');
    process.exit(1);
  }

  for (const id of ids) {
    const el = await page.$('#' + id);
    const out = path.resolve(__dirname, `slide-${id.slice(1)}.png`);
    await el.screenshot({ path: out });
    const stat = fs.statSync(out);
    console.log(`wrote ${path.basename(out)} (${(stat.size / 1024 / 1024).toFixed(1)} MB)`);
  }

  await browser.close();
})();
