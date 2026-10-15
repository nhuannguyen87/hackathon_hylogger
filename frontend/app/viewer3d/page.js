"use client";

// 3D: the satellite map on its own until you pick a hole - on the map, or in
// the list of holes with core photos - then that hole opens on the right as a
// real drill core (its NVCL tray photos wrapped round a cylinder at their
// true depths, see Hole3D). A second pick stands the two cores side by side
// at the same depth; a third replaces whichever was picked first, in place.
// Pick a chosen hole again, or its ×, to put it back.

import { Suspense, useEffect, useState } from "react";
import dynamic from "next/dynamic";
import { useSearchParams } from "next/navigation";
import { getDistance, getHoles, getMineralLogs } from "@/lib/api";
import { CONFIDENCE_THRESHOLD } from "@/config";
import MapPanel from "@/components/MapPanel";

const HoleMap = dynamic(() => import("@/components/HoleMap"), {
  ssr: false,
  loading: () => <p className="hint" style={{ padding: 16 }}>Loading map…</p>,
});
const Hole3D = dynamic(() => import("@/components/Hole3D"), { ssr: false });

const MAX_HOLES = 2; // the map marks two (A and B)

export default function Viewer3DPageWrapper() {
  // useSearchParams needs a Suspense boundary in the app router
  return (
    <Suspense fallback={<div className="page"><p className="hint">Loading…</p></div>}>
      <Viewer3DPage />
    </Suspense>
  );
}

function Viewer3DPage() {
  const params = useSearchParams();
  const [holes, setHoles] = useState([]);
  const [photoHoles, setPhotoHoles] = useState([]);
  const [search, setSearch] = useState("");
  const [mineralLogs, setMineralLogs] = useState(null);
  // ids: the open holes, in their on-screen places; older: which place a
  // third pick takes (the hole picked longest ago)
  const [{ ids: chosen, older }, setPick] = useState(() => ({
    ids: [params.get("a"), params.get("b")].filter(Boolean), older: 0,
  }));
  const [distance, setDistance] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    getHoles().then(setHoles).catch((err) => setError(err.message));
    getHoles({ withPhotos: true }).then(setPhotoHoles).catch(() => setPhotoHoles([]));
    getMineralLogs(CONFIDENCE_THRESHOLD).then(setMineralLogs).catch(() => setMineralLogs(null));
  }, []);

  const [a, b] = chosen;
  useEffect(() => {
    setDistance(null);
    if (a && b) getDistance(a, b).then(setDistance).catch(() => setDistance(null));
  }, [a, b]);

  function toggle(holeId) {
    setPick(({ ids, older: first }) => {
      if (ids.includes(holeId)) return { ids: ids.filter((id) => id !== holeId), older: 0 };
      if (ids.length < MAX_HOLES) return { ids: [...ids, holeId], older: 0 };
      return { ids: ids.map((id, i) => (i === first ? holeId : id)), older: 1 - first };
    });
  }
  // the latest pick, for the map to fly to
  const latest = chosen.length === MAX_HOLES ? chosen[1 - older] : chosen[0];

  const needle = search.trim().toLowerCase();
  const holeList = (
    <MapPanel label="hole list" head={<span className="section-title" style={{ margin: 0 }}>Holes with core photos · {photoHoles.length}</span>}>
      <input type="search" placeholder="Search hole id" value={search} onChange={(e) => setSearch(e.target.value)} style={{ marginTop: 8 }} />
      <div className="hole-list short">
        {photoHoles.filter((h) => h.hole_id.toLowerCase().includes(needle)).map((h) => (
          <button key={h.hole_id} type="button" className={`hole-row ${chosen.includes(h.hole_id) ? "selected" : ""}`}
                  aria-pressed={chosen.includes(h.hole_id)} onClick={() => toggle(h.hole_id)}>
            <span className="id">{chosen.includes(h.hole_id) && `${"AB"[chosen.indexOf(h.hole_id)]} · `}{h.hole_id}</span>
            <span className="len">{Math.round(h.drawn_length_m || 0)} m</span>
          </button>
        ))}
      </div>
    </MapPanel>
  );

  return (
    <div className="split">
      <div className="map-area">
        {error && <div className="error" style={{ position: "absolute", top: 12, left: 260, zIndex: 3 }}>{error}</div>}
        <HoleMap
          holes={holes}
          mineralLogs={mineralLogs}
          initial3d
          selectedId={a}
          selectedIdB={b}
          onSelect={toggle}
          flyToId={latest}
          coreStripPanel={false}
          focusIds={chosen}
          panel={holeList}
        />
        {!chosen.length && (
          <div className="legend">
            Pick a hole on the map or in the list · a second opens beside it · a third replaces the first
          </div>
        )}
      </div>

      {chosen.length > 0 && (
        <div className="core3d-area">
          <Hole3D holeIds={chosen} distanceKm={distance?.distance_km} onClose={toggle} />
        </div>
      )}
    </div>
  );
}
