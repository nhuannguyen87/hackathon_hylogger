"use client";

// "Open in QGIS": copies a GeoJSON layer URL from the Django API. QGIS loads it
// directly - Layer > Add Layer > Add Vector Layer > Protocol: HTTP(S) > paste -
// so a GIS user gets the same holes, colours and flags the site shows.

import { useState } from "react";

export default function QgisLink({ url, label }) {
  const [copied, setCopied] = useState(false);
  function copy() {
    navigator.clipboard?.writeText(url).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }
  return (
    <button
      type="button"
      className="link-button"
      onClick={copy}
      title={`${url}\n\nIn QGIS: Layer > Add Layer > Add Vector Layer > Protocol: HTTP(S) > paste this URL. `
        + "Style by the 'colour' field for the site's palette."}
    >
      {copied ? "Copied - paste into QGIS" : label}
    </button>
  );
}
