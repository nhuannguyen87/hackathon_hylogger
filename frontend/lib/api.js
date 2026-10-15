// Every call to the Django API goes through here. One place to add auth headers
// or change error handling later.

import { API_BASE } from "@/config";

async function get(path) {
  const response = await fetch(`${API_BASE}${path}`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(
      `${response.status} from ${path}. Is the Django server running on ${API_BASE}?`
    );
  }
  return response.json();
}

export const getStats = () => get("/stats/");

// 327 hole ids carry a suffix like " [chips]" - encode every id that goes in a path
const holePath = (holeId) => `/holes/${encodeURIComponent(holeId)}`;

// commodity / group / species: the valuable-minerals filters; withPhotos: the
// 3D tab's list (see views.hole_list)
export const getHoles = ({ search = "", anomaliesOnly = false, withPhotos = false, limit = 3000, commodity, group, species } = {}) => {
  const query = new URLSearchParams({ limit: String(limit) });
  if (search) query.set("search", search);
  if (anomaliesOnly) query.set("anomalies_only", "1");
  if (withPhotos) query.set("with_photos", "1");
  for (const [key, value] of Object.entries({ commodity, group, species })) if (value) query.set(key, value);
  return get(`/holes/?${query}`);
};

export const getHole = (holeId) => get(`${holePath(holeId)}/`);
export const getMeasurements = (holeId) => get(`${holePath(holeId)}/measurements/`);
export const getTrays = (holeId) => get(`${holePath(holeId)}/trays/`);
export const getAnomalies = (holeId) => get(`${holePath(holeId)}/anomalies/`);
export const getTrace = (holeId, stepM = 5) => get(`${holePath(holeId)}/trace/?step_m=${stepM}`);
export const getNearby = (holeId, km = 25) => get(`${holePath(holeId)}/nearby/?km=${km}`);
export const getDistance = (a, b) => get(`/distance/?${new URLSearchParams({ a, b })}`);
export const getMinerals = () => get("/minerals/");
// {hole_id: %} - how much of one detected mineral (group or species) each hole holds
export const getRichness = (kind, code) => get(`/minerals/richness/?${kind}=${encodeURIComponent(code)}`);
export const getHoleMinerals = (holeId) => get(`${holePath(holeId)}/minerals/`);
// company lab assays (WAMEX via GSWA's DASC package) + each element's best 5 m
export const getAssays = (holeId) => get(`${holePath(holeId)}/assays/`);
export const getGeology = (holeId) => get(`${holePath(holeId)}/geology/`);
// GeoJSON layers QGIS opens straight from the URL: "holes" (collars, takes the
// hole-list filters), "intervals" (3D logged metres), "assays" (3D, ?element=)
export const qgisUrl = (layer, params = {}) => {
  const query = new URLSearchParams(Object.entries(params).filter(([, v]) => v)).toString();
  return `${API_BASE}/qgis/${layer}.geojson${query ? `?${query}` : ""}`;
};
// the hole's per-metre log + assays as a CSV, for logging software
export const exportUrl = (holeId) => `${API_BASE}${holePath(holeId)}/export.csv`;
export const getVocab = () => get("/vocab/");

/**
 * Every hole's mineral log in one call, merged into [from_m, to_m, group]
 * runs - what lets the map colour every 3D core on first load. Pass
 * CONFIDENCE_THRESHOLD so it greys out the same intervals StripLog does.
 */
export const getMineralLogs = (minConfidence) => get(`/mineral-logs/?min_confidence=${minConfidence}`);

/**
 * Real VSWIR/TIR spectrum + mineral call, only for the handful of holes with
 * has_full_spectrum=true. null (not an error) for every other hole - that's
 * the normal case, not a failure, so it doesn't go through get()'s throw.
 */
export const getSpectralSample = async (holeId, depthM) => {
  const query = depthM != null ? `?depth_m=${depthM}` : "";
  const response = await fetch(`${API_BASE}${holePath(holeId)}/spectral-sample/${query}`, { cache: "no-store" });
  if (response.status === 404) return null;
  if (!response.ok) throw new Error(`${response.status} from /holes/${holeId}/spectral-sample/`);
  return response.json();
};

/**
 * Continuous core-photo + TSG strip (core_strip.py output), only for holes
 * that have actually been run through that pipeline. null (not an error)
 * for every other hole - same normal-not-a-failure shape as getSpectralSample.
 */
export const getCoreStrip = async (holeId) => {
  const response = await fetch(`${API_BASE}${holePath(holeId)}/core-strip/`, { cache: "no-store" });
  // 202: the backend is building this hole's strip from NVCL right now - ask again shortly
  if (response.status === 202) return { building: true };
  // 404: no photos for this hole (NVCL has none, or they're another hole's) - say why
  if (response.status === 404) {
    const body = await response.json().catch(() => ({}));
    return { unavailable: body.detail || "No core photos for this hole." };
  }
  if (!response.ok) throw new Error(`${response.status} from /holes/${holeId}/core-strip/`);
  return response.json();
};
