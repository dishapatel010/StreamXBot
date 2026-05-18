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



@bot.on_guest_message()
async def handle_guest_save(_, message: Message):
    try:
        # THIS is the actual replied media message
        orig = message.reply_to_message

        if not orig:
            await _reply(message, "Reply to an audio file to save it.")
            return

        # protected content check
        if getattr(orig, "has_protected_content", False):
            await _reply(message, "This file cannot be saved due to protected content.")
            return

        # Correct media checks
        is_audio = bool(orig.audio or orig.voice)

        is_document_audio = (
            bool(orig.document)
            and bool(getattr(orig.document, "mime_type", ""))
            and orig.document.mime_type.startswith("audio/")
        )

        if not (is_audio or is_document_audio):
            await _reply(message, "I only save audio files.")
            return

        s = await _get_settings()

        enabled = bool(s.get("enabled", True))

        channel_id = int(
            s.get("channel_id")
            or getattr(Config, "DUMP_CHANNEL_ID", 0)
            or getattr(Config, "CHANNEL_ID", 0)
        )

        if not enabled:
            await _reply(message, "Guest-save is disabled.")
            return

        if not channel_id:
            await _reply(
                message,
                "No channel configured. Use /guestsave_setchannel <id>"
            )
            return

        # DIRECT SEND USING FILE_ID
        try:

            if orig.audio:
                sent = await bot.send_audio(
                    chat_id=channel_id,
                    audio=orig.audio.file_id,
                    caption=orig.caption or ""
                )

            elif orig.voice:
                sent = await bot.send_voice(
                    chat_id=channel_id,
                    voice=orig.voice.file_id,
                    caption=orig.caption or ""
                )

            elif orig.document:
                sent = await bot.send_document(
                    chat_id=channel_id,
                    document=orig.document.file_id,
                    caption=orig.caption or ""
                )

            else:
                await _reply(message, "Unsupported media type.")
                return

        except Exception as e:
            LOG.error("Failed to send media: %s", e)

            await _reply(
                message,
                f"Failed to save file.\n\nError:\n{str(e)}"
            )
            return

        # Trigger same indexing as when a new audio is added in channel_id
        try:
            from stream.plugins.db.audioIndex import channel_audio_filter
            await channel_audio_filter(bot, sent)
        except Exception as e:
            LOG.error("Failed to index guest-saved file: %s", e)

        await _reply(message, "Saved to archive successfully!")

    except Exception as e:
        LOG.exception("guest_save handler failed")

        try:
            await _reply(
                message,
                f"Internal error:\n{str(e)}"
            )
        except Exception:
            pass