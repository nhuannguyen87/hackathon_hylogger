"use client";

// The rock the company logged down the hole (WAMEX, via GSWA's DASC
// package), on the same depth scale as the mineral log beside it - so what
// HyLogger measured and what a geologist logged compare metre for metre.
// Most intervals carry only the company's own code: those are plain dark
// grey (hatching already means "untrusted" and "below detection" next door),
// with the code on hover. Codes differ between companies, so the site never
// guesses a rock from one (holes/geology.py).

import { useState } from "react";
import { tipAt } from "@/lib/format";

export const CODE_ONLY = "#3d4a57";
export const ROCK_FAMILIES = {
  felsic: ["Felsic", "#e8a5a0"],
  mafic: ["Mafic–intermediate", "#4f8a64"],
  ultramafic: ["Ultramafic", "#8a6bb3"],
  sedimentary: ["Sedimentary", "#d9b45a"],
  metamorphic: ["Metamorphic", "#7f93a8"],
  regolith: ["Regolith", "#c97a3d"],
  vein: ["Vein", "#eef1f4"],
  other: ["Other rock", "#a3adb8"],
};

export default function GeologyTrack({ geology, maxDepth, height = 420, width = 22 }) {
  const [hover, setHover] = useState(null);
  if (!geology?.intervals.length) return null;
  const toY = (depth) => (depth / maxDepth) * height;
  return (
    <div style={{ position: "relative" }}>
      <svg width={width} height={height + 16} role="img"
           aria-label={`Rock the company logged, ${geology.intervals.length} intervals`}>
        <g transform="translate(0, 8)">
          {geology.intervals.map((r, i) => {
            const y = toY(r.from_m);
            const show = (event) => setHover({ r, x: event.clientX, y: event.clientY });
            return (
              <rect key={i} x={0} y={y} width={width} height={Math.max(1, toY(r.to_m) - y)}
                    fill={r.family === "code" ? CODE_ONLY : ROCK_FAMILIES[r.family][1]}
                    onMouseEnter={show} onMouseMove={show} onMouseLeave={() => setHover(null)} />
            );
          })}
          <rect x={0} y={0} width={width} height={height} fill="none" stroke="var(--line)" />
        </g>
      </svg>

      {hover && (
        <div className="tooltip" style={tipAt(hover)}>
          {hover.r.from_m}–{hover.r.to_m} m · rock the company logged
          <br />
          {hover.r.family === "code"
            ? `code "${hover.r.code}" only - GSWA hasn't harmonised it, so it isn't interpreted here`
            : `${hover.r.rock || hover.r.name} (${hover.r.rock ? "GSWA's name" : "company's name"}) · ${ROCK_FAMILIES[hover.r.family][0]}`}
        </div>
      )}
    </div>
  );
}
