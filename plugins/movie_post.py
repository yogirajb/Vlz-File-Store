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

FOOTER = "Powered By : https://t.me/MzMoviiez"


# ========= HELPERS =========
def size_format(size):
    gb = size / (1024 ** 3)
    return f"{gb:.1f} GB" if gb >= 1 else f"{size / (1024 ** 2):.0f} MB"


def detect_audio(name):
    n = name.lower()
    if "dual" in n:
        return "Dual Audio"
    for a in ["hindi", "english", "tamil", "telugu", "malayalam"]:
        if a in n:
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


def get_episode(name):
    m = re.search(r"(S\d{2}E\d{2})", name.upper())
    return m.group(1) if m else None


def clean_title(name):
    name = re.sub(r"(S\d{2}E\d{2})", "", name, flags=re.I)
    name = re.sub(r"(480p|720p|1080p|x264|x265|hevc|web-dl|bluray|hdrip)", "", name, flags=re.I)
    name = re.sub(r"\.(mkv|mp4|avi|webm)", "", name, flags=re.I)
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


def build_caption(title, files):
    txt = f"🎬 {title}\n\n"
    for f in files:
        ep = f"{f['episode']} | " if f.get("episode") else ""
        txt += (
            f"📁 {f['audio']} | {ep}{f['quality']} | {f['codec']}\n"
            f"     👉 <a href='{f['link']}'>Click Here</a> ({f['size']})\n\n"
        )
    return txt + FOOTER


# ========= FULL AUTO POST =========
@Client.on_message(filters.video | filters.document)
async def auto_post(client, message):

    # 🔐 ADMIN ONLY
    if not message.from_user or message.from_user.id not in ADMINS:
        return

    file = message.video or message.document
    if not file or not file.file_name:
        return

    title = clean_title(file.file_name)

    entry = {
        "episode": get_episode(file.file_name),
        "quality": get_quality(file.file_name),
        "codec": get_codec(file.file_name),
        "audio": detect_audio(file.file_name),
        "size": size_format(file.file_size),
        "link": shortlink(f"{BASE_URL}/dl/{file.file_id}")
    }

    data = movies.find_one({"title": title})

    # ===== UPDATE EXISTING POST =====
    if data:
        files = [
            f for f in data["files"]
            if not (
                f["quality"] == entry["quality"]
                and f["codec"] == entry["codec"]
                and f.get("episode") == entry.get("episode")
            )
        ]
        files.append(entry)

        movies.update_one(
            {"title": title},
            {"$set": {"files": files}}
        )

        await client.edit_message_caption(
            POST_CHANNEL_ID,
            data["post_id"],
            build_caption(title, files),
            parse_mode="html"
        )

    # ===== NEW POST =====
    else:
        poster = get_poster(title)
        caption = build_caption(title, [entry])

        if poster:
            msg = await client.send_photo(
                POST_CHANNEL_ID,
                poster,
                caption=caption,
                parse_mode="html"
            )
        else:
            msg = await client.send_message(
                POST_CHANNEL_ID,
                caption,
                parse_mode="html"
            )

        movies.insert_one({
            "title": title,
            "files": [entry],
            "post_id": msg.id
        })
