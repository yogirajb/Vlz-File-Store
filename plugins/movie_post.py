from pyrogram import Client, filters
from pymongo import MongoClient
import os
import re

# ===== ENV VARIABLES (SAFE FOR KOYEB / HEROKU) =====
POST_CHANNEL_ID = int(os.environ.get("POST_CHANNEL_ID", "0"))
DB_URI = os.environ.get("DB_URI")

# ===== MONGODB =====
mongo = MongoClient(DB_URI)
db = mongo["vlz_filestore"]
movies = db.movies

# ===== CHANNEL FOOTER =====
FOOTER = "Powered By : https://t.me/MzMoviiez"


# ===== UTILS =====
def size_format(size: int) -> str:
    gb = size / (1024 ** 3)
    if gb >= 1:
        return f"{gb:.1f} GB"
    return f"{size / (1024 ** 2):.0f} MB"


def get_quality(name: str) -> str:
    name = name.lower()
    for q in ("480p", "720p", "1080p"):
        if q in name:
            return q
    return "HD"


def get_codec(name: str) -> str:
    name = name.lower()
    for c in ("x264", "x265"):
        if c in name:
            return c
    return "x264"


def clean_movie_name(name: str) -> str:
    name = re.sub(r"\.(mkv|mp4|avi|mov|webm)$", "", name, flags=re.I)
    name = re.sub(r"(480p|720p|1080p|x264|x265)", "", name, flags=re.I)
    name = name.replace(".", " ")
    name = re.sub(r"\s+", " ", name)
    return name.strip().title()


def build_caption(movie: str, files: list) -> str:
    text = f"🎬 {movie}\n\n"
    for f in files:
        text += (
            f"📁 Hindi | {f['quality']} | {f['codec']}\n"
            f"     Click Here ({f['size']})\n\n"
        )
    text += FOOTER
    return text


# ===== MAIN HANDLER =====
@Client.on_message(filters.command("link") & filters.reply)
async def movie_auto_post(client, message):

    if POST_CHANNEL_ID == 0:
        await message.reply_text("❌ POST_CHANNEL_ID not set")
        return

    reply = message.reply_to_message
    file = reply.video or reply.document

    if not file or not file.file_name:
        await message.reply_text("❌ Please reply to a video or document file")
        return

    movie_name = clean_movie_name(file.file_name)

    entry = {
        "quality": get_quality(file.file_name),
        "codec": get_codec(file.file_name),
        "size": size_format(file.file_size),
        "link": file.file_id
    }

    data = movies.find_one({"movie": movie_name})

    # ===== UPDATE EXISTING POST =====
    if data:
        movies.update_one(
            {"movie": movie_name},
            {"$push": {"files": entry}}
        )

        data = movies.find_one({"movie": movie_name})

        await client.edit_message_text(
            chat_id=POST_CHANNEL_ID,
            message_id=data["post_id"],
            text=build_caption(movie_name, data["files"]),
            disable_web_page_preview=True
        )

        await message.reply_text("✅ Movie quality added & channel post updated")

    # ===== CREATE NEW POST =====
    else:
        post = await client.send_message(
            chat_id=POST_CHANNEL_ID,
            text=build_caption(movie_name, [entry]),
            disable_web_page_preview=True
        )

        movies.insert_one({
            "movie": movie_name,
            "files": [entry],
            "post_id": post.id
        })

        await message.reply_text("✅ Movie posted to channel")
