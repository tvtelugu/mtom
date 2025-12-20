import requests
import json
import re
import os
from datetime import datetime
import pytz

# --- CONFIGURATION ---
PORTAL_URL = "http://line.vueott.com:80"
MAC_ADDR = "00:1B:79:33:6A:F2"
EPG_URL = "https://avkb.short.gy/tsepg.xml.gz"

# Logo & Sync Sources
SOURCE_TATA = "https://raw.githubusercontent.com/ForceGT/Tata-Sky-IPTV/master/code_samples/allChannels.json"
SOURCE_JIO1 = "https://raw.githubusercontent.com/alex8875/m3u/refs/heads/main/jtv.m3u"
SOURCE_JIO2 = "https://raw.githubusercontent.com/alex8875/m3u/refs/heads/main/jstar.m3u"

USER_AGENT = "Mozilla/5.0 (QtEmbedded; U; Linux; C) AppleWebKit/533.3 (KHTML, like Gecko) MAG200 stbapp ver: 2 rev: 250 Safari/533.3"
NEW_GROUP_NAME = "𝐌𝐚𝐜 𝐓𝐕"
POWERED_BY = "@tvtelugu"

def normalize_name(name):
    """Deep cleans names for cross-source matching and branding."""
    if not name: return ""
    # Remove portal tags, quality markers
    name = re.sub(r'(TELUGU|IN-PREM|FHD|HD|SD|UHD|4K)\s*\|\s*', '', name, flags=re.IGNORECASE)
    name = re.sub(r'\b(FHD|HD|SD|UHD|4K)\b', '', name, flags=re.IGNORECASE)
    name = re.sub(r'[\(\[\]\)]', '', name)
    name = ' '.join(name.split()).lower().strip()
    
    # Dynamic Branding Rules
    if "maa" in name:
        sub = name.replace("star", "").replace("maa", "").replace("tv", "").strip()
        return f"star maa {sub}".strip()
    if "ntv" in name: return "ntv telugu"
    if "history tv18" in name or "history tv 18" in name: return "history tv18 hd telugu"
    if "vanitha" in name: return "vanitha"
    if "holly" in name and "wood" in name: return "tata play hollywood local"
    
    return name

def get_master_logo_db():
    """Merges logos from all 3 sources."""
    db = {}
    sources = [("TATA", SOURCE_TATA, "json"), ("JIO1", SOURCE_JIO1, "m3u"), ("JIO2", SOURCE_JIO2, "m3u")]
    for name, url, fmt in sources:
        try:
            resp = requests.get(url, timeout=15)
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
    return db

def clean_url(raw_cmd):
    if not raw_cmd: return ""
    match = re.search(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', raw_cmd)
    return f"{match.group(0)}|User-Agent={USER_AGENT}" if match else ""

def run_sync():
    logo_db = get_master_logo_db()
    ist = pytz.timezone('Asia/Kolkata')
    curr_time = datetime.now(ist).strftime('%d-%m-%Y %I:%M %p')
    
    headers = {'User-Agent': USER_AGENT, 'X-User-Agent': 'Model: MAG250', 'Cookie': f'mac={MAC_ADDR}'}
    session = requests.Session()
    
    try:
        print("[*] Portal Handshake...")
        auth = session.get(f"{PORTAL_URL}/portal.php?type=stb&action=handshake&JsHttpRequest=1-xml", headers=headers).json()
        token = auth.get('js', {}).get('token')
        session.headers.update({'Authorization': f'Bearer {token}'})

        print("[*] Fetching Channels...")
        ch_resp = session.get(f"{PORTAL_URL}/portal.php?type=itv&action=get_all_channels&JsHttpRequest=1-xml").json()
        channels = ch_resp.get('js', {}).get('data', [])

        m3u_entries = []
        seen_keys = set()

        for ch in (channels or []):
            p_name = ch.get('name', '')
            norm = normalize_name(p_name)
            
            # Filter Telugu content only
            if "telugu" in p_name.lower() or "telugu" in str(ch.get('tv_genre_id', '')):
                if norm in seen_keys: continue
                
                url = clean_url(ch.get('cmd', ''))
                if not url: continue

                # Default values
                final_name = re.sub(r'(TELUGU|IN-PREM)\s*\|\s*', '', p_name, flags=re.IGNORECASE).strip()
                final_logo = ch.get('logo', '')
                final_id = ch.get('xmltv_id', '')

                # Dynamic Sync Overrides
                if norm in logo_db:
                    final_name = logo_db[norm]['name']
                    if "maa" in norm and "star" not in final_name.lower():
                        final_name = f"Star {final_name}"
                    final_logo = logo_db[norm]['logo']
                    if logo_db[norm]['id']: final_id = logo_db[norm]['id']

                # Format channel display name for @tvtelugu
                final_name = final_name.replace("Tata Sky", "Tata Play")
                
                entry = (f'#EXTINF:-1 tvg-id="{final_id}" tvg-name="{final_name}" '
                         f'tvg-logo="{final_logo}" group-title="{NEW_GROUP_NAME}", {final_name}\n{url}')
                
                m3u_entries.append(entry)
                seen_keys.add(norm)

        if m3u_entries:
            m3u_entries.sort(key=lambda x: x.split(",")[-1].strip().lower())
            with open("Live.m3u", "w", encoding="utf-8") as f:
                f.write(f'#EXTM3U x-tvg-url="{EPG_URL}"\n')
                f.write(f'# {POWERED_BY} | UPDATED: {curr_time} IST\n\n')
                f.write("\n".join(m3u_entries))
            print(f"[SUCCESS] Live.m3u updated with {len(m3u_entries)} channels.")
            
    except Exception as e: print(f"[-] Error: {e}")

if __name__ == "__main__":
    run_sync()
