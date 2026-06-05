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

## Important note about the database

The app currently defaults to SQLite in `instance/app.db` for local development. That works locally, but it is not a good persistence layer for Vercel deployments.

If you only want to verify the UI and basic flow, you can deploy as-is.
If you want persistent data on Vercel, switch `DATABASE_URL` to a hosted database.

## Entry point

Vercel should use `api/index.py`:

```python
from app import create_app

app = create_app()
```

## Notes

- This project does not need a custom `vercel.json` for the default Flask deployment path.
- Let Vercel detect the Python app automatically from `api/index.py`.
