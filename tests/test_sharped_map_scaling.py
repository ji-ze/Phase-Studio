"""Regression tests for the reversible SharpED map-value power transform.

Plain Python test (no pytest dependency; run with
`python tests/test_sharped_map_scaling.py`), following this project's usual
checks-list-plus-exit-code convention.

Covers, in order:
  1. The pure numerical helpers (`apply_signed_power` / `invert_signed_power`)
     over the pinned input set, for every documented exponent.
  2. Backward compatibility: the default exponent 1.0 must leave the uploaded
     file and the returned file byte-for-byte identical to the pre-feature
     workflow, with no XPLOR read/rewrite happening at all.
  3. A mocked SharpED round trip through the real `run_sharped_deblur()`,
     with a fake "identity" server, proving the forward and inverse
     transforms are placed correctly in the client pipeline.
  4. A mocked round trip with a *non-identity* server, proving the inverse is
     applied to what the server actually returned and not to a cached copy of
     what was uploaded.
"""
import math
import os
import shutil
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

results_log = []


def check(name, cond):
    results_log.append((name, bool(cond)))
    print(("PASS" if cond else "FAIL") + " - " + name)


# The pinned input set from the feature specification: negative, zero and
# positive values spanning two orders of magnitude.
FIXTURE_VALUES = [-16.0, -4.0, -1.0, 0.0, 1.0, 4.0, 16.0]
EXPONENTS = [0.0, 0.5, 0.75, 1.0, 2.0]

# Values used for the mocked server round trips. Chosen so that the XPLOR text
# format's %12.5E precision, not the maths, sets the tolerances below.
ROUND_TRIP_VALUES = [-16.0, -4.25, -1.0, 0.0, 0.5, 4.0, 16.75]


def _write_test_xplor(appmod, path, values, title="test map"):
    """A minimal but genuinely valid N x 1 x 1 XPLOR map carrying `values`."""
    import numpy as np
    n = len(values)
    xmap = appmod.XplorMap(
        title=title,
        grid=(n, 0, n - 1, 1, 0, 0, 1, 0, 0),
        cell=(10.0, 11.0, 12.0, 90.0, 90.0, 90.0),
        axis_order="ZYX",
        data=np.asarray(values, dtype=np.float64),
    )
    appmod.write_xplor_map(path, xmap)
    return xmap


def main():
    import numpy as np
    import phase_studio.app as appmod
    from phase_studio.sharped_map_scaling import (
        SHARPED_MAP_VALUE_EXPONENT_DEFAULT,
        apply_signed_power,
        describe_map_value_exponent,
        invert_signed_power,
        map_value_scaling_is_identity,
        normalize_map_value_exponent,
    )

    x = np.asarray(FIXTURE_VALUES, dtype=np.float64)

    # =========================================================================
    # 1. Pure numerical transform.
    # =========================================================================
    check("Default exponent is exactly 1.0", SHARPED_MAP_VALUE_EXPONENT_DEFAULT == 1.0)

    for a in EXPONENTS:
        forward = apply_signed_power(x, a)
        back = invert_signed_power(forward, a)

        if a in (0.0, 1.0):
            check(f"a={a}: forward transform is an exact identity (bit-for-bit)", np.array_equal(forward, x))
            check(f"a={a}: inverse transform is an exact identity (bit-for-bit)", np.array_equal(back, x))
        else:
            check(
                f"a={a}: forward followed by inverse recovers the original values",
                np.allclose(back, x, rtol=1e-12, atol=1e-12),
            )
            check(
                f"a={a}: forward actually changes the values (not a silent no-op)",
                not np.array_equal(forward, x),
            )

        # Sign/zero structure must hold for every exponent, identity included.
        check(f"a={a}: negative values stay strictly negative", all(float(v) < 0.0 for v in forward[:3]))
        check(
            f"a={a}: zero stays exactly zero (no NaN, inf or signed-zero artifact)",
            float(forward[3]) == 0.0 and math.copysign(1.0, float(forward[3])) > 0,
        )
        check(f"a={a}: positive values stay strictly positive", all(float(v) > 0.0 for v in forward[4:]))
        check(f"a={a}: forward result is entirely finite", bool(np.all(np.isfinite(forward))))
        check(f"a={a}: inverse result is entirely finite", bool(np.all(np.isfinite(back))))

    # Hand-verifiable values from the specification: a negative voxel under a
    # fractional exponent must stay real and negative, and invert exactly.
    half = apply_signed_power(np.asarray([-4.0]), 0.5)
    check("a=0.5: forward(-4) == -2 exactly (not NaN and not complex)", float(half[0]) == -2.0)
    check("a=0.5: inverse(-2) recovers -4 exactly", float(invert_signed_power(half, 0.5)[0]) == -4.0)

    squared = apply_signed_power(np.asarray([-3.0, 3.0]), 2.0)
    check("a=2.0: forward(-3, 3) == (-9, 9)", [float(v) for v in squared] == [-9.0, 9.0])

    # The caller's array must never be modified in place.
    original = np.asarray(FIXTURE_VALUES, dtype=np.float64)
    snapshot = original.copy()
    apply_signed_power(original, 0.75)
    invert_signed_power(original, 0.75)
    check("Neither helper mutates the caller's array", np.array_equal(original, snapshot))

    # dtype preservation for a non-float64 float map.
    f32 = np.asarray(FIXTURE_VALUES, dtype=np.float32)
    check("float32 input keeps its dtype through the forward transform", apply_signed_power(f32, 0.5).dtype == np.float32)

    # Non-finite input is refused with a clear error rather than silently
    # replaced by an invented finite value.
    for bad, label in ((np.nan, "NaN"), (np.inf, "+inf"), (-np.inf, "-inf")):
        try:
            apply_signed_power(np.asarray([1.0, bad]), 0.5)
            raised = False
        except ValueError as exc:
            raised = "non-finite" in str(exc)
        check(f"A map containing {label} raises a clear ValueError instead of being silently clipped", raised)

    # Exponent validation and classification.
    check("a=0.0 classifies as identity/bypass", map_value_scaling_is_identity(0.0))
    check("a=1.0 classifies as identity", map_value_scaling_is_identity(1.0))
    check("a=0.75 does not classify as identity", not map_value_scaling_is_identity(0.75))
    check("A negative stored exponent falls back to the 1.0 default", normalize_map_value_exponent(-2.0) == 1.0)
    check("A non-numeric stored exponent falls back to the 1.0 default", normalize_map_value_exponent("nonsense") == 1.0)
    check("A NaN stored exponent falls back to the 1.0 default", normalize_map_value_exponent(float("nan")) == 1.0)
    check("A valid stored exponent is preserved exactly", normalize_map_value_exponent("0.75") == 0.75)

    # Logging policy: one line per request, silent at the default.
    check("a=1.0 produces no per-request log line", describe_map_value_exponent(1.0) == "")
    check("a=0.0 logs that scaling is disabled", describe_map_value_exponent(0.0) == "[SharpED] Map value scaling disabled")
    check("a=0.75 logs the exponent to 3 decimals", describe_map_value_exponent(0.75) == "[SharpED] Map value exponent: 0.750")

    # =========================================================================
    # Mocked SharpED round trips through the real run_sharped_deblur().
    # =========================================================================
    tmpdir = Path(tempfile.mkdtemp())
    real_client = appmod.SharpEDServerClient
    uploads = []

    class FakeSharpEDServerClient:
        """Stands in for the HTTP client. `server_transform` decides what the
        fake server "computes" from the voxel values it received."""

        server_transform = staticmethod(lambda values: values)

        def __init__(self, base_url="", timeout=0.0):
            self.base_url = base_url

        def get_models(self, log=None):
            raise AssertionError("get_models() must not be called for an explicit model name")

        def execute(self, file_path, bearer_token, out_path, elements, model,
                    outres=0.2, poll_seconds=2, max_polls=-1, log=None, stop_event=None):
            received = appmod.read_xplor_map(Path(file_path))
            uploads.append((Path(file_path), Path(file_path).read_bytes(), received.data.copy()))
            produced = appmod.XplorMap(
                title=received.title,
                grid=received.grid,
                cell=received.cell,
                axis_order=received.axis_order,
                data=np.asarray(FakeSharpEDServerClient.server_transform(received.data), dtype=np.float64),
            )
            appmod.write_xplor_map(Path(out_path), produced)
            return Path(out_path)

    def run_round_trip(name, exponent, server_transform, values=FIXTURE_VALUES):
        """Run the real run_sharped_deblur() against the fake server."""
        del uploads[:]
        case_dir = tmpdir / name
        case_dir.mkdir(parents=True, exist_ok=True)
        input_map = case_dir / "input.xplor"
        output_map = case_dir / "output.xplor"
        _write_test_xplor(appmod, input_map, values)
        input_bytes_before = input_map.read_bytes()
        FakeSharpEDServerClient.server_transform = staticmethod(server_transform)
        appmod.SharpEDServerClient = FakeSharpEDServerClient
        log_lines = []
        try:
            appmod.run_sharped_deblur(
                input_map, output_map,
                "https://example.invalid", "token", "test-model", "C N O", 0.2,
                0.0, 600, 1, 1,
                log_lines.append,
                map_value_exponent=exponent,
            )
        finally:
            appmod.SharpEDServerClient = real_client
        return {
            "input_map": input_map,
            "input_bytes_before": input_bytes_before,
            "output_map": output_map,
            "uploaded_path": uploads[0][0],
            "uploaded_bytes": uploads[0][1],
            "uploaded_values": uploads[0][2],
            "downstream_values": appmod.read_xplor_map(output_map).data,
            "log": log_lines,
        }

    # -------------------------------------------------------------------------
    # 2. Backward compatibility at the default exponent.
    # -------------------------------------------------------------------------
    default_run = run_round_trip("default_a1", SHARPED_MAP_VALUE_EXPONENT_DEFAULT, lambda v: v * 2.0)
    check(
        "a=1.0: the file uploaded to SharpED is the untouched input map itself, not a rewritten copy",
        default_run["uploaded_path"] == default_run["input_map"],
    )
    check(
        "a=1.0: the uploaded bytes are exactly the bytes the pre-feature workflow uploaded",
        default_run["uploaded_bytes"] == default_run["input_bytes_before"],
    )
    check(
        "a=1.0: the input map on disk is left completely unmodified",
        default_run["input_map"].read_bytes() == default_run["input_bytes_before"],
    )
    check(
        "a=1.0: the values SharpED received are the original map values, bit-for-bit",
        np.array_equal(default_run["uploaded_values"], x),
    )
    check(
        "a=1.0: the map handed downstream is exactly the server's own output (no inverse pass)",
        np.array_equal(default_run["downstream_values"], x * 2.0),
    )
    check(
        "a=1.0: no map value exponent line is written to the execution log",
        not any("Map value exponent" in line or "Map value scaling" in line for line in default_run["log"]),
    )
    check(
        "a=1.0: no scaled upload file is created next to the output map",
        not (default_run["output_map"].parent / "output.sharped_input.xplor").exists(),
    )

    # a = 0 must behave identically to a = 1 (explicit bypass).
    bypass_run = run_round_trip("bypass_a0", 0.0, lambda v: v * 2.0)
    check(
        "a=0.0: bypass uploads the untouched input map, exactly like a=1.0",
        bypass_run["uploaded_path"] == bypass_run["input_map"]
        and bypass_run["uploaded_bytes"] == bypass_run["input_bytes_before"],
    )
    check(
        "a=0.0: bypass hands the server's own output downstream, untransformed",
        np.array_equal(bypass_run["downstream_values"], x * 2.0),
    )
    check(
        "a=0.0: the execution log says scaling is disabled",
        any("Map value scaling disabled" in line for line in bypass_run["log"]),
    )

    # -------------------------------------------------------------------------
    # 3. Identity server: original -> forward -> server -> inverse -> original.
    # -------------------------------------------------------------------------
    rt = np.asarray(ROUND_TRIP_VALUES, dtype=np.float64)
    for a in (0.5, 0.75, 2.0):
        run = run_round_trip(f"identity_server_a{a}", a, lambda v: v, values=ROUND_TRIP_VALUES)
        check(
            f"a={a}: the values SharpED received are the forward-transformed map, not the original",
            np.allclose(run["uploaded_values"], apply_signed_power(rt, a), rtol=1e-5, atol=1e-9),
        )
        check(
            f"a={a}: an identity SharpED server round-trips back to the original map values",
            np.allclose(run["downstream_values"], rt, rtol=1e-4, atol=1e-6),
        )
        check(
            f"a={a}: the forward transform ran exactly once (uploaded is not double-transformed)",
            not np.allclose(run["uploaded_values"], apply_signed_power(apply_signed_power(rt, a), a), rtol=1e-3, atol=1e-6),
        )
        check(
            f"a={a}: the original input map on disk is never overwritten",
            run["input_map"].read_bytes() == run["input_bytes_before"],
        )
        check(
            f"a={a}: the exponent is reported exactly once in the execution log",
            sum(1 for line in run["log"] if line == f"[SharpED] Map value exponent: {a:.3f}") == 1,
        )

    # -------------------------------------------------------------------------
    # 4. Non-identity server: the inverse must be applied to the SERVER's
    #    output, not to a cached copy of what was uploaded.
    # -------------------------------------------------------------------------
    a = 0.5
    server_scale = 3.0
    modified = run_round_trip("modifying_server", a, lambda v: v * server_scale, values=ROUND_TRIP_VALUES)
    expected_downstream = invert_signed_power(apply_signed_power(rt, a) * server_scale, a)
    check(
        "Non-identity server: downstream values equal inverse(server output), to XPLOR text precision",
        np.allclose(modified["downstream_values"], expected_downstream, rtol=1e-4, atol=1e-6),
    )
    check(
        "Non-identity server: downstream values are NOT simply the original map (the server's change survives)",
        not np.allclose(modified["downstream_values"], rt, rtol=1e-3, atol=1e-6),
    )
    check(
        "Non-identity server: downstream values are NOT the raw server output (the inverse really ran)",
        not np.allclose(modified["downstream_values"], apply_signed_power(rt, a) * server_scale, rtol=1e-3, atol=1e-6),
    )
    check(
        "Non-identity server: signs are preserved end to end",
        all(
            (float(got) < 0) == (float(want) < 0) and (float(got) == 0.0) == (float(want) == 0.0)
            for got, want in zip(modified["downstream_values"], expected_downstream)
        ),
    )

    shutil.rmtree(tmpdir, ignore_errors=True)

    failed = [name for name, ok in results_log if not ok]
    print()
    if failed:
        print(f"{len(failed)} check(s) FAILED: {failed}")
        sys.exit(1)
    else:
        print(f"All {len(results_log)} checks passed.")
        sys.exit(0)


if __name__ == "__main__":
    main()
