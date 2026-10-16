# Phase Studio 2.0.4 — development only

Not published; OAuth production acceptance is pending.

- Added system-browser Jana2020 Authorization Code + PKCE S256 sign-in for
  the supplied public `phase-studio` client, without a client secret.
- Added a temporary IPv4 loopback callback and process-only one-hour access.
  Expiration uses browser reauthorization; no refresh or ID tokens are requested.
- Resume protected status/download requests after renewal without a new upload.
  Preserve the secure manual access-key fallback and all scientific workflows.
- Added local mock-provider regressions, scaled UI evidence and opt-in frozen
  callback diagnostics for standalone and Jana ONEDIR builds.

See `docs/auth/JANA2020_OAUTH_2_0_4.md`. Mocked and frozen diagnostic successes
are not production API acceptance. Do not publish before real acceptance passes.

## HKL and powder diagnostic acceptance

- Final execution consistency: replace idle log placeholder on real start,
  preserve shared GUI logging, count completed-cycle events, validate active
  handoff candidates before confirmation and retain sealed threshold identity.
- Show ineffective Feedback settings explicitly without changing their values;
  label the existing powder no-σ correction mode and fit Wizard pages to content.
- Use consistent visible atom marker areas in the shared viewers. Ranking,
  canonical coordinates, periodic connectivity and scientific defaults remain
  unchanged. Historical ochlor artifacts replace synthetic execution geometry
  in the ten-window acceptance set.
- Final distributions will be rebuilt from the selected committed revision in
  a separate clean worktree. Build manifest records source SHA and artifact hashes.

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
