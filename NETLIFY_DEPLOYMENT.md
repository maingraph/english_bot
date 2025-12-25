# Netlify Deployment Guide

## Important Notes

⚠️ **The Telegram bot (`bot.py`) CANNOT run on Netlify** - it needs continuous polling which requires a long-running process. You'll need to run the bot separately (locally or on another service like Railway/Render).

✅ **The TMA (Telegram Mini App) CAN run on Netlify** - it's been adapted to work as serverless functions.

---

## Step 1: Fix Netlify Configuration

### 1.1 Update `netlify.toml`

Make sure your `netlify.toml` looks like this:

```toml
[build]
  command = "echo 'No build needed'"
  publish = "public"

[build.environment]
  PYTHON_VERSION = "3.11"

[[redirects]]
  from = "/api/*"
  to = "/.netlify/functions/tma-api?route=:splat"
  status = 200

[[redirects]]
  from = "/*"
  to = "/index.html"
  status = 200
```

### 1.2 Directory Structure

Your project should have:
```
duel-ladder-bot/
├── public/
│   └── index.html          # TMA frontend
├── netlify/
│   └── functions/
│       └── tma-api.py      # API serverless function
├── duel_ladder_bot/        # Your Python package
├── requirements.txt
└── netlify.toml
```

---

## Step 2: Set Environment Variables in Netlify

Go to **Netlify Dashboard** → **Site settings** → **Environment variables** and add:

```
BOT_TOKEN=your_bot_token_from_botfather
ADMIN_TOKEN=classroom2024
DB_PATH=duel_ladder.sqlite3
```

**Note:** Netlify Functions can't use SQLite files directly (they're read-only). For a full deployment, you'd need to use a database service. For a **classroom demo**, the simplified function uses in-memory state.

---

## Step 3: Deploy

1. **Push to GitHub** (if not already):
   ```bash
   git add .
   git commit -m "Netlify deployment"
   git push
   ```

2. **In Netlify Dashboard:**
   - Go to your site
   - Click **"Deploys"** tab
   - Click **"Trigger deploy"** → **"Deploy site"**

3. **Wait for deployment** (usually 1-2 minutes)

---

## Step 4: Update Frontend API URLs

The frontend in `public/index.html` needs to use Netlify's function URLs. Update the API calls:

**Find this in `public/index.html` (around line 840-850):**
```javascript
async function api(method, endpoint, body = null) {
  const headers = {
    'Content-Type': 'application/json',
    'X-Telegram-Init-Data': initData,
  };
  if (adminToken) {
    headers['X-Admin-Token'] = adminToken;
  }
  const opts = { method, headers };
  if (body) opts.body = JSON.stringify(body);
  const res = await fetch(endpoint, opts);  // <-- This needs to change
  return res.json();
}
```

**Change to:**
```javascript
async function api(method, endpoint, body = null) {
  // Netlify Functions base URL
  const baseUrl = window.location.origin;
  const functionUrl = `${baseUrl}/.netlify/functions/tma-api`;
  
  const headers = {
    'Content-Type': 'application/json',
    'X-Telegram-Init-Data': initData,
  };
  if (adminToken) {
    headers['X-Admin-Token'] = adminToken;
  }
  
  // Map endpoint to query param
  let url = functionUrl;
  if (endpoint.includes('/join')) {
    url += '?route=join';
  } else if (endpoint.includes('/state')) {
    url += '?route=state';
  } else if (endpoint.includes('/answer')) {
    url += '?route=answer';
  } else if (endpoint.includes('/admin')) {
    url += '?route=admin';
  }
  
  const opts = { method, headers };
  if (body) opts.body = JSON.stringify(body);
  const res = await fetch(url, opts);
  return res.json();
}
```

---

## Step 5: Set TMA URL in Bot

Once deployed, you'll get a URL like: `https://your-site.netlify.app`

1. **Run your bot locally** (or on another service):
   ```bash
   python bot.py
   ```

2. **In Telegram, send to your bot:**
   ```
   /tma_set https://your-site.netlify.app
   ```

3. **Test the Mini App:**
   - Open your bot
   - Click **"🎮 Play (Mini App)"** button
   - Should open the TMA!

---

## Step 6: Run the Bot Separately

Since Netlify can't run the bot, you have options:

### Option A: Run Locally (for testing)
```bash
python bot.py
```

### Option B: Deploy Bot to Railway/Render
Follow the `RAILWAY_DEPLOYMENT.md` guide, but only deploy the bot service (not TMA).

### Option C: Use Telegram Webhooks (Advanced)
Configure your bot to use webhooks instead of polling. This works better with serverless.

---

## Troubleshooting

### "Page not found" Error

**Cause:** Netlify is trying to serve static files but can't find `index.html`.

**Fix:**
1. Make sure `public/index.html` exists
2. Check `netlify.toml` has `publish = "public"`
3. Redeploy

### API Returns 404

**Cause:** Function routing not working.

**Fix:**
1. Check `netlify.toml` redirects are correct
2. Verify `netlify/functions/tma-api.py` exists
3. Check Netlify build logs for errors

### "Module not found" in Function

**Cause:** Dependencies not installed.

**Fix:**
1. Add `requirements.txt` to root
2. Netlify should auto-install, but check build logs
3. You may need to add a `runtime.txt` with `python-3.11`

### State Resets on Every Request

**Cause:** Netlify Functions are stateless (this is expected).

**Fix:** This is normal for serverless. For a classroom demo, it's fine. For production, use a database (PostgreSQL, MongoDB, etc.).

---

## Quick Checklist

- [ ] `public/index.html` exists
- [ ] `netlify/functions/tma-api.py` exists
- [ ] `netlify.toml` is configured
- [ ] Environment variables set in Netlify
- [ ] Frontend API URLs updated
- [ ] Bot running separately (locally or elsewhere)
- [ ] TMA URL set in bot via `/tma_set`

---

## Next Steps

1. ✅ Deploy TMA to Netlify
2. ✅ Run bot separately
3. ✅ Set TMA URL in bot
4. ✅ Test with students!

**You're all set!** 🎉

