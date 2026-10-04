# Fire Control frontend demo

The frontend is plain HTML/CSS/JavaScript served by the FastAPI application on the **same origin** as the API. No React, Vite, second server or production authentication is in use.

## Pages and behavior

| URL | Current behavior |
|---|---|
| `/` | Dashboard with **illustrative** inventory figures |
| `/registro` | Registration visual demo |
| `/iniciar-sesion` | Sign-in visual demo |

Submitting either account form or clicking its Google icon navigates to `/` without sending or validating credentials. The dashboard's “Cerrar sesión” button navigates to `/iniciar-sesion`; there is no session to invalidate. The root URL still opens the dashboard directly. These screens are **not access control**.

The dashboard fetches `GET /health` and `GET /inventory/categories` for an API connection indicator and live category count. Other figures, charts, movements, alerts, filters and exported CSV are demonstration data. Sidebar items do not navigate to implemented inventory pages.

The dashboard has a dark/light toggle in the app bar. It changes the current page theme; it does not save the choice across reloads. The red accent is defined in dashboard CSS tokens, while the account pages use their own stylesheet.

## Files

- `index.html` — dashboard markup and versioned asset links.
- `css/tokens.css`, `css/layout.css`, `css/components.css`, `css/theme-light.css` — dashboard styling and light mode.
- `js/data.js`, `js/render.js`, `js/app.js` — sample data, rendering and UI events, including logout navigation.
- `pages/registro/index.html`, `pages/iniciar-sesion/index.html` — separate account pages.
- `css/registro.css`, `js/registro.js`, `js/iniciar-sesion.js` — account-page styling and demo navigation.

## Run locally

Create `.env.test` for `fireassets_test`, install dependencies into `.venv`, start PostgreSQL and apply the committed migration to the test database. Then, from the repository root:

```bash
./scripts/test-up.sh
```

```powershell
.\scripts\test-up.ps1
```

The scripts use `.venv` without manual activation, verify the database name in `.env.test`, and start Uvicorn on `http://127.0.0.1:8000`. They do not create databases or run migrations. Stop with `Ctrl+C`. The clickable Uvicorn URL opens `/`, not `/iniciar-sesion`; open the latter explicitly to view the sign-in demo. Swagger UI remains at `/docs`.

HTML/CSS/JS responses use `Cache-Control: no-store` and the dashboard references versioned assets to prevent stale browser copies. If a page was already open before an edit, reload it.
