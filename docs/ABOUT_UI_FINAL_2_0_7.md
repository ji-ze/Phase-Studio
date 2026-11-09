# Phase Studio 2.0.7 final About correction

The approved native PySide6 About uses four exclusive navigation cards in a 2 × 2 grid and one shared scrolling content panel. All sections retain the same 720 × 420 logical-pixel desktop geometry, including Citation. The original logo, Science Gothic wordmark, white/navy/cyan palette and Segoe UI controls are retained.

The main Authors panel distinguishes Phase Studio authorship from SharpED development credits. Extended contacts, institution address and scientific collaboration details open in the independent document viewer. Its **Original AUTHORS.md** toggle, **Copy original** and **Open original** retain access to the unchanged complete source. License and Third-party cards contain summaries and viewer actions; no full license is embedded in the main dialog. The reader has searchable dependency selection, full-text search, friendly titles, secondary original paths and original-layout access. Markdown code spans and headings use readable UI fonts without altering source text.

The initial Windows offscreen backend exposed only the registered branding font. The shared font resolver registers installed Segoe UI bytes when needed; system fonts are not redistributed. This fixes actual effective fonts rather than just requested font names. Existing Unicode-safe Science Gothic loading is preserved.

## Before and after evidence

All captures are real Qt widget renders with controlled screen geometry. Offscreen and native Windows backend captures are labeled separately. Neither establishes physical-monitor or mixed-DPI human acceptance.

- [Original before-state gallery](screenshots/about207-correction/before/).
- The intervening tabbed implementation and its reports are preserved locally under `build/about207-final-tabs/`; its 720 × 330 Citation geometry is superseded. Its source snapshot and diff are retained under `build/about207-final-cards/before-tabs/`.
- [Final standalone Authors](screenshots/about207-final-cards/standalone-authors.png), [License](screenshots/about207-final-cards/standalone-license.png), [Third-party](screenshots/about207-final-cards/standalone-third-party.png), [Citation](screenshots/about207-final-cards/standalone-citation.png).
- [Final Jana2020 Authors](screenshots/about207-final-cards/jana-authors.png), [License](screenshots/about207-final-cards/jana-license.png), [Third-party](screenshots/about207-final-cards/jana-third-party.png), [Citation](screenshots/about207-final-cards/jana-citation.png).
- [Narrow scrolling action](screenshots/about207-final-cards/narrow-authors-action.png), [short screen](screenshots/about207-final-cards/short-screen-authors.png), [short-screen action reached](screenshots/about207-final-cards/short-screen-authors-action.png), [focus distinct from selection](screenshots/about207-final-cards/standalone-focus-versus-selection.png).
- [MIT reader](screenshots/about207-final-cards/standalone-mit-viewer.png), [dependency reader](screenshots/about207-final-cards/standalone-third-party-viewer.png), [contacts](screenshots/about207-final-cards/standalone-contacts-viewer.png), [collaboration and address](screenshots/about207-final-cards/standalone-collaboration-viewer.png), [original credits](screenshots/about207-final-cards/standalone-original-credits.png), [original CFF](screenshots/about207-final-cards/standalone-citation-metadata.png).
- [125%](screenshots/about207-final-cards/authors-1.25.png), [150%](screenshots/about207-final-cards/authors-1.5.png), [200%](screenshots/about207-final-cards/authors-2.png), [native Windows backend](screenshots/about207-final-cards/authors-native.png).

Each scale report captures both runtime profiles, all four sections, independent viewers, narrow and short windows. Assertions cover exclusive selection, unchanged outer geometry, exact raw legal bytes, copy/open/search, safe embedded-resource handling, effective fonts and scrolling the actual credits action fully into the viewport. Screenshots and contact sheets were visually reviewed, including full-size reader and constrained-window renders.

Eleven original legal authorities remain byte-identical to the preserved baseline. Source and frozen evidence additionally verifies complete packaged notices, legal fonts, source modules and Unicode extraction paths. No license, citation or authorship resource was rewritten.

The narrowly related Help change removes the redundant About contents link while preserving original help sections. The existing prepared update-dialog fix describes an installed development version ahead of published stable truthfully; version comparison, trust and update security are unchanged. Unrelated Run Overview/workshop work remains preserved outside this change.

Exact source commit, final focused/full regression counts, nine scientific authority results, both unsigned Windows artifact hashes and frozen screenshot verification are recorded in the latest validation section of [draft PR #21](https://github.com/ji-ze/Phase-Studio/pull/21), with full logs in `build/about207-final-cards/`. Earlier reports remain historical evidence.

Physical/mixed-DPI acceptance, interactive Jana refinement and the broader release gates remain unverified. Keep PR #21 draft. No merge, tag, production signing or publication is authorized.
