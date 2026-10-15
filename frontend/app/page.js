"use client";

// The main view: the map with the hole list and the Valuable minerals filter
// as minimisable boxes on it, hole detail on the right.

import { useEffect, useState } from "react";
import dynamic from "next/dynamic";
import { getHoles, getMineralLogs, qgisUrl } from "@/lib/api";
import { CONFIDENCE_THRESHOLD } from "@/config";
import { distinctName } from "@/lib/format";
import HoleDetail from "@/components/HoleDetail";
import MapPanel from "@/components/MapPanel";
import QgisLink from "@/components/QgisLink";
import ValuableMinerals, { useValuableMinerals } from "@/components/ValuableMinerals";

// MapLibre touches `window`, so it can't run during server rendering.
const HoleMap = dynamic(() => import("@/components/HoleMap"), {
  ssr: false,
  loading: () => <p className="hint" style={{ padding: 16 }}>Loading map…</p>,
});

export default function ExplorePage() {
  const [holes, setHoles] = useState([]);
  const [search, setSearch] = useState("");
  const [anomaliesOnly, setAnomaliesOnly] = useState(false);
  const minerals = useValuableMinerals();
  // hoveredId: cheap live preview (list row + map highlight only, no fetch).
  // detailId: what the right-hand panel actually fetches and shows - only
  // moves on a real click, so sweeping the mouse across the list or map
  // doesn't fire a getHole/getMeasurements/... round trip per hole passed over.
  const [hoveredId, setHoveredId] = useState(null);
  const [detailId, setDetailId] = useState(null);
  const [error, setError] = useState(null);
  // Every hole's mineral log, fetched once, so the map's 3D cores are
  // coloured on first load - not only the hole you click. Not refetched with
  // the search: the map looks each shown hole up in it by id.
  const [mineralLogs, setMineralLogs] = useState(null);

  useEffect(() => {
    getMineralLogs(CONFIDENCE_THRESHOLD)
      .then(setMineralLogs)
      .catch(() => setMineralLogs(null)); // the cores just stay one plain colour
  }, []);

  function openDetail(holeId) {
    setHoveredId(holeId);
    setDetailId(holeId);
  }

  // refetch when the filters change, with a short pause so we aren't
  // hitting the API on every keystroke
  useEffect(() => {
    const timer = setTimeout(() => {
      getHoles({ search, anomaliesOnly, ...minerals.filter })
        .then((data) => {
          setHoles(data);
          setError(null);
        })
        .catch((err) => setError(err.message));
    }, 250);
    return () => clearTimeout(timer);
  }, [search, anomaliesOnly, minerals.filter]);
  const shown = minerals.shadeHoles(holes); // richest first when a detected mineral is chosen

  const holeList = (
    <MapPanel label="hole list" head={<span className="section-title" style={{ margin: 0 }}>Holes · {holes.length}</span>}>
      <input
        type="search"
        placeholder="Search hole id or name"
        value={search}
        onChange={(event) => setSearch(event.target.value)}
        style={{ marginTop: 8 }}
      />
      <label
        className="checkbox"
        title="Holes where the anomaly model marked at least one metre as statistically unusual compared with every other hole - worth a closer look, not proof of ore or of bad data."
      >
        <input
          type="checkbox"
          checked={anomaliesOnly}
          onChange={(event) => setAnomaliesOnly(event.target.checked)}
        />
        Unusual readings only
      </label>
      <p className="hint" style={{ margin: "6px 0 0" }}>
        <QgisLink
          label="Copy QGIS link for these holes"
          url={qgisUrl("holes", { search, anomalies_only: anomaliesOnly ? "1" : "", ...minerals.filter })}
        />
      </p>

      <div className="hole-list short">
        {error && <div className="error" style={{ margin: 12 }}>{error}</div>}

        {!error && holes.length === 0 && (
          <p className="empty">
            No holes match.
            <br />
            If the list is empty on first run, load the data:
            <br />
            <code className="mono">python manage.py load_data</code>
          </p>
        )}

        {shown.map((hole) => (
          <button
            key={hole.hole_id}
            className={`hole-row ${hole.hole_id === hoveredId ? "selected" : ""}`}
            onMouseEnter={() => setHoveredId(hole.hole_id)}
            onClick={() => openDetail(hole.hole_id)}
          >
            <span className="id">{hole.hole_id}</span>
            {distinctName(hole) && <span className="name">{distinctName(hole)}</span>}
            {hole.confidential && <span className="badge confidential">confidential</span>}
            <span className="len">{Math.round(hole.drawn_length_m || 0)} m</span>
          </button>
        ))}
      </div>
    </MapPanel>
  );

  return (
    <div className="columns">
      <div className="map-area">
        <HoleMap
          holes={shown}
          mineralLogs={mineralLogs}
          initial3d
          selectedId={hoveredId}
          onHover={setHoveredId}
          onSelect={openDetail}
          flyToId={detailId}
          panel={<>{holeList}<ValuableMinerals {...minerals} /></>}
          coreControls={false}
        />
      </div>

      <HoleDetail holeId={detailId} onSelect={openDetail} />
    </div>
  );
}
