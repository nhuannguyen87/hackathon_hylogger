// How one metre's mineral call reads in a hover: the dominant SWIR group is
// only the strongest SWIR-active mineral, so it is shown with its specific
// mineral, its spectral weight (Wt - not a confidence, per GSWA's FAQ) and
// the rest of the mix - SWIR and TIR, the TIR one seeing quartz and feldspar.

/** "CHLORITE 60% · WHITE-MICA 30% · KAOLIN 10%" - biggest shares first. */
export function formatMix(shares, top = 3) {
  return Object.entries(shares || {})
    .sort((a, b) => b[1] - a[1])
    .slice(0, top)
    .map(([group, share]) => `${group} ${share}%`)
    .join(" · ");
}

/** The lines every interval hover shows about its minerals. */
export function mineralLines(m) {
  if (!m.mineral_1) return ["no mineral logged"];
  const lines = [
    `Dominant SWIR group: ${m.mineral_1}${m.mineral_1_species ? ` (${m.mineral_1_species})` : ""}`,
  ];
  if (m.mineral_1_pct != null) lines.push(`spectral weight (Wt) ${m.mineral_1_pct.toFixed(2)}`);
  const swir = formatMix(m.mix?.swir);
  const tir = formatMix(m.mix?.tir);
  if (swir) lines.push(`SWIR mix: ${swir}`);
  if (tir) lines.push(`TIR mix: ${tir}`);
  return lines;
}
