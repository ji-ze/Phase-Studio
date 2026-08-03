# Phase Studio Example Workflows

These examples describe typical Phase Studio configurations. Replace the file
paths with paths from your own Jana2020 project or external dataset.

## 1. Jana `.inflip` Diagnostic Run Without SharpED

Use this workflow to reproduce an existing Jana2020 Superflip calculation,
check reflection parsing and run EDMA on the raw Superflip map.

1. Open Phase Studio.
2. On `Paths`, set `Input data mode` to `Jana .inflip`.
3. Select `Jana .inflip`.
4. Set `Superflip exe/path` to the original Superflip executable.
5. Set `EDMA exe/path` to EDMA.
6. Press `Test HKL load`.
7. Press `Analyze completeness`.
8. On `Basic v3`, set:
   - `Cycles to run`: `1`
   - `Next-cycle modelfile`: `none`
   - `Run EDMA after Superflip map`: enabled
   - `Run SharpED deblurring`: disabled
   - `Run EDMA after deblurred map`: disabled
9. On `Advanced: EDMA`, set `plimit after Superflip sigma`:
   - `1.6` for good, clean maps;
   - `2.5` or `3.0` for noisy maps where weak maxima produce too many false
     peaks.
10. On `Advanced: Superflip`, keep `Save Superflip XPLOR map` enabled.
11. Press `Run`.

Expected outputs include the generated Superflip input, the Superflip XPLOR
map, Superflip log, EDMA output from the raw map and `metrics.csv`.

## 2. Jana `.inflip` With SharpED Deblurring And Jana2020 Hand-Off

Use this workflow when the raw Superflip solution is recognizable but the map
needs SharpED-assisted deblurring before peak extraction or Jana transfer.

1. On `Paths`, set `Input data mode` to `Jana .inflip`.
2. Select the Jana `.inflip`.
3. Set `Work directory` to a new run folder.
4. On `Basic v3`, set:
   - `Cycles to run`: `2` or more
   - `Next-cycle modelfile`: `deblurred_xplor`
   - `XPLOR damping 1/x`: `1.0` for no damping, or lower values for stronger
     damping
   - `Run EDMA after Superflip map`: enabled
   - `Run SharpED deblurring`: enabled
   - `Run EDMA after deblurred map`: enabled
5. On `SharpED`, set:
   - `Server URL`: `https://jana.fzu.cz`
   - `API token`: your SharpED token
   - `Model`: `Koala 2.0` for a typical deblurring run, or `Vieper 3.0` when
     that model is available and better matches the dataset
   - `Elements`: blank to derive elements from composition, or explicit values
     such as `C N O Zn`
   - `Max upload size MB`: `100` for the public server limit
6. On `Advanced: EDMA`, set:
   - `plimit after Superflip sigma`: `1.6` for good maps, or `2.5` to `3.0`
     for noisy raw Superflip maps;
   - `plimit after deblurring sigma`: `1.25` for the reconstructed/deblurred
     map.
7. Press `Run`.
8. After completion, press `Pass data to Jana2020`.
9. In the hand-off dialog, choose the recommended cycle or override it manually.
10. Choose `Deblurred map (SharpED output)` or `Superflip map`, then press
    `Pass to Jana2020`.

Expected outputs include raw Superflip maps, SharpED-deblurred maps, EDMA
models from both branches, per-cycle logs and a Jana2020 hand-off calculation.

## 3. Standalone External HKL + CIF Structure Solution

Use this workflow for data prepared outside Jana2020. The external reference
must be a CIF/INS/RES-compatible structure file because Phase Studio needs the
unit cell, space group and composition.

1. On `Paths`, set `Input data mode` to `External HKL + CIF reference`.
2. Select `External HKL`.
3. Select `External reference file` as a CIF, INS or RES file.
4. Set `HKL data format`:
   - use `auto` first;
   - use `intensity` for `h k l I sigma(I)`;
   - use `amplitude_dummy_sigma` for `h k l Fobs sigma(Fobs)`;
   - use `fobs_zero_phase_sigma` for fixed-width `h k l Fobs phase sigma`.
5. Press `Test HKL load` and confirm that value/sigma columns are correct.
6. Press `Analyze completeness` and inspect `d_min`, `d_full` and shell
   completeness.
7. On `Basic v3`, choose either:
   - `Next-cycle modelfile`: `superflip_xplor` for SharpED-free cycling; or
   - `Next-cycle modelfile`: `deblurred_edma_cif` for EDMA-CIF seeded cycling.
8. If SharpED is enabled, fill the SharpED tab as in workflow 2.
9. On `Advanced: EDMA`, use these starting thresholds:
   - `plimit after Superflip sigma`: `1.6` for good maps, or `2.5` to `3.0`
     for noisy raw Superflip maps;
   - `plimit after deblurring sigma`: `1.25` for the reconstructed/deblurred
     map.
10. On `Advanced: Superflip`, keep at least one export enabled. `Save Superflip
   XPLOR map` is the safest default because EDMA and SharpED use XPLOR maps.
11. Optional: enable `Save standardized HKL I/sigma/phase` to store the
    normalized reflection export used by the run.
12. Press `Run`.

Expected outputs include generated Superflip inputs, maps, EDMA structure
exports and `metrics.csv`. Jana2020 hand-off is not normally used in this
standalone mode unless the run was opened from a Jana wrapper context.
