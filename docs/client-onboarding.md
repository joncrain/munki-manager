# Onboarding a Mac client

This is the end-to-end path for pointing a Mac at a Munki Manager server so that
[Munki](https://github.com/munki/munki) pulls its catalogs/manifests from here
and (optionally) reports check-ins back.

There are three ways to onboard, in increasing order of scale:

1. **Self-service walkthrough** — send the user a link, they install a
   generated configuration profile. *Best for small teams and one-offs.*
2. **Manual `defaults write`** — run a couple of commands (or a script) on the
   Mac. *Fine for lab machines or CI workers.*
3. **MDM-deployed profile** — bake the same profile into your MDM and push it
   to every Mac. *Best at scale.*

All three options produce the same thing: a small set of Munki preferences in
the `ManagedInstalls` domain.

## What a client needs

| Preference | Domain | Required? | Value |
|---|---|---|---|
| `SoftwareRepoURL` | `ManagedInstalls` | Yes | `https://<your-server>/repo` (no trailing slash) |
| `ClientIdentifier` | `ManagedInstalls` | No | Munki manifest name; defaults to hostname |
| `PackageURL` | `ManagedInstalls` | When packages live off-app | e.g. `https://pkgs.example.com/pkgs`; managed in **Settings → Package & client resource URLs** (or pinned via `MUNKI_REPO_PKG_BASE_URL`) |
| `ClientResourceURL` | `ManagedInstalls` | Optional | Only when `client_resources/` lives on a different host than `pkgs/`; otherwise auto-derived from `PackageURL` |
| `AdditionalHttpHeaders` | `ManagedInstalls` | Only when repo Basic auth is enabled | `["Authorization: Basic <base64>"]` |

Catalogs, manifests, and icons are served from the app under `/repo/…`.
**Packages** and **client resources** are served by whatever host
`PackageURL` / `ClientResourceURL` point at (typically nginx on the same
box) — Munki fetches them directly. The app does not redirect or proxy
those requests because Munki's downloader drops `Authorization` headers
on cross-origin 302s.

Reporting back into Munki Manager is **separate** from the repo URL and is
optional. If you want this Mac to appear on the **Reporting** page, install
the small Swift postflight in [`agent/`](../agent/README.md); it reads the
same `SoftwareRepoURL` and POSTs to `/api/v1/reports/checkin`.

---

## Option 1 — Self-service walkthrough (recommended)

**Admin side:**

1. Open **Settings → Client enrollment tokens**.
2. Click **Create**. Optionally set a label and a Munki manifest name.
3. Copy the **Enrollment URL** that appears (the raw token is also shown).
   This is your only chance to see it.
4. Send the URL to the user.

**User side:**

1. Open the URL on the Mac you want to enroll. It looks like
   `https://munki.example.com/enroll?token=…`.
2. Click **Download .mobileconfig**. This consumes the token.
3. Double-click the downloaded file, then open **System Settings → Privacy
   & Security → Profiles** and click **Install**.
4. If Munki isn't installed yet, grab the latest
   [release](https://github.com/munki/munki/releases/latest) and run it.
5. Trigger the first check-in:

   ```bash
   sudo /usr/local/munki/managedsoftwareupdate --checkonly
   ```

Tokens are:

- **One-time**: redeeming sets `redeemed_at` and the server rejects reuse.
- **Short-lived**: default 24 h (configurable per token, up to 30 days).
- **Hashed at rest** (SHA-256); the plaintext is only ever shown to the admin
  who created it.

### What the generated profile contains

The server builds a standard `Configuration` profile (`PayloadScope` =
`System`) containing a single payload whose `PayloadType` is literally
`ManagedInstalls`. Each Munki preference is a sibling key at the top
level of that payload — there is **no** `com.apple.ManagedClient.preferences`
wrapper and **no** `Forced` / `mcx_preference_settings` nesting. Munki
reads these directly via CFPreferences.

```xml
<dict>
    <key>PayloadType</key>
    <string>ManagedInstalls</string>
    <key>PayloadIdentifier</key>
    <string>com.munkimanager.enroll.managed-installs.{uuid}</string>
    <key>PayloadUUID</key>
    <string>{uuid}</string>
    <key>PayloadVersion</key>
    <integer>1</integer>
    <key>PayloadEnabled</key>
    <true/>

    <key>SoftwareRepoURL</key>
    <string>https://munki.example.com/repo</string>
    <key>ClientIdentifier</key>
    <string>site_default</string>
    <!-- Optional: only when packages live off-app -->
    <key>PackageURL</key>
    <string>https://pkgs.example.com/pkgs</string>
    <!-- Optional: only when repo Basic auth is on -->
    <key>AdditionalHttpHeaders</key>
    <array>
        <string>Authorization: Basic &lt;base64&gt;</string>
    </array>
</dict>
```

### Embedding the `Authorization` header in the profile

When repo Basic auth is enabled, Munki Manager will bake
`AdditionalHttpHeaders` into the profile with the correct
`Authorization: Basic …` line so the user doesn't have to configure it. The
flow depends on where the password lives:

- **Env-var mode** (`MUNKI_REPO_BASIC_AUTH_USER` /
  `MUNKI_REPO_BASIC_AUTH_PASSWORD` set on the API): the server already has
  the plaintext. Nothing extra to do — every generated profile gets the
  header.
- **Settings UI mode** (DB-stored Argon2 hash): the server can't recover
  the plaintext from a hash, so when you **create** an enrollment token
  the UI asks you to enter the current repo password. Munki Manager verifies
  it against the hash, Fernet-encrypts it with the server's
  `SECRET_KEY`, binds it to that single token, and wipes it the moment
  the token is redeemed.
- **Basic auth off**: no header is embedded (and none is needed).

The “Token created” panel in the admin UI tells you whether the profile
will contain the header; the public `/enroll` page also mirrors this
(“profile will include the header” vs “ask your admin for credentials”).

---

## Option 2 — Manual `defaults write` on the Mac

For a quick one-off (e.g. a lab Mac), you can skip the profile and set the
preferences directly:

```bash
sudo defaults write /Library/Preferences/ManagedInstalls \
  SoftwareRepoURL "https://munki.example.com/repo"

# optional — pin to a specific manifest rather than using the hostname
sudo defaults write /Library/Preferences/ManagedInstalls \
  ClientIdentifier "site_default"

# optional — only when packages are hosted off-app (matches what the
# enrollment mobileconfig emits from the Settings UI)
sudo defaults write /Library/Preferences/ManagedInstalls \
  PackageURL "https://pkgs.example.com/pkgs"

# optional — only if repo Basic auth is enabled on the server
sudo defaults write /Library/Preferences/ManagedInstalls \
  AdditionalHttpHeaders -array \
  "Authorization: Basic $(printf 'munki:shared-secret' | base64)"

sudo /usr/local/munki/managedsoftwareupdate --checkonly
```

These writes are persisted to `/Library/Preferences/ManagedInstalls.plist`.
A configuration profile overrides these same keys, so mixing the two is
fine — the profile wins.

---

## Option 3 — MDM-deployed configuration profile

The mobileconfig generated by Option 1 is a regular, unsigned Apple
configuration profile. You can:

1. Generate it once (any valid token works) and download it.
2. Open it in your MDM's profile editor (Jamf, Kandji, Mosyle, Intune, etc.)
   and assign it to a Smart Group / Dynamic Group / all managed Macs.
3. Optionally re-sign it with an Apple Developer "Installer" certificate so
   macOS treats it as `verified` rather than `unsigned`.

On MDM-managed Macs the profile installs silently and there's no user
interaction required — this is the recommended path for fleets.

If you prefer to author the profile by hand, the minimum payload is the
`ManagedInstalls` snippet shown above, wrapped in a standard
`PayloadType=Configuration` profile.

---

## Installing the Munki Manager postflight (optional but useful)

The postflight makes Macs show up on the **Reporting** page with check-in
history, install reports, hardware info, and installed software.

See [`agent/README.md`](../agent/README.md) for the full build/install
instructions. The short version:

```bash
cd agent
make build
sudo make install-local   # copies build/postflight → /usr/local/munki/postflight
```

It reads `SoftwareRepoURL` from the same profile/preferences and POSTs to
`{origin}/api/v1/reports/checkin` at the end of every `managedsoftwareupdate`
run. **`POST /reports/checkin` is intentionally unauthenticated** (the route
is public in the RBAC middleware); serial numbers are the only key. If you
need to restrict it, front it with a reverse proxy that requires mTLS or a
shared token.

---

## Verifying a client is connected

On the Mac:

```bash
# preferences are live?
defaults read /Library/Managed\ Preferences/ManagedInstalls SoftwareRepoURL

# Munki can reach the repo?
sudo /usr/local/munki/managedsoftwareupdate --checkonly -v
```

On the server:

- **Reporting → Devices** lists the Mac within a minute of the first
  postflight run.
- The API log shows `POST /api/v1/reports/checkin 200` per check-in.
- `GET /repo/catalogs/all` over HTTPS returns a plist (use Basic auth if you
  enabled it).

---

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| Munki logs `Could not retrieve catalog all from server` | `SoftwareRepoURL` missing or wrong; test with `curl https://host/repo/catalogs/all`. |
| `401 Unauthorized` from `/repo/…` | Repo Basic auth is on and the profile doesn't include `AdditionalHttpHeaders`. Regenerate the profile with env-mode auth, or add the header manually. |
| `failed: error 302` during package download | The profile is missing `PackageURL` and your packages live off-app. Set it in **Settings → Package & client resource URLs** and re-enroll (or `defaults write PackageURL`). |
| `401 Unauthorized` downloading a package | Munki sends the repo's `AdditionalHttpHeaders` to the `PackageURL` host too. Either make those credentials work there as well, or strip `Authorization` at that host. |
| Mac never shows up on Reporting | The postflight isn't installed, `SoftwareRepoURL` is missing, or the origin isn't reachable. Check `/var/log/system.log` for `munki_manager_postflight:` lines. |
| Token download says "token already used" | Tokens are one-time by design; create a new one in **Settings**. |
| Token says "token expired" | Default TTL is 24 h; bump `TTL (hours)` when creating the token, or regenerate. |
