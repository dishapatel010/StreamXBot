import time
import uuid
import asyncio
from pyrogram import filters
from pyrogram.types import Message

from stream import bot
from stream.database.MongoDb import db_handler
from stream.helpers.filters import sudo_cmd
from stream.helpers.logger import LOGGER

LOG = LOGGER(__name__)


def _pick_audio_media(message: Message):
    media = message.audio
    if not media and message.document and (message.document.mime_type or "").startswith("audio/"):
        media = message.document
    return media


async def create_user_playlist(user_id: int, playlist_name: str) -> str:
    now = time.time()
    playlist_id = uuid.uuid4().hex
    from Api.services.genColor import ensure_user_playlist_cover, ensure_user_playlist_normal_cover
    
    try:
        cover = await ensure_user_playlist_cover(playlist_id=playlist_id, name=playlist_name, force=True)
    except Exception:
        cover = {}
        
    try:
        normal_cover = await ensure_user_playlist_normal_cover(playlist_id=playlist_id, name=playlist_name, force=True)
    except Exception:
        normal_cover = {}
        
    doc = {
        "_id": playlist_id,
        "user_id": int(user_id),
        "name": playlist_name,
        "cover_id": cover.get("cover_id"),
        "cover_url": cover.get("url"),
        "normal_thumbnail": normal_cover.get("url"),
        "created_at": now,
        "updated_at": now,
    }
    await db_handler.get_collection("user_playlists").collection.insert_one(doc)
    return playlist_id


async def run_chat_index_background(
    message: Message,
    status_message: Message,
    userbot,
    chat_id: int,
    playlist_id: str,
    playlist_name: str
):
    try:
        await status_message.edit(f"🚀 Started indexing history of '{playlist_name}' in the background...")
        
        from stream.plugins.userBot.service import _has_audio_media
        from stream.plugins.db.audioIndex import _upsert_minimal, _enrich_audio_doc
        
        # Concurrency limit: max 2 active audio file downloads/enrichments at once
        sem = asyncio.Semaphore(2)
        
        async def safe_enrich_task(msg_obj, media_obj):
            async with sem:
                try:
                    await _enrich_audio_doc(msg_obj, media_obj)
                except Exception as e:
                    LOG.error(f"Enrichment error for msg {msg_obj.id}: {e}")

        track_ids = []
        scanned = 0
        found = 0
        consecutive_already_indexed = 0
        
        last_update_time = time.time()
        
        async for msg in userbot.get_chat_history(chat_id):
            scanned += 1
            if _has_audio_media(msg):
                media = _pick_audio_media(msg)
                if media:
                    found += 1
                    try:
                        # 1. Upsert minimally to get track ID
                        track_id = await _upsert_minimal(msg, media)
                        track_ids.append(track_id)
                        
                        # Check if already fully enriched in the database
                        doc = await db_handler.audio_collection.collection.find_one({"_id": track_id})
                        is_enriched = doc and doc.get("lyrics") is not None
                        
                        if is_enriched:
                            consecutive_already_indexed += 1
                        else:
                            consecutive_already_indexed = 0
                            # 2. Enrich under the strict concurrency semaphore only if not yet enriched
                            asyncio.create_task(safe_enrich_task(msg, media))
                    except Exception as e:
                        LOG.error(f"Failed to index msg {msg.id} in {chat_id}: {e}")
            
            # If we find 30 consecutive already-indexed tracks, we stop scanning history!
            if consecutive_already_indexed >= 30:
                LOG.info(f"Reached already indexed tracks boundary in chat {chat_id}. Stopping scan early.")
                break
            
            # Micro-sleep to prevent userbot FloodWait on Telegram API
            await asyncio.sleep(0.01)
                        
            # Periodic status update throttled to once every 3.0 seconds
            now = time.time()
            if now - last_update_time >= 3.0:
                try:
                    await status_message.edit(
                        f"⏳ Indexing '{playlist_name}'...\n"
                        f"• Messages Scanned: {scanned}\n"
                        f"• Audio Files Found: {found}"
                    )
                    last_update_time = now
                except Exception:
                    pass

        if not track_ids:
            await status_message.edit(f"❌ Indexing complete. No audio files found in '{playlist_name}'.")
            return

        # 3. Add all tracks to user's playlist
        tracks_col = db_handler.get_collection("playlist_tracks").collection
        last = await tracks_col.find_one({"playlist_id": playlist_id}, {"position": 1}, sort=[("position", -1)])
        next_pos = int(last.get("position") or 0) + 1 if last else 1

        now = time.time()
        added_count = 0
        
        for tid in track_ids:
            res = await tracks_col.update_one(
                {"playlist_id": playlist_id, "track_id": tid},
                {
                    "$setOnInsert": {"position": next_pos, "added_at": now},
                    "$set": {"playlist_id": playlist_id, "track_id": tid}
                },
                upsert=True
            )
            if res.upserted_id is not None:
                added_count += 1
                next_pos += 1
                
        # 4. Trigger playlist cover update based on new tracks added
        try:
            from Api.services.genColor import ensure_user_playlist_cover, ensure_user_playlist_normal_cover, _collage_hash
            from Api.services.track_service import get_tracks_by_ids
            
            cursor = (
                tracks_col.find({"playlist_id": playlist_id}, {"_id": 0, "track_id": 1})
                .sort([("position", 1)])
                .limit(4)
            )
            first_4_ids = []
            async for r in cursor:
                tid = r.get("track_id")
                if tid:
                    first_4_ids.append(tid)
                    
            track_thumbs = []
            if first_4_ids:
                tracks_list = await get_tracks_by_ids(first_4_ids)
                from Api.routers.playlists import _track_thumbnail_url
                for tdoc in tracks_list:
                    if isinstance(tdoc, dict):
                        url = _track_thumbnail_url(tdoc)
                        if url:
                            track_thumbs.append(url)
                            
            current_hash = _collage_hash(track_thumbs) if track_thumbs else None
            
            cover = await ensure_user_playlist_cover(
                playlist_id=playlist_id, 
                name=playlist_name, 
                force=True, 
                collage_urls=track_thumbs
            )
            normal_cover = await ensure_user_playlist_normal_cover(
                playlist_id=playlist_id, 
                name=playlist_name, 
                force=True, 
                collage_urls=track_thumbs
            )
            
            await db_handler.get_collection("user_playlists").collection.update_one(
                {"_id": playlist_id},
                {"$set": {
                    "cover_id": cover.get("cover_id"), 
                    "cover_url": cover.get("url"), 
                    "normal_thumbnail": normal_cover.get("url"),
                    "collage_hash": current_hash,
                    "updated_at": time.time()
                }},
            )
        except Exception as e:
            LOG.error(f"Failed to update playlist cover: {e}")

        await status_message.edit(
            f"🎉 **Indexing & Playlist Creation Complete!**\n\n"
            f"• Playlist Name: `{playlist_name}`\n"
            f"• Scanned Messages: {scanned}\n"
            f"• Audio Files Found: {found}\n"
            f"• Added to Playlist: {added_count} new tracks!"
        )

    except Exception as e:
        LOG.exception("Error in run_chat_index_background")
        try:
            await status_message.edit(f"❌ Background indexing failed:\n`{str(e)}`")
        except Exception:
            pass


@bot.on_message(filters.command(["index", "index_chat"]) & sudo_cmd)
async def chat_indexer(_, message: Message):
    from stream.plugins.userBot.service import USERBOT_CLIENT
    if not USERBOT_CLIENT:
        await message.reply_text("❌ Userbot is not running or Config.SESSION_STRING is missing.")
        return

    user_id = message.from_user.id if message.from_user else None
    if not user_id:
        await message.reply_text("❌ Failed to resolve sender user ID.")
        return

    parts = message.text.split(maxsplit=1)
    target_chat = message.chat.id
    if len(parts) > 1:
        raw_target = parts[1].strip()
        try:
            target_chat = int(raw_target)
        except ValueError:
            target_chat = raw_target

    status = await message.reply_text("🔍 Resolving target chat via Userbot...")
    try:
        chat_info = await USERBOT_CLIENT.get_chat(target_chat)
        chat_name = chat_info.title or chat_info.first_name or f"Chat {target_chat}"
        chat_id = chat_info.id
    except Exception as e:
        await status.edit(f"❌ Failed to access chat `{target_chat}` via Userbot:\n`{e}`")
        return

    col_playlists = db_handler.get_collection("user_playlists").collection
    existing_playlist = await col_playlists.find_one({"user_id": int(user_id), "name": chat_name})
    if existing_playlist:
        playlist_id = existing_playlist["_id"]
        await status.edit(f"ℹ️ Playlist '{chat_name}' already exists. Indexing and appending tracks...")
    else:
        await status.edit(f"🎨 Creating playlist '{chat_name}'...")
        try:
            playlist_id = await create_user_playlist(user_id, chat_name)
        except Exception as e:
            await status.edit(f"❌ Failed to create playlist:\n`{e}`")
            return

    # Start the background indexing task
    asyncio.create_task(
        run_chat_index_background(
            message=message,
            status_message=status,
            userbot=USERBOT_CLIENT,
            chat_id=chat_id,
            playlist_id=playlist_id,
            playlist_name=chat_name
        )
    )
