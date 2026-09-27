import random
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from db import (
    create_room, get_room, delete_room,
    add_player_to_room, get_room_players, remove_player_from_room
)


def generate_room_id() -> str:
    return str(random.randint(1000, 9999))

def room_keyboard(room_id: str, is_captain: bool = False):
    buttons = [
        [InlineKeyboardButton(text="✅ Готов", callback_data=f"ready_{room_id}")],
        [InlineKeyboardButton(text="🚪 Выйти", callback_data=f"leave_{room_id}")],
    ]
    if is_captain:
        buttons.append([InlineKeyboardButton(text="🎮 Начать игру", callback_data=f"start_{room_id}")])
        buttons.append([InlineKeyboardButton(text="🤖 Добавить бота", callback_data=f"addbot_{room_id}")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


async def room_text(room_id: str) -> str:
    room = await get_room(room_id)
    if not room:
        return "Комната не найдена."

    players = await get_room_players(room_id)
    captain_id = room[1]

    text = f"🏠 Комната #{room_id}\n"
    text += f"👥 Игроков: {len(players)}/6\n\n"

    for uid, uname, role, ready in players:
        mark = "👑" if uid == captain_id else "▫️"
        ready_mark = "✅" if ready else "⏳"
        text += f"{mark} {uname} — {role or 'роль не выбрана'} {ready_mark}\n"

    if len(players) < 6:
        text += f"\nОжидаем ещё {6 - len(players)} игроков."
    else:
        text += "\nВсе на месте! Капитан может начинать."

    return text
def roles_keyboard(room_id: str):
    buttons = [
        [InlineKeyboardButton(text="⚔️ Керри", callback_data=f"setrole_{room_id}_carry")],
        [InlineKeyboardButton(text="💚 Саппорт", callback_data=f"setrole_{room_id}_support")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data=f"back_{room_id}")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


ROLE_NAMES = {
    "carry": "⚔️ Керри",
    "support": "💚 Саппорт",
}
