# SharpED service access and Phase Studio

Phase Studio is MIT-licensed desktop software. SharpED is a separate hosted
service; its terms do not license Phase Studio or distribute models/weights.

The owner supplied `SharpED_Online_Service_and_API_Terms_2026-10-13_FINAL.pdf`,
SHA-256 `343079ba5bc3f1a00dd0c7f30a0399943beb3b2874fb43c4e5e37967f1fedc36`.
It is summarized here, not redistributed without a provider-published URL.
Users must accept the actual current terms presented by the service.

The document distinguishes the web interface `https://sharped.fzu.cz/` from
the Public API `https://jana.fzu.cz/`. The canonical client base is the latter:
GET `/sharp-ed/models`, POST `/api/user/sharp-ed/upload`, and associated user
status/download routes. No internal worker API or split-host inference is used.
Both public catalogues were checked on 13 October 2026: UNIVERSAL,
SEED (cyclic CF), PEAK A (model prediction), PEAK B (model prediction), with
PEAK A as server default. No credential, upload or inference was used for this
catalogue audit. Authenticated inference on the documented host still requires
real-account acceptance.

Sign into a SharpED account, accept its current terms, obtain any required
entitlement and generate a personal token. Shared Jana account infrastructure
does not make acceptance of Jana software terms equivalent to SharpED acceptance.
The client uses bearer credentials and job tokens; keep them out of public
code, screenshots and diagnostic reports. Missing, expired or revoked tokens,
and entitlement/subscription denial, are service-access problems distinct from
scientific calculations. Valid credentials do not guarantee service availability.

The supplied terms allow no-service-fee preview until 31 October 2026 at
23:59 Europe/Prague, with no automatic paid conversion. Subsequent access and
fees depend on the provider; no permanent exemption or pricing tier is asserted.

HTTPS protects transmission; the service accesses plaintext during processing.
Submit only data you may share. Separate 60-minute active-server-storage timers
apply to input and inferred output maps from their respective upload times.
Queued inputs can expire; promptly download and independently retain results.
The terms prohibit using submitted scientific content for training, fine-tuning
or independent research, but do not claim that account metadata or all backups
share the map-deletion timer. Current service/privacy notices remain operative.
