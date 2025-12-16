from pyrogram import Client, filters
from pymongo import MongoClient
import os, re, requests

# ========= ENV =========
POST_CHANNEL_ID = int(os.environ.get("POST_CHANNEL_ID", "0"))
DB_URI = os.environ.get("DB_URI")
BASE_URL = os.environ.get("BASE_URL")
TMDB_API_KEY = os.environ.get("TMDB_API_KEY")
SHORTLINK_URL = os.environ.get("SHORTLINK_URL")
SHORTLINK_API = os.environ.get("SHORTLINK_API")

ADMINS = [int(x) for x in os.environ.get("ADMINS", "").split() if x.isdigit()]

mongo = MongoClient(DB_URI)
db = mongo["vlz_filestore"]
movies = db.movies
pending = db.pending

FOOTER = "Powered By : https://t.me/MzMoviiez"


# ========= HELPERS =========
def size_format(size):
    gb = size / (1024 ** 3)
    return f"{gb:.1f} GB" if gb >= 1 else f"{size / (1024 ** 2):.0f} MB"


def detect_audio(name):
    name = name.lower()
    if "dual" in name:
        return "Dual Audio"
    for a in ["hindi", "english", "tamil", "telugu", "malayalam"]:
        if a in name:
            return a.title()
    return "Hindi"


def get_quality(name):
    for q in ("480p", "720p", "1080p"):
        if q in name.lower():
            return q
    return "HD"


def get_codec(name):
    for c in ("x265", "x264", "hevc"):
        if c in name.lower():
            return c.upper()
    return "x264"


def extract_series(name):
    match = re.search(r"(S\\d{2}E\\d{2})", name.upper())
    return match.group(1) if match else None


def clean_title(name):
    name = re.sub(r"(S\\d{2}E\\d{2})", "", name, flags=re.I)
    name = re.sub(r"(480p|720p|1080p|x264|x265|hevc)", "", name, flags=re.I)
    name = re.sub(r"\\.(mkv|mp4|avi)", "", name, flags=re.I)
    return name.replace("_", " ").replace(".", " ").strip().title()


def shortlink(url):
    try:
        r = requests.get(
            f"https://{SHORTLINK_URL}/api",
            params={"api": SHORTLINK_API, "url": url},
            timeout=10
        ).json()
        return r.get("shortenedUrl") or url
    except:
        return url


def get_poster(title):
    try:
        r = requests.get(
            "https://api.themoviedb.org/3/search/multi",
            params={"api_key": TMDB_API_KEY, "query": title},
            timeout=5
        ).json()
        if r.get("results"):
            p = r["results"][0].get("poster_path")
            if p:
                return f"https://image.tmdb.org/t/p/w500{p}"
    except:
        pass
    return None


def build_caption(title, items):
    txt = f"🎬 {title}\n\n"
    for i in items:
        ep = f"{i['episode']} | " if i.get("episode") else ""
        txt += (
            f"📁 {i['audio']} | {ep}{i['quality']} | {i['codec']}\n"
            f"     👉 <a href='{i['link']}'>Click Here</a> ({i['size']})\n\n"
        )
    return txt + FOOTER


# ========= AUTO SAVE (PENDING) =========
@Client.on_message(filters.video | filters.document)
async def save_pending(client, message):
    if not message.from_user or message.from_user.id not in ADMINS:
        return

    file = message.video or message.document
    if not file:
        return

    pending.insert_one({
        "file_id": file.file_id,
        "file_name": file.file_name,
        "file_size": file.file_size,
        "chat_id": message.chat.id,
        "msg_id": message.id
    })

    await message.reply("⏳ File saved. Use /approve to post or /reject to cancel.")


# ========= APPROVE =========
@Client.on_message(filters.command("approve") & filters.reply)
async def approve_post(client, message):
    if message.from_user.id not in ADMINS:
        return

    p = pending.find_one({"msg_id": message.reply_to_message.id})
    if not p:
        await message.reply("❌ No pending file found")
        return

    title = clean_title(p["file_name"])
    episode = extract_series(p["file_name"])
    quality = get_quality(p["file_name"])
    codec = get_codec(p["file_name"])
    audio = detect_audio(p["file_name"])

    link = shortlink(f"{BASE_URL}/dl/{p['file_id']}")

    entry = {
        "episode": episode,
        "quality": quality,
        "codec": codec,
        "audio": audio,
        "size": size_format(p["file_size"]),
        "link": link
    }

    data = movies.find_one({"title": title})

    if data:
        data["files"].append(entry)
        movies.update_one({"title": title}, {"$set": {"files": data["files"]}})
        await client.edit_message_caption(
            POST_CHANNEL_ID,
            data["post_id"],
            build_caption(title, data["files"]),
            parse_mode="html"
        )
    else:
        poster = get_poster(title)
        caption = build_caption(title, [entry])
        msg = await client.send_photo(
            POST_CHANNEL_ID,
            poster,
            caption=caption,
            parse_mode="html"
        )
        movies.insert_one({
            "title": title,
            "files": [entry],
            "post_id": msg.id
        })

    pending.delete_one({"_id": p["_id"]})
    await message.reply("✅ Approved & posted")


# ========= REJECT =========
@Client.on_message(filters.command("reject") & filters.reply)
async def reject_post(client, message):
    if message.from_user.id not in ADMINS:
        return
    pending.delete_one({"msg_id": message.reply_to_message.id})
    await message.reply("❌ File rejected")
