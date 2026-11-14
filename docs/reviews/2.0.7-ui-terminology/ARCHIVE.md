# Historical terminology evidence

Eight generated inventories (8,036,680 bytes before ZIP metadata; exact individual
sizes are in ARCHIVED_EVIDENCE.json) are archived outside maintained source.
No experimental dataset or legal notice is removed. Original Git history remains
available at snapshot `9458722d48f1ed0a0e198ff95635f7897782559e`; the first inventory
commit was `a1c6b0255eb0868561d4eb9ddbb6260c3b86cd2e`. These identifiers locate
historical evidence, not a claim that it was generated from the later snapshot.

Archive: `terminology-evidence-9458722.zip`, 8,038,166 bytes.
SHA-256: `ad08e33db66d1b9a97c5269d44a86a65630d98cc8fab0a01c6b3554b8c2ee7ad`.
Every original file and canonical Git blob has its own SHA-256, byte count and
lossless line-ending restoration rule in ARCHIVED_EVIDENCE.json. The ZIP uses
stored entries, fixed timestamps, sorted names and fixed permissions so it is
deterministic across platforms without relying on a compression-library version.

Restore the historical original bytes without rerunning a scientific calculation:

```powershell
git fetch origin
python packaging/tools/archive_terminology_evidence.py --output build/terminology-evidence-9458722.zip
```

The output must be new; the command refuses replacement and verifies the complete
archive digest. The original accepted source snapshot remains available. The
manual GitHub workflow `scientific-audit-evidence.yml` performs the same export
and publishes it as a 90-day Actions artifact. The final development acceptance
archive also includes the historical ZIP. No release workflow is triggered.

Fresh **current-source** inventory capture remains available:

```powershell
$env:PYTHONHASHSEED = '0'
$env:QT_QPA_PLATFORM = 'offscreen'
$env:QT_SCALE_FACTOR = '1'
$env:PHASE_STUDIO_TERMINOLOGY_OUTPUT = "$PWD/build/ui-terminology-current"
python docs/reviews/2.0.7-ui-terminology/build_inventory.py
python docs/reviews/2.0.7-ui-terminology/build_findings.py
```

Fresh observations depend on the source, Qt/font versions and controlled fixture
environment; they are not represented as byte-identical regeneration of the old
capture. Only the historical Git-blob restoration command makes that guarantee.
The generators default to ignored build output so ordinary use does not restore
large generated files into a pull request.
