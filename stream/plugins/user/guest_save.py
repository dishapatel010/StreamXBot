from typing import Optional, Any, Dict
from pyrogram import filters
from pyrogram.types import Message, InlineQueryResultArticle, InputTextMessageContent

from stream import bot
from stream.core.config_manager import Config
from stream.database.MongoDb import db_handler
from stream.helpers.logger import LOGGER

LOG = LOGGER(__name__)

SETTINGS_DOC_ID = "guest_save"


def _is_admin(user_id: int) -> bool:
    try:
        if int(user_id) == int(getattr(Config, "OWNER_ID", 0) or 0):
            return True
    except Exception:
        pass
    try:
        s = getattr(Config, "SUDO_USERS", []) or []
        if isinstance(s, (list, tuple, set)):
            return int(user_id) in [int(x) for x in s]
    except Exception:
        pass
    return False


async def _get_settings() -> Dict[str, Any]:
    col = db_handler.get_collection("botsettings").collection
    doc = await col.find_one({"_id": SETTINGS_DOC_ID})
    if not isinstance(doc, dict):
        return {}
    return doc


async def _update_settings(updates: Dict[str, Any]) -> None:
    col = db_handler.get_collection("botsettings").collection
    await col.update_one({"_id": SETTINGS_DOC_ID}, {"$set": updates}, upsert=True)


async def _reply(message: Message, text: str):
    if getattr(message, "guest_query_id", None):
        try:
            await bot.answer_guest_query(
                message.guest_query_id,
                result=InlineQueryResultArticle(
                    title="Guest Save",
                    input_message_content=InputTextMessageContent(text)
                )
            )
            return
        except Exception as e:
            LOG.info("Failed to answer_guest_query: %s", e)
    # Fallback to standard reply
    await message.reply_text(text)


@bot.on_message(filters.command(["guestsave_setchannel", "gs_set"]))
async def cmd_set_channel(_, message: Message):
    if not message.from_user or not _is_admin(message.from_user.id):
        await message.reply_text("Only owner/sudo can use this command.")
        return

    parts = message.text.split()
    if len(parts) < 2:
        await message.reply_text("Usage: /guestsave_setchannel <channel_id>")
        return
    try:
        cid = int(parts[1].strip())
    except Exception:
        await message.reply_text("Invalid channel id")
        return

    await _update_settings({"channel_id": cid})
    await message.reply_text(f"Guest-save channel set to {cid}")


@bot.on_message(filters.command(["guestsave_enable", "gs_enable"]))
async def cmd_enable(_, message: Message):
    if not message.from_user or not _is_admin(message.from_user.id):
        await message.reply_text("Only owner/sudo can use this command.")
        return
    await _update_settings({"enabled": True})
    await message.reply_text("Guest-save enabled")


@bot.on_message(filters.command(["guestsave_disable", "gs_disable"]))
async def cmd_disable(_, message: Message):
    if not message.from_user or not _is_admin(message.from_user.id):
        await message.reply_text("Only owner/sudo can use this command.")
        return
    await _update_settings({"enabled": False})
    await message.reply_text("Guest-save disabled")


@bot.on_message(filters.command(["guestsave_status", "gs_status"]))
async def cmd_status(_, message: Message):
    if not message.from_user or not _is_admin(message.from_user.id):
        await message.reply_text("Only owner/sudo can use this command.")
        return
    s = await _get_settings()
    await message.reply_text(f"Guest-save settings:\n{str(s)}")


async def _forward_to_channel(orig: Message, channel_id: int) -> tuple[Optional[Message], Optional[str]]:
    LOG.info("Received guest message: %s", orig)
    errs = []
    # 1. Try to forward first (preserves original author/message metadata)
    try:
        forwarded = await bot.forward_messages(chat_id=channel_id, from_chat_id=orig.reply_to_message.chat.id, message_ids=orig.reply_to_message.id)
        if isinstance(forwarded, list):
            return (forwarded[0] if forwarded else None), None
        return forwarded, None
    except Exception as e:
        errs.append(f"Forward failed: {e}")
        LOG.info("Step 1 (Forward) failed: %s", e)

    # 2. Try copy_message (copies the message without forward header)
    try:
        copied = await bot.copy_message(chat_id=channel_id, from_chat_id=orig.reply_to_message.chat.id, message_id=orig.reply_to_message.id)
        return copied, None
    except Exception as e:
        errs.append(f"Copy failed: {e}")
        LOG.info("Step 2 (Copy) failed: %s", e)

    # 3. Fallback: Send by file_id if we have the media file_id (crucial for Guest Mode!)
    try:
        LOG.info("Attempting Step 3 (Send by file_id) to channel %s...", channel_id)
        if orig.reply_to_message.audio:
            res = await bot.send_audio(
                chat_id=channel_id,
                audio=orig.reply_to_message.audio.file_id,
            )
            LOG.info("Step 3 (Send Audio by file_id) succeeded!")
            return res, None
        elif orig.reply_to_message.voice:
            res = await bot.send_voice(
                chat_id=channel_id,
                voice=orig.reply_to_message.voice.file_id
            )
            LOG.info("Step 3 (Send Voice by file_id) succeeded!")
            return res, None
        elif orig.reply_to_message.document:
            res = await bot.send_document(
                chat_id=channel_id,
                document=orig.reply_to_message.document.file_id
            )
            LOG.info("Step 3 (Send Document by file_id) succeeded!")
            return res, None
    except Exception as e:
        errs.append(f"Send by file_id failed: {e}")
        LOG.info("Step 3 (Send by file_id) failed: %s", e)
    
    return None, "; ".join(errs)



@bot.on_guest_message()
async def handle_guest_save(_, message: Message):
    try:
        orig = message.reply_to_message
        if not orig:
            await _reply(message, "Reply to an audio file to save it.")
            return

        # respect protected content
        if getattr(orig, "has_protected_content", False):
            await _reply(message, "This file cannot be forwarded due to protected content.")
            return

        # accept audio/voice/document with audio mime
        is_audio = bool(orig.reply_to_message.audio or orig.reply_to_message.voice)
        is_document_audio = False
        if orig.reply_to_message.document and getattr(orig.reply_to_message.document, "mime_type", "") and orig.reply_to_message.document.mime_type.startswith("audio/"):
            is_document_audio = True

        if not (is_audio or is_document_audio):
            await _reply(message, "I only save audio files. Reply to an audio file.")
            return

        s = await _get_settings()
        enabled = bool(s.get("enabled", True))
        channel_id = int(s.get("channel_id") or getattr(Config, "DUMP_CHANNEL_ID", 0) or getattr(Config, "CHANNEL_ID", 0))

        if not enabled:
            await _reply(message, "Guest-save is disabled.")
            return
        if not channel_id:
            await _reply(message, "No channel configured. Owner can set with /guestsave_setchannel <id>")
            return

        forwarded, err_msg = await _forward_to_channel(orig, channel_id)
        if not forwarded:
            error_text = "Failed to save file to archive (check bot permissions)."
            if err_msg:
                error_text += f"\nDetails: {err_msg}"
            await _reply(message, error_text)
            return

        # store metadata in audio_collection if available
        try:
            audio_col = db_handler.audio_collection.collection
            doc = {
                "source_chat_id": int(orig.reply_to_message.chat.id),
                "source_message_id": int(orig.reply_to_message.id),
                "saved_chat_id": int(forwarded.chat.id),
                "saved_message_id": int(forwarded.id),
                "created_at": __import__('time').time(),
            }
            await audio_col.insert_one(doc)
        except Exception:
            LOG.info("Failed to insert audio metadata")

        await _reply(message, "Saved to archive. Thanks!")

    except Exception:
        LOG.info("guest_save handler failed")
        try:
            await _reply(message, "Internal error while saving.")
        except Exception:
            pass
