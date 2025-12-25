# How to Use the Vocab Duel Bot

## 📚 Step 1: Import Vocabulary

You have 3 `.docx` files with vocabulary. Import them into the database:

### Option A: Import via Command Line (Recommended)

```bash
cd /Users/imjustchilling/Desktop/duel-ladder-bot
source .venv/bin/activate

# Import all 3 files at once
python import_docx_vocab.py document-16.docx document-17.docx document-19.docx

# Or if you want to wipe existing vocab first:
python import_docx_vocab.py document-16.docx document-17.docx document-19.docx --wipe
```

**What this does:**
- Extracts words, synonyms, and antonyms from the tables in your `.docx` files
- Adds them to the SQLite database
- Shows you how many words were inserted

### Option B: Import via Telegram Bot (Manual)

If you prefer to add words one by one via the bot:

1. Open your bot in Telegram
2. Send: `/addword Challenge|A difficult task|desafío|difficulty,obstacle,test|ease,advantage,simplicity|Example sentence`

**Format:** `word|definition|translation|syn1,syn2,syn3|ant1,ant2,ant3|example`

### Check Word Count

After importing, verify:
```bash
# Via command line
python -c "from duel_ladder_bot.runtime import db; print(f'Words in DB: {db.count_words()}')"
```

Or in Telegram: `/words_count`

---

## 🎮 Step 2: Start the Bot

### Run the Bot Locally

```bash
cd /Users/imjustchilling/Desktop/duel-ladder-bot
source .venv/bin/activate
python bot.py
```

The bot will start polling for messages. Keep this terminal running.

**Note:** If you deployed to Netlify, the TMA (Mini App) is already live. The bot needs to run separately (locally or on Railway/Render).

---

## 👨‍🏫 Step 3: Admin Setup (You)

### Set Your Admin ID

1. Message [@userinfobot](https://t.me/userinfobot) on Telegram to get your user ID
2. Add it to your `.env` file:
   ```
   ADMIN_IDS=YOUR_TELEGRAM_USER_ID
   ```
3. Restart the bot

### Set the Mini App URL

In Telegram, send to your bot:
```
/tma_set https://subtle-mermaid-ae1faa.netlify.app
```

This tells the bot where your Mini App is hosted.

---

## 🎯 Step 4: Start a Game Session

### As Admin (You):

1. **Start an event:**
   ```
   /event_start 30
   ```
   This starts a 30-minute event. Adjust the number for different durations.

2. **Open the Mini App admin panel:**
   ```
   /tma_admin
   ```
   Then **tap the "🛠 Open Admin Panel (Mini App)" button** (don't copy/paste the link).

3. **In the Mini App admin panel:**
   - Tap **"Open"** to open the lobby for players
   - Wait for students to join
   - Tap **"Start"** when ready

### As a Student:

1. **Open the bot in Telegram**
2. **Tap "🎮 Play (Mini App)"** button
3. **Tap "🎮 Open Game (Mini App)"** in the message (this opens it properly inside Telegram)
4. **Tap "✨ Join Game"** in the Mini App
5. Wait for the admin to start the game

---

## 🎲 Step 5: During the Game

### Students See:
- Current round number (e.g., "Round 3/10")
- Timer counting down
- Question with 4 multiple-choice options
- Mini leaderboard (top 5 players + their rank)
- Their score, correct answers count

### Admin Can:
- **"Next"** - Manually advance to next round (if auto-advance is slow)
- **"Reset"** - Reset the game (use carefully!)

---

## 🏆 Step 6: After the Game

- Students see the **full leaderboard** with final rankings
- Their final rank, points, and correct answers
- Admin can start a new game by tapping **"Open"** again

---

## 📊 Other Useful Commands

### For Students:
- `/menu` - See dashboard with your status
- `/leaderboard` - View current leaderboard
- `/mystats` - Your personal stats
- `/join` - Join the matchmaking queue
- `/pause` - Pause auto-matchmaking
- `/resume` - Resume auto-matchmaking

### For Admin:
- `/words_count` - Check how many words are in the database
- `/event_stop` - Stop the current event
- `/tma_admin` - Get admin Mini App link
- `/tma_set <url>` - Set Mini App URL
- `/vocab_reset CONFIRM` - Wipe all vocabulary (keeps user/event data)

---

## 🔧 Troubleshooting

### "Invalid auth" when joining
- Make sure you opened the Mini App **via the button**, not by copying a URL
- The button ensures Telegram passes authentication data

### "Lobby not open"
- Admin needs to tap **"Open"** in the admin panel first
- Then students can join

### Bot not responding
- Check that `python bot.py` is still running
- Check your `BOT_TOKEN` in `.env` is correct
- Restart the bot

### No words in database
- Run the import script: `python import_docx_vocab.py document-16.docx document-17.docx document-19.docx`
- Check with `/words_count`

---

## 🎓 Quick Start Checklist

- [ ] Import vocabulary from `.docx` files
- [ ] Set `ADMIN_IDS` in `.env` and restart bot
- [ ] Run `python bot.py` (keep it running)
- [ ] Set TMA URL: `/tma_set https://subtle-mermaid-ae1faa.netlify.app`
- [ ] Start event: `/event_start 30`
- [ ] Open admin panel: `/tma_admin` → tap button
- [ ] Tap **"Open"** in admin panel
- [ ] Students join via **"🎮 Play (Mini App)"** button
- [ ] Tap **"Start"** when ready!

**You're all set!** 🎉

