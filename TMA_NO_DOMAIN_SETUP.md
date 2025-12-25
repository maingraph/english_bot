# TMA (Telegram Mini App) — No Domain Setup

Telegram Mini Apps must be reachable via **HTTPS** from users’ devices.

If your bot + TMA run locally on your laptop, you need a tunnel that gives you a temporary `https://...` URL.

## What happened on your network (from the logs)

- **ngrok**: requires an account + authtoken now (`ERR_NGROK_4018`)
- **cloudflared quick tunnel**: your network blocks Cloudflare Tunnel’s outbound port **7844** (`dial tcp …:7844: i/o timeout`)
- **localhost.run**: your network blocks outbound SSH on **22** and **443** (timeout / connection closed)

So you need a tunnel that works over standard HTTPS on port **443** to a service your network allows, or you must change networks.

## Step 0 — run the TMA server

In one terminal:

```bash
cd /Users/imjustchilling/Desktop/duel-ladder-bot
source .venv/bin/activate
python run_tma.py --port 8080
```

Keep it running.

## Option A (recommended) — LocalTunnel (no domain, often no signup)

This usually works on restricted networks because it’s normal HTTPS outbound.

1) Install Node.js if you don’t have it (skip if you do).
2) Run:

```bash
npx --yes localtunnel --port 8080
```

It prints a URL like `https://xxxx.loca.lt`.

## Option B — Switch networks (fastest when school Wi‑Fi blocks tunnels)

Use your phone hotspot (or another Wi‑Fi), then retry Cloudflare quick tunnel:

```bash
TUNNEL_TRANSPORT_PROTOCOL=http2 cloudflared tunnel --url http://localhost:8080
```

If your network allows Cloudflare Tunnel, it will print a URL like `https://xxxx.trycloudflare.com`.

## Option C — Host it for free (still “no domain”, but needs an account)

If tunnels are blocked everywhere, you’ll need *some* hosting:
- Vercel / Netlify / Render / Fly.io (they give you a free `https://...` subdomain)

## After you have an HTTPS URL — connect it to the bot

In Telegram (as admin), run:

```text
/tma_set https://YOUR-HTTPS-URL
```

Now the bot’s **“🎮 Play (Mini App)”** keyboard button opens the Mini App.

## Admin panel

Get your private admin link with:

```text
/tma_admin
```

It returns `https://YOUR-HTTPS-URL/?admin=...` which enables the bottom admin controls in the Mini App.


