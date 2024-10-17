# Migrations

The app automatically applies schema migrations on startup.
To add a new revision, do the following:
  - start the backend using `docker compose up -d --build`, so your schema in postgres is up-to-date
  - modify `models.py` to your liking
  - run `alembic revision --autogenerate -m "my change"`
  - verify the newly created file under `migrations/versions`
  - start the backend with the new code, it should log that it's applying that schema and you should see your update
    in the postgres database
  - commit the new file to git, let it be reviewed. the production version(s) will be updated automatically
