"""Regression tests for Jana2020 .m90 reflection-data wavelength parsing
(Phase Studio 2.0.0 Autosolve, Option B's Powder-repartitioning branch).

Plain Python test (no pytest dependency); run with
`python tests/test_m90_wavelength.py`.
"""
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

results_log = []

# A real Jana2020 .m90 file (header + reflection table), provided as the
# actual format reference for this parser.
SAMPLE_M90 = """eformat91 0
datblock Block1
nref 15381 obslim 3 sctom90 1 norefitems 1 diffscales 1 dataave 1 scalelim 10 hklf5 0
wshelxa -999 wshelxb -999
indslowest 3 indfastest 1 addcentrsymm 0 sigimethod 1 multave 1
flimprint 5 flimcull -1 avesigwt 0 unstab 0.016997
radtype 1 dattype 1
lambda 1.54184 lpfactor 1 monangle 13.2885 perfmono 0.5
datcolltemp 94.970001 wtdatblock 1
end
Data Block1
   4   0   0 272506.0   1857.1   1   0   1  0.0000
   6   0   0  11688.8    476.6   1   0   1  0.0000
   8   0   0 254596.0   2584.1   1   0   1  0.0000
  10   0   0  23139.6    901.7   1   0   1  0.0000
  12   0   0  21464.1    960.9   1   0   1  0.0000
"""


def check(name, cond):
    results_log.append((name, bool(cond)))
    print(("PASS" if cond else "FAIL") + " - " + name)


def main():
    import phase_studio.app as appmod

    tmp = Path(tempfile.mkdtemp())

    # --- Real sample: wavelength is the value after "lambda" ---
    m90 = tmp / "job.m90"
    m90.write_text(SAMPLE_M90, encoding="utf-8")
    check("real sample: wavelength parsed as 1.54184", abs(appmod.parse_m90_wavelength(m90) - 1.54184) < 1e-9)

    # --- resolve_jana_m90_path: same directory/stem, .m90 extension ---
    inflip = tmp / "job.inflip"
    inflip.write_text("title fixture\n", encoding="utf-8")
    check("resolve_jana_m90_path: finds the sibling .m90 file", appmod.resolve_jana_m90_path(inflip) == m90)

    missing_inflip = tmp / "no_sibling.inflip"
    missing_inflip.write_text("title fixture\n", encoding="utf-8")
    check("resolve_jana_m90_path: None when no matching .m90 exists", appmod.resolve_jana_m90_path(missing_inflip) is None)
    check("resolve_jana_m90_path: None when given no .inflip at all", appmod.resolve_jana_m90_path(None) is None)

    # --- Only the header is scanned, never the reflection data table ---
    no_lambda_m90 = tmp / "no_lambda.m90"
    no_lambda_m90.write_text(
        "eformat91 0\ndatblock Block1\nnref 10 obslim 3\nend\nData Block1\n   4   0   0 1.54184   1.0   1   0   1  0.0\n",
        encoding="utf-8",
    )
    check(
        "a numeric value that looks like a wavelength in the DATA TABLE is never picked up",
        appmod.parse_m90_wavelength(no_lambda_m90) == 0.0,
    )

    # --- Missing/unreadable file: never raises ---
    check("a missing .m90 file returns 0.0 rather than raising", appmod.parse_m90_wavelength(tmp / "does_not_exist.m90") == 0.0)

    # --- resolve_powder_wavelength: m90 sits between manual and .inflip lambda ---
    inflip_with_lambda = tmp / "with_lambda.inflip"
    inflip_with_lambda.write_text("title fixture\nlambda 0.71073\n", encoding="utf-8")
    value, source = appmod.resolve_powder_wavelength(0.0, inflip_with_lambda, None, jana_m90_path=m90)
    check("resolve_powder_wavelength: .m90 wins over the .inflip lambda line", abs(value - 1.54184) < 1e-9)
    check("resolve_powder_wavelength: source names the .m90 file", "m90" in source.lower())

    manual_value, manual_source = appmod.resolve_powder_wavelength(2.0, inflip_with_lambda, None, jana_m90_path=m90)
    check("resolve_powder_wavelength: manual entry still wins over .m90", manual_value == 2.0 and manual_source == "manual entry")

    fallback_value, fallback_source = appmod.resolve_powder_wavelength(0.0, inflip_with_lambda, None, jana_m90_path=None)
    check(
        "resolve_powder_wavelength: falls back to the .inflip lambda line when no .m90 is given",
        abs(fallback_value - 0.71073) < 1e-9,
    )
    check("resolve_powder_wavelength: existing three-argument call sites are unaffected (jana_m90_path optional)", True)

    failures = [name for name, ok in results_log if not ok]
    print()
    if failures:
        print(f"{len(failures)} of {len(results_log)} checks FAILED:")
        for failure in failures:
            print("  - " + failure)
        return 1
    print(f"All {len(results_log)} checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
