# Railway Deployment Tutorial

This guide will help you deploy your **Duel Ladder Bot** and **Telegram Mini App** to Railway, giving you a public HTTPS URL that works for all your students.

---

## Prerequisites

- A GitHub account
- A Railway account (free tier works)
- Your bot token from [@BotFather](https://t.me/BotFather)

---

## Step 1: Prepare Your Project

### 1.1 Push to GitHub

If you haven't already, push your project to GitHub:

```bash
cd /Users/imjustchilling/Desktop/duel-ladder-bot

# Initialize git if needed
git init
git add .
git commit -m "Initial commit"

# Create a new repo on GitHub, then:
git remote add origin https://github.com/YOUR_USERNAME/duel-ladder-bot.git
git branch -M main
git push -u origin main
```

---

## Step 2: Create Railway Account & Project

### 2.1 Sign Up

1. Go to [railway.app](https://railway.app)
2. Click **"Start a New Project"**
3. Sign in with **GitHub** (recommended)

### 2.2 Create New Project

1. Click **"New Project"**
2. Select **"Deploy from GitHub repo"**
3. Choose your `duel-ladder-bot` repository
4. Railway will detect it's a Python project

---

## Step 3: Deploy the Telegram Bot

### 3.1 Configure the Bot Service

1. Railway will create a service automatically. Click on it.
2. Go to **Settings** → **Deploy**
3. Set **Root Directory** to: `.` (current directory)
4. Set **Start Command** to: `python bot.py`

### 3.2 Set Environment Variables

Go to **Variables** tab and add:

```
BOT_TOKEN=your_bot_token_from_botfather
ADMIN_IDS=your_telegram_user_id
DB_PATH=duel_ladder.sqlite3
ADMIN_TOKEN=classroom2024
```

**To find your Telegram user ID:**
- Message [@userinfobot](https://t.me/userinfobot) on Telegram
- Copy your numeric ID

### 3.3 Deploy

1. Railway will auto-deploy when you push to GitHub
2. Or click **"Deploy"** manually
3. Wait for deployment to complete (check **Deployments** tab)

---

## Step 4: Deploy the TMA Server (Separate Service)

### 4.1 Create Second Service

1. In your Railway project, click **"+ New"** → **"Empty Service"**
2. Name it: `tma-server`

### 4.2 Connect to Same GitHub Repo

1. Click the new service
2. Go to **Settings** → **Source**
3. Connect to the same GitHub repo
4. Set **Root Directory** to: `.`
5. Set **Start Command** to: `python run_tma.py --host 0.0.0.0 --port $PORT`

### 4.3 Set Environment Variables

Go to **Variables** and add:

```
BOT_TOKEN=your_bot_token_from_botfather
ADMIN_TOKEN=classroom2024
DB_PATH=duel_ladder.sqlite3
```

**Important:** Railway sets `$PORT` automatically. Don't override it.

### 4.4 Generate Public Domain

1. Go to **Settings** → **Networking**
2. Click **"Generate Domain"**
3. Copy the HTTPS URL (e.g., `https://tma-server-production-xxxx.up.railway.app`)

---

## Step 5: Link TMA URL to Bot

### 5.1 Get Your Bot Running

1. Make sure your bot service is deployed and running
2. Check the **Logs** tab to see if it started successfully

### 5.2 Set TMA URL in Bot

You have two options:

**Option A: Use Railway's runtime URL (recommended)**

1. In your **bot service**, go to **Variables**
2. Add: `TMA_URL=https://your-tma-service.up.railway.app`
3. Redeploy the bot service

**Option B: Set it dynamically via Telegram**

1. Open your bot in Telegram
2. Send: `/tma_set https://your-tma-service.up.railway.app`
3. The bot will remember this URL

---

## Step 6: Import Vocabulary

### 6.1 Access Your Bot

Your bot should be running. Test it by sending `/start` in Telegram.

### 6.2 Import Words

You can import vocabulary in two ways:

**Method 1: Via Telegram (if you have the import script)**

```bash
# Run locally, or use Railway's CLI
railway run python import_docx_vocab.py document-16.docx document-17.docx document-19.docx
```

**Method 2: Via Railway Console**

1. Install Railway CLI: `npm i -g @railway/cli`
2. Run: `railway login`
3. Run: `railway link` (select your project)
4. Run: `railway run python import_docx_vocab.py document-16.docx document-17.docx document-19.docx`

**Method 3: Use the bot commands**

1. Send `/addword word|definition|translation|syn1,syn2|ant1,ant2|example` to your bot
2. Or send `/importwords` followed by lines of vocabulary

---

## Step 7: Test Everything

### 7.1 Test the Bot

1. Open your bot in Telegram
2. Send `/start`
3. Send `/menu`
4. You should see the **"🎮 Play (Mini App)"** button

### 7.2 Test the Mini App

1. Click the **"🎮 Play (Mini App)"** button
2. The Mini App should open in Telegram
3. If it asks for a password, check that your TMA URL is set correctly

### 7.3 Test Admin Panel

1. Open: `https://your-tma-service.up.railway.app?admin=classroom2024`
2. You should see the admin controls

---

## Step 8: Start a Game

### 8.1 Start an Event

In your bot, send:
```
/event_start 30
```
This starts a 30-minute event.

### 8.2 Students Join

Students should:
1. Open your bot
2. Press **"🎮 Play (Mini App)"**
3. Or press **"🎮 Join & Play"** in the bot

---

## Troubleshooting

### Bot won't start

- Check **Logs** tab in Railway
- Verify `BOT_TOKEN` is correct
- Make sure `ADMIN_IDS` is set (comma-separated if multiple)

### TMA shows "password required"

- Verify `TMA_URL` is set in bot's environment variables
- Make sure the TMA service has a public domain generated
- Check that both services are running

### Database issues

- Railway uses ephemeral storage by default
- Consider using Railway's **PostgreSQL** addon for persistent storage
- Or use Railway's **Volume** feature to persist SQLite

### Can't import vocabulary

- Use Railway CLI to run import scripts
- Or use bot commands `/addword` or `/importwords`

---

## Optional: Use PostgreSQL (Recommended for Production)

### Add PostgreSQL Database

1. In Railway project, click **"+ New"** → **"Database"** → **"Add PostgreSQL"**
2. Railway will create a PostgreSQL database
3. Update your code to use PostgreSQL instead of SQLite (requires code changes)

**For now, SQLite works fine for a single lesson!**

---

## Quick Reference

### Railway Service URLs

- **Bot Service:** No public URL needed (runs in background)
- **TMA Service:** `https://your-service.up.railway.app` (set this as `TMA_URL`)

### Important Commands

```bash
# Deploy locally (for testing)
railway up

# View logs
railway logs

# Run commands in Railway environment
railway run python script.py

# Open Railway dashboard
railway dashboard
```

### Environment Variables Checklist

**Bot Service:**
- ✅ `BOT_TOKEN`
- ✅ `ADMIN_IDS`
- ✅ `DB_PATH` (optional, defaults to `duel_ladder.sqlite3`)
- ✅ `TMA_URL` (your TMA service URL)
- ✅ `ADMIN_TOKEN` (optional, defaults to `classroom2024`)

**TMA Service:**
- ✅ `BOT_TOKEN`
- ✅ `ADMIN_TOKEN` (optional, defaults to `classroom2024`)
- ✅ `DB_PATH` (must match bot service if sharing DB)

---

## Next Steps

1. ✅ Both services deployed
2. ✅ TMA URL set in bot
3. ✅ Vocabulary imported
4. ✅ Test with `/start` and Mini App button
5. ✅ Start your lesson with `/event_start 30`

**You're all set!** 🎉

