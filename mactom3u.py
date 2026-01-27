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
SOURCE_TATA = "https://raw.githubusercontent.com/ForceGT/Tata-Sky-IPTV/master/code_samples/allChannels.json"

USER_AGENT = "Mozilla/5.0 (QtEmbedded; U; Linux; C) AppleWebKit/533.3 (KHTML, like Gecko) MAG200 stbapp ver: 2 rev: 250 Safari/533.3"
NEW_GROUP_NAME = "𝐌𝐚𝐜 𝐓𝐕"
POWERED_BY = "@tvtelugu"

def normalize_name(name):
    if not name: return ""
    # Remove technical suffixes and prefixes
    name = re.sub(r'(TELUGU|IN-PREM|FHD|HD|SD|UHD|4K)\s*\|\s*', '', name, flags=re.IGNORECASE)
    name = re.sub(r'\b(FHD|HD|SD|UHD|4K)\b', '', name, flags=re.IGNORECASE)
    name = re.sub(r'[\(\[\]\)]', '', name)
    # Remove all spaces for "fuzzy" comparison
    return "".join(name.split()).lower().strip()

def get_master_logo_db():
    print("[*] Fetching External Logo Database...")
    db = {}
    sources = [
        ("TV_TELUGU", SOURCE_TV_TELUGU, "json_alt"), 
        ("TATA", SOURCE_TATA, "json")
    ]
    
    for name, url, fmt in sources:
        try:
            resp = requests.get(url, timeout=10)
            if fmt == "json_alt":
                for item in resp.json():
                    orig_name = item.get('Channel Name', '')
                    norm = normalize_name(orig_name)
                    db[norm] = {"logo": item.get('logo'), "name": orig_name, "id": ""}
            elif fmt == "json":
                for item in resp.json():
                    norm = normalize_name(item['channel_name'])
                    if norm not in db:
                        db[norm] = {"logo": item['channel_logo'], "name": item['channel_name'], "id": f"ts{item['channel_id']}"}
        except: continue
    return db

def find_best_match(portal_name, logo_db):
    """
    Attempts to find a logo even if the match is only partial.
    """
    p_norm = normalize_name(portal_name)
    
    # 1. Try Exact Match
    if p_norm in logo_db:
        return logo_db[p_norm]
    
    # 2. Try Partial Match (is logo name inside portal name or vice versa?)
    for db_norm, data in logo_db.items():
        if db_norm in p_norm or p_norm in db_norm:
            return data
            
    return None

def run_sync():
    logo_db = get_master_logo_db()
    ist = pytz.timezone('Asia/Kolkata')
    curr_time = datetime.now(ist).strftime('%d %B %Y | %I:%M %p')
    
    headers = {'User-Agent': USER_AGENT, 'X-User-Agent': 'Model: MAG250', 'Cookie': f'mac={MAC_ADDR}'}
    session = requests.Session()
    
    try:
        print(f"[*] Connecting to: {PORTAL_URL}")
        auth_resp = session.get(f"{PORTAL_URL}/portal.php?type=stb&action=handshake&JsHttpRequest=1-xml", headers=headers)
        token = auth_resp.json().get('js', {}).get('token')
        
        if not token: return print("[-] Auth Failed.")
        session.headers.update({'Authorization': f'Bearer {token}', 'Cookie': f'mac={MAC_ADDR}'})

        ch_resp = session.get(f"{PORTAL_URL}/portal.php?type=itv&action=get_all_channels&JsHttpRequest=1-xml").json()
        channels = ch_resp.get('js', {}).get('data', [])

        m3u_entries = []
        seen_urls = set()

        for ch in channels:
            raw_name = ch.get('name', '')
            cmd = ch.get('cmd', '')
            
            # Filter for Telugu
            if "telugu" in raw_name.lower() or "telugu" in str(ch.get('tv_genre_id', '')).lower():
                url = re.search(r'http[s]?://[^\s|]+', cmd)
                if not url or url.group(0) in seen_urls: continue
                final_url = f"{url.group(0)}|User-Agent={USER_AGENT}"

                # FORCE PARTIAL MATCHING
                match_data = find_best_match(raw_name, logo_db)
                
                if match_data:
                    final_name = match_data['name']
                    final_logo = match_data['logo']
                    final_id = match_data['id'] or ch.get('xmltv_id', '')
                else:
                    # Fallback to original portal info if no match found
                    final_name = re.sub(r'(TELUGU|IN-PREM)\s*\|\s*', '', raw_name, flags=re.IGNORECASE).strip()
                    final_logo = ch.get('logo', '')
                    final_id = ch.get('xmltv_id', '')

                entry = (f'#EXTINF:-1 tvg-id="{final_id}" tvg-name="{final_name}" '
                         f'tvg-logo="{final_logo}" group-title="{NEW_GROUP_NAME}", {final_name}\n{final_url}')
                
                m3u_entries.append(entry)
                seen_urls.add(url.group(0))

        if m3u_entries:
            with open("Live.m3u", "w", encoding="utf-8") as f:
                f.write(f'#EXTM3U x-tvg-url="{EPG_URL}"\n# POWERED BY: {POWERED_BY}\n\n')
                f.write("\n".join(m3u_entries))
            print(f"[+] Saved {len(m3u_entries)} channels with forced matching.")

    except Exception as e: print(f"[-] Error: {e}")

if __name__ == "__main__":
    run_sync()
