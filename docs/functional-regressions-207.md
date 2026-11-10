# Phase Studio 2.0.7 functional corrections

Run readiness checks the selected reflection source as well as its declared
format. A positive observed-value significance threshold requires finite,
positive measured uncertainties. Validation happens before allocating a run or
checking execution dependencies. The worker repeats the guard for direct and
continued execution. Validation never changes the configured threshold.

Intensity filtering uses I/σ(I); amplitude filtering uses F/σ(F). The existing
map-feedback conversion uses F/[2σ(F)] for its derived intensity criterion.
These are different quantities. Zero bypasses significance filtering. FWHM and
native ignored auxiliary columns do not establish measured uncertainties.

External measured amplitude data have an explicit **F · measured σ(F)** input
choice. The historical amplitude/dummy choice remains available for saved
configurations and native compatibility; it does not acquire measured-sigma
provenance merely because an auxiliary number is positive. Direct numerical
writer APIs retain their existing behavior for caller-supplied measured rows.

The Jana2020 Superflip + SharpED Wizard always includes Map Feedback after
Configure, including one-cycle runs. One-cycle feedback controls are inactive
because there is no subsequent cycle. Their settings remain available when the
cycle count increases. The observed significance threshold is explicit and
must be changed by the user when the input lacks measured uncertainties.

Large Wizard input loading publishes crystal metadata before reflection
diagnostics complete. Results are keyed to source identity and reference
settings; stale worker completions are discarded. Closing cancels delivery.
Input diagnostics do not require a Superflip executable.

Presentation changes retain original scientific authorities and source files:

- Recommendation values are rounded for display; technical details and copy
  preserve the authoritative full-precision explanation and ranking order.
- The execution table filters persisted events without replacing their IDs,
  timestamps, native commands or original payloads. Full structured details,
  original log access and sanitized export remain available.
- Analysis tables retain full-precision values for copy/export. Unavailable
  uncertainty and powder analyses explain missing prerequisites.
- About uses four exclusive navigation cards and independent document readers.
  Original legal resources, raw copy and source-opening actions are retained.

Local screenshot and real-data evidence belongs under ignored `build/` paths.
It must not be published as repository assets. Automated offscreen or native
Qt captures do not establish physical-monitor, mixed-DPI, browser SSO, Jana
refinement, clean-VM or production-signing acceptance.
