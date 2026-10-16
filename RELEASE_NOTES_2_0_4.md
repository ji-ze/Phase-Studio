# Phase Studio 2.0.4 — development preview

## HKL and powder diagnostic acceptance

- Verified standard Superflip FWHM as degrees 2θ from local documentation,
  source and installed-executable comparisons. Resolve wavelength from the
  incoming input or matching Jana `.m90`; never invent an experimental value.
- Add read-only, transitive peak-overlap diagnostics with the verified inclusive
  boundary and default separation 0.2. Complete ochlor group membership matches
  the installed Superflip: 91 groups, 193/631 affected records (30.59%).
- If wavelength is missing, hide dependent overlap results and ask the user to
  supply it. Keep wavelength-independent d_min, d98 and HKL coverage available.
- Preserve direct F/σ(F), optional derived intensity significance, adaptive
  charts, full-precision exports and stable structured nonmodal details.
- Add ten actual current Wizard acceptance screenshots, with offline scientific
  and UI fixtures explicitly identified. Physical-monitor and real Jana GUI
  acceptance remain separate from automated tests and frozen startup checks.

See `docs/ui/POWDER_OVERLAP_2_0_4.md` and
`docs/screenshots/2.0.4/wizard/README.md`. This is release preparation, not a
GitHub Release or automatic artifact publication.
