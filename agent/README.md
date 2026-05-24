# Munki Manager client agents

## Swift postflight (`src/` + `Makefile`)

Layout matches the palantiri-client pattern: **`Makefile`** and **`src/`** for Swift sources.

```bash
cd agent
make build                 # universal binary → build/postflight
make install-local         # unsigned copy to /usr/local/munki (sudo)

# Installer package (unsigned — no Apple Developer IDs required)
make pkg                   # → build/munki-manager-client-$(VERSION).unsigned.pkg
sudo installer -pkg build/munki-manager-client-1.0.unsigned.pkg -target /   # 1.0 = VERSION in Makefile

# Signed release (set DEV_CODESIGN_ID + DEV_PKG_SIGN_ID in repo .env or environment)
make package               # build → codesign binary → stage payload → pkgbuild → productsign
make                       # same as full chain: build sign install package
```

Package identifier: `com.munkimanager.pkg.munki-manager-client`. Optional **`scripts/`** (e.g. `preinstall`) is passed to `pkgbuild` when that directory exists — see comments at the top of **`Makefile`**.

Set **`PRODUCT_ARCHIVE=True`** for a distribution-style product archive (`productbuild` + `distribution.xml`) instead of a single signed component pkg.

### Configuration

No extra preference: postflight reads **`SoftwareRepoURL`** (same as Munki) and POSTs to **`{origin}/api/v1/reports/checkin`**, where `origin` is scheme + host + port only (repo path is stripped). This matches Munki Manager’s single-origin setup (repo and API on the same host, the frontend proxying `/api/*`).

The easiest way to set `SoftwareRepoURL` on a managed Mac is the self-service enrollment flow: an admin creates a one-time token in **Settings → Client enrollment tokens**, hands the URL to the user, and the user downloads a generated `.mobileconfig`. See [`docs/client-onboarding.md`](../docs/client-onboarding.md) for the full walkthrough and the `defaults write` alternative.

If `SoftwareRepoURL` is missing or not a usable HTTP(S) URL, the script exits 0 so Munki is not blocked.

**Troubleshooting:** The Reporting page only triggers **GET** `/reports/machines` and `/reports/compliance` — that is *not* a client check-in. Confirm the server sees **POST** `/api/v1/reports/checkin`. On the Mac, stderr from postflight goes to Munki’s context (e.g. `syslog` / Console); on success you should see `munki_manager_postflight: check-in OK 200 ...`.
