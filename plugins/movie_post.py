from pyrogram import Client, filters
from pymongo import MongoClient
from config import POST_CHANNEL_ID
import re

mongo = MongoClient()
db = mongo["vlz_filestore"]
movies = db.movies

TAG = "Powered By : https://t.me/MzMoviiez"


def size_format(size):
    gb = size / (1024 ** 3)
    if gb >= 1:
        return f"{gb:.1f} GB"
    return f"{size / (1024 ** 2):.0f} MB"


def get_quality(name):
    for q in ["480p", "720p", "1080p"]:
        if q.lower() in name.lower():
            return q
    return "HD"


def get_codec(name):
    for c in ["x264", "x265"]:
        if c.lower() in name.lower():
            return c
    return "x264"


def clean(name):
    name = re.sub(r"\.(mkv|mp4|avi)", "", name, flags=re.I)
    name = re.sub(r"(480p|720p|1080p|x264|x265)", "", name, flags=re.I)
    name = name.replace(".", " ")
    return name.strip().title()


def build(movie, files):
    text = f"🎬 {movie}\n\n"
    for f in files:
        text += (
            f"📁 Hindi | {f['quality']} | {f['codec']}\n"
            f"     Click Here ({f['size']})\n\n"
        )
    return text + TAG


@Client.on_message(filters.command("link") & filters.reply)
async def auto_post(client, message):

    file = message.reply_to_message.video or message.reply_to_message.document

    movie = clean(file.file_name)
    entry = {
        "quality": get_quality(file.file_name),
        "codec": get_codec(file.file_name),
        "size": size_format(file.file_size),
        "link": file.file_id
    }

    data = movies.find_one({"movie": movie})

    if data:
        movies.update_one(
            {"movie": movie},
            {"$push": {"files": entry}}
        )
        data = movies.find_one({"movie": movie})

        await client.edit_message_text(
            POST_CHANNEL_ID,
            data["post_id"],
            build(movie, data["files"]),
            disable_web_page_preview=True
        )
    else:
        msg = await client.send_message(
            POST_CHANNEL_ID,
            build(movie, [entry]),
            disable_web_page_preview=True
        )
        movies.insert_one({
            "movie": movie,
            "files": [entry],
            "post_id": msg.id
        })

    await message.reply_text("✅ Movie channel post updated")
