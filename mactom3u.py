import requests
import re
import os
from datetime import datetime
import pytz

# --- CONFIGURATION ---
PORTAL_URL = "http://line.vueott.com:80"
MAC_ADDR = "00:1A:79:00:3d:1f" 
EPG_URL = "https://avkb.short.gy/tsepg.xml.gz"
SOURCE_TV_TELUGU = "https://tvtelugu.pages.dev/logo/channels.json"

USER_AGENT = "Mozilla/5.0 (QtEmbedded; U; Linux; C) AppleWebKit/533.3 (KHTML, like Gecko) MAG200 stbapp ver: 2 rev: 250 Safari/533.3"
NEW_GROUP_NAME = "𝐌𝐚𝐜 𝐓𝐕"
POWERED_BY = "@tvtelugu"

def clean_final_name(name):
    """Handles specific renames and quality normalization."""
    if not name: return ""
    
    # 1. Convert FHD/UHD to HD
    name = re.sub(r'\b(FHD|UHD|4K)\b', 'HD', name, flags=re.IGNORECASE)
    
    # 2. Specific Forced Renames
    renames = {
        "Hollywood Local": "Tata Play Hollywood Local Telugu",
        "Tata Sky Telugu Cinema Hd": "Tata Play Telugu Cinema",
        "Tata Sky Telugu Cinema": "Tata Play Telugu Cinema",
        "Abn Andhra Jyothy": "ABN Andhra Jyothi",
        "Gemini Fhd": "Gemini HD",
        "Star Maa Fhd": "Star Maa HD",
        "Star Maa Movies Fhd": "Star Maa Movies HD",
        "Nat Geo Fhd": "Nat Geo HD"
    }
    
    # Check for direct matches or partials in the rename dict
    for old, new in renames.items():
        if old.lower() in name.lower():
            name = new
            break

    # 3. Fix Capitalization (CINEMANIA -> Cinemania)
    words = name.split()
    name = " ".join([w.capitalize() if w.isupper() and len(w) > 1 else w for w in words])
    
    return name.strip()

def check_link(url):
    """Verifies if the stream is active."""
    try:
        r = requests.head(url, headers={'User-Agent': USER_AGENT}, timeout=2)
        return r.status_code == 200
    except:
        return False

def get_json_db():
    db = {}
    try:
        resp = requests.get(SOURCE_TV_TELUGU, timeout=10)
        for item in resp.json():
            name = item.get('Channel Name', '').strip()
            norm = re.sub(r'[^a-z0-9]', '', name.lower())
            db[norm] = {"name": name, "logo": item.get('logo')}
    except: pass
    return db

def run_sync():
    json_db = get_json_db()
    ist = pytz.timezone('Asia/Kolkata')
    curr_time = datetime.now(ist).strftime('%d %B %Y | %I:%M %p')
    
    headers = {'User-Agent': USER_AGENT, 'X-User-Agent': 'Model: MAG250', 'Cookie': f'mac={MAC_ADDR}'}
    session = requests.Session()
    
    try:
        print("[*] Connecting to Portal...")
        auth = session.get(f"{PORTAL_URL}/portal.php?type=stb&action=handshake&JsHttpRequest=1-xml", headers=headers).json()
        token = auth.get('js', {}).get('token')
        session.headers.update({'Authorization': f'Bearer {token}', 'Cookie': f'mac={MAC_ADDR}'})
        
        channels = session.get(f"{PORTAL_URL}/portal.php?type=itv&action=get_all_channels&JsHttpRequest=1-xml").json().get('js', {}).get('data', [])

        unique_channels = {} # Key: Normalized Name, Value: M3U Entry

        print(f"[*] Filtering and deduplicating {len(channels)} channels...")

        for ch in channels:
            raw_name = ch.get('name', '')
            if "telugu" not in raw_name.lower() and "telugu" not in str(ch.get('tv_genre_id', '')):
                continue

            cmd = ch.get('cmd', '')
            url_match = re.search(r'http[s]?://[^\s|]+', cmd)
            if not url_match: continue
            stream_url = url_match.group(0)

            # --- PROCESS NAME ---
            # Remove "TELUGU |" prefixes first
            display_name = re.sub(r'(TELUGU|IN-PREM)\s*\|\s*', '', raw_name, flags=re.IGNORECASE).strip()
            display_name = clean_final_name(display_name)
            
            # --- MATCH LOGO ---
            norm_key = re.sub(r'[^a-z0-9]', '', display_name.lower())
            logo = ch.get('logo', '')
            if norm_key in json_db:
                display_name = json_db[norm_key]['name']
                logo = json_db[norm_key]['logo']

            # --- DEDUPLICATION & LIVE CHECK ---
            # If we already have this channel name, check if the current one works
            if norm_key not in unique_channels:
                print(f"Checking: {display_name}...")
                if check_link(stream_url):
                    entry = (f'#EXTINF:-1 tvg-id="{ch.get("xmltv_id", "")}" '
                             f'tvg-logo="{logo}" group-title="{NEW_GROUP_NAME}", {display_name}\n'
                             f'{stream_url}|User-Agent={USER_AGENT}')
                    unique_channels[norm_key] = entry

        # --- SAVE FILE ---
        if unique_channels:
            sorted_entries = sorted(unique_channels.values(), key=lambda x: x.split(",")[-1])
            with open("Live.m3u", "w", encoding="utf-8") as f:
                f.write(f'#EXTM3U x-tvg-url="{EPG_URL}"\n# POWERED BY: {POWERED_BY}\n\n')
                f.write("\n".join(sorted_entries))
            print(f"[SUCCESS] Saved {len(unique_channels)} unique, working channels.")

    except Exception as e:
        print(f"[-] Error: {e}")

if __name__ == "__main__":
    run_sync()
