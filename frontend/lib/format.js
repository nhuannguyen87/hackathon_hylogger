/** Most holes have hole_name === hole_id (e.g. "KD1"/"KD1") - only worth
 * showing the name separately when it actually says something extra. */
export function distinctName(hole) {
  if (!hole?.hole_name || hole.hole_name === hole.hole_id) return null;
  return hole.hole_name;
}

/** Where a hover tooltip goes: right of the cursor, or left of it near the
 * screen's right edge (the hole card sits there), so it never runs off. */
export const tipAt = ({ x, y }) => (x > window.innerWidth - 300
  ? { right: window.innerWidth - x + 14, top: y - 10 }
  : { left: x + 14, top: y - 10 });
