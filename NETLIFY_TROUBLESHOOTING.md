# Netlify TMA Troubleshooting

## "Connection error. Try again." When Joining

### Step 1: Check Browser Console

1. Open your Mini App in Telegram
2. Open browser DevTools (if possible) or check Netlify Function logs
3. Look for the actual error message

### Step 2: Common Issues

#### Issue: "Lobby not open"
**Solution:** The admin needs to open the lobby first:
1. Open the TMA with `?admin=classroom2024` in the URL
2. Click the **"Open"** button in the admin panel
3. Then players can join

#### Issue: Function not found (404)
**Solution:** 
1. Check that `netlify/functions/tma-api.py` exists
2. Redeploy on Netlify
3. Check Netlify build logs for errors

#### Issue: CORS errors
**Solution:** The function should already handle CORS, but if you see CORS errors:
- Check that `Access-Control-Allow-Origin: *` is in response headers
- Verify the function is returning proper headers

#### Issue: Authentication failed
**Solution:**
- Make sure `BOT_TOKEN` is set in Netlify environment variables
- The function validates Telegram's init data - if this fails, check your bot token

### Step 3: Test the Function Directly

You can test the Netlify function directly:

```bash
curl -X POST https://your-site.netlify.app/.netlify/functions/tma-api?route=join \
  -H "Content-Type: application/json" \
  -H "X-Telegram-Init-Data: YOUR_INIT_DATA" \
  -d '{}'
```

### Step 4: Check Netlify Logs

1. Go to Netlify Dashboard
2. Click on your site
3. Go to **Functions** tab
4. Click on `tma-api`
5. Check the **Logs** tab for errors

### Step 5: Verify Environment Variables

In Netlify Dashboard → Site settings → Environment variables, make sure you have:
- `BOT_TOKEN` - Your Telegram bot token
- `ADMIN_TOKEN` - Admin password (default: `classroom2024`)
- `DB_PATH` - Database path (optional)

### Step 6: Test Admin Panel

1. Open: `https://your-site.netlify.app?admin=classroom2024`
2. You should see admin buttons at the bottom
3. Click **"Open"** to open the lobby
4. Then try joining again

---

## Quick Fix Checklist

- [ ] Function deployed successfully (check Netlify build logs)
- [ ] Environment variables set (`BOT_TOKEN`, `ADMIN_TOKEN`)
- [ ] Admin opened the lobby (click "Open" in admin panel)
- [ ] Browser console shows no CORS errors
- [ ] Function logs show the request is reaching the function

---

## Still Not Working?

1. **Check the exact error** in browser console or Netlify logs
2. **Verify the function URL** - should be `/.netlify/functions/tma-api`
3. **Test with curl** to isolate frontend vs backend issues
4. **Check Netlify function timeout** - functions have a 10s timeout by default

