# Mandatory manual acceptance before release

Record tester, exact source SHA, final package SHA-256, Windows version, physical
display setup, scale and evidence for each check. An unchecked item is UNVERIFIED.
Offscreen acceptance and controlled protocol fixtures do not close these gates.

- [ ] On both distributions inspect small/large/fullscreen and detached windows
  at physical 100/125/150/200% DPI, including mixed-monitor moves and restart
  geometry. Inspect About/licenses, splash Science Gothic, View/Analyze data,
  graphs/exported labels, Result Selection and Jana Wizard.
- [ ] From a disposable copy of a complete real Jana project, launch the intended
  integration executable, preserve incoming metadata, select the intended
  source/cycle, return its exact map and EDMA model together, and continue actual
  refinement. Record before/after project hashes. Repeat with another result;
  verify no stale artifacts. Verify cancellation/error preserves the project.
- [ ] Complete actual browser Sign in and reauthentication in the normal desktop;
  verify credential persistence after application restart without exporting tokens.
- [ ] Verify both packages on a clean supported Windows VM with no development
  dependencies, as a standard user, including native scientific-program paths.
- [ ] Verify ordinary unprefixed paths over 260 characters on a host configured
  to support them. The current host disables LongPathsEnabled; reading font
  files through explicit Windows extended-length paths has separate acceptance,
  which does not prove launching the complete application from a long path.
- [ ] Complete terminology/editorial owner review using current status rather
  than treating archived historical findings as blanket current approval.
- [ ] Obtain independent scientific review of native-authority provenance,
  original boundary discrepancy and per-group conservation evidence.
- [ ] Complete SignPath Foundation approval and narrow artifact configurations;
  independently review helper-before-embedding and publication protections.
- [ ] Verify actual production Authenticode publisher, timestamp and trust chains
  for the three owned executables, final package inventories and runtime probes.
  Verify the unchanged Ed25519 identity and final signed asset hashes separately.
- [ ] Only after all mandatory gates, approve the exact source SHA and final
  production artifacts. Merge/publication still require explicit authorization.

This task does not submit another SharpED job. Saved real responses support
offline integration acceptance; a fresh inference must be separately authorized
if needed to complete a later manual scenario.
