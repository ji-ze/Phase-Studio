# Temporary SharpED compatibility bridge in 1.0.9

Before the URL migration, inference worked through `jana.fzu.cz`, but its model
catalog was stale. Moving everything to `sharped.fzu.cz` corrected discovery,
while the previously accepted token received HTTP 401 on authenticated upload.

Production now uses one `SharpEDServerClient` with two endpoint roles:

- Current catalog and current DEFAULT: `https://sharped.fzu.cz/sharp-ed/models`.
- Upload, status, and result download: `https://jana.fzu.cz/api/user/sharp-ed/...`.
- Legacy `/sharp-ed/models` is queried only as separate compatibility evidence.
  Its catalog/default never replaces the current visible catalog/default.

The main GUI and Wizard use the same catalog presentation. Unsupported entries
and DEFAULT are disabled with a short explanation, and the existing model status
shows the temporary routing. Editable/manual selections are also checked before
upload. Compatibility is refreshed at submission; if it cannot be verified, the
client stops before upload. Explicit model names are never substituted. DEFAULT
is resolved freshly from the current catalog and must pass the same check.

There is no host fallback on authentication failure; the existing token recovery
flow remains in use. Job links from either configured host are bound to the
selected inference host. Unknown job hosts and cross-origin HTTP redirects are
rejected before credentials can be forwarded.

## Live acceptance, 2026-09-13

Both public catalogs returned HTTP 200. The current catalog listed 11 models,
defaulting to `koala 4.0`. Legacy compatibility metadata listed these 10 models:

`koala 1.0`, `koala 2.0`, `viper 2.0`, `viper 3.0`, `viper 4.0`,
`koalaB 1.0`, `agama 1.0`, `agama 2.0`, `buzzard 1.0`, `buzzard 2.0`.

No local settings/environment token was present. The user's previously supplied
temporary token was used only in process memory. A generated 32-cubed synthetic
density map with `viper 3.0` uploaded, completed, and downloaded successfully
through the legacy backend; the downloaded map parsed and contained finite
values. No user scientific data was uploaded.

A separate diagnostic upload explicitly requesting `koala 4.0` returned HTTP 422:
`The selected model is invalid.` Thus current DEFAULT is unavailable during this
bridge. Users must select a compatible concrete model. The other nine advertised
legacy models were not individually submitted; metadata advertises compatibility,
while the full job lifecycle was demonstrated specifically with `viper 3.0`.

## Removing the bridge

Change `PRODUCTION_ENDPOINTS` in `phase_studio/sharped_server_client.py` to
`SharpEDEndpoints(DEFAULT_SERVER_URL, DEFAULT_SERVER_URL)` when authentication
and inference have migrated. The same client then uses the final host throughout,
skips legacy compatibility lookup/validation, and shows no temporary status.
No GUI or scientific implementation needs to change. Custom server overrides
already use one host for both roles; ordinary users configure only one service.

`tests/test_sharped_bridge.py` covers both split and unified configurations,
the complete mocked job lifecycle, exact model/map submission, DEFAULT behavior,
unavailable compatibility, selector state, host confinement, authentication
failure, and credential redaction. Scientific transforms and workflows are
unchanged. Existing built executables must be rebuilt to include this source fix.
