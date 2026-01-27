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
    """Verifies if the stream is active."""
    try:
        r = requests.head(url, headers={'User-Agent': USER_AGENT}, timeout=2)
        return r.status_code == 200
    except:
        return False

def clean_final_name(name):
    if not name: return ""

    # 1. Standardize Case for Suffixes
    name = re.sub(r'\b(hd|Hd|hD)\b', 'HD', name)
    name = re.sub(r'\b(tv|Tv|tV)\b', 'TV', name)
    name = re.sub(r'\b(fhd|Fhd|FHD)\b', 'HD', name)
    name = re.sub(r'\bsd\b', '', name, flags=re.IGNORECASE) # Remove "Sd" tags

    # 2. Strict Mapping Rules
    mapping = {
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
        r"Zee Telugu Sd": "Zee Telugu",
        r"Abn Andhra Jyothy": "ABN Andhra Jyothi"
    }

    for pattern, replacement in mapping.items():
        if re.search(pattern, name, re.IGNORECASE):
            name = replacement
            break
    
    # Final cleanup of extra spaces
    return ' '.join(name.split()).strip()

def get_json_db():
    db = {}
    try:
        resp = requests.get(SOURCE_TV_TELUGU, timeout=10)
        for item in resp.json():
            name = item.get('Channel Name', '').strip()
            # Normalize for matching
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
    
    # List of channels to totally remove
    BLACKLIST = ["udaya movies"]

    try:
        print("[*] Connecting to Portal...")
        auth = session.get(f"{PORTAL_URL}/portal.php?type=stb&action=handshake&JsHttpRequest=1-xml", headers=headers).json()
        token = auth.get('js', {}).get('token')
        session.headers.update({'Authorization': f'Bearer {token}', 'Cookie': f'mac={MAC_ADDR}'})
        
        channels_data = session.get(f"{PORTAL_URL}/portal.php?type=itv&action=get_all_channels&JsHttpRequest=1-xml").json()
        channels = channels_data.get('js', {}).get('data', [])

        unique_channels = {} # Key: Normalized Name, Value: M3U Entry

        for ch in channels:
            raw_name = ch.get('name', '')
            
            # Blacklist Filter
            if any(b in raw_name.lower() for b in BLACKLIST): continue

            # Telugu Filter
            if "telugu" not in raw_name.lower() and "telugu" not in str(ch.get('tv_genre_id', '')):
                continue

            cmd = ch.get('cmd', '')
            url_match = re.search(r'http[s]?://[^\s|]+', cmd)
            if not url_match: continue
            stream_url = url_match.group(0)

            # Apply strict naming and formatting
            display_name = re.sub(r'(TELUGU|IN-PREM)\s*\|\s*', '', raw_name, flags=re.IGNORECASE).strip()
            display_name = clean_final_name(display_name)
            
            # Matching for strict logo priority
            norm_key = re.sub(r'[^a-z0-9]', '', display_name.lower())
            logo = ch.get('logo', '')
            if norm_key in json_db:
                # Strictly take Logo from JSON if matched
                logo = json_db[norm_key]['logo']

            # DEDUPLICATION: Only add if this brand isn't already stored
            if norm_key not in unique_channels:
                print(f"Validating: {display_name}")
                if check_link(stream_url):
                    entry = (f'#EXTINF:-1 tvg-id="{ch.get("xmltv_id", "")}" '
                             f'tvg-logo="{logo}" group-title="{NEW_GROUP_NAME}", {display_name}\n'
                             f'{stream_url}|User-Agent={USER_AGENT}')
                    unique_channels[norm_key] = entry

        # SAVE FILE
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
