import urllib.request
import urllib.parse
import json
import time
import os
import subprocess
import threading

BOT_TOKEN = "8617750956:AAGaxjK85kAP1Q605KXnK5-P0IpeJ7enrD8"
BASE_URL = "https://api.telegram.org/bot" + BOT_TOKEN

# Simple cache: query -> telegram file_id (so repeated songs send instantly)
CACHE_FILE = "music_cache.json"

def load_cache():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r") as f:
                return json.load(f)
        except:
            pass
    return {}

def save_cache(cache):
    try:
        with open(CACHE_FILE, "w") as f:
            json.dump(cache, f)
    except:
        pass

cache = load_cache()


# ── Telegram helpers ──────────────────────────────────────────────

def tg(method, params=None, files=None):
    url = BASE_URL + "/" + method
    if files:
        # multipart upload
        boundary = "----MusicBot2025"
        body = b""
        for name, value in (params or {}).items():
            body += ("--" + boundary + "\r\n").encode()
            body += ('Content-Disposition: form-data; name="' + name + '"\r\n\r\n').encode()
            body += (str(value) + "\r\n").encode()
        for name, (filename, filedata, mimetype) in files.items():
            body += ("--" + boundary + "\r\n").encode()
            body += ('Content-Disposition: form-data; name="' + name + '"; filename="' + filename + '"\r\n').encode()
            body += ("Content-Type: " + mimetype + "\r\n\r\n").encode()
            body += filedata
            body += b"\r\n"
        body += ("--" + boundary + "--\r\n").encode()
        req = urllib.request.Request(url, data=body,
            headers={"Content-Type": "multipart/form-data; boundary=" + boundary})
        timeout = 120
    else:
        data = json.dumps(params).encode("utf-8") if params else None
        req = urllib.request.Request(url, data=data,
            headers={"Content-Type": "application/json"} if data else {})
        timeout = 15
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print("[TG error]", e)
        return None


def send_msg(chat_id, text, markup=None):
    p = {"chat_id": chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}
    if markup: p["reply_markup"] = markup
    return tg("sendMessage", p)

def edit_msg(chat_id, msg_id, text, markup=None):
    p = {"chat_id": chat_id, "message_id": msg_id, "text": text, "parse_mode": "HTML"}
    if markup: p["reply_markup"] = markup
    tg("editMessageText", p)

def send_action(chat_id, action="upload_document"):
    tg("sendChatAction", {"chat_id": chat_id, "action": action})

def answer_cb(cb_id, text=""):
    tg("answerCallbackQuery", {"callback_query_id": cb_id, "text": text})


# ── Music search & download ───────────────────────────────────────

def search_itunes(query, limit=6):
    try:
        url = "https://itunes.apple.com/search?term=" + urllib.parse.quote(query) + \
              "&media=music&entity=song&limit=" + str(limit)
        with urllib.request.urlopen(url, timeout=8) as r:
            return json.loads(r.read().decode()).get("results", [])
    except:
        return []

def download_mp3(query):
    """Download full MP3 via archive.org free music search."""
    out = "dl_" + str(abs(hash(query.lower())) % 999999) + ".mp3"
    if os.path.exists(out): os.remove(out)

    # Search archive.org (whitelisted, has millions of free MP3s)
    search_url = "https://archive.org/advancedsearch.php?q=" + urllib.parse.quote(query + " audio") + "&fl[]=identifier,title,creator&rows=5&output=json&mediatype=audio"
    print("[Archive.org] Searching:", query)
    try:
        req = urllib.request.Request(search_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            results = json.loads(r.read().decode())
        docs = results.get("response", {}).get("docs", [])
        print("[Archive.org] Found", len(docs), "results")
    except Exception as e:
        print("[Archive.org search error]", e)
        docs = []

    for doc in docs:
        identifier = doc.get("identifier", "")
        if not identifier:
            continue
        # Get file listing for this item
        meta_url = "https://archive.org/metadata/" + identifier
        try:
            req = urllib.request.Request(meta_url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as r:
                meta = json.loads(r.read().decode())
            files = meta.get("files", [])
            # Find an mp3 file
            for f in files:
                if f.get("name", "").lower().endswith(".mp3"):
                    mp3_url = "https://archive.org/download/" + identifier + "/" + urllib.parse.quote(f["name"])
                    print("[Archive.org] Downloading:", mp3_url[:80])
                    try:
                        req2 = urllib.request.Request(mp3_url, headers={"User-Agent": "Mozilla/5.0"})
                        with urllib.request.urlopen(req2, timeout=60) as r2:
                            data = r2.read()
                        if len(data) > 50000:  # at least 50kb
                            with open(out, "wb") as fout:
                                fout.write(data)
                            print("[Archive.org] Downloaded", len(data), "bytes")
                            return out
                    except Exception as e:
                        print("[Archive.org download error]", e)
                        continue
        except Exception as e:
            print("[Archive.org meta error]", e)
            continue

    print("[Archive.org] Nothing found for:", query)
    return None


# ── Main handlers ─────────────────────────────────────────────────

POPULAR = ["Top Hits 2024", "Hip Hop", "Pop", "Rock Classics", "Chill Vibes", "R&B"]

def start_keyboard():
    rows = []
    for i in range(0, len(POPULAR), 2):
        row = [{"text": "🎵 " + POPULAR[i], "callback_data": "cat|" + POPULAR[i]}]
        if i+1 < len(POPULAR):
            row.append({"text": "🎵 " + POPULAR[i+1], "callback_data": "cat|" + POPULAR[i+1]})
        rows.append(row)
    return {"inline_keyboard": rows}

def results_keyboard(tracks):
    rows = []
    for i, t in enumerate(tracks):
        name = t.get("trackName", "?")[:30]
        artist = t.get("artistName", "?")[:20]
        rows.append([{"text": "⬇️  " + artist + " – " + name, "callback_data": "dl|" + str(i)}])
    return {"inline_keyboard": rows}


# Temporary store for search results per user
user_results = {}  # chat_id -> list of tracks

def handle_message(msg):
    chat_id = msg["chat"]["id"]
    text = msg.get("text", "").strip()
    if not text: return
    print("[MSG]", chat_id, repr(text[:50]))

    if text.startswith("/start"):
        send_msg(chat_id,
            "🎵 <b>Music Bot</b>\n\n"
            "Type any <b>song</b> or <b>artist</b> name and I'll find it for you!\n"
            "You can also search by <b>lyrics</b> 🎶\n\n"
            "Or pick a collection below 👇",
            start_keyboard()
        )
        return

    if text.startswith("/"): return

    # Search iTunes for results
    send_action(chat_id, "typing")
    tracks = search_itunes(text, limit=6)

    if not tracks:
        send_msg(chat_id, "😔 Nothing found for <b>" + text + "</b>\nTry a different name.")
        return

    user_results[chat_id] = tracks

    send_msg(chat_id,
        "🔎 Results for <b>" + text + "</b> — tap to download 👇",
        results_keyboard(tracks)
    )


def process_download(chat_id, query, track_name, artist, status_msg_id):
    global cache
    key = (artist + " " + track_name).lower().strip()

    # Check cache first — instant send!
    if key in cache:
        edit_msg(chat_id, status_msg_id, "⚡ Sending from cache…")
        file_id = cache[key]
        result = tg("sendAudio", {
            "chat_id": chat_id,
            "audio": file_id,
            "title": track_name,
            "performer": artist,
        })
        if result and result.get("ok"):
            edit_msg(chat_id, status_msg_id, "✅ Done! Search another song anytime 🎵")
            return
        else:
            # Cache miss (file expired), fall through to download
            del cache[key]
            save_cache(cache)

    edit_msg(chat_id, status_msg_id, "⬇️ Downloading <b>" + artist + " – " + track_name + "</b>…")
    send_action(chat_id, "upload_document")

    path = download_mp3(query)

    if path is None:
        edit_msg(chat_id, status_msg_id,
            "😔 Couldn't find <b>" + track_name + "</b>.\nTry typing: <code>" + artist + " " + track_name + "</code>")
        return

    edit_msg(chat_id, status_msg_id, "📤 Uploading…")
    with open(path, "rb") as f:
        file_data = f.read()
    try: os.remove(path)
    except: pass

    result = tg("sendAudio", {
        "chat_id": chat_id,
        "title": track_name[:64],
        "performer": artist[:64],
    }, files={"audio": ("audio.mp3", file_data, "audio/mpeg")})

    if result and result.get("ok"):
        # Save file_id to cache
        sent = result["result"]
        fid = sent.get("audio", {}).get("file_id")
        if fid:
            cache[key] = fid
            save_cache(cache)
        done_msg = "✅ Done! Search another song anytime 🎵"
        if is_preview:
            done_msg = "⏱ 30s preview (full song unavailable on this server)🎵\nSearch another song anytime!"
        edit_msg(chat_id, status_msg_id, done_msg)
    else:
        edit_msg(chat_id, status_msg_id, "❌ Upload failed. File might be too large (50MB limit).")


def handle_callback(cb):
    chat_id = cb["message"]["chat"]["id"]
    msg_id  = cb["message"]["message_id"]
    data    = cb.get("data", "")
    cb_id   = cb["id"]
    answer_cb(cb_id)

    if data.startswith("cat|"):
        genre = data[4:]
        send_action(chat_id, "typing")
        tracks = search_itunes(genre + " music", limit=6)
        if not tracks:
            send_msg(chat_id, "😔 Nothing found for " + genre)
            return
        user_results[chat_id] = tracks
        send_msg(chat_id,
            "🎵 <b>" + genre + "</b> — tap to download 👇",
            results_keyboard(tracks)
        )

    elif data.startswith("dl|"):
        idx = int(data[3:])
        tracks = user_results.get(chat_id, [])
        if not tracks or idx >= len(tracks):
            send_msg(chat_id, "⚠️ Session expired. Search again.")
            return

        track = tracks[idx]
        track_name = track.get("trackName", "Unknown")
        artist     = track.get("artistName", "Unknown")
        query      = artist + " " + track_name

        r = send_msg(chat_id, "🔍 Looking up <b>" + artist + " – " + track_name + "</b>…")
        if not r or not r.get("ok"): return
        status_id = r["result"]["message_id"]

        t = threading.Thread(
            target=process_download,
            args=(chat_id, query, track_name, artist, status_id),
            daemon=True
        )
        t.start()


# ── Polling loop ──────────────────────────────────────────────────

def run_bot():
    print("=" * 50)
    print("  🎵 Music Bot is running!")
    print("=" * 50)

    me = tg("getMe")
    if not me or not me.get("ok"):
        print("❌ Cannot connect to Telegram. Check token / internet.")
        return
    print("  Bot: @" + me["result"].get("username", "?"))
    print("  Cache:", len(cache), "songs stored\n")

    offset = None
    while True:
        params = {"timeout": 5, "allowed_updates": ["message", "callback_query"]}
        if offset: params["offset"] = offset

        resp = tg("getUpdates", params)
        if resp and resp.get("ok"):
            for upd in resp["result"]:
                offset = upd["update_id"] + 1
                try:
                    if "message" in upd:
                        handle_message(upd["message"])
                    elif "callback_query" in upd:
                        handle_callback(upd["callback_query"])
                except Exception as e:
                    print("[Error]", e)
        else:
            time.sleep(3)

if __name__ == "__main__":
    run_bot()
