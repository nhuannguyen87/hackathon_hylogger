"use client";

// The Minerals tab's right side: a hole's card (every mineral in it, its lab
// assays, its GSWA documents) or the holes behind the chosen mineral. The
// HyLogger vocabulary lives in the How to read guide.

import { useEffect, useState } from "react";
import { getAssays, getHoleMinerals } from "@/lib/api";
import { mineralColour } from "@/config";
import { openGuide } from "./HowToRead";

export default function MineralDetail({ choice, holes, shaded, holeId, onSelect }) {
  return (
    <aside className="detail wide">
      {holeId ? (
        <HoleCard holeId={holeId} choice={choice} onBack={() => onSelect(null)} />
      ) : choice ? (
        <ChoiceHoles choice={choice} holes={holes} shaded={shaded} onSelect={onSelect} />
      ) : (
        <div className="hint">
          <p style={{ marginTop: 0 }}>Pick a mineral on the left, or a hole on the map.</p>
          <button type="button" className="link-button" onClick={openGuide}>What do the colours and terms mean?</button>
        </div>
      )}
    </aside>
  );
}

function ChoiceHoles({ choice, holes, shaded, onSelect }) {
  return (
    <>
      <h2 style={{ margin: "0 0 4px", fontSize: 18 }}>{choice.name}</h2>
      <p className="hint" style={{ marginBottom: 10 }}>
        {choice.kind === "commodity"
          ? `${holes.length} holes drilled for ${choice.name.toLowerCase()} (GSWA catalog), richest first by their best 5 m lab-assay grade (ppm = g/t); holes with no assays for it last. HyLogger itself can't see metals.`
          : choice.kind === "group"
            ? `${holes.length} holes where HyLogger detected ${choice.code} in at least one metre, richest first (% = its average share of the hole's logged metres).`
            : `${holes.length} holes where ${choice.name} was the dominant mineral in at least one metre, richest first (% = share of the logged metres).`}
      </p>
      <div style={{ margin: "0 -16px", borderTop: "1px solid var(--line)" }}>
        {holes.map((hole) => (
          <button key={hole.hole_id} type="button" className="hole-row" onClick={() => onSelect(hole.hole_id)}>
            <span className="id">
              {shaded && <span className="legend-swatch" style={{ display: "inline-block", background: hole.colour, marginRight: 6, verticalAlign: -1 }} />}
              {hole.hole_id}
            </span>
            <span className="len">
              {shaded && `${richnessLabel(hole.richness, choice.kind)} · `}{Math.round(hole.drawn_length_m || 0)} m
            </span>
          </button>
        ))}
      </div>
    </>
  );
}

function HoleCard({ holeId, choice, onBack }) {
  const [card, setCard] = useState(null);
  const [assays, setAssays] = useState(null);
  useEffect(() => {
    setCard(null);
    setAssays(null);
    getHoleMinerals(holeId).then(setCard).catch((err) => setCard({ error: err.message }));
    getAssays(holeId).then(setAssays).catch(() => setAssays(null));
  }, [holeId]);

  return (
    <>
      {choice && (
        <button type="button" className="link-button" onClick={onBack}>← {choice.name} holes</button>
      )}
      <h2 style={{ margin: "4px 0 6px", fontSize: 20 }} className="mono">{holeId}</h2>
      {!card && <p className="hint">Loading…</p>}
      {card?.error && <div className="error">{card.error}</div>}
      {card && !card.error && <HoleCardBody card={card} assays={assays} />}
    </>
  );
}

function HoleCardBody({ card, assays }) {
  return (
    <>
      {card.commodities.length > 0 && (
        <p style={{ margin: "0 0 10px" }}>
          <span className="hint">Drilled for </span>
          {card.commodities.map((c) => (
            <span key={c.code} className="badge" style={{ marginRight: 4 }}>{c.name}</span>
          ))}
        </p>
      )}

      <table className="facts">
        <tbody>
          <tr><td>Project</td><td>{card.project || "–"}</td></tr>
          <tr><td>Location</td><td>{card.location || "–"}</td></tr>
          <tr><td>Sample type</td><td>{card.sample_type || "–"}</td></tr>
          <tr title="How far a geologist has checked the mineral interpretation - see Processing level below">
            <td>Processing level</td>
            <td>{card.process_level ? (/^\d+$/.test(card.process_level) ? `Level ${card.process_level}` : card.process_level) : "–"}</td>
          </tr>
          <tr><td>Logged here</td><td>{card.logged_metres} m</td></tr>
        </tbody>
      </table>

      <p className="section-title">GSWA documents</p>
      {!card.in_catalog && <p className="hint">This hole isn&apos;t in the GSWA HyLogger catalog by name.</p>}
      <ul className="doc-links">
        {card.links.map((l) => (
          <li key={l.key}>
            {l.url
              ? <a href={l.url} target="_blank" rel="noopener noreferrer">{l.label} ↗</a>
              : <span className="hint">{l.label} · not available</span>}
          </li>
        ))}
      </ul>

      <p className="section-title">Lab assays · best 5 m</p>
      {!assays ? <p className="hint">Loading…</p> : !Object.keys(assays.best).length ? (
        <p className="hint">No company lab assays for this hole in GSWA&apos;s interim package.</p>
      ) : (
        <>
          <table className="mineral-table">
            <thead><tr><th>Element</th><th>ppm (g/t)</th><th>depth m</th></tr></thead>
            <tbody>
              {Object.entries(assays.best).slice(0, 8).map(([element, b]) => (
                <tr key={element}>
                  <td>{element}</td>
                  <td>{b.ppm === 0 ? "below detection" : b.ppm}</td>
                  <td>{b.from_m}–{b.to_m}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="hint" style={{ marginTop: -10, marginBottom: 16 }} title={assays.source}>
            Richest stretch of at least 5 m, averaged by interval length. Company results reported to WAMEX;
            GSWA did no quality control{assays.cutoff_ppm.Au ? " · gold cut-off guide: 0.01 ppm (10 ppb) over 5 m" : ""}.
          </p>
        </>
      )}

      <p className="section-title">Every mineral HyLogger detected</p>
      {card.groups.length === 0 ? (
        <p className="hint">
          No HyLogger mineral log is loaded for this hole - the Summary Mineral Logs and Summary Histogram links above have GSWA&apos;s own.
        </p>
      ) : (
        <>
          <p className="hint" style={{ marginBottom: 6 }}>
            % = average share of the {card.logged_metres} logged metres (trace = under 0.05%, – = not seen) ·
            m = metres where it is at least {card.present_pct}%.
            TIR also sees quartz and feldspar, which SWIR can&apos;t.
          </p>
          <table className="mineral-table">
            <thead>
              <tr><th>Mineral</th><th>SWIR</th><th>TIR</th><th>m</th></tr>
            </thead>
            <tbody>
              {card.groups.map((g) => (
                <tr key={g.code} title={g.code}>
                  <td>
                    <span className="legend-swatch" style={{ background: mineralColour(g.code), marginRight: 6 }} />
                    {g.name}
                  </td>
                  <td>{share(g.swir_pct)}</td>
                  <td>{share(g.tir_pct)}</td>
                  <td>{Math.max(g.swir_metres, g.tir_metres)}</td>
                </tr>
              ))}
            </tbody>
          </table>

          {card.species.length > 0 && (
            <>
              <p className="section-title">Specific minerals (SWIR)</p>
              <table className="mineral-table">
                <thead><tr><th>Mineral</th><th>Group</th><th>m dominant</th></tr></thead>
                <tbody>
                  {card.species.map((s) => (
                    <tr key={s.name}><td>{s.name}</td><td>{s.group}</td><td>{s.metres}</td></tr>
                  ))}
                </tbody>
              </table>
            </>
          )}
        </>
      )}
    </>
  );
}

// a hole's richness in the list: % of a mineral, or ppm of a commodity's best 5 m
function richnessLabel(value, kind) {
  if (value == null) return "no assays";
  if (kind === "commodity") return value === 0 ? "below detection" : `${value} ppm`;
  return value ? `${value}%` : "<0.1%";
}

// null: that sensor never saw it · 0: seen, but only in traces
const share = (pct) => (pct == null ? "–" : pct === 0 ? "trace" : `${pct}%`);
