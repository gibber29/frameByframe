# Transfer local albums to Render

## Badly Explained

The same tool also supports a separate, insert-only Badly Explained import.
After setting `TARGET_DATABASE_URL` as below, preview it with:

```powershell
docker compose run --rm --no-deps -e TARGET_DATABASE_URL api python -m backend.app.db.transfer_albums --category badly_explained
```

After checking the count, repeat with `--apply`:

```powershell
docker compose run --rm --no-deps -e TARGET_DATABASE_URL api python -m backend.app.db.transfer_albums --category badly_explained --apply
```

This copies titles, aliases, all four clues, image keys, difficulty, active flags
and timestamps, without touching albums or player history.

## Albumnesia

This insert-only tool copies `content_entries` for Albumnesia and their
`albumnesia_content` metadata, including aliases, active flags, difficulty,
timestamps, distortions and cover-editor masks. It preserves IDs and image keys.
It does not copy games, users, rooms, streaks, schedules, movie puzzles or other
categories. It never resets a database, creates tables, or overwrites content.
Both databases must already have the current Alembic migrations applied.

Ensure the images referenced by local albums are committed under `assets/scenes`
and included in the deployed Docker image. The tool checks local image existence;
it does not upload files or verify the remote filesystem.

From the repository root in PowerShell, with Docker Desktop and the local
database running:

```powershell
$renderAlbumSecret = Read-Host 'Paste Render PostgreSQL External Database URL' -AsSecureString
$env:TARGET_DATABASE_URL = [System.Net.NetworkCredential]::new('', $renderAlbumSecret).Password
docker compose run --rm --no-deps -e TARGET_DATABASE_URL api python -m backend.app.db.transfer_albums
```

Use Render PostgreSQL's **External** URL, not its private/Internal URL. Require
TLS by adding `?sslmode=require` if the URL has no query parameters (otherwise
add `&sslmode=require`). The tool accepts `postgres://`, `postgresql://`, and
`postgresql+psycopg://` prefixes. Never put this URL into Git, frontend variables,
chat, or a Docker command argument. The hidden prompt keeps it out of shell
history; the environment value is still accessible to trusted local processes.

The first command validates and stages inserts, then rolls them back. After
checking the dry-run count, run:

```powershell
docker compose run --rm --no-deps -e TARGET_DATABASE_URL api python -m backend.app.db.transfer_albums --apply
Remove-Item Env:TARGET_DATABASE_URL
Remove-Variable renderAlbumSecret
```

All inserts commit together only after all checks pass. Re-running skips exact
matches; a conflicting ID, image key or normalized primary answer stops the
whole import without overwriting existing rows. No migrations or seed commands
are run by this tool. Connection failures intentionally omit exception details
to avoid printing database credentials.

Refresh the player opening page after import. Daily needs at least one active,
playable album; five-album multiplayer needs at least five. Keep public admin
endpoints disabled. Render Free does not persist newly uploaded image files
across deployments; committing images into the build covers the existing files.
