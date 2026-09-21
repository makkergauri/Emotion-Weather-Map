# Deploying

The frontend goes on **Vercel**, the backend on **Render**. Both are free.

Why split them: Vercel runs Python as serverless functions with no persistent
disk, and this backend needs one — the SQLite cache, the daily snapshots behind
the 7-day strip, and the background warm-up all assume a long-running process.
Render provides exactly that, so the code deploys unchanged.

The order matters, because each side needs the other's URL.

---

## 1. Backend on Render

1. Push the repo to GitHub, including `render.yaml`.
2. On [render.com](https://render.com): **New → Blueprint**, pick the repo, and
   apply. Render reads `render.yaml` and creates the service.
3. It will ask for `CORS_ORIGINS`. You don't have the Vercel URL yet, so enter
   `http://localhost:5173` for now — step 3 replaces it.
4. When the deploy finishes, open `https://YOUR-SERVICE.onrender.com/api/health`.
   You should see `"status": "ok"`. Copy that base URL.

Leave `NEWS_API_KEY` unset. NewsAPI's free plan is licensed for development only,
and the RSS fallback serves every country without it.

## 2. Frontend on Vercel

1. On [vercel.com](https://vercel.com): **Add New → Project**, import the repo.
2. Set **Root Directory** to `frontend`. Vercel detects Vite from there.
3. Under **Environment Variables**, add:

   | Name | Value |
   | --- | --- |
   | `VITE_API_BASE_URL` | `https://YOUR-SERVICE.onrender.com` |

4. Deploy, and copy the production URL — `https://your-project.vercel.app`.

This variable is baked in **at build time**. If you change it later, you must
redeploy for it to take effect; editing it alone does nothing.

## 3. Connect them

Back on Render: **Environment → `CORS_ORIGINS`** → set it to your Vercel URL.

It must match exactly: `https://`, no trailing slash, no path. Save, and Render
redeploys by itself.

## 4. Keep the backend awake

Render sleeps free services after 15 idle minutes, and waking takes up to a
minute. The workflow in `.github/workflows/keep-alive.yml` pings it every ten.

On GitHub: **Settings → Secrets and variables → Actions → Variables → New
repository variable**:

| Name | Value |
| --- | --- |
| `BACKEND_URL` | `https://YOUR-SERVICE.onrender.com` |

Then **Actions → Keep backend awake → Run workflow** to check it succeeds.

## 5. Check it like a reviewer would

Open the Vercel URL in a private window, so nothing is cached.

- [ ] The map loads, and grey pins fill in over roughly thirty seconds
- [ ] The header reaches 12/12 reporting
- [ ] Clicking a country flies in and shows its cities
- [ ] The panel's station strip reads `SRC RSS`

---

## When something's wrong

**Every pin stays grey, and the browser console mentions CORS.** `CORS_ORIGINS` on
Render doesn't exactly match the URL in your address bar. Check for a trailing
slash, or `http` where it should be `https`.

**Requests go to `your-project.vercel.app/api/...` and return 404.**
`VITE_API_BASE_URL` wasn't set when Vercel built. Set it, then redeploy.

**The first load takes a minute.** The backend was asleep. The page says so while
it waits. If it keeps happening, the keep-alive workflow isn't running — check
the Actions tab.

**Pins stay grey but there's no CORS error.** Open `/api/health` on the backend.
If `countries_cached` stays at 0, Google News is refusing Render's IP range. It
usually clears within the hour; nothing in this repo can force it.

---

## Honest limits of the free tier

**The cache resets on every deploy.** Render's free disk isn't persistent, so the
7-day strip starts empty after each deploy and builds up from there. A paid
persistent disk, or moving the store to Postgres, would fix it.

**Keep-alive is best effort.** GitHub may delay scheduled runs, and disables them
entirely on repositories with no activity for 60 days.