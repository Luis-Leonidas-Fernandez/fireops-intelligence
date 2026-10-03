# Dashboard frontend

Padre Nuestro dashboard demo served by Fire Control. Its analytics remain **sample data**; the only Fire Control integration is a small API connection indicator and a live category count. This demo does not display inventory assets or use production data.

## Structure

- `index.html` — semantic page structure and script/style entry points.
- `css/tokens.css` — color, type, spacing, and global design tokens.
- `css/layout.css` — responsive shell and page layout.
- `css/components.css` — navigation, cards, charts, table, and control styling.
- `js/data.js` — static demonstration metrics.
- `js/render.js` — presentation of those metrics in the DOM.
- `js/app.js` — local UI events, filters, date selection, CSV export, and a read-only Fire Control connection check.

## Run locally

From the project root, start the frontend and API together in one terminal:

### macOS / Linux

```bash
./scripts/test-up.sh
```

### Windows PowerShell

```powershell
.\scripts\test-up.ps1
```

Open `http://127.0.0.1:8000/`. Stop the server with Ctrl+C. The `test-up` scripts require an existing `.venv` and `.env.test`, verify that the configured database is named `fireassets_test`, and start FastAPI on loopback. They do **not** run migrations. Do not use the normal `.env` to start the API for this demo.

The page requests `GET /health` and then `GET /inventory/categories` on the same origin. The API docs remain at `/docs`. No credentials or write requests are sent. If the API or test database is unavailable, the status says so and the sample dashboard still works.

The analytics, navigation labels, and secondary controls remain demonstrations rather than live inventory or separate routes. The category count is the only value read from the backend.
