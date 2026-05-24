# Google Workspace: SAML 2.0 (IdP) setup

This document describes how to configure **Google Workspace** as a **SAML 2.0 identity provider** (IdP) for a custom application using the [Google Admin console](https://admin.google.com/). Attribute names, menus, and screenshots change over time; when in doubt, use Google’s own admin help for *SAML* or *SSO*.

**Munki Manager note:** The application’s **built-in** SSO is **OpenID Connect** only (`AUTH_MODE=oidc`), not SAML. There are no `/saml/acs` or similar endpoints in this repository. If you need users to sign in with **SAML to Google** but Munki Manager to accept **OIDC** (or headers), you typically deploy an **identity or reverse proxy** in between (for example a product that speaks SAML to Google and OIDC or trusted headers to the app), or you use a separate IdP that federates to Google with SAML. For **direct** Google + Munki Manager SSO, use an **OAuth 2.0 / OIDC** client in Google Cloud; see [users-and-auth.md](users-and-auth.md) and the OIDC variables in `.env.example`. The steps below are still the right way to set up **Workspace ↔ SAML** for whatever **service provider** (SP) you are integrating.

---

## 1. Prerequisites (Google Workspace)

- A **super administrator** (or a delegated admin with permission to manage **Apps** and **Web and mobile apps** / SAML) can create the SAML app.
- Know which **users or groups** should be allowed to launch the app (all users, or a subset via organizational units / groups, depending on your policy).

---

## 2. Add a custom SAML app

1. Sign in to [Google Admin](https://admin.google.com/) as a super admin.
2. Open **Apps** → **Web and mobile apps** (or **App access control**, depending on your admin UI version).
3. Choose **Add app** → **Add custom SAML app** (wording may be *Add a SAML app* or *SAML*).
4. **App name**
   Enter a name your users will see (for example `Munki Manager` or the name of your identity bridge), optional description, and an icon if you want.
5. **Google IdP** — Google will show the values your **service provider** needs. **Download** the **IdP metadata** (XML) if the SP can import it; otherwise copy:
   - **SSO URL** (sometimes labeled *SAML 2.0 endpoint* or *Sign-in URL*)
   - **Entity ID** (IdP *Issuer*)
   - **X.509 certificate** (or multiple certificates; note **primary** vs **rollover** if Google offers both)

6. **Service provider** — On the same wizard you will enter the SP details **your application vendor or proxy** gives you. Typical fields:

| Field | Purpose |
|--------|--------|
| **ACS URL** (Assertion Consumer Service) | The HTTPS URL where the SP receives the SAML `POST` response. Must be **exact** (trailing slash rules depend on the SP). |
| **Entity ID** (Audience / SP entity ID) | A URI the SP expects in the `AudienceRestriction` of the assertion (often a URN or `https://` identifier). |
| **Name ID format** | Often **PERSISTENT**, **UNSPECIFIED**, or **EMAIL** / *Primary email* — your SP’s documentation will specify. |
| **Start URL** (optional) | If users should land on a specific path when opening the app from the Google app launcher, set the SP’s recommended URL. |
| **Signed response** (if offered) | Many SPs require the IdP to sign assertions; keep **on** unless the SP says otherwise. |

7. **Attribute mapping**
   Map Google directory attributes to SAML attributes the **SP** expects. Common needs:

| Google attribute | Typical SAML *Name* (examples — follow your SP) |
|------------------|-----------------------------------------------|
| *Primary email* | `email`, `mail`, or `NameID` as email |
| *First name* / *Last name* | `firstName` / `lastName` or a single `displayName` |
| *Google unique user ID* | sometimes `sub` or `name_id` (SP-specific) |

The SP’s SAML metadata or setup guide lists **exact** claim names; mismatches are a frequent source of `Invalid audience` or missing email errors on the SP side.

8. **Finish** the wizard, then set **ON for everyone** or limit to an **organizational unit** or **group** (recommended for least privilege).

---

## 3. After creation

- **User access:** Confirm the right OUs/groups are enabled for the SAML app.
- **SSO / session behavior:** If your org uses a third-party IdP in front of Google, or strict session policies, test sign-in the way end users will (browser, managed devices, private window).
- **Certificate updates:** If Google shows certificate **expiry** or **rollover**, update the copy stored on the SP (or in your proxy) before the old cert stops working; many SPs allow two certs during rotation.
- **Testing:** Google Admin may offer a **SAML** test (or a link to *Test Single Sign-On*). The SP’s documentation may also describe capturing a failed assertion for support.

---

## 4. Common problems

| Symptom | What to check |
|--------|----------------|
| **403 / audience invalid** (SP) | `Entity ID` in Google (Audience) must match the SP’s expected **Entity ID** exactly. |
| **No email / Name ID wrong** | Attribute mapping and **Name ID** format; many apps require **Name ID** = *Primary email*. |
| **HTTP POST to wrong host** | **ACS URL** in Google must match the SP (including `https` and path); typos and trailing slashes break ACS. |
| **Clock / NotBefore** errors | NTP and time sync on the SP; rare but check if assertions are “not yet valid.” |
| **App not visible in launcher** | App access: OU/group, and whether the app is only enabled for a subset of users. |

---

## 5. Munki Manager: OIDC alternative (no SAML in-app)

| Goal | Suggestion |
|------|------------|
| **Google sign-in to Munki Manager** (native app SSO) | Use `AUTH_MODE=oidc` with a **Web** OAuth client in **Google Cloud** and Google’s **OIDC** endpoints, not the SAML app in Admin. See [users-and-auth.md](users-and-auth.md#oidc-auth_modeoidc) and `OIDC_*` in `.env.example`. |
| **Workspace SAML must** be the protocol | Use a **reverse proxy** or **identity product** in front of Munki Manager that implements SAML to Google and something the app can use (for example **OIDC** to the app, or **JWT in headers** if you extend or integrate carefully). The stock app only documents **JWT and OIDC** for the API and UI. |

---

## Related

- [users-and-auth.md](users-and-auth.md) — Munki Manager auth modes, first admin, RBAC
- [deployment.md](deployment.md) — public URL, reverse proxy, `PUBLIC_APP_URL`
- [Google Help — Set up a custom SAML app](https://support.google.com/a/answer/6087519) (primary reference; UI may differ slightly)
