/** Library risk aliases express known evidence, not an assessment of missing data. */
export function hasKnownRansomware(summary) {
  return (
    summary?.ransomware?.status === 'known' ||
    summary?.known_ransomware === true ||
    summary?.ransomware_known === true
  );
}
