"use client";

// Minerals: the 3D tab's satellite map and standing cores, but picked by
// mineral instead of by hole (the Valuable minerals panel). A hole's card on
// the right lists every mineral in it, not just the dominant one. "Section"
// swaps the map for a geologist's section view around the clicked hole.

import { useEffect, useState } from "react";
import dynamic from "next/dynamic";
import { getHoles } from "@/lib/api";
import MineralDetail from "@/components/MineralDetail";
import SectionView from "@/components/SectionView";
import ValuableMinerals, { holeCount, useValuableMinerals } from "@/components/ValuableMinerals";

const HoleMap = dynamic(() => import("@/components/HoleMap"), {
  ssr: false,
  loading: () => <p className="hint" style={{ padding: 16 }}>Loading map…</p>,
});

const VERB = { commodity: "drilled for", group: "with", species: "with" };

export default function MineralsPage() {
  const minerals = useValuableMinerals();
  const { choice, filter, shadeHoles } = minerals;
  const [holes, setHoles] = useState([]);
  const [holeId, setHoleId] = useState(null);
  const [error, setError] = useState(null);
  const [mode, setMode] = useState("map");
  const [centreId, setCentreId] = useState(null); // the section's middle hole

  useEffect(() => {
    setHoleId(null);
    getHoles(filter).then(setHoles).catch((err) => setError(err.message));
  }, [filter]);

  const shown = shadeHoles(holes);
  const centre = holeId || centreId;
  return (
    <div className="columns">
      <div className="map-area">
        <div className="view-toggle" role="group" aria-label="View">
          <button type="button" aria-pressed={mode === "map"} onClick={() => setMode("map")}>Map</button>
          <button type="button" aria-pressed={mode === "section"} disabled={!centre}
                  title={centre ? `Section through the holes around ${centre}` : "Click a hole on the map first"}
                  onClick={() => { setCentreId(centre); setMode("section"); }}>
            Section
          </button>
        </div>
        {/* kept mounted while the section shows, so the map keeps its place */}
        <div className="map-layer" hidden={mode !== "map"}>
          <HoleMap
            holes={shown}
            initial3d
            selectedId={holeId}
            onSelect={setHoleId}
            flyToId={holeId}
            coreStripPanel={false}
            panel={mode === "map" && <ValuableMinerals {...minerals} />}
          />
          <div className="legend">
            {error || (choice
              ? `${holeCount(holes.length)} ${VERB[choice.kind]} ${choice.name}`
              : `${holeCount(holes.length)} · pick a mineral on the left`)}
          </div>
        </div>
        {mode === "section" && (
          <SectionView
            centreId={centreId}
            selectedId={holeId}
            onSelect={setHoleId}
            onCentre={setCentreId}
            highlight={choice?.kind === "group" ? choice.code : choice?.group}
            panel={<ValuableMinerals {...minerals} />}
          />
        )}
      </div>

      <MineralDetail choice={choice} holes={shown} shaded={!!minerals.richness} holeId={holeId} onSelect={setHoleId} />
    </div>
  );
}
