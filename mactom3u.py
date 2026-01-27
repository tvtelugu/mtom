import requests
import json
import re
import os
from datetime import datetime
import pytz

# --- CONFIGURATION ---
PORTAL_URL = "http://line.vueott.com:80"
MAC_ADDR = "00:1A:79:00:3d:1f" 
EPG_URL = "https://avkb.short.gy/tsepg.xml.gz"

# YOUR PRIMARY SOURCE
SOURCE_TV_TELUGU = "https://tvtelugu.pages.dev/logo/channels.json"

USER_AGENT = "Mozilla/5.0 (QtEmbedded; U; Linux; C) AppleWebKit/533.3 (KHTML, like Gecko) MAG200 stbapp ver: 2 rev: 250 Safari/533.3"
NEW_GROUP_NAME = "𝐌𝐚𝐜 𝐓𝐕"
POWERED_BY = "@tvtelugu"

def clean_name(name):
    """Deep cleaning for strict comparison."""
    if not name: return ""
    # Remove technical tags
    name = re.sub(r'(TELUGU|IN-PREM|FHD|HD|SD|UHD|4K|TV)\s*\|\s*', '', name, flags=re.IGNORECASE)
    name = re.sub(r'\b(FHD|HD|SD|UHD|4K|TV|NEWS)\b', '', name, flags=re.IGNORECASE)
    # Remove all non-alphanumeric characters and spaces
    return re.sub(r'[^a-z0-9]', '', name.lower())

def get_strict_logo_db():
    """Fetches your specific JSON and prepares normalized keys."""
    print(f"[*] Fetching Strict Source: {SOURCE_TV_TELUGU}")
    db = []
    try:
        resp = requests.get(SOURCE_TV_TELUGU, timeout=15)
        data = resp.json()
        for item in data:
            orig_name = item.get('Channel Name', '').strip()
            db.append({
                "norm": clean_name(orig_name),
                "display_name": orig_name,
                "logo": item.get('logo'),
                "raw_json_name": orig_name.lower()
            })
        print(f"[+] Loaded {len(db)} strict definitions.")
    except Exception as e:
        print(f"[-] Failed to load source: {e}")
    return db

def run_sync():
    # 1. Load your strict database
    strict_db = get_strict_logo_db()
    
    ist = pytz.timezone('Asia/Kolkata')
    curr_time = datetime.now(ist).strftime('%d %B %Y | %I:%M %p')
    headers = {'User-Agent': USER_AGENT, 'X-User-Agent': 'Model: MAG250', 'Cookie': f'mac={MAC_ADDR}'}
    session = requests.Session()
    
    try:
        # 2. Portal Authentication
        print(f"[*] Connecting to Portal...")
        auth_resp = session.get(f"{PORTAL_URL}/portal.php?type=stb&action=handshake&JsHttpRequest=1-xml", headers=headers)
        token = auth_resp.json().get('js', {}).get('token')
        if not token: return print("[-] Auth Failed.")
        
        session.headers.update({'Authorization': f'Bearer {token}', 'Cookie': f'mac={MAC_ADDR}'})
        
        # 3. Get Channels
        ch_resp = session.get(f"{PORTAL_URL}/portal.php?type=itv&action=get_all_channels&JsHttpRequest=1-xml").json()
        portal_channels = ch_resp.get('js', {}).get('data', [])
        print(f"[*] Portal has {len(portal_channels)} channels. Starting Strict Matching...")

        m3u_entries = []
        matched_portal_ids = set()

        # 4. STRICT MATCHING LOGIC
        # We loop through your JSON entries first to ensure they get priority
        for entry in strict_db:
            target_norm = entry['norm']
            
            for ch in portal_channels:
                p_id = ch.get('id')
                if p_id in matched_portal_ids: continue
                
                p_raw_name = ch.get('name', '')
                p_norm = clean_name(p_raw_name)

                # PARTIAL MATCH: Check if your JSON name is inside the portal name or vice versa
                if target_norm in p_norm or p_norm in target_norm:
                    cmd = ch.get('cmd', '')
                    url_match = re.search(r'http[s]?://[^\s|]+', cmd)
                    
                    if url_match:
                        stream_url = f"{url_match.group(0)}|User-Agent={USER_AGENT}"
                        
                        # Use YOUR name and YOUR logo strictly
                        m3u_line = (f'#EXTINF:-1 tvg-id="{ch.get("xmltv_id", "")}" '
                                    f'tvg-name="{entry["display_name"]}" '
                                    f'tvg-logo="{entry["logo"]}" '
                                    f'group-title="{NEW_GROUP_NAME}", {entry["display_name"]}\n'
                                    f'{stream_url}')
                        
                        m3u_entries.append(m3u_line)
                        matched_portal_ids.add(p_id)
                        # Once matched to a strict logo, move to the next JSON entry
                        break 

        # 5. Save output
        if m3u_entries:
            m3u_entries.sort()
            with open("Live.m3u", "w", encoding="utf-8") as f:
                f.write(f'#EXTM3U x-tvg-url="{EPG_URL}"\n')
                f.write(f'# POWERED BY: {POWERED_BY}\n')
                f.write(f'# TOTAL CHANNELS: {len(m3u_entries)}\n')
                f.write(f'# UPDATED: {curr_time}\n\n')
                f.write("\n".join(m3u_entries))
            print(f"\n[SUCCESS] Live.m3u created with {len(m3u_entries)} strictly matched channels.")
        else:
            print("[-] No matches found between your JSON and the Portal.")

    except Exception as e:
        print(f"[-] Error: {e}")

if __name__ == "__main__":
    run_sync()
