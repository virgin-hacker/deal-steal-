"""
Code & Deal Watcher (email edition)

Polls a configurable list of RSS feeds (gaming code subreddits, deal/coupon
subreddits, retail promo-code searches) and emails you when a new post
matches (promo code, redeem code, coupon code, giveaway, gift card, etc.).

Run once:      python bot.py --once
Run forever:   python bot.py
"""
import argparse
import hashlib
import json
import os
import smtplib
import time
from email.mime.text import MIMEText
from pathlib import Path

import feedparser
from dotenv import load_dotenv

load_dotenv()

SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
EMAIL_FROM = os.getenv("EMAIL_FROM", SMTP_USER)
EMAIL_TO = os.getenv("EMAIL_TO")
CHECK_INTERVAL_MINUTES = int(os.getenv("CHECK_INTERVAL_MINUTES", "15"))

BASE_DIR = Path(__file__).parent
SEEN_FILE = BASE_DIR / "seen.json"
SOURCES_FILE = BASE_DIR / "sources.json"

DEFAULT_KEYWORDS = [
    "promo code", "promo codes", "redeem code", "redeem codes",
    "coupon code", "discount code", "voucher code", "reward code",
    "gift card", "free code", "free codes", "giveaway", "free cash",
]


def load_json(path, default):
    if path.exists():
        try:
            return json.loads(path.read_text())
        except json.JSONDecodeError:
            return default
    return default


def save_json(path, data):
    path.write_text(json.dumps(data, indent=2))


def entry_id(source_name, entry):
    raw = entry.get("id") or entry.get("link") or entry.get("title", "")
    return hashlib.sha256(f"{source_name}:{raw}".encode()).hexdigest()


def matches_keywords(text, keywords):
    text = text.lower()
    return any(k in text for k in keywords)


def send_email(subject, body):
    if not all([SMTP_HOST, SMTP_USER, SMTP_PASSWORD, EMAIL_TO]):
        raise RuntimeError("Set SMTP_HOST, SMTP_USER, SMTP_PASSWORD and EMAIL_TO in .env first.")

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = EMAIL_FROM
    msg["To"] = EMAIL_TO

    try:
        if SMTP_PORT == 465:
            with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=15) as server:
                server.login(SMTP_USER, SMTP_PASSWORD)
                server.send_message(msg)
        else:
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as server:
                server.starttls()
                server.login(SMTP_USER, SMTP_PASSWORD)
                server.send_message(msg)
    except Exception as e:
        print(f"Email send failed: {e}")


def check_sources():
    sources = load_json(SOURCES_FILE, [])
    if not sources:
        print("sources.json is empty — add at least one feed to watch.")
        return False

    seen = load_json(SEEN_FILE, [])
    seen_set = set(seen)
    new_seen = list(seen)
    found_any = False

    for source in sources:
        name = source["name"]
        url = source["url"]
        keywords = source.get("keywords", DEFAULT_KEYWORDS)

        try:
            feed = feedparser.parse(url)
        except Exception as e:
            print(f"[{name}] failed to fetch: {e}")
            continue

        if getattr(feed, "bozo", False) and not feed.entries:
            print(f"[{name}] feed didn't parse cleanly — check the URL in sources.json")
            continue

        for entry in feed.entries:
            eid = entry_id(name, entry)
            if eid in seen_set:
                continue

            title = entry.get("title", "")
            summary = entry.get("summary", "")
            combined = f"{title} {summary}"

            if matches_keywords(combined, keywords):
                link = entry.get("link", "")
                send_email(
                    subject=f"🎟️ {name}: {title[:80]}",
                    body=f"{name}\n\n{title}\n\n{link}",
                )
                found_any = True
                print(f"[{name}] emailed: {title}")

            new_seen.append(eid)
            seen_set.add(eid)

    if len(new_seen) > 5000:
        new_seen = new_seen[-5000:]
    save_json(SEEN_FILE, new_seen)
    return found_any


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="Check sources one time and exit (good for cron / GitHub Actions).")
    args = parser.parse_args()

    if args.once:
        check_sources()
        return

    print(f"Watching for codes every {CHECK_INTERVAL_MINUTES} min. Ctrl+C to stop.")
    while True:
        try:
            check_sources()
        except Exception as e:
            print(f"Error during check: {e}")
        time.sleep(CHECK_INTERVAL_MINUTES * 60)


if __name__ == "__main__":
    main()
