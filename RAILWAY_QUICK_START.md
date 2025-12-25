# Railway Quick Start (5 Minutes)

## 1. Push to GitHub

```bash
git add .
git commit -m "Ready for Railway"
git push
```

## 2. Create Railway Project

1. Go to [railway.app](https://railway.app) → **New Project** → **Deploy from GitHub**
2. Select your repo

## 3. Deploy Bot Service

**Settings → Deploy:**
- Start Command: `python bot.py`

**Variables:**
```
BOT_TOKEN=your_token
ADMIN_IDS=your_telegram_id
TMA_URL=(set after step 4)
```

## 4. Deploy TMA Service

**New Service → Empty Service:**
- Start Command: `python run_tma.py --host 0.0.0.0 --port $PORT`
- **Settings → Networking → Generate Domain**
- Copy the HTTPS URL

**Variables:**
```
BOT_TOKEN=your_token
ADMIN_TOKEN=classroom2024
```

## 5. Link TMA to Bot

In **Bot Service → Variables**, add:
```
TMA_URL=https://your-tma-service.up.railway.app
```

Redeploy bot service.

## 6. Test

1. Send `/start` to your bot
2. Click **"🎮 Play (Mini App)"** button
3. Should open the Mini App!

## 7. Import Vocabulary

```bash
railway run python import_docx_vocab.py document-16.docx document-17.docx document-19.docx
```

Or use bot commands: `/addword` or `/importwords`

---

**Done!** Your bot is live with a public HTTPS URL. 🎉

