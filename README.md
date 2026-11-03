# Tutor

A parent-managed digital notebook. Children write freely with a stylus across a full page; Python reconstructs the page and, in later milestones, interprets and checks the mathematics.

**Current state: Milestone 1.** A working multi-page notebook in the browser, built on the Digital Ink contract. A public website sits at `/`. There is no handwriting recognition, grading, login or family account yet. Track the project in [docs/STATUS.md](docs/STATUS.md); detailed evidence is in [docs/PROGRESS.md](docs/PROGRESS.md).

## Run it on Windows with Docker Desktop

Requires Docker Desktop. Python and Node are not needed on the host. In PowerShell, from the repository root:

```powershell
Copy-Item .env.example .env
notepad .env          # replace both secrets with your own random values
docker compose up -d --build --wait web
```

The website is at <http://localhost:8000/>. Open <http://localhost:8000/notebook/> and write with a mouse or stylus. Use **Move page** and the zoom buttons to get around a page, and **New page** for more. **Save page** asks Python to rebuild the page from the stored operations and compares the result with the browser's.

If port 8000 is taken, set `WEB_PORT` in `.env`. Postgres is not published to the host, so it cannot clash with other projects.

Stop with `docker compose down`. Add `-v` to delete the local database as well.

### Testing on a real tablet

The prototype has no authentication, so it only listens on this PC by default. On a network you trust, set these in `.env` and run the `up` command again:

```
WEB_BIND=0.0.0.0
DJANGO_EXTRA_ALLOWED_HOSTS=<your PC's LAN IP>
```

Then open `http://<your PC's LAN IP>:8000/notebook/` on the tablet. Use adult test writing only, never a child's. Set `WEB_BIND` back to `127.0.0.1` afterwards.

## Tests

```powershell
docker compose run --rm web pytest
docker compose run --rm web sh -c "ruff check . && ruff format --check . && mypy ."
docker compose run --rm --no-deps web python scripts/validate_contracts.py
docker compose --profile js run --rm js
docker compose --profile e2e run --rm --build e2e
```

End-to-end tests run on Chromium, Firefox and WebKit. The first build downloads all three and takes several minutes, and a full run takes about five minutes.

## Layout

| Path | Purpose |
|---|---|
| `contracts/` | Versioned schemas and fixtures shared by every platform |
| `apps/notebooks/ink/` | Python ink core, with no Django imports |
| `apps/notebooks/` | Journal storage, sync rules, prototype HTTP API |
| `apps/pages/` | Public website, at `/` |
| `static/js/ink/` | Browser ink core and writing interface |
| `firmware/elecrow_esp32p4/` | Hardware profile only; there is no firmware yet |
| `docs/` | Specifications, decisions, risks and progress |
