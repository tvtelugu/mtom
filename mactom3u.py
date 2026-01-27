import requests
import re
import os
import json
from datetime import datetime
import pytz

# --- CONFIGURATION ---
PORTAL_URL = "http://line.vueott.com:80"
MAC_ADDR = "00:1A:79:00:3d:1f" 
EPG_URL = "https://avkb.short.gy/tsepg.xml.gz"
SOURCE_TV_TELUGU = "https://tvtelugu.pages.dev/logo/channels.json"

USER_AGENT = "Mozilla/5.0 (QtEmbedded; U; Linux; C) AppleWebKit/533.3 (KHTML, like Gecko) MAG200 stbapp ver: 2 rev: 250 Safari/533.3"
NEW_GROUP_NAME = "𝐌𝐚𝐜 𝐓𝐕"
MOVIE_GROUP_NAME = "𝐌𝐨𝐯𝐢𝐞𝐬"
POWERED_BY = "@tvtelugu"

def check_link(url):
    """Verifies if stream is alive within 3 seconds."""
    try:
        r = requests.head(url, headers={'User-Agent': USER_AGENT}, timeout=3, allow_redirects=True)
        return r.status_code == 200
    except:
        return False

def clean_final_name(name):
    """Strict standardization and targeted renaming."""
    if not name: return ""

    # 1. Standardize Case and Global Typo Fix
    name = re.sub(r'\b(hd|Hd|hD)\b', 'HD', name)
    name = re.sub(r'\b(tv|Tv|tV)\b', 'TV', name)
    name = re.sub(r'\b(fhd|Fhd|FHD|4k|4K)\b', 'HD', name)
    name = re.sub(r'Telegu', 'Telugu', name, flags=re.IGNORECASE)
    
    # Remove 'SD' or 'Sd' specifically to keep names clean
    name = re.sub(r'\b(sd|Sd|SD)\b', '', name).strip()

    # 2. FORCED RENAMES (Specific User Requests)
    mapping = {
        r"TV\s*9": "TV9 Telugu",
        r"CINEMANIA HD": "Cine Mania",
        r"CINEMANIA": "Cine Mania",
        r"ZEE CINEMALU SD": "Zee Cinemalu",
        r"Nat Geo Wild": "Nat Geo Wild HD",
        r"Ntv News": "NTV Telugu",
        r"Raj Musix": "Raj Musix Telugu",
        r"Raj News": "Raj News Telugu",
        r"Nat Geo HD": "National Geographic HD",
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
        r"Zee CinemaluHD": "Zee Cinemalu HD",
        r"Zee Telugu Sd": "Zee Telugu",
        r"Abn Andhra Jyothy": "ABN Andhra Jyothi"
    }

    # 3. DYNAMIC RENAMING (Telugu 1-10, Telugu 2022 -> Telugu Movies 24/7)
    if re.search(r'Telugu\s*([1-9]|10|2022)', name, re.IGNORECASE):
        return "Telugu Movies 24/7"

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
        print(f"[*] Connecting to Portal: {PORTAL_URL}")
        auth = session.get(f"{PORTAL_URL}/portal.php?type=stb&action=handshake&JsHttpRequest=1-xml", headers=headers).json()
        token = auth.get('js', {}).get('token')
        session.headers.update({'Authorization': f'Bearer {token}', 'Cookie': f'mac={MAC_ADDR}'})
        
        cat_resp = session.get(f"{PORTAL_URL}/portal.php?type=itv&action=get_genres&JsHttpRequest=1-xml").json()
        genres = {g.get('id'): g.get('title', '').lower() for g in cat_resp.get('js', [])}

        ch_resp = session.get(f"{PORTAL_URL}/portal.php?type=itv&action=get_all_channels&JsHttpRequest=1-xml").json()
        channels = ch_resp.get('js', {}).get('data', [])

        unique_channels = {} 
        seen_streams = set()

        for ch in channels:
            raw_name = ch.get('name', '')
            genre_name = genres.get(ch.get('tv_genre_id'), "")
            
            # Broad search for Telugu content
            is_match = re.search(r"(telugu|telegu|cine mania|tv 9|cinemania)", raw_name, re.IGNORECASE) or re.search(r"(telugu|telegu)", genre_name, re.IGNORECASE)
            if not is_match or any(b in raw_name.lower() for b in BLACKLIST): continue

            cmd = ch.get('cmd', '')
            url_match = re.search(r'http[s]?://[^\s|]+', cmd)
            if not url_match: continue
            stream_url = url_match.group(0)

            if stream_url in seen_streams: continue

            # Cleanup and Rename
            display_name = re.sub(r'(TELUGU|TELEGU|IN-PREM)\s*\|\s*', '', raw_name, flags=re.IGNORECASE).strip()
            display_name = clean_final_name(display_name)
            
            # Group assignment
            target_group = NEW_GROUP_NAME
            if display_name == "Telugu Movies 24/7" or "Cine Mania" in display_name:
                target_group = MOVIE_GROUP_NAME

            # Logo override
            logo = ch.get('logo', '')
            if "24-7.png" in logo or display_name == "Telugu Movies 24/7":
                logo = "https://tvtelugu.pages.dev/logo/tvtelugu.png"

            norm_key = re.sub(r'[^a-z0-9]', '', display_name.lower())
            
            # JSON priority override
            if norm_key in json_db:
                display_name = json_db[norm_key]['name']
                logo = json_db[norm_key]['logo']

            # Deduplication logic
            if norm_key in unique_channels and display_name != "Telugu Movies 24/7":
                continue

            print(f"Checking: {display_name}")
            if check_link(stream_url):
                # Unique keys for 24/7 movies to prevent auto-merging different movie streams
                final_key = norm_key if display_name != "Telugu Movies 24/7" else f"{norm_key}_{len(seen_streams)}"
                
                entry = (f'#EXTINF:-1 tvg-id="{ch.get("xmltv_id", "")}" '
                         f'tvg-logo="{logo}" group-title="{target_group}", {display_name}\n'
                         f'{stream_url}|User-Agent={USER_AGENT}')
                
                unique_channels[final_key] = entry
                seen_streams.add(stream_url)

        if unique_channels:
            # Sort: Movies group first, then alpha
            sorted_entries = sorted(unique_channels.values(), key=lambda x: (MOVIE_GROUP_NAME not in x, x.split(",")[-1].strip().lower()))
            with open("Live.m3u", "w", encoding="utf-8") as f:
                f.write(f'#EXTM3U x-tvg-url="{EPG_URL}"\n# POWERED BY: {POWERED_BY}\n\n')
                f.write("\n".join(sorted_entries))
            print(f"[SUCCESS] Live.m3u created with {len(unique_channels)} channels.")

    except Exception as e: print(f"[-] Error: {e}")

if __name__ == "__main__":
    run_sync()
