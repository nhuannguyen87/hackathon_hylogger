"use client";

// The right-hand panel: what this hole is, its mineral log beside its lab
// assays, and what's near it.

import { useEffect, useState } from "react";
import Link from "next/link";
import { exportUrl, getAssays, getGeology, getHole, getMeasurements, getNearby, getSpectralSample, getTrays, qgisUrl } from "@/lib/api";
import { ANOMALY_COLOUR, LOW_CONFIDENCE_COLOUR, MINERAL_COLOURS } from "@/config";
import { distinctName } from "@/lib/format";
import AssayTrack from "./AssayTrack";
import GeologyTrack, { CODE_ONLY, ROCK_FAMILIES } from "./GeologyTrack";
import QgisLink from "./QgisLink";
import StripLog from "./StripLog";
import CoreTrays from "./CoreTrays";

export default function HoleDetail({ holeId, onSelect }) {
  const [hole, setHole] = useState(null);
  const [measurements, setMeasurements] = useState([]);
  const [trays, setTrays] = useState([]);
  const [nearby, setNearby] = useState([]);
  // undefined = still checking, null = checked and nothing available, object = real data
  const [spectral, setSpectral] = useState(undefined);
  const [assays, setAssays] = useState(null);
  const [geology, setGeology] = useState(null);
  const [element, setElement] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!holeId) return;
    let cancelled = false;
    setError(null);
    setHole(null);
    setSpectral(undefined);
    setAssays(null);
    setGeology(null);
    getGeology(holeId).then((data) => !cancelled && setGeology(data)).catch(() => {});
    // its own request: assays never hold up the rest of the panel
    getAssays(holeId).then((data) => {
      if (cancelled) return;
      setAssays(data);
      setElement(data.elements[0] ?? null); // precious metals come first
    }).catch(() => !cancelled && setAssays(null));

    Promise.all([
      getHole(holeId),
      getMeasurements(holeId),
      getTrays(holeId),
      getNearby(holeId, 50),
    ])
      .then(([holeData, measurementData, trayData, nearbyData]) => {
        if (cancelled) return;
        setHole(holeData);
        setMeasurements(measurementData);
        setTrays(trayData);
        setNearby(nearbyData);
        // separate request: every hole tries this, but the 5 database5553
        // holes answer instantly while everyone else is a live NVCL lookup
        // (a few seconds) - no need to hold up the rest of the panel on it
        getSpectralSample(holeId).then((data) => !cancelled && setSpectral(data));
      })
      .catch((err) => !cancelled && setError(err.message));

    return () => {
      cancelled = true;
    };
  }, [holeId]);

  if (!holeId) {
    return (
      <aside className="detail">
        <p className="empty">
          Pick a hole on the map or in the list.
          <br />
          Its mineral log appears here.
        </p>
      </aside>
    );
  }

  if (error) {
    return <aside className="detail"><div className="error">{error}</div></aside>;
  }

  if (!hole) {
    return <aside className="detail"><p className="hint">Loading {holeId}…</p></aside>;
  }

  const lowConfidence = measurements.filter((m) => m.confidence < 0.5).length;
  // one depth scale for minerals, logged rock and assays, so a metre lines up across all three
  const deepest = Math.max(0, ...measurements.map((m) => m.depth_to_m), ...(assays?.intervals ?? []).map((r) => r.to_m),
    ...(geology?.intervals ?? []).map((r) => r.to_m));
  const rocks = geology?.intervals ?? [];
  const families = [...new Set(rocks.map((r) => r.family))].filter((f) => f !== "code");

  return (
    <aside className="detail">
      <h2 style={{ margin: "0 0 2px", fontSize: 20 }} className="mono">{hole.hole_id}</h2>
      <p style={{ margin: "0 0 16px", color: "var(--text-dim)" }}>
        {distinctName(hole)}
        {hole.confidential && (
          <span className="badge confidential" style={{ marginLeft: 8 }}>confidential</span>
        )}
        {hole.has_full_spectrum && (
          <span
            className="badge"
            style={{ marginLeft: 8, background: "rgba(185, 140, 255, 0.15)", color: "var(--accent-b)" }}
            title="Full spectrum restored locally from database5553/ - instant, pre-verified. Every other hole still shows its own spectrum below, fetched live from NVCL."
          >
            verified spectrum
          </span>
        )}
      </p>

      <table className="facts">
        <tbody>
          <tr title={'GSWA catalog "Total (m)": metres of core scanned, not the depth of the hole'}>
            <td>Scanned</td><td>{fmt(hole.borehole_length_m)} m</td>
          </tr>
          <tr title="Depth range the mineral log covers - often starts below the collar">
            <td>Logged</td>
            <td>{hole.logged_to_m == null ? "–" : `${fmt(hole.logged_from_m)}–${fmt(hole.logged_to_m)} m`}</td>
          </tr>
          <tr><td>Collar elevation</td><td>{fmt(hole.elevation_m)} m</td></tr>
          <tr><td>Latitude</td><td>{hole.latitude?.toFixed(5)}</td></tr>
          <tr><td>Longitude</td><td>{hole.longitude?.toFixed(5)}</td></tr>
          <tr title={hole.position?.note || (hole.position
            ? "GDA2020 position from GSWA's DASC HyLogger package; at least one other source (the company collar or the NVCL catalog) agrees within 0.5 km."
            : "Position from the NVCL catalog; this hole is not in GSWA's DASC package.")}>
            <td>Position</td>
            <td>
              {hole.position?.source === "DASC GDA2020" ? "GDA2020 · GSWA\u00a0DASC" : "NVCL catalog"}
              {hole.position?.note && <> <span className="badge warn">location checked</span></>}
            </td>
          </tr>
          <tr><td>Inclination</td><td>{fmt(hole.inclination_deg)}°</td></tr>
          <tr><td>Azimuth</td><td>{fmt(hole.azimuth_deg)}°</td></tr>
          <tr title={hole.gswa_level?.level === 2
            ? "GSWA Level 2: a geologist refined which minerals the unmixing may use (User results) - more accurate mineral labels. The site reads these where released."
            : "GSWA Level 1: automatic (System) interpretation only. GSWA's advice: treat mineral labels with caution; mineral GROUPS are more accurate than mineral names."}>
            <td>GSWA processing</td>
            <td>{hole.gswa_level
              ? <span className={`badge ${hole.gswa_level.level === 2 ? "" : "warn"}`}>
                  Level {hole.gswa_level.level} · {hole.gswa_level.level === 2 ? "geologist-refined" : "automatic only"}
                </span>
              : "–"}</td>
          </tr>
          <tr><td>Intervals</td><td>{hole.measurement_count}</td></tr>
          <tr>
            <td>Flagged</td>
            <td>
              {hole.anomaly_count > 0
                ? <span className="badge warn">{hole.anomaly_count} unusual</span>
                : <span className="badge">none</span>}
            </td>
          </tr>
        </tbody>
      </table>

      <p className="section-title">Mineral log · dominant SWIR mineral group</p>
      <p className="hint" style={{ marginTop: -4, marginBottom: 10 }}>
        Each band is the strongest SWIR-active mineral in that metre, not the whole rock -
        quartz and feldspar don&apos;t show in SWIR. Hover for the specific mineral and the SWIR/TIR mix.
      </p>
      {assays?.elements.length > 0 && (
        <label className="hint" style={{ display: "block", marginBottom: 6 }}>
          Lab assays beside it:{" "}
          <select value={element ?? ""} onChange={(event) => setElement(event.target.value)}>
            {assays.elements.map((e) => <option key={e} value={e}>{e}</option>)}
          </select>
        </label>
      )}
      <div style={{ display: "flex", gap: 8, alignItems: "flex-start" }}>
        <StripLog measurements={measurements} height={420} maxDepth={deepest || undefined} />
        <GeologyTrack geology={geology} maxDepth={deepest} height={420} />
        {assays && element && <AssayTrack assays={assays} element={element} maxDepth={deepest} height={420} />}
      </div>
      {rocks.length > 0 && (
        <p className="hint" style={{ margin: "4px 0 0", fontSize: 10, lineHeight: 1.6 }} title={geology.source}>
          Middle column: the rock the company logged (WAMEX).{" "}
          {families.map((f) => (
            <span key={f} style={{ whiteSpace: "nowrap", marginRight: 6 }}>
              <span className="legend-swatch" style={{ display: "inline-block", verticalAlign: "-1px", marginRight: 3, background: ROCK_FAMILIES[f][1] }} />
              {ROCK_FAMILIES[f][0]}
            </span>
          ))}
          {rocks.some((r) => r.family === "code") && (
            <span style={{ whiteSpace: "nowrap" }}>
              <span className="legend-swatch" style={{ display: "inline-block", verticalAlign: "-1px", marginRight: 3, background: CODE_ONLY }} />
              company code only ({rocks.filter((r) => r.family === "code").length} of {rocks.length}), not yet harmonised by GSWA
            </span>
          )}
        </p>
      )}
      {assays?.elements.length > 0 && (
        <p className="hint" style={{ margin: "4px 0 8px", fontSize: 10 }} title={assays.source}>
          Assays: company results reported to WAMEX, compiled by GSWA (no GSWA quality control).
          Hatched = below detection · red ? = suspect units, set aside.
        </p>
      )}
      <Legend measurements={measurements} lowConfidence={lowConfidence} />
      {measurements.length > 0 && (
        <p style={{ margin: "8px 0 0" }}>
          <a href={exportUrl(hole.hole_id)} download>Download this hole as CSV</a>
          <span className="hint"> · per metre, with assays</span>
        </p>
      )}
      {(measurements.length > 0 || assays?.elements.length > 0) && (
        <p className="hint" style={{ margin: "6px 0 0" }}>
          3D in QGIS:{" "}
          {measurements.length > 0 && <QgisLink label="mineral metres" url={qgisUrl("intervals", { holes: hole.hole_id })} />}
          {measurements.length > 0 && element && " · "}
          {element && <QgisLink label={`${element} assays`} url={qgisUrl("assays", { element, holes: hole.hole_id })} />}
        </p>
      )}

      <CoreTrays trays={trays} />

      <p className="section-title" style={{ marginTop: 22 }}>Full spectral data</p>
      {spectral === undefined && (
        <p className="hint">
          {hole.has_full_spectrum ? "Loading real VSWIR/TIR spectrum…" : "Checking NVCL for a real spectrum here (a few seconds)…"}
        </p>
      )}
      {spectral === null && (
        <p className="hint">No spectral log available for this hole.</p>
      )}
      {spectral && <FullSpectrum sample={spectral} />}

      <p className="section-title" style={{ marginTop: 22 }}>Nearest holes</p>
      {nearby.length === 0 ? (
        <p className="hint">Nothing else within 50 km.</p>
      ) : (
        <div>
          {nearby.slice(0, 6).map((other) => (
            <button
              key={other.hole_id}
              className="hole-row"
              onClick={() => onSelect?.(other.hole_id)}
            >
              <span className="id">{other.hole_id}</span>
              <span className="name">{other.hole_name}</span>
              <span className="len">{other.distance_km.toFixed(1)} km</span>
            </button>
          ))}
          <p style={{ marginTop: 12 }}>
            <Link href={`/viewer3d?a=${encodeURIComponent(hole.hole_id)}&b=${encodeURIComponent(nearby[0].hole_id)}`}>
              Compare with {nearby[0].hole_id} in 3D →
            </Link>
          </p>
        </div>
      )}
    </aside>
  );
}

function Legend({ measurements, lowConfidence }) {
  // only show minerals that actually appear in this hole
  const present = [...new Set(measurements.map((m) => m.mineral_1).filter(Boolean))];

  return (
    <div style={{ fontSize: 11, color: "var(--text-dim)" }}>
      {present.map((mineral) => (
        <div className="legend-item" key={mineral}>
          <span
            className="legend-swatch"
            style={{ background: MINERAL_COLOURS[mineral] || "var(--text-dim)" }}
          />
          {mineral}
        </div>
      ))}
      <div className="legend-item" style={{ marginTop: 10 }}>
        <span className="legend-swatch" style={{ background: LOW_CONFIDENCE_COLOUR }} />
        low confidence ({lowConfidence})
      </div>
      <div className="legend-item">
        <span className="legend-swatch" style={{ background: ANOMALY_COLOUR }} />
        unusual reading
      </div>
    </div>
  );
}

// One label per backend/holes/*_bridge.py source value - keep in sync with
// views.hole_spectral_sample's three-tier fallback order.
const SPECTRAL_SOURCE_LABELS = {
  database5553: "restored locally",
  data5553_tsg: "local TSG file",
  nvcl_live: "live from NVCL",
};

/** Real per-depth mineral calls + a VSWIR/TIR sparkline, from etl4_bridge.py
 * (database5553/, instant), tsg_bridge.py (data5553/, instant) or
 * nvcl_bridge.py (live NVCL, a few seconds). */
function FullSpectrum({ sample }) {
  const uniqueMinerals = [...new Set(sample.minerals.map((m) => m.mineral))];

  return (
    <div>
      <p className="hint" style={{ marginBottom: 8 }}>
        Sample {sample.sample_no} of {sample.sample_count} · {sample.md_m?.toFixed(2)} m
        {" · "}
        {SPECTRAL_SOURCE_LABELS[sample.source] || sample.source}
      </p>

      {uniqueMinerals.length > 0 && (
        <div style={{ marginBottom: 12 }}>
          {uniqueMinerals.map((mineral) => (
            <span key={mineral} className="badge" style={{ marginRight: 6, marginBottom: 6, display: "inline-block" }}>
              {mineral}
            </span>
          ))}
        </div>
      )}

      {sample.spectra.map((spectrum) => (
        <Sparkline key={spectrum.region} spectrum={spectrum} />
      ))}
    </div>
  );
}

/** Plain SVG polyline - wavelength on x, reflectance on y, no library. */
function Sparkline({ spectrum, width = 320, height = 70 }) {
  const values = spectrum.values;
  const finite = values.filter((v) => v != null && Number.isFinite(v));
  if (!finite.length) return null;

  const min = Math.min(...finite);
  const max = Math.max(...finite) || 1;
  const toX = (i) => (i / (values.length - 1)) * width;
  const toY = (v) => height - ((v - min) / (max - min || 1)) * height;

  const points = values
    .map((v, i) => (v == null || !Number.isFinite(v) ? null : `${toX(i).toFixed(1)},${toY(v).toFixed(1)}`))
    .filter(Boolean)
    .join(" ");

  return (
    <div style={{ marginBottom: 10 }}>
      <p className="hint" style={{ marginBottom: 2 }}>
        {spectrum.region} · {values.length} channels · {spectrum.wavelength[0]}–{spectrum.wavelength.at(-1)} {spectrum.wavelength_unit}
      </p>
      <svg width={width} height={height} role="img" aria-label={`${spectrum.region} spectrum`}>
        <polyline points={points} fill="none" stroke="var(--accent)" strokeWidth="1.5" />
      </svg>
    </div>
  );
}

const fmt = (value) => (value == null ? "–" : Number(value).toFixed(1));
