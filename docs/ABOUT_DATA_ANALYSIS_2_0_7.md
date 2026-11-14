# About, input analysis and startup typography — 2.0.7

This development change follows the immutable scientific validation snapshot
`2eae1ecd0c83dc6e19d9a99b302d3f479282fc70`. Its completed campaign recorded
834 passed, 4 skipped and 37 successful subtests, nine independent authorities,
native-format checks and both frozen profiles. Each frozen profile loaded all
eight actual returned inference maps. Those results do not validate subsequent
UI changes; the new source SHA and its own regression/build results belong in
the accompanying test-build manifest. PR #21 remains draft; no release/signing.

## Legal authorities and rendering

About now presents five navigable sections: About & Contacts, Authors &
Acknowledgements, License, Third-party Licenses, Citation. Authors use the
GitHub Markdown dialect with embedded HTML disabled; the third-party table uses
the same renderer. The legal browser denies embedded resource loads. External
document links are restricted to HTTPS and mailto; opening the selected original
is a separate explicit action. Search, selection, copy and vertical scrolling
remain available. Dependency notices have a selector rather than hundreds of
tabs and retain their original text. Citation offers a readable citation and
the original CFF source. Its displayed scalar metadata is read from CFF without
introducing a runtime YAML dependency.

Help and About share AUTHORS.md and the citation presentation. Jiří Zelenka
remains the sole Phase Studio author, with zelenka@fzu.cz. SharpED is separately
credited to Jiří Zelenka, Jan Rohlíček (rohlicek@fzu.cz), Monika Kučeráková
(kucerakova@fzu.cz) and Zdeněk Buk. Copyright ownership remains distinct from
authorship. LICENSE, THIRD_PARTY_NOTICES.md and the font's OFL notice are unchanged.
CITATION.cff adds only the author's email and was validated against the official
[CFF 1.2.0 schema](https://raw.githubusercontent.com/citation-file-format/citation-file-format/1.2.0/schema.json).
The existing bundle collector includes these authorities in both distributions.

## Splash root cause

The old splash set a QFont before effective styling, while the main header also
specified Science Gothic in the stylesheet. A shown, styled old splash resolved
to **Segoe UI / weight 400**. The corrected splash resolves after polishing and
specifies Science Gothic / regular / zero extra tracking in the stylesheet.
Sharp/ED uses the established wordmark face and separate colors. Status and
progress labels retain the ordinary UI font. This is a Qt splash; no separate
PyInstaller/Tk splash is configured. Acceptance checks inspect QFontInfo after
showing the widgets and compare the splash with the actual main-window title.

## View data and Analyze data

Main Input and Jana Wizard entry points use the new labels. View data retains
the existing incremental reflection model, original per-record values, exact
column semantics, HKL search, sorting, copy/export and integrity/provenance
diagnostics. Widths and dummy sigma remain explicitly separate from uncertainty.

Analyze data uses one existing cached diagnostic snapshot, not an independent
parser or coverage engine. It provides Overview, Resolution, Intensity &
Amplitude, Signal & Uncertainty, Symmetry & Coverage, Powder & Peak Overlap,
Advanced Diagnostics. Detailed original diagnostics remain embedded. Figures
are created lazily; paired plots, navigation toolbar, count scale, resolution
axis, display-only histogram detail, point hover and PNG/SVG export are shared.
CSV contains full-precision numbers for the displayed plotted series; advanced
resolution rows expose the full original shell statistics and added counts.

Graphs include record/literal-HKL/allowed-orbit frequency versus resolution,
reciprocal-shell-width-normalized record density, cumulative records, I/F
distribution and mean/median versus resolution, genuine-uncertainty mean/median
significance, fractions above 2 and 3, sigma distribution, direct signed F/σ(F),
shell and cumulative indexed coverage, allowed/indexed/missing orbit counts,
FWHM versus resolution, overlap fraction and overlap-group size distribution.
Applicable overlap records use the existing read-only group inspector.
Unavailable categories explain their missing scientific prerequisites.

## Definitions and limitations

* d_min and d98 retain the established accepted-domain and cumulative ≥98%
  definitions. d_full is a separate strict 100% cumulative allowed-orbit boundary,
  computed in the same existing theoretical-radius traversal as d98. Friedel
  mates are combined; 000 and systematic absences excluded. Equal-radius
  boundaries retain the existing absolute 1e-12 reciprocal-radius grouping and
  the established domain-boundary tolerance. Coverage of indexed powder HKLs is
  not independent experimental completeness or a count of resolved peaks.
* Shell statistics retain the authority's (lo, hi] sinθ/λ intervals. d runs toward
  higher resolution to the right; it is the reciprocal of twice that coordinate.
  Density explicitly uses reciprocal-shell width even when the axis displays d.
* Significance limits require ≥20 finite genuine-uncertainty records per shell,
  an above-threshold shell followed by at least two below-threshold shells,
  and no later recovery or sparse/missing outer tail. Linear interpolation of
  means in sinθ/λ estimates the crossing. Adjacent shell boundaries give a
  bracket, not a confidence interval. Missing crossings remain unavailable.
  F+σ(F) intensity significance uses the existing first-order |F|/(2σ(F))
  approximation, explicitly derived and unreliable near zero. No FWHM, dummy
  sigma or fabricated uncertainties enter these calculations.
* CC1/2 is never inferred from merged unique HKLs or duplicate text rows. The
  current input readers do not establish verified unmerged/scaled observations;
  native computation of CC1/2 remains unsupported. External JSON can provide
  ordered lo/hi reciprocal intervals, cc_half and paired_orbits (at least 3),
  plus source, method and independence_evidence strings. Import validates the
  interchange, not the truth of the producer's independence claim. Its graph
  identifies that provenance. The configurable cutoff has no universal default
  scientific validity; it uses the same sustained crossing rule and requires
  ≥20 paired orbits per shell. Original CC statistics are not recalculated.
* Inspection does not alter RunConfig, input files, reconstruction filters,
  Map Feedback, maps or selected results. Existing numerical analysis AST is
  pinned to the scientific snapshot except the added strict-coverage field.

Independent checks cover I/σ, phased I and F/σ, dummy sigma, I/F with FWHM,
negative/zero values, missing uncertainty, cutoff interpolation, sparse tails,
nonmonotonic recovery, nonorthogonal metrics, strict complete spheres, external
CC validation and 100,000 repeated records counted separately from unique HKL.
Existing symmetry, absences, Friedel and wavelength authorities remain in force.
GUI acceptance checks both modes, all tabs and plot pairs at 100/125/150/200%,
effective font, intact license text, rendered table, search, unchanged input
hashes and figure-label bounds. These controlled offscreen Qt scale tests do
not replace interactive physical-monitor DPI or live Jana refinement acceptance.

The quantified Selexipag native overlap membership precision discrepancy
(3796 native versus 3795 application members, both 794 groups), interactive
Jana continuation/refinement, exhaustive workflow combinations and chemical
truth validation remain separate scientific acceptance gaps. Successful live
inference/download/rendering is not proof of a solved structure.
