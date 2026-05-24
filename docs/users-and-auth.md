# Users and authentication

Munki Manager uses **FastAPI Users** with either **JWT** (email + password) or **OIDC** (SSO). Access to the UI and API is enforced with **JWTs** and **page-level RBAC** (see `/admin/access` for roles).

## Environment variables (summary)

| Variable | Meaning |
|----------|---------|
| `AUTH_MODE` | `disabled` — no login (dev-style; synthetic full-access user for API/UI). `jwt` — email/password only. `oidc` — SSO + optional password accounts. |
| `AUTH_REGISTRATION_OPEN` | When `true`, new accounts can be created via the UI and `POST /api/v1/auth/register`. When `false`, that endpoint returns **403** (see [Closed registration](#closed-registration)). Ignored for `AUTH_MODE=disabled` (registration is never offered). |

`GET /api/v1/auth/config` returns `auth_mode` and `registration_open` so the SPA reads these values at runtime.

## Creating users

### Development (`AUTH_MODE=disabled`)

There is **no database user** and no sign-in. The API uses a synthetic **superuser** principal (`GET /auth/me` reports `is_superuser: true`, legacy `role: "admin"`, and full page **write** permissions). `request.state.user` carries the same principal so RBAC-aware handlers (for example deleting a user under **Access**) see an authenticated superuser. Use this only on trusted machines.

### Email and password (`AUTH_MODE=jwt`)

1. Set `AUTH_MODE=jwt`, `SECRET_KEY`, and `DATABASE_URL`.
2. Run migrations (`alembic upgrade head`).
3. If `AUTH_REGISTRATION_OPEN=true` (default in `.env.example`), open **`/register`** in the app, or call **`POST /api/v1/auth/register`** with JSON:

   ```json
   {
     "email": "you@example.com",
     "password": "your-secure-password",
     "display_name": "Your Name"
   }
   ```

   `display_name` is optional. The UI enforces a minimum password length (8 characters); align with whatever the API accepts (see Swagger at `/api/docs`).

4. New users get a **Viewer** role membership (`on_after_register` in the API). That role is **read-only** on most pages and **cannot** open **`/admin/access`** (no `admin.access` permission). See [First operator / admin access](#first-operator--admin-access) below.

5. Sign in at **`/login`** (`POST /api/v1/auth/login` with form body `username` + `password` per OAuth2 password flow).

### OIDC (`AUTH_MODE=oidc`)

Configure the OIDC endpoints and `PUBLIC_APP_URL` / IdP redirect URLs as in `.env.example`. Users typically sign in with **SSO**; the **first successful login** can create a local user record linked to the IdP subject. You can still allow **password registration** via `/register` when `AUTH_REGISTRATION_OPEN=true` (useful for break-glass or mixed setups).

### Closed registration

When `AUTH_REGISTRATION_OPEN=false`:

- **`POST /auth/register`** returns **403** (“Registration is closed”).
- There is **no admin UI** to type a new email/password for a user; existing users are managed under **`/admin/access`** (roles and permissions only).

Practical options for new people:

1. **OIDC** — add them in your IdP; they sign in when they first appear (account is created on first login).
2. **Temporarily** set `AUTH_REGISTRATION_OPEN=true`, create accounts, then set it back to `false` and restart the API.
3. Advanced: insert or script users via the database / FastAPI Users APIs (not documented here; prefer OIDC or a short registration window).

## First operator / admin access

The **Viewer** role cannot use **`/admin/access`**. After you create the **first** account (or any account that should manage roles), grant full control in one of these ways:

### Option A — Superuser flag (simplest)

In PostgreSQL, set the FastAPI Users **superuser** column on that user’s row (superusers get **write** on every page key):

```sql
UPDATE "user" SET is_superuser = true WHERE email = 'you@example.com';
```

Permission checks read `is_superuser` from the database on each request, so you can use **`/admin/access`** immediately after updating (refresh the page if the UI still shows the old menu).

### Option B — Administrator role

Insert a row into **`user_role`** linking the user to the seeded **Administrator** role (see migration `r2s3t4u5v6w7_add_rbac_tables_oidc.py` for the fixed UUID `a1111111-1111-4111-8111-111111111103`), or copy the role id from `SELECT id, name FROM role WHERE name = 'Administrator';`.

After that, the user can open **`/admin/access`** and assign roles to others without raw SQL.

## Related documentation

- **[deployment.md](deployment.md)** — env vars and production notes.
- **[mac-mini-deployment.md](mac-mini-deployment.md)** — `AUTH_MODE` + `AUTH_REGISTRATION_OPEN` on shared networks.
- **[google-workspace-sso.md](google-workspace-sso.md)** — Google Workspace as a **SAML 2.0 IdP** (Admin custom SAML app). *Built-in* Munki Manager SSO uses **OIDC**; see *OIDC* above and `.env.example`.
- **[api-reference.md](api-reference.md)** — auth endpoints (`/auth/login`, `/auth/register`, `/users/me`).
