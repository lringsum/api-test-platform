# GitHub + Vercel Deployment

This project is now organized for a clean GitHub push and a straightforward Vercel import.

## What was added

- `.gitignore` to keep local artifacts out of Git.
- `.vercelignore` to keep local-only files out of Vercel uploads.
- `api/index.py` as the Vercel-friendly Flask entry point.
- `public/` for CSS and JS so Vercel can serve static assets cleanly.

## Push to GitHub

Run these commands from the project root:

```bash
git init
git add .
git commit -m "initial commit"
git branch -M main
git remote add origin https://github.com/your-name/your-repo.git
git push -u origin main
```

## Create the Vercel project

1. Sign in to Vercel.
2. Create a new project.
3. Import the GitHub repository you just pushed.
4. Keep the default framework detection.
5. Add environment variables in Vercel if needed:
   - `SECRET_KEY`
   - `AI_MODE`
   - `DEFAULT_TIMEOUT`
   - `DATABASE_URL`

## Production database: PostgreSQL

For a real Vercel deployment, use PostgreSQL instead of SQLite.

Recommended setup:

1. Create a PostgreSQL database with a hosted provider available from Vercel Marketplace.
2. Copy the connection string into the Vercel project as `DATABASE_URL`.
3. Redeploy the project.

The application now accepts PostgreSQL URLs such as:

```bash
postgresql+psycopg2://user:password@host:5432/dbname
```

It also accepts the common Vercel / provider forms:

```bash
postgres://user:password@host:5432/dbname
postgresql://user:password@host:5432/dbname
```

## Keep the existing data

If you already have data in the local SQLite file (`instance/app.db`), migrate it into PostgreSQL before switching traffic over.

Before migrating, freeze any writes to the old app so new data does not arrive in SQLite after the copy starts.

Use the migration script:

```bash
python scripts/migrate_sqlite_to_postgres.py --target "postgresql+psycopg2://user:password@host:5432/dbname"
```

If your source database is not the default `instance/app.db`, pass it explicitly:

```bash
python scripts/migrate_sqlite_to_postgres.py --source "sqlite:///D:/path/to/app.db" --target "postgresql+psycopg2://user:password@host:5432/dbname"
```

The script copies all rows table by table and resets PostgreSQL sequences afterwards.

Recommended migration flow:

1. Stop or freeze the current SQLite-backed deployment.
2. Run the migration script once.
3. Point `DATABASE_URL` at the PostgreSQL database in Vercel.
4. Redeploy and verify the data.
5. Reopen writes on the new deployment.

## Entry point

Vercel should use `api/index.py`:

```python
from app import create_app

app = create_app()
```

## Notes

- This project does not need a custom `vercel.json` for the default Flask deployment path.
- Let Vercel detect the Python app automatically from `api/index.py`.
