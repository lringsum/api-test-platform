# Local Run Guide

This project is configured to use a local SQLite database only.
All runtime data is stored in `instance/app.db` under the project directory.

## What changed

- The app no longer reads `DATABASE_URL` or PostgreSQL connection strings.
- The database is always resolved to the local SQLite file in `instance/app.db`.
- The Flask instance path is local to the project, so data stays on your machine.

## Run locally

1. Install dependencies:

```bash
pip install -r requirements.txt
```

2. Start the app:

```bash
python run.py
```

3. Open:

[http://127.0.0.1:5000/](http://127.0.0.1:5000/)

## Data location

The SQLite database file is:

```text
instance/app.db
```

If you want to reset the data, stop the app and delete that file.

## Notes

- Keep `instance/app.db` out of Git if you want to avoid committing local data.
- The existing `seed_data.py` script can still be used to repopulate demo data.
- If you previously used a hosted database, the app will no longer connect to it.
