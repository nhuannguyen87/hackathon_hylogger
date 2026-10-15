"use client";

// The Minerals tab's section view: the holes around one hole, the way a
// geologist sees a drilled deposit in Leapfrog or Micromine. Every hole at its
// true dip and azimuth, true scale both ways (orthographic, no exaggeration),
// its mineral log coloured down the hole, inside a box ruled in RL (metres
// above sea level), with a scale bar and the view direction. Drag to orbit,
// scroll to zoom. No geological solids: HyLogger gives drill holes and their
// minerals, not a 3D geology model.

import { useEffect, useMemo, useRef, useState } from "react";
import DeckGL, { OrbitView, PathLayer, TextLayer } from "deck.gl";
import { getHoles, getMineralLogs } from "@/lib/api";
import { CONFIDENCE_THRESHOLD, mineralColour, toRgb } from "@/config";
import { desurveyOffset } from "@/lib/desurvey";
import MapPanel from "./MapPanel";

const VIEW = new OrbitView({ orbitAxis: "Z", orthographic: true });
const RADII_KM = [1, 2, 5, 10];
const MAX_HOLES = 80;
const METRES_PER_DEGREE_LAT = 110540; // as lib/desurvey.js
const FONT = "Inter, system-ui, -apple-system, sans-serif";

// slate on a pale canvas, as mining 3D software draws a section
const INK = [51, 65, 85, 255];
const RULE = [100, 116, 139, 90];
const RULE_FAINT = [100, 116, 139, 40];
const CASING = [15, 23, 42, 235]; // under every colour, so pale minerals hold on a pale canvas
const UNLOGGED = [100, 116, 139, 160];
const OTHER = [37, 62, 99, 255]; // logged, but not the mineral picked
const UNCERTAIN = [203, 213, 225, 255];
const FOCUS = [13, 148, 136, 255];

let loaded = null; // every hole and mineral log, fetched once per visit

export default function SectionView({ centreId, selectedId, onSelect, onCentre, highlight, panel }) {
  const { data, error } = useSectionData();
  const containerRef = useRef(null);
  const [radiusKm, setRadiusKm] = useState(2);
  const [view, setView] = useState(null);
  const [hover, setHover] = useState(null);

  const centre = data?.holes.find((hole) => hole.hole_id === centreId);
  const scene = useMemo(
    () => (centre ? buildScene(centre, data.holes, data.logs, radiusKm, highlight) : null),
    [centre, data, radiusKm, highlight],
  );
  const frame = scene && `${centreId}:${radiusKm}`;
  const reset = () => {
    if (scene && containerRef.current) setView(fit(scene, containerRef.current));
  };
  // frame the box afresh for a new centre or radius, not for a new highlight
  useEffect(reset, [frame]); // eslint-disable-line react-hooks/exhaustive-deps

  const isFocus = (d) => d.hole.hole_id === selectedId;
  const pick = { pickable: true, onClick: (info) => info.object && onSelect(info.object.hole.hole_id) };
  // every line faces the camera (a flat one is edge-on, so invisible, from the
  // side) and draws in layer order: halo, casing, then colour on top of it
  const line = { billboard: true, widthUnits: "pixels", parameters: { depthCompare: "always" } };
  const labels = view && scene ? rlLabels(scene, view) : [];
  const named = view && scene ? collarLabels(scene, view, selectedId) : [];
  const showTip = (info) => setHover(info.object ? { x: info.x, y: info.y, segment: info.object } : null);
  const layers = scene ? [
    new PathLayer({
      id: "rules", data: scene.rules, getPath: (d) => d.path, getColor: (d) => d.colour,
      getWidth: 1, ...line,
    }),
    new PathLayer({
      id: "focus", data: [...scene.logged, ...scene.unlogged].filter(isFocus), getPath: (d) => d.path,
      getColor: FOCUS, getWidth: 15, capRounded: true, ...line,
    }),
    new PathLayer({
      id: "unlogged", data: scene.unlogged, getPath: (d) => d.path, getColor: UNLOGGED,
      getWidth: 1.5, onHover: showTip, ...line, ...pick,
    }),
    new PathLayer({
      id: "casing", data: scene.logged, getPath: (d) => d.path, getColor: CASING,
      getWidth: 6.5, capRounded: true, ...line,
    }),
    new PathLayer({
      // round caps: a 1 m run is under a pixel at section scale, a dot still shows its colour
      id: "minerals", data: scene.logged, getPath: (d) => d.path, getColor: (d) => d.colour,
      getWidth: 4, capRounded: true, onHover: showTip, ...line, ...pick,
    }),
    new TextLayer({
      id: "rl-labels", data: labels, getPosition: (d) => d.position, getText: (d) => d.text,
      getSize: 11, getColor: (d) => d.colour || INK, getTextAnchor: (d) => d.anchor, getAlignmentBaseline: "center",
      getPixelOffset: (d) => d.offset, fontFamily: FONT, fontWeight: 500,
      parameters: { depthCompare: "always" },
    }),
    new TextLayer({
      id: "collars", data: named, getPosition: (d) => d.position, getText: (d) => d.hole.hole_id,
      getSize: (d) => (isFocus(d) ? 12 : 10), getColor: (d) => (isFocus(d) ? FOCUS : INK),
      getTextAnchor: "middle", getAlignmentBaseline: "bottom", getPixelOffset: [0, -8],
      fontFamily: FONT, fontWeight: 600, parameters: { depthCompare: "always" },
      updateTriggers: { getSize: selectedId, getColor: selectedId }, ...pick,
    }),
  ] : [];

  const inSection = scene?.collars.some((c) => c.hole.hole_id === selectedId);
  return (
    <div ref={containerRef} className="section-canvas">
      {view && scene && (
        <DeckGL views={VIEW} viewState={view} controller={{ inertia: false }} layers={layers}
                onViewStateChange={({ viewState }) => setView(viewState)}
                getCursor={({ isHovering, isDragging }) => (isDragging ? "grabbing" : isHovering ? "pointer" : "grab")} />
      )}

      <div className="map-panels">
        {panel}
        <MapPanel label="section" head={<span className="section-title" style={{ margin: 0 }}>Section</span>}>
          {scene ? (
            <>
              <label className="slider-row" style={{ gridTemplateColumns: "1fr auto" }}>
                <span>{scene.count} holes within</span>
                <select value={radiusKm} onChange={(event) => setRadiusKm(Number(event.target.value))}
                        aria-label="Section radius">
                  {RADII_KM.map((km) => <option key={km} value={km}>{km} km of {centreId}</option>)}
                </select>
              </label>
              {selectedId && selectedId !== centreId && inSection && (
                <button type="button" className="link-button" onClick={() => onCentre(selectedId)}>
                  Centre on {selectedId}
                </button>
              )}
              <div className="legend-compact">
                {scene.legend.map(([name, colour]) => (
                  <div className="legend-item" key={name}>
                    <span className="legend-swatch" style={{ background: `rgb(${colour.slice(0, 3)})` }} />
                    {name}
                  </div>
                ))}
              </div>
              <p className="hint" style={{ margin: "6px 0 0", fontSize: 11 }}>
                RL: metres above sea level. Drag to orbit, scroll to zoom.{" "}
                <button type="button" className="link-button" onClick={reset}>Reset view</button>
              </p>
            </>
          ) : (
            <p className="hint" style={{ margin: "6px 0 0" }}>
              {error || (data ? "Click a hole on the map first: the section is drawn around it." : "Loading holes…")}
            </p>
          )}
        </MapPanel>
      </div>

      {view && scene && <Hud view={view} />}

      {hover && (
        <div className="tooltip" style={{ position: "absolute", left: hover.x + 14, top: hover.y + 14 }}>
          {hover.segment.hole.hole_id} · {hover.segment.from.toFixed(0)}–{hover.segment.to.toFixed(0)} m
          <br />
          {hover.segment.label}
        </div>
      )}
    </div>
  );
}

function useSectionData() {
  const [data, setData] = useState(loaded);
  const [error, setError] = useState(null);
  useEffect(() => {
    if (loaded) return;
    Promise.all([getHoles(), getMineralLogs(CONFIDENCE_THRESHOLD)])
      .then(([holes, logs]) => setData((loaded = { holes, logs })))
      .catch((err) => setError(err.message));
  }, []);
  return { data, error };
}

/** The holes within radiusKm of the centre hole in local metres (x east,
 * y north, z RL), cut into their mineral runs, plus the ruled box around them. */
function buildScene(centre, holes, logs, radiusKm, highlight) {
  const perLon = METRES_PER_DEGREE_LAT * Math.cos((centre.latitude * Math.PI) / 180);
  const near = holes
    .map((hole) => ({
      hole, x: (hole.longitude - centre.longitude) * perLon, y: (hole.latitude - centre.latitude) * METRES_PER_DEGREE_LAT,
    }))
    .filter((p) => Math.hypot(p.x, p.y) <= radiusKm * 1000 && (p.hole.drawn_length_m || p.hole.borehole_length_m) > 0)
    .sort((a, b) => Math.hypot(a.x, a.y) - Math.hypot(b.x, b.y))
    .slice(0, MAX_HOLES);

  const logged = [], unlogged = [], collars = [], metres = {}, dips = [], ends = [];
  for (const { hole, x, y } of near) {
    const length = hole.drawn_length_m || hole.borehole_length_m;
    const at = (depth) => {
      const o = desurveyOffset(depth, hole.inclination_deg ?? -90, hole.azimuth_deg ?? 0);
      return [x + o.east_m, y + o.north_m, (hole.elevation_m ?? 0) - o.tvd_m];
    };
    const add = (list, from, to, colour, label) => list.push({ hole, from, to, colour, label, path: [at(from), at(to)] });
    let reached = 0;
    for (const [from, to, code] of logs.holes[hole.hole_id] ?? []) {
      const top = Math.max(from, reached);
      const bottom = Math.min(to, length);
      if (bottom <= top) continue;
      if (top > reached) add(unlogged, reached, top, UNLOGGED, "not logged");
      if (code === null) {
        add(logged, top, bottom, UNCERTAIN, "uncertain reading");
      } else {
        const group = logs.groups[code];
        metres[group] = (metres[group] || 0) + (bottom - top);
        const colour = !highlight || group === highlight ? toRgb(mineralColour(group)) : OTHER;
        add(logged, top, bottom, colour, group || "no mineral called");
      }
      reached = bottom;
    }
    if (reached < length) add(unlogged, reached, length, UNLOGGED, "not logged");
    collars.push({ hole, position: at(0), logged: !!logs.holes[hole.hole_id] });
    ends.push(at(0), at(length));
    if (Math.abs(hole.inclination_deg ?? -90) < 85) dips.push(hole.azimuth_deg ?? 0);
  }
  if (!collars.length) return null;

  // look across the holes' dip direction, so their lean shows in profile
  const look = dips.length ? (circularMean(dips) + 90) % 360 : 0;
  // the ruled box, square to that view: u across the screen, v into it
  const r = ((look + 90) * Math.PI) / 180;
  const f = (look * Math.PI) / 180;
  const toXY = (u, v) => [u * Math.sin(r) + v * Math.sin(f), u * Math.cos(r) + v * Math.cos(f)];
  const us = ends.map(([x, y]) => x * Math.sin(r) + y * Math.cos(r));
  const vs = ends.map(([x, y]) => x * Math.sin(f) + y * Math.cos(f));
  const zs = ends.map((point) => point[2]);
  const padH = Math.max(25, 0.08 * Math.max(Math.max(...us) - Math.min(...us), Math.max(...vs) - Math.min(...vs)));
  const [u0, u1, v0, v1] = [Math.min(...us) - padH, Math.max(...us) + padH, Math.min(...vs) - padH, Math.max(...vs) + padH];
  const padZ = Math.max(20, 0.06 * (Math.max(...zs) - Math.min(...zs)));
  const step = niceStep((Math.max(...zs) - Math.min(...zs) + 2 * padZ) / 6);
  const z0 = Math.floor((Math.min(...zs) - padZ) / step) * step;
  const z1 = Math.ceil((Math.max(...zs) + padZ) / step) * step;
  const corners = [toXY(u0, v0), toXY(u1, v0), toXY(u1, v1), toXY(u0, v1)];

  // RL loops round it, faint rules up its faces, corner posts
  const rules = [], levels = [];
  const post = ([x, y], colour) => rules.push({ path: [[x, y, z0], [x, y, z1]], colour });
  for (let z = z0; z <= z1 + 1e-6; z += step) {
    rules.push({ path: [...corners, corners[0]].map(([x, y]) => [x, y, z]), colour: RULE });
    levels.push({ z, text: `${z > 0 ? "+" : ""}${Math.round(z)}` });
  }
  const gap = niceStep(Math.max(u1 - u0, v1 - v0) / 6);
  for (let u = Math.ceil(u0 / gap) * gap; u < u1; u += gap) [v0, v1].forEach((v) => post(toXY(u, v), RULE_FAINT));
  for (let v = Math.ceil(v0 / gap) * gap; v < v1; v += gap) [u0, u1].forEach((u) => post(toXY(u, v), RULE_FAINT));
  corners.forEach((corner) => post(corner, RULE));
  const edges = corners.map((a, i) => [(a[0] + corners[(i + 1) % 4][0]) / 2, (a[1] + corners[(i + 1) % 4][1]) / 2]);
  const north = edges.reduce((best, e) => (e[1] > best[1] ? e : best));

  // legend: what the colours in this section mean, most metres first
  const groups = Object.keys(metres).sort((a, b) => metres[b] - metres[a]);
  const legend = highlight
    ? [[highlight, toRgb(mineralColour(highlight))], ["other minerals", OTHER]]
    : groups.map((g) => [g || "no call", toRgb(mineralColour(g))]);
  legend.push(["uncertain", UNCERTAIN], ["not logged", UNLOGGED]);

  return {
    logged, unlogged, collars, rules, levels, legend, corners, look, count: collars.length,
    north: [...north, z1],
    frame: { centre: [...toXY((u0 + u1) / 2, (v0 + v1) / 2), (z0 + z1) / 2], width: u1 - u0, height: z1 - z0 },
  };
}

/** A view of the whole box from the side (plunge 0), looking across the dip. */
function fit(scene, element) {
  const { centre, width, height } = scene.frame;
  const room = Math.max(element.clientWidth - 330, 200); // the panels sit on the left
  const zoom = Math.log2(Math.min(room / width, (element.clientHeight - 130) / height));
  // move the box right of the panels: the target goes left along the screen
  const right = ((scene.look + 90) * Math.PI) / 180;
  const shift = 125 / 2 ** zoom;
  return {
    target: [centre[0] - shift * Math.sin(right), centre[1] - shift * Math.cos(right), centre[2]],
    zoom, minZoom: zoom - 3, maxZoom: zoom + 6,
    rotationOrbit: orbitFor(scene.look), rotationX: 0, minRotationX: -89, maxRotationX: 89,
  };
}

// OrbitView (orbit axis Z) starts south of its target looking north, and
// rotationOrbit turns the world under it - so it is the bearing looked along
const orbitFor = (look) => look;
const lookOf = (orbit) => ((orbit % 360) + 360) % 360;
// a point's distance to the right across the screen, for that bearing
const screenX = (look) => {
  const right = ((look + 90) * Math.PI) / 180;
  return ([x, y]) => x * Math.sin(right) + y * Math.cos(right);
};

/** RL labels up the box's two corners that are leftmost and rightmost on screen. */
function rlLabels(scene, view) {
  const side = screenX(lookOf(view.rotationOrbit));
  const corners = [...scene.corners].sort((a, b) => side(a) - side(b));
  const [left, right] = [corners[0], corners[3]];
  const top = scene.levels.at(-1).z;
  return [
    ...scene.levels.flatMap(({ z, text }) => [
      { position: [...left, z], text, anchor: "end", offset: [-8, 0] },
      { position: [...right, z], text, anchor: "start", offset: [8, 0] },
    ]),
    { position: [...left, top], text: "RL m", anchor: "end", offset: [-8, -16] },
    { position: scene.north, text: "N", anchor: "middle", offset: [0, -12], colour: FOCUS },
  ];
}

/** Collar names that don't overlap on screen: the hole in focus first, then
 * logged holes, then the nearest to the centre (scene order). */
function collarLabels(scene, view, selectedId) {
  const perMetre = 2 ** view.zoom; // pixels
  const side = screenX(lookOf(view.rotationOrbit));
  const rank = (c) => (c.hole.hole_id === selectedId ? 0 : c.logged ? 1 : 2);
  const named = [];
  for (const c of [...scene.collars].sort((a, b) => rank(a) - rank(b))) {
    const clear = named.every((o) => Math.abs(side(o.position) - side(c.position)) * perMetre > 84
                                  || Math.abs(o.position[2] - c.position[2]) * perMetre > 16);
    if (clear) named.push(c);
  }
  return named;
}

/** View direction and a scale bar, true everywhere in an orthographic view. */
function Hud({ view }) {
  const perPixel = 1 / 2 ** view.zoom; // metres
  const length = niceStep(150 * perPixel, [1, 2, 5]);
  const width = length / perPixel;
  const bearing = String(Math.round(lookOf(view.rotationOrbit)) % 360).padStart(3, "0");
  const plunge = String(Math.round(Math.abs(view.rotationX))).padStart(2, "0");
  return (
    <div className="section-hud">
      <div>Looking {bearing}° · plunge {plunge}°</div>
      <div className="scalebar" style={{ width }}>
        {[0, 1, 2, 3].map((i) => <span key={i} className={i % 2 ? "light" : ""} />)}
      </div>
      <div className="scalebar-labels" style={{ width }}>
        <span>0</span><span>{format(length / 2)}</span><span>{format(length)} m</span>
      </div>
    </div>
  );
}

const format = (metres) => (metres >= 1000 ? `${metres / 1000}k` : String(metres));

function niceStep(raw, mantissas = [1, 2, 2.5, 5]) {
  const power = 10 ** Math.floor(Math.log10(raw));
  return (mantissas.find((m) => m * power >= raw) ?? 10) * power;
}

function circularMean(degrees) {
  const rad = degrees.map((d) => (d * Math.PI) / 180);
  const mean = Math.atan2(rad.reduce((s, r) => s + Math.sin(r), 0), rad.reduce((s, r) => s + Math.cos(r), 0));
  return ((mean * 180) / Math.PI + 360) % 360;
}
