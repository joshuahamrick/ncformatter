# Gotenberg for NcFormatter (print-accurate Word → PDF)

NcFormatter calls `GOTENBERG_URL/forms/libreoffice/convert` when local LibreOffice/Word is unavailable (e.g. Vercel).

## Fly.io (recommended)

1. [Install Flyctl](https://fly.io/docs/hands-on/install-flyctl/) (Windows: `winget install fly.io.superfly`) and log in: `fly auth login`
2. Edit `fly.toml` in this folder: set `app = "your-unique-app-name"` (globally unique on Fly).
3. Create the app once (skip if it already exists):
   ```bash
   cd deploy/gotenberg
   fly apps create your-unique-app-name
   ```
4. Deploy:
   ```bash
   fly deploy
   ```
   Or from repo root on Windows: `powershell -File deploy/gotenberg/deploy.ps1`
5. Your base URL is `https://your-unique-app-name.fly.dev` (see `fly status`).
6. In **Vercel** → Project → Environment variables:
   - `GOTENBERG_URL` = `https://your-unique-app-name.fly.dev` (no trailing slash)
   - Optional Basic auth (step below): `GOTENBERG_BASIC_AUTH` = `username:password`
7. Redeploy the Vercel project so Python functions pick up the new env.

### Optional: HTTP Basic auth (recommended if the URL is public)

1. Add to **`[env]`** in `fly.toml` (then commit or edit only on the server):
   ```toml
   API_ENABLE_BASIC_AUTH = "true"
   ```
2. Set credentials as Fly secrets (values are not stored in git):
   ```bash
   fly secrets set \
     GOTENBERG_API_BASIC_AUTH_USERNAME=ncformatter \
     GOTENBERG_API_BASIC_AUTH_PASSWORD='your-long-random-secret'
   fly deploy
   ```
3. On Vercel set `GOTENBERG_BASIC_AUTH` = `ncformatter:your-long-random-secret` (same username and password).

## Local Docker

From repo root:

```bash
docker compose -f deploy/gotenberg/docker-compose.yml up -d
```

Set locally (or in `.env` for tools): `GOTENBERG_URL=http://127.0.0.1:3044`

## Verify

```bash
curl -sS -o /dev/null -w "%{http_code}" https://YOUR-APP.fly.dev/health
# expect 200
```

Convert a test docx (replace path):

```bash
curl --fail -o out.pdf -F "files=@./template.docx" \
  https://YOUR-APP.fly.dev/forms/libreoffice/convert
```

With Basic auth:

```bash
curl --fail -u 'USER:PASS' -o out.pdf -F "files=@./template.docx" \
  https://YOUR-APP.fly.dev/forms/libreoffice/convert
```
