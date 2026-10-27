// Prefix Check: static annotation app for the human validation of the pipeline-disclosure labels.
// No backend on purpose (plain files on Vercel): answers live in localStorage and leave the browser only through
// "Export my labels". Part 1 is locked once the system output is shown, so the unaided judgement cannot be edited
// after seeing what the system served.
"use strict";

const Q_A = [
  { id: "q0", prompt: "Q0. Before reading: have you read this book or do you know its plot?", opts: [["yes", "Yes"], ["no", "No"]] },
  { id: "q1", prompt: "Q1. From these passages only, what gender does the text establish for the character?", opts: [["male", "Male"], ["female", "Female"], ["undetermined", "Not determined"]] },
  { id: "q2", prompt: "Q2. How sure are you?", opts: [["clear", "Clear"], ["suspect", "Suspect"], ["none", "No usable cue"]] },
];
const Q_B_VALUE = [
  { id: "q3", prompt: "Q3. Is the served value backed up by the passages?", opts: [["supported", "Supported"], ["unsupported", "Unsupported (text does not settle it)"], ["contradicted", "Contradicted (text points the other way)"]] },
  { id: "q4", prompt: "Q4. Would a careful first-time reader of these passages plausibly hold this value?", opts: [["yes", "Yes"], ["no", "No"]] },
];
const Q_B_NONE = [
  { id: "q3", prompt: "Q3. No value was served. Did the passages settle a value that could have been served?", opts: [["settled", "Yes, they settle one"], ["not_settled", "No, they do not"]] },
];

let DATA = null, ME = null, MINE = [], CUR = 0, LABELS = {};
const $ = id => document.getElementById(id);
const storeKey = () => `prefix-check:${DATA.version}:${ME}`;
const qB = ev => (ev.served ? Q_B_VALUE : Q_B_NONE);
const required = ev => Q_A.concat(qB(ev)).map(q => q.id);

function load() {
  try { LABELS = JSON.parse(localStorage.getItem(storeKey()) || "{}"); } catch { LABELS = {}; }
}
function save() {
  try { localStorage.setItem(storeKey(), JSON.stringify(LABELS)); } catch { /* private mode: export still works */ }
}
const partA = key => Q_A.every(q => LABELS[key] && LABELS[key][q.id]);
const complete = ev => required(ev).every(q => LABELS[ev.case] && LABELS[ev.case][q]);
const started = ev => LABELS[ev.case] && Q_A.some(q => LABELS[ev.case][q.id]);

function esc(s) {
  return String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}
// Highlight the character's own mention inside the passage so the reader can see which person each cue is about.
function passage(p) {
  const t = esc(p.text), m = esc(p.mention);
  return m ? t.replace(m, `<mark class="rev">${m}</mark>`) : t;
}

function renderSide() {
  $("side").innerHTML = MINE.map((ev, i) => {
    const mark = complete(ev) ? '<span class="tick">✓</span>' : started(ev) ? '<span class="part">…</span>' : "";
    return `<button data-i="${i}" class="${i === CUR ? "cur" : ""}"><span>${i + 1}<span class="t">. ${esc(ev.book)}</span></span>${mark}</button>`;
  }).join("");
  $("side").querySelectorAll("button").forEach(b => b.onclick = () => go(+b.dataset.i));
  $("progress").textContent = `${MINE.filter(complete).length} / ${MINE.length} done`;
}

function qBlock(key, q, locked) {
  const cur = (LABELS[key] || {})[q.id];
  const opts = q.opts.map(([v, lab]) =>
    `<label><input type="radio" name="${q.id}" value="${v}" ${cur === v ? "checked" : ""} ${locked ? "disabled" : ""}> ${lab}</label>`).join("");
  return `<div class="q"><div class="prompt">${q.prompt}</div><div class="opts">${opts}</div></div>`;
}

function renderItem() {
  const ev = MINE[CUR], key = ev.case, L = LABELS[key] || {};
  const revealed = !!L.revealed;
  const names = [ev.name].concat(ev.aliases.filter(a => a !== ev.name));
  const ps = ev.passages.map((p, i) =>
    `<div class="dist">Passage ${i + 1}, chapter ${p.chapter}</div><div class="passage"><p>…${passage(p)}…</p></div>`).join("");
  const served = ev.served ? `<b>${ev.served}</b>` : "<b>no value</b> (the system left it unknown)";
  const partB = revealed ? `
    <div class="card">
      <h3>2 · System output</h3>
      <div class="who-is"><span>At chapter ${ev.cut}, the system served for ${esc(ev.name)}: ${served}</span></div>
      ${qB(ev).map(q => qBlock(key, q, false)).join("")}
      <div class="q"><label><input type="checkbox" id="ctx" ${L.needs_context ? "checked" : ""}> Needs broader context (my answers depend on events not shown here)</label></div>
      <div class="q"><div class="prompt">Notes (optional)</div><textarea id="note" placeholder="Anything odd about this item">${esc(L.note || "")}</textarea></div>
    </div>` : `
    <div class="card">
      <button id="reveal" class="primary" ${partA(key) ? "" : "disabled"}>Show system output</button>
      <span class="muted small" id="status"> Answer Q0 to Q2 first. They lock once you press this.</span>
    </div>`;
  $("item").innerHTML = `
    <div class="card">
      <div class="muted small">Item ${CUR + 1} of ${MINE.length}</div>
      <h2>${esc(ev.book)}</h2>
      <div class="who-is"><span>Character: <b>${names.map(esc).join(" / ")}</b></span><span>Cut: <b>chapter ${ev.cut}</b></span><span>Mentions up to the cut: <b>${ev.mentions}</b></span></div>
      ${qBlock(key, Q_A[0], revealed)}
    </div>
    <div class="card">
      <h3>1 · What the book shows by the cut</h3>
      <div class="muted small">${ev.passages.length} passage(s) up to the cut. The character's name is highlighted. Nothing after the cut is shown.</div>
      ${ps}
      ${qBlock(key, Q_A[1], revealed)}${qBlock(key, Q_A[2], revealed)}
    </div>
    ${partB}
    <div class="nav">
      <button id="prev" ${CUR === 0 ? "disabled" : ""}>← Previous</button>
      <span class="status muted" id="status2"></span>
      <button id="next" class="primary">${CUR === MINE.length - 1 ? "Finish" : "Next →"}</button>
    </div>`;
  $("item").querySelectorAll('input[type="radio"]').forEach(r => r.onchange = () => setAnswer(key, r.name, r.value));
  if ($("reveal")) $("reveal").onclick = () => { setAnswer(key, "revealed", true); renderItem(); };
  if ($("ctx")) $("ctx").onchange = e => setAnswer(key, "needs_context", e.target.checked);
  if ($("note")) $("note").oninput = e => setAnswer(key, "note", e.target.value);
  $("prev").onclick = () => go(CUR - 1);
  $("next").onclick = () => {
    if (!complete(ev)) { $("status2").textContent = "Please answer every question for this item first."; return; }
    if (CUR < MINE.length - 1) go(CUR + 1); else finish();
  };
  window.scrollTo({ top: 0 });
}

function setAnswer(key, field, value) {
  const row = LABELS[key] || (LABELS[key] = { case: key });
  row[field] = value;
  row.updated_at = new Date().toISOString();
  save();
  renderSide();
  // Part 1 answers can enable the reveal button without a full re-render.
  const b = $("reveal");
  if (b) b.disabled = !partA(key);
}

function go(i) { CUR = Math.max(0, Math.min(MINE.length - 1, i)); renderSide(); renderItem(); }

function finish() {
  const left = MINE.filter(ev => !complete(ev)).length;
  $("status2").textContent = left ? `${left} item(s) still incomplete (see the list on the left).` : "All done. Press “Export my labels” and send the file to Adhyan.";
}

function exportLabels() {
  const done = MINE.filter(complete).length;
  if (done < MINE.length && !confirm(`Only ${done} of ${MINE.length} items are complete. Export anyway?`)) return;
  const out = { app: "prefix-check", version: DATA.version, annotator: ME,
    exported_at: new Date().toISOString(), assigned: MINE.map(ev => ev.case), labels: LABELS };
  const blob = new Blob([JSON.stringify(out, null, 1)], { type: "application/json" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `labels_${ME}.json`;
  a.click();
  URL.revokeObjectURL(a.href);
}

function begin(name) {
  ME = name;
  MINE = DATA.cases.filter(ev => ev.annotators.includes(name));
  load();
  const firstOpen = MINE.findIndex(ev => !complete(ev));
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
    } catch { alert("This file is not a Prefix Check export for this item set."); }
  };
  r.readAsText(file);
}

async function init() {
  const openGuide = e => { e && e.preventDefault(); $("guide").showModal(); };
  $("guideBtn").onclick = openGuide; $("guideLink").onclick = openGuide;
  $("guideClose").onclick = () => $("guide").close();
  $("exportBtn").onclick = exportLabels;
  try {
    DATA = await (await fetch("cases.json", { cache: "no-cache" })).json();
  } catch {
    $("loadErr").hidden = false;
    $("loadErr").textContent = "The item file could not be loaded. Tell Adhyan.";
    return;
  }
  $("names").innerHTML = DATA.annotators.map(n => `<button class="primary" data-n="${n}">I am ${n}</button>`).join("");
  $("names").querySelectorAll("button").forEach(b => b.onclick = () => begin(b.dataset.n));
  $("importFile").onchange = e => e.target.files[0] && importFile(e.target.files[0]);
}
init();
