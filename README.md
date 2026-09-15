# FrameByFrame

FrameByFrame is a daily movie-frame guessing game.

## Backend Setup

Requirements:

- Python 3.12
- Docker and Docker Compose

Create a local environment file from the example and set your own local values:

```bash
cp .env.example .env
```

Start PostgreSQL and the FastAPI backend:

```bash
docker compose up --build
```

The API container runs Alembic migrations and the idempotent reference-data seed before startup.
`database/schema.sql` is retained as a reference snapshot and is not executed by Docker.

The API will be available at:

```text
http://localhost:8000
```

The functional player frontend is available at:

```text
http://localhost:5173
```

Health check:

```text
GET http://localhost:8000/api/v1/health
```

Run tests locally:

```bash
pip install -e ".[dev]"
pytest
```

Run migrations and tests in Docker (without resetting the database volume):

```bash
docker compose run --rm api alembic upgrade head
docker compose run --rm api pytest
docker compose run --rm frontend npm test
docker compose run --rm frontend npm run build
```

The development gameplay API is available under `/api/v1/game`. It uses a
signed, HTTP-only guest cookie to resume one session per daily puzzle. Public
gameplay endpoints never include the movie title until a session is complete.

Configure the local gameplay environment with `GUEST_COOKIE_SECRET`,
`GUEST_COOKIE_SECURE`, and `GAME_TIMEZONE`. Use a long random cookie secret and
enable secure cookies when serving over HTTPS.

## Local puzzle authoring

Docker Compose enables the development-only admin tool and mounts `assets/scenes`
for processed image storage. Open `http://localhost:8000/admin/puzzles` after startup. Set
`ADMIN_ENABLED=false` to omit both the admin page and admin API routes.
Set a private `ADMIN_TOKEN`; the wizard requests it once per browser tab and
sends it in `X-Admin-Token` for every mutation. Admin authentication does not
use cookies, so there is no cookie-authenticated CSRF surface.

The Create Puzzle wizard stages WebP, PNG, and JPEG uploads under
`assets/scenes/.staging`, corrects image orientation, and converts accepted
files to WebP. Successful saves move them to
`assets/scenes/<generated-movie-slug>/<generated-id>.webp`. Configure upload
limits with `UPLOAD_MAX_BYTES`, `UPLOAD_RATE_LIMIT_PER_MINUTE`, and
`UPLOAD_WEBP_QUALITY`. Images remain accessible only through backend endpoints.

The unified content manager is available at
`http://localhost:8000/admin/content`. It keeps the Iconic Movies wizard
available and adds complete Badly Explained and Albumnesia authoring. Uploaded
source images are stored under opaque generated keys. Albumnesia text and
subject masks are stored as normalized `0..1` coordinates; previews never
modify the original stored image. Its selectable techniques are Pixel
Hangover, Sleeve Shredder, Channel Damage, Identity Crisis, and Outline Only.

Content manager API routes include:

```text
GET    /api/v1/admin/content
GET    /api/v1/admin/content/check-answer
POST   /api/v1/admin/content/badly-explained
POST   /api/v1/admin/content/albumnesia
GET    /api/v1/admin/content/{content_id}
PATCH  /api/v1/admin/content/{content_id}/badly-explained
PATCH  /api/v1/admin/content/{content_id}/albumnesia
POST   /api/v1/admin/content/{content_id}/image
GET    /api/v1/admin/content/{content_id}/image
POST   /api/v1/admin/content/{content_id}/duplicate
DELETE /api/v1/admin/content/{content_id}
```

No additional environment variables are required. The content manager reuses
`ADMIN_ENABLED`, `ADMIN_TOKEN`, `ASSET_ROOT`, `UPLOAD_MAX_BYTES`,
`UPLOAD_RATE_LIMIT_PER_MINUTE`, and `UPLOAD_WEBP_QUALITY`.

Wizard API routes include:

```text
POST   /api/v1/admin/uploads
GET    /api/v1/admin/uploads/{stage_id}/image
DELETE /api/v1/admin/uploads/{stage_id}
GET    /api/v1/admin/classifications
POST   /api/v1/admin/tags
POST   /api/v1/admin/puzzles/complete
POST   /api/v1/admin/puzzles/{puzzle_id}/image
```

The same page includes daily scheduling for ready puzzles. Scheduling API
routes are available only when the development admin is enabled:

```text
GET    /api/v1/admin/schedule
POST   /api/v1/admin/schedule
PATCH  /api/v1/admin/schedule/{daily_puzzle_id}
DELETE /api/v1/admin/schedule/{daily_puzzle_id}
```

Player gameplay routes are:

```text
GET  /api/v1/game/categories
POST /api/v1/game/start
POST /api/v1/game/{session_id}/glimpse
POST /api/v1/game/{session_id}/guess
POST /api/v1/game/{session_id}/hints/cryptic
POST /api/v1/game/{session_id}/hints/title-pattern
GET  /api/v1/game/{session_id}/state
GET  /api/v1/game/{session_id}/result
```

The Vite client uses relative API paths by default and proxies `/api` to
FastAPI during development. Set `VITE_API_BASE_URL` only when the API is served
from a separate public origin.
