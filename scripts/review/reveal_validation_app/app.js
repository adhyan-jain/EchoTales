// Reveal Check: static annotation app for the journal's human validation of the reveal oracle.
// No backend on purpose (hosted as plain files on Vercel): answers live in localStorage and leave the browser only
// through "Export my labels", so nothing depends on a server staying up while three people label.
"use strict";

const QUESTIONS = [
  { id: "q0", prompt: "Q0. Before reading: have you read this book or do you know its plot?", opts: [["yes", "Yes"], ["no", "No"]] },
  { id: "q1", prompt: "Q1. Does the highlighted reveal say that the alias is the hidden identity?", opts: [["explicit", "Explicit"], ["implied", "Implied only"], ["no", "No"]] },
  { id: "q2", prompt: "Q2. Does the reveal read as a revelation or as a reminder?", opts: [["revelation", "Revelation"], ["reminder", "Reminder"], ["cant_tell", "Can't tell"]] },
  { id: "q3", prompt: "Q3. From the earlier passages only, could a first-time reader name the hidden identity?", opts: [["no", "No"], ["suspect", "Suspect"], ["confident", "Confident"]] },
  { id: "q4", prompt: "Q4. Is this a valid item (real hidden person, specific named identity)?", opts: [["yes", "Yes"], ["no", "No"]] },
];
const REQUIRED = QUESTIONS.map(q => q.id);

let DATA = null, ME = null, MINE = [], CUR = 0, LABELS = {};
const $ = id => document.getElementById(id);
const storeKey = () => `reveal-check:${DATA.version}:${ME}`;

function load() {
  try { LABELS = JSON.parse(localStorage.getItem(storeKey()) || "{}"); } catch { LABELS = {}; }
}
function save() {
  try { localStorage.setItem(storeKey(), JSON.stringify(LABELS)); } catch { /* private mode: export still works */ }
}
const complete = key => REQUIRED.every(q => LABELS[key] && LABELS[key][q]);
const started = key => LABELS[key] && REQUIRED.some(q => LABELS[key][q]);

function esc(s) {
  return s.replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}
// Gutenberg text is hard-wrapped at ~70 columns; reflow single newlines, keep blank lines as paragraph breaks,
// and turn the [[...]] marks written by build_reveal_validation_set.py into highlights.
function passage(text, cls) {
  return text.split(/\n\s*\n/).map(p => {
    const h = esc(p.replace(/\s*\n\s*/g, " ")).replace(/\[\[(.+?)\]\]/g, `<mark class="${cls}">$1</mark>`);
    return `<p>${h}</p>`;
  }).join("");
}
function aboutChars(n) {
  if (n < 1000) return "just before the reveal chapter";
  return `about ${Math.round(n / 1000).toLocaleString()},000 characters before the reveal chapter`;
}

function renderSide() {
  $("side").innerHTML = MINE.map((ev, i) => {
    const mark = complete(ev.key) ? '<span class="tick">✓</span>' : started(ev.key) ? '<span class="part">…</span>' : "";
    return `<button data-i="${i}" class="${i === CUR ? "cur" : ""}"><span>${i + 1}<span class="t">. ${esc(ev.book.split("(")[0].trim())}</span></span>${mark}</button>`;
  }).join("");
  $("side").querySelectorAll("button").forEach(b => b.onclick = () => go(+b.dataset.i));
  const done = MINE.filter(ev => complete(ev.key)).length;
  $("progress").textContent = `${done} / ${MINE.length} done`;
}

function qBlock(key, q) {
  const cur = (LABELS[key] || {})[q.id];
  const opts = q.opts.map(([v, lab]) =>
    `<label><input type="radio" name="${q.id}" value="${v}" ${cur === v ? "checked" : ""}> ${lab}</label>`).join("");
  return `<div class="q"><div class="prompt">${q.prompt}</div><div class="opts">${opts}</div></div>`;
}

function renderItem() {
  const ev = MINE[CUR], key = ev.key, L = LABELS[key] || {};
  const alias = ev.alias.map(a => `“${esc(a)}”`).join(" or ");
  const pre = ev.pre.map((p, i) =>
    `<div class="dist">Passage ${i + 1}, ${aboutChars(p.chars_before_cutoff)}</div><div class="passage">${passage(p.window, "")}</div>`).join("");
  $("item").innerHTML = `
    <div class="card">
      <div class="muted small">Item ${CUR + 1} of ${MINE.length}</div>
      <h2>${esc(ev.book)}</h2>
      <div class="who-is"><span>Alias: <b>${alias}</b></span><span>Hidden identity: <b>${esc(ev.identity)}</b></span></div>
      ${qBlock(key, QUESTIONS[0])}
    </div>
    <div class="card">
      <h3>1 · The reveal</h3>
      <div class="muted small">The highlighted sentence is where the book is taken to reveal the identity.</div>
      <div class="passage">${passage(ev.reveal, "rev")}</div>
      ${qBlock(key, QUESTIONS[1])}${qBlock(key, QUESTIONS[2])}
    </div>
    <div class="card">
      <h3>2 · Before the reveal</h3>
      <div class="muted small">Passages a reader sees earlier in the book. The alias is highlighted.</div>
      ${pre}
      ${qBlock(key, QUESTIONS[3])}
    </div>
    <div class="card">
      <h3>3 · The item</h3>
      ${qBlock(key, QUESTIONS[4])}
      <div class="q"><div class="prompt">Notes (optional)</div><textarea id="note" placeholder="Anything odd about this item">${esc(L.note || "")}</textarea></div>
    </div>
    <div class="nav">
      <button id="prev" ${CUR === 0 ? "disabled" : ""}>← Previous</button>
      <span class="status muted" id="status"></span>
      <button id="next" class="primary">${CUR === MINE.length - 1 ? "Finish" : "Next →"}</button>
    </div>`;
  $("item").querySelectorAll('input[type="radio"]').forEach(r => r.onchange = () => setAnswer(key, r.name, r.value));
  $("note").oninput = e => setAnswer(key, "note", e.target.value);
  $("prev").onclick = () => go(CUR - 1);
  $("next").onclick = () => {
    if (!complete(key)) { $("status").textContent = "Please answer all five questions first."; return; }
    if (CUR < MINE.length - 1) go(CUR + 1); else finish();
  };
  window.scrollTo({ top: 0 });
}

function setAnswer(key, field, value) {
  const row = LABELS[key] || (LABELS[key] = { event_id: MINE[CUR].event_id });
  row[field] = value;
  row.updated_at = new Date().toISOString();
  save();
  renderSide();
}

function go(i) { CUR = Math.max(0, Math.min(MINE.length - 1, i)); renderSide(); renderItem(); }

function finish() {
  const left = MINE.filter(ev => !complete(ev.key)).length;
  $("status").textContent = left ? `${left} item(s) still incomplete (see the list on the left).` : "All done. Press “Export my labels” and send the file to Adhyan.";
}

function exportLabels() {
  const done = MINE.filter(ev => complete(ev.key)).length;
  if (done < MINE.length && !confirm(`Only ${done} of ${MINE.length} items are complete. Export anyway?`)) return;
  const out = { app: "reveal-check", version: DATA.version, seed: DATA.seed, annotator: ME,
    exported_at: new Date().toISOString(), assigned: MINE.map(ev => ev.key), labels: LABELS };
  const blob = new Blob([JSON.stringify(out, null, 1)], { type: "application/json" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `labels_${ME}.json`;
  a.click();
  URL.revokeObjectURL(a.href);
}

function begin(name) {
  ME = name;
  MINE = DATA.events.filter(ev => ev.annotators.includes(name));
  load();
  const firstOpen = MINE.findIndex(ev => !complete(ev.key));
  CUR = firstOpen < 0 ? 0 : firstOpen;
  $("start").hidden = true; $("app").hidden = false; $("barRight").hidden = false;
  $("who").textContent = name;
  go(CUR);
}

function importFile(file) {
  const r = new FileReader();
  r.onload = () => {
    try {
      const d = JSON.parse(r.result);
      if (d.version !== DATA.version || !DATA.annotators.includes(d.annotator)) throw new Error("wrong file");
      ME = d.annotator;
      localStorage.setItem(storeKey(), JSON.stringify(d.labels || {}));
      begin(d.annotator);
    } catch { alert("This file is not a Reveal Check export for this item set."); }
  };
  r.readAsText(file);
}

async function init() {
  DATA = await (await fetch("events.json", { cache: "no-cache" })).json();
  $("names").innerHTML = DATA.annotators.map(n => `<button class="primary" data-n="${n}">I am ${n}</button>`).join("");
  $("names").querySelectorAll("button").forEach(b => b.onclick = () => begin(b.dataset.n));
  $("importFile").onchange = e => e.target.files[0] && importFile(e.target.files[0]);
  const openGuide = e => { e && e.preventDefault(); $("guide").showModal(); };
  $("guideBtn").onclick = openGuide; $("guideLink").onclick = openGuide;
  $("guideClose").onclick = () => $("guide").close();
  $("exportBtn").onclick = exportLabels;
}
init();
