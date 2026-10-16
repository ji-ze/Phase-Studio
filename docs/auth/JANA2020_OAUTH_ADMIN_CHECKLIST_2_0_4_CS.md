> Historical investigation record. The subsequently supplied native-client contract and implementation are documented in [JANA2020_OAUTH_2_0_4.md](JANA2020_OAUTH_2_0_4.md). Earlier missing-configuration conclusions below are superseded.

# Podklady od správce Jana2020 / SharpED pro Phase Studio 2.0.4

Níže je zpráva určená správci. Potřebujeme veřejnou konfiguraci a popis rozhraní,
nikoliv hesla, `client_secret`, privátní podpisové klíče ani uživatelské tokeny.

---

Připravujeme přihlášení Phase Studio přes Jana2020 pomocí OAuth 2.0 Authorization
Code + PKCE S256. Uživatel se má přihlásit v běžném prohlížeči a aplikace má
automaticky získat access token použitelný pro SharpED bez ručního kopírování.

Jana2020 zveřejňuje OIDC discovery a web SharpED používá OAuth. Registrace
Phase Studio podle dostupné informace existuje, ale nemáme její konfiguraci.
Prosím o následující informace a potvrzení:

1. **Existující registrace Phase Studio.** Přesný veřejný `client_id`, název
   registrace, prostředí (test/produkce) a potvrzení, že jde o **public native
   desktop client**, který při výměně kódu nepotřebuje žádný `client_secret`.
   Potřebujeme `token_endpoint_auth_method=none`. Nepoužijeme webový klient
   `sharped` a nechceme vytvářet duplicitní registraci.

2. **Autorizační server.** Přesný `issuer`, discovery URL, `authorization_endpoint`
   a `token_endpoint`. Aktuálně jsou zveřejněny issuer `https://jana.fzu.cz`,
   discovery `https://jana.fzu.cz/.well-known/openid-configuration`, autorizace
   `https://jana.fzu.cz/oauth/authorize` a tokeny `https://jana.fzu.cz/oauth/token`.
   Prosím potvrďte, že platí také pro veřejný desktopový klient, a případně
   uveďte odlišnou konfiguraci testovacího prostředí. Identifikujte použitý
   OAuth/OIDC provider a jeho relevantní dokumentaci.

3. **Návrat z prohlížeče.** Přesná schválená loopback redirect URI a pravidla
   registrace portu. Navrhujeme `http://127.0.0.1:{ephemeral_port}/callback`:
   pouze lokální rozhraní, přesná cesta `/callback`, dynamicky přidělený port.
   Jde o návrh, nikoliv už ověřenou registraci. Potvrďte podporu proměnného
   portu podle RFC 8252 a případnou samostatnou podporu IPv6 loopbacku.

4. **Authorization Code + PKCE.** Potvrzení `response_type=code`, vynucení
   `code_challenge_method=S256` a secretless výměny kódu s `code_verifier`.
   Uveďte dobu platnosti a jednorázovost kódu, kontrolu přesného redirect URI,
   odmítání chybějícího/nesprávného verifieru a ochranu proti downgrade.
   Potvrďte podporu `state` a případně autorizačního response parametru `iss`.
   Veřejná metadata nyní uvádějí pouze `client_secret_post` a
   `client_secret_basic`; potřebujeme vysvětlit a vyřešit rozpor s veřejným
   klientem, nikoliv dostat secret k vložení do EXE.

5. **Scopes a audience pro SharpED.** Přesné minimální scopes a `audience` nebo
   `resource`, případné další standardní parametry a pravidla souhlasu.
   `openid profile email` pro identitu samy nepotvrzují oprávnění inference.
   Potvrďte, zda pro tento účel vůbec potřebujeme OIDC identitu, nebo stačí
   OAuth access token. Název inference scope/audience nechceme odhadovat.

6. **Kompatibilita SharpED API.** Potvrďte, zda stávající upload/status/download
   `/api/user/sharp-ed/...` přijmou získaný OAuth **access token** v
   `Authorization: Bearer`. Pokud ne, popište potřebnou serverovou úpravu nebo
   dokumentovanou výměnu tokenu. ID token se nesmí používat jako API credential.
   Potvrďte souběžnou funkčnost dosavadních ručně generovaných API tokenů,
   kontrolu vlastnictví úloh a zachování současných inference endpointů.

7. **Bezplatná kontrola přístupu.** URL, metoda, požadované scopes a ukázka
   neobsahující citlivé údaje pro endpoint, který ověří token a oprávnění
   SharpED, aniž vytvoří úlohu, přijme mapu, spotřebuje kvótu nebo účtuje
   inference. Potřebujeme response schema a významy chyb: nepřihlášený,
   expirovaný/neplatný token, chybějící oprávnění, nedostupná služba. Veřejný
   seznam modelů není ověření tokenu.

8. **Oprávnění a předplatné.** Jak API vyhodnocuje právo na SharpED a změny
   účtu/předplatného; které serverové odpovědi jednoznačně prokazují odmítnutí
   oprávnění. Úspěšné přihlášení nesmí automaticky znamenat inference přístup.
   Aplikace nebude odhadovat ani pevně definovat tarifní plány.

9. **Ověřování tokenů a případné OIDC.** Formát access tokenu (JWT/opaque),
   serverová validace issuer/audience/expiry/scopes a případná introspekce.
   Pokud použijeme OIDC, potřebujeme podporované asymetrické podpisové
   algoritmy, `jwks_uri`, rotaci klíčů, nonce a pravidla ID-token claims;
   případně `userinfo_endpoint`. Současná metadata uvádějí pouze HS256 a
   neuvádějí JWKS. Sdílený HS256 podpisový secret nesmí být distribuován
   v desktopové aplikaci. Alternativou je OAuth-only tok bez ID-token identity.

10. **Platnost a obnova přihlášení.** Doba platnosti access tokenu, dostupnost
    refresh tokenů pro veřejný klient, potřebné scopes, podporovaný grant,
    rotace, doba nečinnosti/celková životnost a reakce na opětovné použití nebo
    odvolání. Metadata refresh grant nyní neuvádějí. Potřebujeme také pravidla
    bezpečné souběžné obnovy při více SharpED operacích.

11. **Odhlášení a odvolání.** Dokumentovaný revocation endpoint, požadavky na
    veřejného klienta a rozsah odvolání access/refresh tokenů. Pokud je
    podporováno OIDC logout, dodejte jeho dokumentaci a odlište odhlášení
    aplikace od ukončení sdílené browser session Jana2020. Lokální odstranění
    credentials musí zůstat možné i bez dostupného serveru.

12. **Testovací prostředí.** Testovací issuer/client/redirect/scopes/audience,
    podmínky pro test přístupu bez placených úloh a způsob připravení testovacích
    účtů s povoleným i zamítnutým přístupem. Potřebujeme ověřit přihlášení,
    callback, token exchange, API oprávnění, expiraci, refresh, revokaci a nové
    přihlášení ve Windows standalone i v Jana2020 ONEDIR. Uživatel zadává
    přihlašovací údaje pouze v prohlížeči; neposílá je vývojovému asistentovi.

13. **Pravidla nasazení.** Potvrďte možnost použití registrace pro veřejně
    distribuovanou Phase Studio, schválení produkčního klienta a kontakt na
    správce pro konfiguraci a bezpečnostní chyby. Dodejte redigovanou ukázku
    authorization requestu a token request/response, s placeholdery namísto
    skutečných kódů a tokenů; uvedené parametry musí odpovídat registraci.

Nejnaléhavější pro první browser-to-desktop test jsou body **1–7** a testovací
konfigurace z bodu **12**. Body **8–11 a 13** potřebujeme před produkčním
zapnutím; OIDC podrobnosti se použijí jen tehdy, pokud bude OIDC součástí řešení.

Prosím neposílejte hesla, secrets, privátní klíče ani skutečné uživatelské tokeny.
Veřejný `client_id`, URL a pravidla scopes/redirectu jsou správné podklady.
