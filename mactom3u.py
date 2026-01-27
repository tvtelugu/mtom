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

SOURCE_TATA = "https://raw.githubusercontent.com/ForceGT/Tata-Sky-IPTV/master/code_samples/allChannels.json"
SOURCE_JIO1 = "https://raw.githubusercontent.com/alex8875/m3u/refs/heads/main/jtv.m3u"
SOURCE_JIO2 = "https://raw.githubusercontent.com/alex8875/m3u/refs/heads/main/jstar.m3u"

USER_AGENT = "Mozilla/5.0 (QtEmbedded; U; Linux; C) AppleWebKit/533.3 (KHTML, like Gecko) MAG200 stbapp ver: 2 rev: 250 Safari/533.3"
NEW_GROUP_NAME = "𝐌𝐚𝐜 𝐓𝐕"
POWERED_BY = "@tvtelugu"

def normalize_name(name):
    if not name: return ""
    name = re.sub(r'(TELUGU|IN-PREM|FHD|HD|SD|UHD|4K)\s*\|\s*', '', name, flags=re.IGNORECASE)
    name = re.sub(r'\b(FHD|HD|SD|UHD|4K)\b', '', name, flags=re.IGNORECASE)
    name = re.sub(r'[\(\[\]\)]', '', name)
    name = ' '.join(name.split()).lower().strip()
    if "maa" in name:
        sub = name.replace("star", "").replace("maa", "").replace("tv", "").strip()
        return f"star maa {sub}".strip() if sub else "star maa"
    return name

def get_master_logo_db():
    print("[*] Fetching External Logo Database...")
    db = {}
    sources = [("TATA", SOURCE_TATA, "json"), ("JIO1", SOURCE_JIO1, "m3u"), ("JIO2", SOURCE_JIO2, "m3u")]
    for name, url, fmt in sources:
        try:
            resp = requests.get(url, timeout=10)
            if fmt == "json":
                for item in resp.json():
                    norm = normalize_name(item['channel_name'])
                    db[norm] = {"id": f"ts{item['channel_id']}", "logo": item['channel_logo'], "name": item['channel_name']}
            else:
                matches = re.findall(r'tvg-logo="([^"]+)".*?,(.*?)\n', resp.text)
                for logo_url, ch_name in matches:
                    norm = normalize_name(ch_name)
                    if norm not in db:
                        db[norm] = {"id": "", "logo": logo_url, "name": ch_name.strip()}
        except: continue
    print(f"[+] Loaded {len(db)} logos from external sources.")
    return db

def clean_url(raw_cmd):
    if not raw_cmd: return ""
    match = re.search(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', raw_cmd)
    if not match: return ""
    url = match.group(0)
    # FORCE the MAC address in the URL
    if "mac=" in url:
        url = re.sub(r'mac=[0-9A-Fa-f:]+', f'mac={MAC_ADDR}', url)
    return f"{url}|User-Agent={USER_AGENT}"

def run_sync():
    logo_db = get_master_logo_db()
    ist = pytz.timezone('Asia/Kolkata')
    curr_time = datetime.now(ist).strftime('%d %B %Y | %I:%M %p')
    
    headers = {'User-Agent': USER_AGENT, 'X-User-Agent': 'Model: MAG250', 'Cookie': f'mac={MAC_ADDR}'}
    session = requests.Session()
    
    try:
        print(f"[*] Connecting to: {PORTAL_URL}")
        # 1. Handshake
        handshake_url = f"{PORTAL_URL}/portal.php?type=stb&action=handshake&JsHttpRequest=1-xml"
        auth_resp = session.get(handshake_url, headers=headers)
        auth = auth_resp.json()
        token = auth.get('js', {}).get('token')
        
        if not token:
            print("[-] Critical Error: Could not get Token from Portal. Check MAC address validity.")
            return

        session.headers.update({'Authorization': f'Bearer {token}', 'Cookie': f'mac={MAC_ADDR}'})

        # 2. Get Channels
        print("[*] Requesting Channel List...")
        ch_resp = session.get(f"{PORTAL_URL}/portal.php?type=itv&action=get_all_channels&JsHttpRequest=1-xml").json()
        channels = ch_resp.get('js', {}).get('data', [])

        if not channels:
            print("[-] Error: Portal returned 0 channels. The MAC might be expired or blocked.")
            return

        print(f"[*] Portal returned {len(channels)} total channels. Filtering for Telugu...")

        m3u_entries = []
        seen_keys = set()

        for ch in channels:
            p_name = ch.get('name', '')
            norm = normalize_name(p_name)
            
            # BROAD FILTER: Check name or genre for Telugu
            if "telugu" in p_name.lower() or "telugu" in str(ch.get('tv_genre_id', '')).lower():
                if norm in seen_keys: continue
                
                url = clean_url(ch.get('cmd', ''))
                if not url: continue

                final_name = re.sub(r'(TELUGU|IN-PREM)\s*\|\s*', '', p_name, flags=re.IGNORECASE).strip()
                final_logo = ch.get('logo', '')
                final_id = ch.get('xmltv_id', '')

                if norm in logo_db:
                    final_name = logo_db[norm]['name']
                    final_logo = logo_db[norm]['logo']
                    if logo_db[norm]['id']: final_id = logo_db[norm]['id']

                entry = (f'#EXTINF:-1 tvg-id="{final_id}" tvg-name="{final_name}" '
                         f'tvg-logo="{final_logo}" group-title="{NEW_GROUP_NAME}", {final_name}\n{url}')
                
                m3u_entries.append(entry)
                seen_keys.add(norm)

        # 3. Save File
        if m3u_entries:
            m3u_entries.sort(key=lambda x: x.split(",")[-1].strip().lower())
            file_path = os.path.join(os.getcwd(), "Live.m3u")
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(f'#EXTM3U x-tvg-url="{EPG_URL}"\n')
                f.write(f'# POWERED BY: {POWERED_BY}\n')
                f.write(f'# LAST UPDATED: {curr_time} IST\n\n')
                f.write("\n".join(m3u_entries))
            
            print(f"\n[SUCCESS] File Created: {file_path}")
            print(f"[+] Total Telugu Channels Saved: {len(m3u_entries)}")
        else:
            print("[-] No Telugu channels were found in the list. File not created.")
            
    except Exception as e: 
        print(f"[-] Python Error: {e}")

if __name__ == "__main__":
    run_sync()
