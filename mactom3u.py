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
SOURCE_TV_TELUGU = "https://tvtelugu.pages.dev/logo/channels.json"

USER_AGENT = "Mozilla/5.0 (QtEmbedded; U; Linux; C) AppleWebKit/533.3 (KHTML, like Gecko) MAG200 stbapp ver: 2 rev: 250 Safari/533.3"
NEW_GROUP_NAME = "𝐌𝐚𝐜 𝐓𝐕"
POWERED_BY = "@tvtelugu"

def clean_comparison_name(name):
    """Removes all special characters and technical tags for matching."""
    if not name: return ""
    name = re.sub(r'(TELUGU|IN-PREM|FHD|HD|SD|UHD|4K|TV|NEWS)\s*\|\s*', '', name, flags=re.IGNORECASE)
    name = re.sub(r'\b(FHD|HD|SD|UHD|4K|TV|NEWS)\b', '', name, flags=re.IGNORECASE)
    return re.sub(r'[^a-z0-9]', '', name.lower())

def get_json_db():
    """Fetches your JSON and creates a lookup dictionary."""
    print(f"[*] Fetching Reference Logos: {SOURCE_TV_TELUGU}")
    db = {}
    try:
        resp = requests.get(SOURCE_TV_TELUGU, timeout=15)
        for item in resp.json():
            orig_name = item.get('Channel Name', '').strip()
            norm = clean_comparison_name(orig_name)
            db[norm] = {"name": orig_name, "logo": item.get('logo')}
    except Exception as e:
        print(f"[-] JSON Load Error: {e}")
    return db

def find_strict_match(portal_name, json_db):
    """Checks for a match in the JSON database."""
    p_norm = clean_comparison_name(portal_name)
    
    # Check 1: Exact normalized match
    if p_norm in json_db:
        return json_db[p_norm]
    
    # Check 2: Partial match (If JSON name is inside Portal name)
    for j_norm, data in json_db.items():
        if j_norm != "" and (j_norm in p_norm or p_norm in j_norm):
            return data
            
    return None

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
        seen_urls = set()

        for ch in channels:
            raw_name = ch.get('name', '')
            
            # Filter for Telugu Channels Only
            if "telugu" in raw_name.lower() or "telugu" in str(ch.get('tv_genre_id', '')).lower():
                cmd = ch.get('cmd', '')
                url_match = re.search(r'http[s]?://[^\s|]+', cmd)
                if not url_match or url_match.group(0) in seen_urls: continue
                
                stream_url = f"{url_match.group(0)}|User-Agent={USER_AGENT}"
                
                # ATTEMPT MATCHING
                match = find_strict_match(raw_name, json_db)
                
                if match:
                    # IF MATCHED: Use JSON details
                    final_name = match['name']
                    final_logo = match['logo']
                else:
                    # IF NOT MATCHED: Clean original portal name but keep portal logo
                    final_name = re.sub(r'(TELUGU|IN-PREM)\s*\|\s*', '', raw_name, flags=re.IGNORECASE).strip()
                    final_logo = ch.get('logo', '')

                m3u_line = (f'#EXTINF:-1 tvg-id="{ch.get("xmltv_id", "")}" '
                            f'tvg-logo="{final_logo}" group-title="{NEW_GROUP_NAME}", {final_name}\n'
                            f'{stream_url}')
                
                m3u_entries.append(m3u_line)
                seen_urls.add(url_match.group(0))

        if m3u_entries:
            m3u_entries.sort(key=lambda x: x.split(",")[-1].strip())
            with open("Live.m3u", "w", encoding="utf-8") as f:
                f.write(f'#EXTM3U x-tvg-url="{EPG_URL}"\n# POWERED BY: {POWERED_BY}\n\n')
                f.write("\n".join(m3u_entries))
            print(f"[SUCCESS] Created M3U with {len(m3u_entries)} channels.")
            
    except Exception as e:
        print(f"[-] Error: {e}")

if __name__ == "__main__":
    run_sync()
