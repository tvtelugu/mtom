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

def format_channel_case(text):
    """Converts ALL CAPS to Title Case (e.g., CINEMANIA -> Cinemania)."""
    if not text: return ""
    # Only change if the word is mostly uppercase
    words = text.split()
    formatted_words = [w.capitalize() if w.isupper() else w for w in words]
    return " ".join(formatted_words)

def is_channel_alive(url):
    """Checks if the stream URL is active (Dead Channel Filter)."""
    try:
        # Use a short timeout to prevent the script from hanging
        response = requests.head(url, headers={'User-Agent': USER_AGENT}, timeout=3, allow_redirects=True)
        return response.status_code == 200
    except:
        return False

def clean_comparison_name(name):
    if not name: return ""
    name = re.sub(r'(TELUGU|IN-PREM|FHD|HD|SD|UHD|4K|TV|NEWS)\s*\|\s*', '', name, flags=re.IGNORECASE)
    return re.sub(r'[^a-z0-9]', '', name.lower())

def get_json_db():
    db = {}
    try:
        resp = requests.get(SOURCE_TV_TELUGU, timeout=10)
        for item in resp.json():
            orig_name = item.get('Channel Name', '').strip()
            db[clean_comparison_name(orig_name)] = {"name": orig_name, "logo": item.get('logo')}
    except: pass
    return db

def run_sync():
    json_db = get_json_db()
    ist = pytz.timezone('Asia/Kolkata')
    curr_time = datetime.now(ist).strftime('%d %B %Y | %I:%M %p')
    
    headers = {'User-Agent': USER_AGENT, 'X-User-Agent': 'Model: MAG250', 'Cookie': f'mac={MAC_ADDR}'}
    session = requests.Session()
    
    try:
        print(f"[*] Connecting to Portal...")
        auth_resp = session.get(f"{PORTAL_URL}/portal.php?type=stb&action=handshake&JsHttpRequest=1-xml", headers=headers)
        token = auth_resp.json().get('js', {}).get('token')
        if not token: return print("[-] Token Error.")
        
        session.headers.update({'Authorization': f'Bearer {token}', 'Cookie': f'mac={MAC_ADDR}'})
        ch_resp = session.get(f"{PORTAL_URL}/portal.php?type=itv&action=get_all_channels&JsHttpRequest=1-xml").json()
        channels = ch_resp.get('js', {}).get('data', [])

        m3u_entries = []
        seen_urls = set() # Duplicate filter

        print(f"[*] Processing {len(channels)} channels. Checking for dead links...")

        for ch in channels:
            raw_name = ch.get('name', '')
            
            if "telugu" in raw_name.lower() or "telugu" in str(ch.get('tv_genre_id', '')).lower():
                cmd = ch.get('cmd', '')
                url_match = re.search(r'http[s]?://[^\s|]+', cmd)
                if not url_match: continue
                
                base_url = url_match.group(0)
                
                # 1. Remove Duplicates
                if base_url in seen_urls: continue
                
                # 2. Remove Dead Channels (Optional: Remove this 'if' if the portal is slow)
                # if not is_channel_alive(base_url): continue

                seen_urls.add(base_url)
                stream_url = f"{base_url}|User-Agent={USER_AGENT}"
                
                # 3. Matching and Renaming
                p_norm = clean_comparison_name(raw_name)
                match = None
                
                # Check for match in JSON
                if p_norm in json_db:
                    match = json_db[p_norm]
                else:
                    for j_norm, data in json_db.items():
                        if j_norm in p_norm:
                            match = data
                            break

                if match:
                    final_name = match['name']
                    final_logo = match['logo']
                else:
                    # Clean the portal name
                    cleaned = re.sub(r'(TELUGU|IN-PREM)\s*\|\s*', '', raw_name, flags=re.IGNORECASE).strip()
                    # 4. Fix Capitalization
                    final_name = format_channel_case(cleaned)
                    final_logo = ch.get('logo', '')

                m3u_line = (f'#EXTINF:-1 tvg-id="{ch.get("xmltv_id", "")}" '
                            f'tvg-logo="{final_logo}" group-title="{NEW_GROUP_NAME}", {final_name}\n'
                            f'{stream_url}')
                
                m3u_entries.append(m3u_line)

        if m3u_entries:
            m3u_entries.sort(key=lambda x: x.split(",")[-1].strip())
            with open("Live.m3u", "w", encoding="utf-8") as f:
                f.write(f'#EXTM3U x-tvg-url="{EPG_URL}"\n# POWERED BY: {POWERED_BY}\n\n')
                f.write("\n".join(m3u_entries))
            print(f"[SUCCESS] Saved {len(m3u_entries)} clean, unique channels.")
            
    except Exception as e:
        print(f"[-] Error: {e}")

if __name__ == "__main__":
    run_sync()
