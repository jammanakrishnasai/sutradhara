
import { COPY } from './frontend/src/copy.js';

const langs = ['en', 'te', 'hi', 'ta', 'ml', 'sa'];
console.log('Available languages in COPY:', Object.keys(COPY));

const enKeys = Object.keys(COPY.en).sort();
console.log(`English has ${enKeys.length} top-level keys.`);

let allPassed = true;

for (const lang of langs) {
  if (!COPY[lang]) {
    console.error(`MISSING LANGUAGE: ${lang}`);
    allPassed = false;
    continue;
  }
  const keys = Object.keys(COPY[lang]).sort();
  const missing = enKeys.filter(k => !(k in COPY[lang]));
  const extra = keys.filter(k => !(k in COPY.en));

  if (missing.length > 0) {
    console.error(`[${lang}] MISSING KEYS (${missing.length}):`, missing);
    allPassed = false;
  }
  if (extra.length > 0) {
    console.warn(`[${lang}] EXTRA KEYS (${extra.length}):`, extra);
  }

  // Audit nested objects
  for (const k of enKeys) {
    if (typeof COPY.en[k] === 'object' && COPY.en[k] !== null && !Array.isArray(COPY.en[k])) {
      const nestedEn = Object.keys(COPY.en[k]).sort();
      const nestedLang = Object.keys(COPY[lang][k] || {}).sort();
      const missingNested = nestedEn.filter(nk => !(nk in (COPY[lang][k] || {})));
      if (missingNested.length > 0) {
        console.error(`[${lang}.${k}] MISSING NESTED KEYS (${missingNested.length}):`, missingNested);
        allPassed = false;
      }
    }
  }

  if (missing.length === 0) {
    console.log(`[${lang}] AUDIT PASSED: All ${enKeys.length} keys present.`);
  }
}

if (allPassed) {
  console.log('\nSUMMARY: TRANSLATION-KEY AUDIT PASSED FOR ALL 6 LANGUAGES!');
} else {
  console.error('\nSUMMARY: TRANSLATION-KEY AUDIT FAILED!');
  process.exit(1);
}
