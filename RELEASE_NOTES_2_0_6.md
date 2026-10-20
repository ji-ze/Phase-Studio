# Phase Studio 2.0.6 — update-system preparation

Development preview. No production release has been published by this work.

- Shared asynchronous update consent, download and verification UI for the
  standalone ONEFILE executable and Jana2020 ONEDIR distribution.
- Canonical Ed25519 release manifests, exact package hashes and sizes, bounded
  downloads, private Windows DPAPI plans and an independent transaction helper.
- Owned-runtime inventory, replacement journal, rollback, process identity
  checks, explicit UAC and verified startup acknowledgement.
- Jana2020 uses an explicit close-and-reopen fallback. Updates never complete
  a scientific handoff or restart a scientific calculation automatically.
- One-time signing-key provisioning and protected GitHub Actions preparation.

The production public verification key is pinned. The maintainer reports that
the matching signing secret and main-restricted signing environment are configured.
Production deployment still requires reviewed-source Actions and native acceptance;
unit tests alone do not establish production readiness. Existing installations
need a one-time manual upgrade to an
updater-capable package. Scientific calculations and exports are unchanged.
