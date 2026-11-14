# Windows signing acceptance for 2.0.7

Status on 2026-11-06: repository integration and controlled tests only.
Foundation approval, account configuration and production certificates are
**UNVERIFIED**. No signing request or public release was made. Repository
variables and secrets were inspected by name only: no SignPath configuration
is present. The existing protected Ed25519 secret is present; its value was
neither retrieved nor changed. Key ID remains `1c016867382d60e0`.

The owner must complete the [Foundation application](https://signpath.org/apply),
confirm project approval, configure the
[trusted GitHub build integration](https://docs.signpath.io/trusted-build-systems/github),
and approve the two narrow artifact configurations in `packaging/signpath/`.
Their ZIP nesting follows the official
[artifact examples](https://docs.signpath.io/artifact-configuration/examples).
These XML files are proposed configurations, not proof of server acceptance.
No identity or service identifier has been invented.

Configure repository variables `SIGNPATH_ORGANIZATION_ID`,
`SIGNPATH_PROJECT_SLUG`, `SIGNPATH_SIGNING_POLICY_SLUG`,
`SIGNPATH_UPDATER_ARTIFACT_CONFIGURATION_SLUG`,
`SIGNPATH_APPLICATION_ARTIFACT_CONFIGURATION_SLUG`,
`SIGNPATH_CERTIFICATE_SUBJECT`, and `SIGNPATH_CERTIFICATE_THUMBPRINTS`.
Thumbprints are explicitly approved SHA-1 certificate identifiers separated
by semicolons, not file hashes. Public certificate policy must be repository
scoped because the embedding job does not access the signing environment.
Store `SIGNPATH_API_TOKEN` as a secret in `phase-studio-release-signing`.
Require service-side signing approval and review environment protection;
the currently observed signing environment has branch restrictions only.
Publication retains its independent protected reviewer approval.

After scientific and mandatory manual acceptance, the owner records the exact
approved 40-character source SHA in repository variable `RELEASE_ACCEPTANCE_SHA`.
The workflow requires this SHA and ancestry in main. This task does not set
the variable, merge the branch, dispatch signing, create a tag or publish.

The workflow builds and checks both unsigned profiles, signs only the owned
updater, verifies its embedded signature, approved identity, trust chains,
timestamp and version, then rebuilds both applications around those final
helper bytes. This regenerates embedded helper hashes and ONEDIR ownership
inventory before application signing. It checks frozen GUI behavior again.
The second request signs only the outer standalone executable and the Jana
main executable inside its ZIP. It never re-signs the embedded helper, Qt,
Microsoft or other third-party binaries.

`verify_signing_transform.py` compares unchanged executable payload bytes,
allowing only PE checksum/security-directory changes and an appended aligned
certificate. Nested ZIP members other than the main executable must be
identical. `verify_authenticode.py` separately uses actual Windows trust APIs,
requires the configured publisher and certificate, valid publisher/timestamp
chains, timestamp EKU, exact version, identical signed helpers and runtime
contracts. Structural PE fixtures are not certificate-validation evidence.

Only after the last binary modification does the existing Ed25519 signer hash
and sign the final six-file asset contract. Both independent signature systems
are checked before publication and again on downloaded draft assets. Missing
configuration, unsigned files or invalid signatures fail closed. Local test
distributions remain explicitly unsigned development builds.

Outstanding production acceptance: server XML validation against actual
GitHub artifacts, Foundation approval, approved certificate policy and online
chain/timestamp validation of genuinely signed final binaries. The current
unsigned preserved build was inspected with Windows Authenticode APIs and
reported `NotSigned`, as expected. Production verification rejects it.
