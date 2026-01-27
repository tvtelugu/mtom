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

def check_link(url):
    """Checks if stream is alive within 2 seconds."""
    try:
        r = requests.head(url, headers={'User-Agent': USER_AGENT}, timeout=2)
        return r.status_code == 200
    except:
        return False

def clean_final_name(name):
    """Strict standardization and targeted renaming."""
    if not name: return ""

    # 1. Generic Standardizing (Case & Quality)
    name = re.sub(r'\b(hd|Hd|hD)\b', 'HD', name)
    name = re.sub(r'\b(tv|Tv|tV)\b', 'TV', name)
    name = re.sub(r'\b(fhd|Fhd|FHD)\b', 'HD', name)
    
    # 2. Targeted Forced Renames
    mapping = {
        r"STUDIO ONEP": "Studio One +",
        r"STUDIO YUVA": "Studio Yuva Alpha",
        r"TATA SKY TELUGU CINEMA": "Tata Play Telugu Cinema",
        r"HOLLYWOOD LOCAL": "Tata Play Hollywood Local Telugu",
        r"Bbc Earth HD": "Sony BBC Earth HD",
        r"Discovery World HD": "Discovery HD World",
        r"Etv$": "ETV Telugu",
        r"Etv Life HD": "ETV Life",
        r"Gemini HD": "Gemini TV HD",
        r"Maa Gold": "Star Maa Gold",
        r"Maa Music": "Star Maa Music",
        r"Maatv": "Star Maa",
        r"Tv9 Telugu News": "TV9 Telugu",
        r"Tv 9": "TV9 Telugu",
        r"Zee CinemaluHD": "Zee Cinemalu HD",
        r"Zee Cinemalu Sd": "Zee Cinemalu",
        r"Zee Telugu Sd": "Zee Telugu"
    }

    for pattern, replacement in mapping.items():
        if re.search(pattern, name, re.IGNORECASE):
            name = replacement
            break
            
    return ' '.join(name.split()).strip()

def get_json_db():
    """Builds a lookup for names and logos from your JSON."""
    db = {}
    try:
        resp = requests.get(SOURCE_TV_TELUGU, timeout=10)
        for item in resp.json():
            name = item.get('Channel Name', '').strip()
            # Normalize key (lowercase, no spaces/symbols)
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
    
    BLACKLIST = ["udaya movies"]

    try:
        print("[*] Connecting to Portal...")
        auth = session.get(f"{PORTAL_URL}/portal.php?type=stb&action=handshake&JsHttpRequest=1-xml", headers=headers).json()
        token = auth.get('js', {}).get('token')
        session.headers.update({'Authorization': f'Bearer {token}', 'Cookie': f'mac={MAC_ADDR}'})
        
        channels_data = session.get(f"{PORTAL_URL}/portal.php?type=itv&action=get_all_channels&JsHttpRequest=1-xml").json()
        channels = channels_data.get('js', {}).get('data', [])

        unique_channels = {} 

        for ch in channels:
            raw_name = ch.get('name', '')
            
            # Skip blacklisted or non-telugu
            if any(b in raw_name.lower() for b in BLACKLIST): continue
            if "telugu" not in raw_name.lower() and "telugu" not in str(ch.get('tv_genre_id', '')):
                continue

            cmd = ch.get('cmd', '')
            url_match = re.search(r'http[s]?://[^\s|]+', cmd)
            if not url_match: continue
            stream_url = url_match.group(0)

            # 1. Clean the name based on rules
            display_name = re.sub(r'(TELUGU|IN-PREM)\s*\|\s*', '', raw_name, flags=re.IGNORECASE).strip()
            display_name = clean_final_name(display_name)
            
            # 2. Strict Logo & Name Match from your JSON
            norm_key = re.sub(r'[^a-z0-9]', '', display_name.lower())
            logo = ch.get('logo', '')
            
            if norm_key in json_db:
                # OVERWRITE with JSON data
                display_name = json_db[norm_key]['name']
                logo = json_db[norm_key]['logo']

            # 3. Deduplication: One working channel per Brand
            if norm_key not in unique_channels:
                print(f"Testing: {display_name}...")
                if check_link(stream_url):
                    entry = (f'#EXTINF:-1 tvg-id="{ch.get("xmltv_id", "")}" '
                             f'tvg-logo="{logo}" group-title="{NEW_GROUP_NAME}", {display_name}\n'
                             f'{stream_url}|User-Agent={USER_AGENT}')
                    unique_channels[norm_key] = entry

        # Save to M3U
        if unique_channels:
            sorted_entries = sorted(unique_channels.values(), key=lambda x: x.split(",")[-1])
            with open("Live.m3u", "w", encoding="utf-8") as f:
                f.write(f'#EXTM3U x-tvg-url="{EPG_URL}"\n# POWERED BY: {POWERED_BY}\n\n')
                f.write("\n".join(sorted_entries))
            print(f"\n[SUCCESS] Final list created with {len(unique_channels)} channels.")

    except Exception as e:
        print(f"[-] Error: {e}")

if __name__ == "__main__":
    run_sync()
