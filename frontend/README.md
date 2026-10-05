# Fire Control frontend demo

The frontend is plain HTML/CSS/JavaScript served by the FastAPI application on the **same origin** as the API. No React, Vite or second server is in use. Account pages authenticate; inventory API authorization is still pending.

## Pages and behavior

| URL | Current behavior |
|---|---|
| `/` | Dashboard with **illustrative** inventory figures |
| `/registro` | Email/password or Google registration |
| `/iniciar-sesion` | Email/password or Google sign-in |

Submitting either account form sends validated credentials to the backend. Google buttons start the server-side OAuth flow. Success establishes the existing HttpOnly session cookie; `/` redirects to sign-in without a valid cookie. Existing password accounts must sign in and choose **Vincular Google** from the dashboard profile menu; matching verified email is required. “Cerrar sesión” requests cookie removal and returns to sign-in. Inventory API endpoints remain public.

The dashboard fetches `GET /health` and `GET /inventory/categories` for an API connection indicator and live category count. Other figures, charts, movements, alerts, filters and exported CSV are demonstration data. Sidebar items do not navigate to implemented inventory pages.

The app bar fetches `GET /auth/me` using the local session cookie and displays the authenticated user's name, or their email when no name is stored. Registration can optionally collect a display name; Google sign-in uses the verified profile name when available. The app bar never uses a sample person's name.

The dashboard has a dark/light toggle in the app bar. It changes the current page theme; it does not save the choice across reloads. The red accent is defined in dashboard CSS tokens, while the account pages use their own stylesheet.

## Files

- `index.html` — dashboard markup and versioned asset links.
- `css/tokens.css`, `css/layout.css`, `css/components.css`, `css/theme-light.css` — dashboard styling and light mode.
- `js/data.js`, `js/render.js`, `js/app.js`, `js/profile.js` — sample data, rendering, authenticated profile, logout and explicit Google linking.
- `pages/registro/index.html`, `pages/iniciar-sesion/index.html` — separate account pages.
- `css/registro.css`, `js/auth-form.js`, `js/validations/credentials.js` — account-page styling, shared form flow and validation.

## Run locally

Create `.env.test` for `fireassets_test`, install dependencies into `.venv`, start PostgreSQL and apply the migrations present in the repository to the test database. Then, from the repository root:

```bash
./scripts/test-up.sh
```

```powershell
.\scripts\test-up.ps1
```

The scripts use `.venv` without manual activation, verify the database name in `.env.test`, and start Uvicorn on `http://127.0.0.1:8000`. They do not create databases or run migrations. Stop with `Ctrl+C`. The clickable Uvicorn URL opens `/`, which redirects to `/iniciar-sesion` without a valid session. Swagger UI remains at `/docs`. For Google credentials and callback setup, see [Google OAuth](../docs/getting-started/google-oauth.md).

HTML/CSS/JS responses use `Cache-Control: no-store` and the dashboard references versioned assets to prevent stale browser copies. If a page was already open before an edit, reload it.

From the repository root, run the frontend form and authenticated-profile tests with `node --test`.
