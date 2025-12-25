#!/usr/bin/env python3
"""
Run the Telegram Mini App server.

Usage:
  python run_tma.py [--port 8080]

Admin access:
  Open the TMA URL with ?admin=YOUR_ADMIN_TOKEN
  (default token is "classroom2024", set ADMIN_TOKEN env var to change)
"""
import argparse
import os
import sys

# Ensure we can import our package
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from duel_ladder_bot.tma_server import run_tma_server

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run TMA server")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    # Railway and other platforms set PORT env var automatically
    default_port = int(os.environ.get("PORT", 8080))
    parser.add_argument("--port", type=int, default=default_port, help="Port to listen on")
    args = parser.parse_args()

    print(f"""
╔══════════════════════════════════════════════════════════════╗
║                    VOCAB DUEL - TMA SERVER                    ║
╠══════════════════════════════════════════════════════════════╣
║  Server URL:  http://{args.host}:{args.port:<5}                           ║
║                                                               ║
║  For players:  Share the Mini App link in Telegram            ║
║  For admin:    Add ?admin=classroom2024 to the URL            ║
╚══════════════════════════════════════════════════════════════╝
""")

    run_tma_server(host=args.host, port=args.port)

