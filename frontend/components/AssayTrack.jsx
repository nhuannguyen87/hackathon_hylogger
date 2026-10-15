"use client";

// Lab chemistry down the hole, drawn on the same depth scale as StripLog so a
// metre's minerals and its assay sit side by side. Each interval is a bar on
// a log scale; the three things a reader must not misread are drawn apart:
//   below detection -> grey hatching at the axis (measured, nothing found)
//   suspect units   -> red "?" (a value rock can't hold - left out, not hidden)
//   no assay        -> nothing at all (a gap is not a zero)
// plus GSWA's gold cut-off as a dashed line and the hole's best 5 m bracketed.

import { useState } from "react";
import { tipAt } from "@/lib/format";

const BAR = "#c9a227";
const SUSPECT = "#ff8a7a";

export default function AssayTrack({ assays, element, maxDepth, height = 420, width = 120 }) {
  const [hover, setHover] = useState(null);
  const rows = assays.intervals.filter((r) =>
    element in r.values || r.below_detection.includes(element) || element in r.suspect);
  if (!rows.length) return null;

  const values = rows.map((r) => r.values[element]).filter((v) => v > 0).sort((a, b) => a - b);
  const cutoff = assays.cutoff_ppm[element];
  const high = values.at(-1) || 1;
  const low = Math.min(cutoff ?? values[0] ?? high / 1000, high / 1000);
  const toX = (v) => Math.max(1, (Math.log10(Math.max(v, low) / low) / Math.log10(high / low)) * (width - 10));
  const toY = (depth) => (depth / maxDepth) * height;
  const best = assays.best[element];

  return (
    <div style={{ position: "relative" }}>
      <svg width={width} height={height + 16} role="img"
           aria-label={`${element} assays down the hole, log scale, ${rows.length} intervals`}>
        <defs>
          <pattern id="bdl" width="4" height="4" patternTransform="rotate(45)" patternUnits="userSpaceOnUse">
            <line x1="0" y1="0" x2="0" y2="4" stroke="#8c9aa5" strokeWidth="1.5" />
          </pattern>
        </defs>
        <g transform="translate(0, 8)">
          <line x1={0} y1={0} x2={0} y2={height} stroke="var(--line)" />
          {rows.map((r, i) => {
            const y = toY(r.from_m);
            const h = Math.max(1, toY(r.to_m) - y);
            const show = (event) => setHover({ r, x: event.clientX, y: event.clientY });
            const common = { onMouseEnter: show, onMouseMove: show, onMouseLeave: () => setHover(null) };
            if (element in r.suspect) {
              return <text key={i} x={4} y={y + h / 2 + 4} fill={SUSPECT} fontSize="11" fontWeight="700" {...common}>?</text>;
            }
            if (!(element in r.values)) {
              return <rect key={i} x={0} y={y} width={6} height={h} fill="url(#bdl)" {...common} />;
            }
            return <rect key={i} x={0} y={y} width={toX(r.values[element])} height={h} fill={BAR} {...common} />;
          })}
          {cutoff != null && (
            <line x1={toX(cutoff)} y1={0} x2={toX(cutoff)} y2={height} stroke="var(--text-dim)" strokeDasharray="3 3" />
          )}
          {best && (
            <path d={`M${width - 4},${toY(best.from_m)} h3 V${toY(best.to_m)} h-3`} fill="none" stroke="var(--text)" strokeWidth="1.5" />
          )}
        </g>
      </svg>
      <p className="hint" style={{ margin: "2px 0 0", fontSize: 10, lineHeight: 1.4 }}>
        {element} ppm, log {format(low)}–{format(high)}
        {cutoff != null && <><br />dashes: {format(cutoff)} ppm cut-off</>}
        {best && <><br />bracket: best 5 m, {format(best.ppm)} ppm</>}
      </p>

      {hover && (
        <div className="tooltip" style={tipAt(hover)}>
          {hover.r.from_m}–{hover.r.to_m} m
          <br />
          {element in hover.r.suspect
            ? `${format(hover.r.suspect[element])} ppm reported - above what rock can hold, most likely a unit error; set aside`
            : element in hover.r.values
              ? `${element} ${format(hover.r.values[element])} ppm (g/t)${element === "Au" && hover.r.values.Au < 1 ? ` = ${Math.round(hover.r.values.Au * 1000)} ppb` : ""}`
              : `${element} below the lab's detection limit`}
        </div>
      )}
    </div>
  );
}

const format = (v) => (v >= 100 ? Math.round(v).toLocaleString() : Number(v.toPrecision(2)));
