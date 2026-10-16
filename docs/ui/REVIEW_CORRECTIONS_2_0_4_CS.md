# Revize dodaného GUI auditu 2.0.4

Podklad: `PhaseStudio_2.0.4_kompletni_revize.zip`, zejména
`REVIZE_Phase_Studio_2.0.4.md`. Audit hodnotí dřívější snímky, nikoli aktuální
zdrojový kód. Tento dokument neoznačuje celý audit ani vydání za uzavřené.

## Opravené potvrzené chyby

- **R06, část R21:** About citovalo pevně verzi 2.0.2. Citace nyní používá
  `version.VERSION` přes existující `__version__`. Nový test vyhodnocuje skutečný
  HTML výraz také s budoucí verzí, aby zabránil dalšímu zastarání.
- **R14:** text správy klíče doporučoval odškrtnout Remember i bez dostupného
  bezpečného úložiště. Nyní v tomto stavu vysvětluje použití pouze pro relaci.
  Test skutečného dialogu kontroluje neaktivní checkbox i text. Ukládání,
  mazání, OAuth a tokeny se nemění.

## Porovnání s aktuálním kódem

- **R01/R02:** již opravené před přijetím této revize: kompaktní Wizard,
  doporučená karta, čtyři vědecké SVG včetně schváleného Autosolve B.
  Viz `JANA_WIZARD_SCIENTIFIC_ICONS_2_0_4.md` a příslušná galerie.
- **R03:** odlišné presety nejsou samy o sobě regresí. Wizard používá
  `sharped_model_for_cycles`: PEAK A pro jeden cyklus, SEED pro více cyklů.
  Plná konfigurace umožňuje serverový default; preflight v `app.py`
  (`on_success` v remediation loop) jej převádí na konkrétní ID před během.
  Záměrně nesjednocujeme vědecké presety bez samostatného rozhodnutí.
- **R04:** Wizard již má upozornění na 0 % i damping 0 ve vazbách ovladačů.
  Výpočet také podmiňuje operace kladnými hodnotami. Stejná explicitní
  prezentace v plné konfiguraci zůstává otevřená.
- **R05:** rozpor pochází z řízených fixture; snímek neprokazuje chybu
  produkčního stavového modelu. Samostatný runner průběhu prošel 18 kontrolami.
  Starou galerii nelze považovat za nový živý běh.
- **R11:** skutečné hlavičky tabulky již mají definice metrik, nezkrácené
  hodnoty a rozlišení doporučeného kandidáta od označeného řádku v tooltipech.
  Navržená změna poměrů a toolbaru zatím provedena nebyla.

## Otevřené části — bez předstírání akceptace

| Revize | Zbývající práce |
|---|---|
| R07/R24 | Responzivita fullscreen, fyzický monitor a přístupnost. |
| R08/R15 | Živé Jana předání, overlay, OAuth lifecycle a dlouhý serverový běh. Historické přihlášení nepokrývá všechny scénáře. |
| R09/R10 | Rozšířená sada skutečných struktur a rozhodnutí o volitelné CPK paletě. |
| R12/R13 | Stavové rozložení execution/standalone a prázdné stavy. |
| R16 | Ověření skutečných Jana/portable binárek a distribučních oprávnění. |
| R17 | Úplné ověření obou větví map feedbacku a jejich terminologie. |
| R18/R19/R20 | Další HKL hierarchie, reálný velký dataset a měření odezvy. |
| R21 | Ostatní kredity a právní/bibliografické podklady; oprava verze sama je neověřuje. |
| R22/R23/R25 | Splash, umístění aktualizací a reorganizace nápovědy. |

V tomto průchodu nebyly měněny vědecké algoritmy, souřadnice, mapy, EDMA,
parametry workflow, export ani protokol předání do Jany. Nebyl proveden
commit, push ani publikace. Protokoly kontrol jsou v
`build/acceptance-review-2.0.4/`.

## Provedené kontroly

- Kompletní pytest sada: **355 passed, 1 skipped, 37 subtests passed**,
  296,81 s. Nový samostatně přidaný test skutečného HTML citace poté **1 passed**;
  nebyl zahrnut v již zahájeném sběru této kompletní sady.
- Přístupový dialog a vědecké ikony: **33 passed**.
- About a map feedback: **16 passed, 1 skipped, 5 subtests passed**.
- Vynechaný opt-in test byl následně spuštěn s uchovaným skutečným vstupem
  ochlor: **1 passed**. Nejde o nový výpočet ani živé předání.
- Samostatný katalog/modely Wizardu: **44 kontrol passed**.
- Samostatný průběh: **18 kontrol passed**.
- Vědecké golden kontroly: **46 kontrol passed**.
- `git diff --check`: bez chyb; pouze upozornění na budoucí LF/CRLF převod
  již rozpracovaných souborů.
