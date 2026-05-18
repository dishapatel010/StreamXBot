from pyrogram import filters
from pyrogram.types import Message, CallbackQuery
from stream.core.config_manager import Config

def is_owner(user_id: int) -> bool:
    owners = getattr(Config, "OWNER_ID", None) or []
    if isinstance(owners, (list, tuple, set)):
        return user_id in owners
    return user_id == owners

def is_sudo(user_id: int) -> bool:
    sudos = getattr(Config, "SUDO_USERS", None) or []
    if isinstance(sudos, (list, tuple, set)):
        return user_id in sudos
    return user_id == sudos

class SudoFilter(filters.Filter):
    def __init__(self):
        super().__init__()

    def __call__(self, client, message: Message) -> bool:
        if not message.from_user:
            return False
        uid = message.from_user.id
        return is_sudo(uid) or is_owner(uid)

sudo = SudoFilter()

def _extract_update(*args):
    if not args:
        return None
    if len(args) >= 3:
        return args[2]
    if len(args) == 2:
        return args[1]
    return args[0]


def dev_users(*args) -> bool:
    update = _extract_update(*args)
    user = None
    if isinstance(update, (Message, CallbackQuery)):
        user = update.from_user

    return bool(user and is_owner(user.id))

def sudo_users(*args) -> bool:
    update = _extract_update(*args)
    user = None
    if isinstance(update, (Message, CallbackQuery)):
        user = update.from_user
    return bool(user and (is_sudo(user.id) or is_owner(user.id)))


dev_cmd = filters.create(dev_users)
sudo_cmd = filters.create(sudo_users)
