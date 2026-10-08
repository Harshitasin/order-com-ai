# Deploy and publish

GitHub stores your code and runs your tests. It does **not** run a Flask + MySQL
app. To get a live link you need a host that can run a Docker container, plus a
MySQL database. Check each provider's current docs and pricing before choosing.

## 1. Before the first push

- [ ] `.env` is in `.gitignore` and `git status` does NOT list it
- [ ] No password in any file: `git grep -n -i "password" -- ":!*.md"` shows only variable names
- [ ] Change every password that ever appeared in a screenshot or chat
- [ ] Groq console: keep the key private; if it ever leaks, delete it at console.groq.com/keys and create a new one
- [ ] Replace `<your-username>` in README.md and `<YOUR NAME>` in LICENSE
- [ ] `pytest` passes

## 2. Push to GitHub

```bash
git init
git add .
git status            # read this list; .env must not be in it
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/<your-username>/order-assistant.git
git push -u origin main
```

If a secret is ever committed, deleting the file is not enough: it stays in history.
Rotate (change) the secret first, then clean the history.

GitHub Actions (`.github/workflows/ci.yml`) now runs the tests and a Docker build on every push.

## 3. Run everything with Docker locally

```bash
cp .env.example .env                # fill in all values, including MYSQL_ROOT_PASSWORD
docker compose up --build -d
docker compose run --rm app python scripts/seed_data.py
# open http://localhost:8000   (demo logins: test1@example.com / test2@example.com, password Test@1234)
docker compose logs -f app
docker compose down                 # add -v to also delete the database volume
```

The seed script reads `MYSQL_ROOT_PASSWORD` from the environment. The MySQL users
are created automatically on the first start by `docker/mysql-init/02_users.sh`.

## 4. Put it online

1. Pick a host that runs Docker images (or a small cloud VM with Docker installed).
2. Create a managed MySQL database there, or run MySQL as a second service.
3. Set the environment variables in the host's dashboard, never in the repository.
4. Run `db/schema.sql`, create the three users from `db/grants.sql`, then seed demo data once.
5. Put the live URL and a short demo video in the README.

## 5. Risks of a public demo

- Every `/chat` call uses your Groq quota. On the free tier, visitors can use it up (the assistant then says it is busy), so keep the rate limits. On a paid tier, set a spend limit.
- Use only the fake test accounts, never real customer data.
- Demo accounts share a password; change it for anything public, or share the link only with recruiters.
- Debug mode must stay off (gunicorn in the Dockerfile does not enable it).
