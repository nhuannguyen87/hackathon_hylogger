"use client";

// The "Valuable minerals" map panel, shared by Explore and the Minerals tab:
// what holes were drilled FOR (GSWA catalog commodities - Gold, Silver... -
// most valuable first) and every mineral HyLogger DETECTED (rarest first,
// each with its specific minerals). Choosing one filters the page's holes and
// shades them light -> dark by how much of it each holds: a detected mineral
// by its share of the logged metres, a commodity by its best 5 m lab-assay
// grade (log scale). A hole with no assays for it stays grey - never pale.

import { Fragment, useCallback, useEffect, useMemo, useState } from "react";
import { getMinerals, getRichness } from "@/lib/api";
import MapPanel from "./MapPanel";

export const holeCount = (n) => `${n} ${n === 1 ? "hole" : "holes"}`;
const UNIT = {
  group: "average share of the hole's logged metres",
  species: "share of the hole's logged metres where it is the dominant mineral",
  commodity: "richest 5 m of the hole's lab assays, ppm (= g/t), log scale",
};
// GSWA's FAQ: a gold ore/waste cut-off may be 10 ppb over a 5 m average - the
// palest blue starts there, so "below cut-off" never looks like ore
const CUTOFF_PPM = { AU: 0.01 };
const NO_DATA = "#8c9aa5";

// Sequential blue, light -> dark (the dataviz reference ramp, steps 100-700)
const RAMP = ["#cde2fb", "#86b6ef", "#3987e5", "#1c5cab", "#0d366b"];
const rgb = (hex) => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16));
function shade(t) {
  const x = Math.min(1, Math.max(0, t)) * (RAMP.length - 1);
  const i = Math.min(RAMP.length - 2, Math.floor(x));
  const [a, b] = [rgb(RAMP[i]), rgb(RAMP[i + 1])];
  return `#${a.map((v, k) => Math.round(v + (b[k] - v) * (x - i)).toString(16).padStart(2, "0")).join("")}`;
}
// ponytail: the darkest step is the 95th percentile, so one extreme hole
// doesn't leave every other hole pale; holes above it share the darkest blue
const pct = (sorted, q) => sorted[Math.floor(q * (sorted.length - 1))];
/** How a value maps to 0..1 on the ramp: linear % for minerals; log ppm for
 * assays, from the cut-off (or the 5th percentile) up to the 95th. */
function scaleOf(values, choice) {
  const sorted = values.filter((v) => v > 0).sort((a, b) => a - b);
  const top = pct(sorted, 0.95) || 1;
  if (choice?.kind !== "commodity") return { low: 0, top, t: (v) => v / top };
  const low = Math.min(CUTOFF_PPM[choice.code] ?? pct(sorted, 0.05) ?? top / 100, top / 10);
  return { low, top, log: true, t: (v) => (v <= low ? 0 : Math.log10(v / low) / Math.log10(top / low)) };
}

/** The chosen mineral, the getHoles() filter for it, and shadeHoles(holes):
 * richest first, each with `richness` (% or ppm; null = no data) and
 * `colour` - unchanged when nothing is chosen. */
export function useValuableMinerals() {
  const [minerals, setMinerals] = useState(null);
  const [choice, setChoice] = useState(null); // {kind: "commodity" | "group" | "species", code, name, group?}
  // {choice, values: {hole_id: % or ppm}} - kept with the choice it was fetched
  // for, so a deselect or a late answer for an earlier choice never paints
  const [loaded, setLoaded] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    getMinerals().then(setMinerals).catch((err) => setError(err.message));
  }, []);

  useEffect(() => {
    if (choice) getRichness(choice.kind, choice.code).then((values) => setLoaded({ choice, values })).catch((err) => setError(err.message));
  }, [choice]);
  const richness = loaded && loaded.choice === choice ? loaded.values : null;

  const scale = useMemo(() => scaleOf(Object.values(richness || {}), choice), [richness, choice]);
  const shadeHoles = useCallback((holes) => (!richness ? holes : holes
    .map((hole) => {
      const value = richness[hole.hole_id] ?? null;
      return { ...hole, richness: value, colour: value == null ? NO_DATA : shade(scale.t(value)) };
    })
    .sort((a, b) => (b.richness ?? -1) - (a.richness ?? -1))), [richness, scale]);

  const choose = (next) => setChoice((now) => (now?.kind === next.kind && now.code === next.code ? null : next));
  const filter = useMemo(() => (choice ? { [choice.kind]: choice.code } : {}), [choice]);
  return { minerals, error, choice, choose, filter, richness, scale, shadeHoles };
}

/** The panel itself; pass it everything useValuableMinerals() returns. */
export default function ValuableMinerals({ minerals, error, choice, choose, richness, scale }) {
  const [search, setSearch] = useState("");
  const needle = search.trim().toLowerCase();
  const match = (...texts) => !needle || texts.some((t) => t.toLowerCase().includes(needle));
  const is = (kind, code) => choice?.kind === kind && choice.code === code;
  const openGroup = choice?.kind === "group" ? choice.code : choice?.group;

  return (
    <MapPanel className="grow" label="valuable minerals list" head={<span className="section-title" style={{ margin: 0 }}>Valuable minerals</span>}>
      <input
        type="search"
        placeholder="Search a mineral (gold, chlorite…)"
        value={search}
        onChange={(event) => setSearch(event.target.value)}
        style={{ marginTop: 8 }}
      />
      {choice && <Chosen choice={choice} richness={richness} scale={scale} onClear={() => choose(choice)} />}
      <div className="hole-list">
        {error && <div className="error" style={{ margin: 12 }}>{error}</div>}
        {!minerals && !error && <p className="hint" style={{ padding: 12 }}>Loading…</p>}
        {minerals && (
          <>
            <p className="mineral-section" title="From the GSWA catalog's Commodity column. HyLogger itself can't see metals like gold or silver.">
              Drilled for · GSWA catalog · most valuable first
            </p>
            {minerals.commodities.filter((c) => match(c.name, c.code)).map((c) => (
              <MineralRow
                key={c.code} name={c.name} detail={`${c.code} · ${holeCount(c.holes)}`}
                selected={is("commodity", c.code)}
                onClick={() => choose({ kind: "commodity", code: c.code, name: c.name })}
              />
            ))}

            <p className="mineral-section" title={`A mineral counts once it makes up at least ${minerals.present_pct}% of one metre (SWIR or TIR).`}>
              Detected by HyLogger · rarest first
            </p>
            {minerals.groups
              .filter((g) => match(g.name, g.code, ...g.species.map((s) => s.name)))
              .map((g) => (
                <Fragment key={g.code}>
                  <MineralRow
                    name={g.name} detail={`${g.code} · ${holeCount(g.holes)}`}
                    selected={is("group", g.code)}
                    onClick={() => choose({ kind: "group", code: g.code, name: g.name })}
                  />
                  {(openGroup === g.code || (needle && !match(g.name, g.code))) && g.species
                    .filter((s) => openGroup === g.code || match(s.name))
                    .map((s) => (
                      <MineralRow
                        key={s.name} sub name={s.name} detail={holeCount(s.holes)}
                        selected={is("species", s.name)}
                        onClick={() => choose({ kind: "species", code: s.name, name: s.name, group: g.code })}
                      />
                    ))}
                </Fragment>
              ))}
          </>
        )}
      </div>
    </MapPanel>
  );
}

/** What's chosen, a way back to every hole, and how the shading reads -
 * kept to a few lines so the list below always has room to pick another. */
function Chosen({ choice, richness, scale, onClear }) {
  const shaded = richness && Object.keys(richness).length > 0;
  const name = choice.name.toLowerCase();
  const note = choice.kind !== "commodity" || !richness ? null
    : shaded ? "Shaded by company lab assays; grey: no assays for it."
      : `No lab assay measures ${name}; holes are listed by what they were drilled for.`;
  return (
    <div className="chosen">
      <div className="chosen-row">
        <span className="chosen-name" title={choice.name}>{choice.name}</span>
        <button type="button" className="chosen-clear" onClick={onClear} aria-label={`Clear ${choice.name} and show every hole`}>
          × Clear
        </button>
      </div>
      {shaded && <Scale choice={choice} scale={scale} />}
      {note && <p className="chosen-note">{note}</p>}
    </div>
  );
}

function Scale({ choice, scale }) {
  const unit = choice.kind === "commodity" ? " ppm" : "%";
  const number = (v) => (v >= 100 ? Math.round(v) : Number(v.toPrecision(2)));
  const meaning = `Darker = more ${choice.name}: ${UNIT[choice.kind]}`;
  return (
    <div className="scale-row" title={meaning}>
      <span>{scale.log && "≤"}{number(scale.low)}{unit}</span>
      <span
        className="scale-bar"
        role="img"
        aria-label={`${meaning}. Pale blue ${number(scale.low)}${unit} to dark blue ${number(scale.top)}${unit} or more`}
        style={{ background: `linear-gradient(to right, ${RAMP.join(", ")})` }}
      />
      <span>{number(scale.top)}{unit}+</span>
    </div>
  );
}

function MineralRow({ name, detail, selected, sub, onClick }) {
  return (
    <button
      type="button"
      className={`hole-row mineral-row ${sub ? "sub" : ""} ${selected ? "selected" : ""}`}
      aria-pressed={selected}
      onClick={onClick}
    >
      <span className="mineral-name">{name}</span>
      <span className="len">{detail}</span>
    </button>
  );
}
