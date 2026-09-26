import fs from 'fs';
import path from 'path';

// The public-facing copy (landing page, page metadata) must not claim more
// than the project has measured, and must not name mechanisms the IP packet
// says are not to be described publicly yet. Rewritten 2026-09-26 after a
// sweep found claims that were false or unmeasured: "every voice" (43% of
// dialogue is attributed), a character "stays one person through a change of
// body" (fails on LOTM), "never leave your computer" (false with a cloud
// model configured), and panels "drawn from" reference sheets.

const ROOT = path.resolve(__dirname, '..', '..');
const FILES = ['src/pages/Landing.js', 'src/pages/Projects.js', 'public/index.html'];

const BANNED = [
  [/spoiler/i, 'spoiler-aware mechanisms are not to be described publicly (IP packet)'],
  [/\bobserver\b|\bwitness\b|knowledge[- ]?time|read[- ]?set|cache key|digest|bitemporal/i, 'internal mechanism names'],
  [/guarantee|perfect|flawless|seamless|100 ?%/i, 'absolute quality claims'],
  [/every voice|full-cast|every character\./i, 'completeness claims voice coverage does not support'],
  [/never leave|no cloud upload/i, 'privacy claim that is false when a cloud model is configured'],
  [/world.?first|state.of.the.art|the only|first ever/i, 'novelty claims'],
  [/right person|stays one person|more reliably/i, 'accuracy claims that are unmeasured or contradicted (LOTM)'],
];

function visibleCopy(file) {
  const raw = fs.readFileSync(path.join(ROOT, file), 'utf8');
  // Drop comments: the docblocks state the rules ("never claim it is the first...").
  return raw
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/^\s*\/\/.*$/gm, '')
    .replace(/<!--[\s\S]*?-->/g, '');
}

describe.each(FILES)('%s', (file) => {
  const text = visibleCopy(file);
  test.each(BANNED)('does not contain %s', (re, why) => {
    const hit = text.match(re);
    expect({ hit: hit && hit[0], why }).toEqual({ hit: null, why });
  });
});
