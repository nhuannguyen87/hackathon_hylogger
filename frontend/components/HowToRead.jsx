"use client";

// "How to read this": what every colour, mark and term on the site means, in
// plain words (wording follows GSWA's hackathon FAQ and vocabulary). Three
// tabs - the marks, drawn on a small specimen strip like a field-guide plate;
// the terms a decision hangs on, grouped by the question they answer; and all
// of GSWA's HyLogger vocabulary, searchable. Opens on a first visit; the top
// bar's "How to read" button (or openGuide()) brings it back.

import { useEffect, useRef, useState } from "react";
import { getVocab } from "@/lib/api";
import { ANOMALY_COLOUR, LOW_CONFIDENCE_COLOUR, MINERAL_COLOURS } from "@/config";

const SEEN = "howto-seen";
export const OPEN_EVENT = "howto:open";
export const openGuide = () => window.dispatchEvent(new Event(OPEN_EVENT));

const GOLD = "#c9a227";
const SUSPECT = "#ff8a7a";

// what each numbered callout on the specimen means
const MARKS = [
  ["Mineral band", "The strongest SWIR mineral in that metre, coloured by group. It is never the whole rock: quartz and feldspar only show in TIR, so hover a band to see both mixes."],
  ["Grey hatching", "That metre can't be trusted: weak signal, poor fit or readings that disagree. Hover to see which. A gap stays visible - nothing is filled in."],
  ["Amber tick", "A statistically unusual metre. Worth a closer look; it is not proof of ore, nor of bad data."],
  ["Gold bars", "Company lab assays beside the minerals at the same depth, on a log scale - longer is richer."],
  ["Hatched stub", "The lab measured it and found less than it can detect. A measured zero, unlike a gap."],
  ["Red question mark", "A value no rock can hold, usually a unit mix-up in the report. Shown, but left out of every average."],
  ["Dashed line", "GSWA's guide cut-off for gold: 10 ppb averaged over 5 m."],
];

const FINDING = [
  ["The map", "Coloured dots are holes with a HyLogger mineral log, in their most common mineral's colour. Faint dots have no log yet. Click a dot or a row in the list to open a hole."],
  ["Valuable minerals", "Pick a commodity (gold, copper…) or a mineral HyLogger detected to keep only the holes that have it. Darker is richer, grey means no data; pick it again to clear. Click a hole for every mineral in it."],
  ["Logged rock", "The narrow middle column on a hole's card is the rock the company logged, on the same depth scale as the minerals. Dark grey means only the company's own code was recorded: GSWA hasn't harmonised it, so the site doesn't guess."],
  ["Processing level", "Each hole is Level 1 (interpreted automatically) or Level 2 (a geologist refined it - more accurate labels). The site reads Level 2 results wherever GSWA has released them."],
  ["Take it further", "Download any hole as a CSV, one row per metre with its assays, or copy a QGIS link to open the same holes and 3D logs in QGIS."],
];

// the decision terms, grouped by the question each one answers
const GROUPS = [
  ["What the scanner sees", ["SWIR", "TIR"]],
  ["How a mineral call is made", ["TSA", "jCLST", "sTSAV", "Grp", "Min", "Wt"]],
  ["How far to trust a reading", ["Error", "Signal to Noise Ratio", "Invalid", "Aspectral", "Mask"]],
  ["Who checked it", ["Processing level", "Level 1", "Level 2", "Level 3"]],
  ["Chemistry clues", ["2200nm wavelength", "2250nm wavelength", "11300nm height", "OTHER-ALOH", "Summary histogram"]],
];

const TABS = ["Reading the site", "Terms for decisions", "Glossary"];

export default function HowToRead() {
  const [open, setOpen] = useState(false);
  const [tab, setTab] = useState(0);
  const [vocab, setVocab] = useState(null);
  const closeRef = useRef(null);

  useEffect(() => {
    try {
      if (!localStorage.getItem(SEEN)) setOpen(true);
    } catch {
      setOpen(true); // storage blocked: show it, it's one click to close
    }
    const show = () => setOpen(true);
    window.addEventListener(OPEN_EVENT, show);
    return () => window.removeEventListener(OPEN_EVENT, show);
  }, []);

  useEffect(() => {
    if (!open) return undefined;
    closeRef.current?.focus();
    if (!vocab) getVocab().then(setVocab).catch(() => setVocab({ key: [], all: [] }));
    const onKey = (event) => event.key === "Escape" && close();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]); // eslint-disable-line react-hooks/exhaustive-deps

  function close() {
    setOpen(false);
    try {
      localStorage.setItem(SEEN, "1");
    } catch { /* fine - it just shows again next visit */ }
  }

  if (!open) return null;
  return (
    <div className="guide-backdrop" onMouseDown={(event) => event.target === event.currentTarget && close()}>
      <div className="guide" role="dialog" aria-modal="true" aria-labelledby="guide-title">
        <header className="guide-head">
          <div>
            <h2 id="guide-title">How to read HyLogger Explorer</h2>
            <p>What every colour, mark and term means, in plain words.</p>
          </div>
          <button ref={closeRef} type="button" className="guide-x" onClick={close} aria-label="Close the guide">×</button>
        </header>

        <div className="guide-tabs" role="tablist">
          {TABS.map((name, i) => (
            <button key={name} type="button" role="tab" aria-selected={tab === i} onClick={() => setTab(i)}>
              {name}
              {i === 1 && vocab ? <span className="guide-count">{vocab.key.length}</span> : null}
              {i === 2 && vocab ? <span className="guide-count">{vocab.all.length}</span> : null}
            </button>
          ))}
        </div>

        <div className="guide-body">
          {tab === 0 && <ReadingTheSite />}
          {tab === 1 && <DecisionTerms vocab={vocab} />}
          {tab === 2 && <Glossary vocab={vocab} />}
        </div>

        <footer className="guide-foot">
          <span>From GSWA&apos;s HyLogger vocabulary and hackathon FAQ.</span>
          <button type="button" className="guide-done" onClick={close}>Got it</button>
        </footer>
      </div>
    </div>
  );
}

function ReadingTheSite() {
  return (
    <>
      <section className="specimen">
        <Specimen />
        <ol className="marks">
          {MARKS.map(([title, text]) => (
            <li key={title}><strong>{title}</strong><span>{text}</span></li>
          ))}
        </ol>
      </section>
      <h3 className="guide-h">Finding and comparing holes</h3>
      <dl className="finding">
        {FINDING.map(([title, text]) => (
          <div key={title}><dt>{title}</dt><dd>{text}</dd></div>
        ))}
      </dl>
    </>
  );
}

/** A miniature strip log + assay track, numbered to match MARKS. */
function Specimen() {
  const bands = [
    [0, 52, MINERAL_COLOURS.CHLORITE], [52, 92, MINERAL_COLOURS["WHITE-MICA"]], [92, 132, "hatch"],
    [132, 196, MINERAL_COLOURS["DARK-MICA"]], [196, 250, MINERAL_COLOURS.AMPHIBOLE], [250, 300, MINERAL_COLOURS.CARBONATE],
  ];
  const assays = [[0, 18, 22], [18, 36, 34], [36, 54, "bdl"], [54, 80, 46], [80, 110, 62], [110, 140, 30],
    [140, 168, 78], [168, 196, 54], [196, 224, "?"], [224, 262, 26], [262, 300, 38]];
  const callout = (n, x, y) => (
    <g key={n}>
      <circle cx={x} cy={y} r="8.5" fill="var(--bg)" stroke="var(--accent)" />
      <text x={x} y={y + 3.5} textAnchor="middle" fontSize="10" fontWeight="700" fill="var(--accent)">{n}</text>
    </g>
  );
  return (
    <svg className="specimen-svg" viewBox="0 0 172 320" role="img"
         aria-label="Example strip log with numbered marks: mineral bands, grey hatching, an amber tick, gold assay bars, a below-detection stub, a red question mark and a dashed cut-off line">
      <defs>
        <pattern id="g-unc" width="6" height="6" patternTransform="rotate(45)" patternUnits="userSpaceOnUse">
          <rect width="6" height="6" fill={LOW_CONFIDENCE_COLOUR} />
          <line x1="0" y1="0" x2="0" y2="6" stroke="#5a6672" strokeWidth="2" />
        </pattern>
        <pattern id="g-bdl" width="4" height="4" patternTransform="rotate(45)" patternUnits="userSpaceOnUse">
          <line x1="0" y1="0" x2="0" y2="4" stroke="#8c9aa5" strokeWidth="1.5" />
        </pattern>
      </defs>
      <g transform="translate(24, 10)">
        {bands.map(([a, b, fill]) => (
          <rect key={a} x={0} y={a} width={30} height={b - a} fill={fill === "hatch" ? "url(#g-unc)" : fill} />
        ))}
        <rect x={0} y={0} width={30} height={300} fill="none" stroke="var(--line)" />
        <rect x={33} y={150} width={6} height={22} fill={ANOMALY_COLOUR} />
        <line x1={50} y1={0} x2={50} y2={300} stroke="var(--line)" />
        {assays.map(([a, b, v]) => (v === "bdl"
          ? <rect key={a} x={50} y={a} width={7} height={b - a} fill="url(#g-bdl)" />
          : v === "?"
            ? <text key={a} x={53} y={(a + b) / 2 + 5} fill={SUSPECT} fontSize="14" fontWeight="700">?</text>
            : <rect key={a} x={50} y={a + 1} width={v} height={b - a - 2} fill={GOLD} />))}
        <line x1={78} y1={0} x2={78} y2={300} stroke="var(--text-dim)" strokeDasharray="3 3" />
      </g>
      {callout(1, 12, 34)}
      {callout(2, 12, 122)}
      {callout(3, 76, 171)}
      {callout(4, 148, 164)}
      {callout(5, 94, 55)}
      {callout(6, 106, 220)}
      {callout(7, 102, 296)}
    </svg>
  );
}

function DecisionTerms({ vocab }) {
  if (!vocab) return <p className="hint">Loading GSWA&apos;s vocabulary…</p>;
  const byLabel = Object.fromEntries(vocab.key.map((t) => [t.label, t]));
  return GROUPS.map(([question, labels]) => {
    const terms = labels.map((label) => byLabel[label]).filter(Boolean);
    if (!terms.length) return null;
    return (
      <section key={question} className="term-group">
        <h3 className="guide-h">{question}</h3>
        {terms.map((t) => (
          <article key={t.slug} className="term-entry">
            <h4>{t.label}{t.alt_labels && <span>{t.alt_labels}</span>}</h4>
            <p>{t.decision}</p>
            {t.definition && (
              <details>
                <summary>GSWA definition</summary>
                <p>{t.definition}</p>
              </details>
            )}
          </article>
        ))}
      </section>
    );
  });
}

function Glossary({ vocab }) {
  const [search, setSearch] = useState("");
  if (!vocab) return <p className="hint">Loading GSWA&apos;s vocabulary…</p>;
  const needle = search.trim().toLowerCase();
  const found = vocab.all.filter((t) => !needle
    || `${t.label} ${t.alt_labels} ${t.definition}`.toLowerCase().includes(needle));
  return (
    <>
      <div className="glossary-search">
        <input type="search" placeholder={`Search ${vocab.all.length} terms (e.g. TSA, aspectral, level)`} value={search}
               onChange={(event) => setSearch(event.target.value)} aria-label="Search the glossary" />
        <span className="hint">{found.length === vocab.all.length ? "All terms" : `${found.length} found`}</span>
      </div>
      <div className="glossary">
        {found.map((t) => (
          <details key={t.slug} className="glossary-term">
            <summary>{t.label}{t.alt_labels && <span>{t.alt_labels}</span>}</summary>
            <p>{t.definition || "No definition in GSWA's workbook yet."}</p>
          </details>
        ))}
        {!found.length && <p className="hint">No term matches “{search}”. Try a shorter word.</p>}
      </div>
    </>
  );
}
