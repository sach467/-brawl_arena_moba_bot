import asyncio
import os
import random
import sqlite3
from datetime import datetime, timedelta
from threading import Thread

from flask import Flask
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from db import (
    init_db, get_player, set_username, update_rating,
    init_rooms_table, create_room, get_room, delete_room,
    add_player_to_room, get_room_players, remove_player_from_room,
    add_bot_to_room, set_player_role,
set_chat_state, get_chat_state, clear_chat_state
)
from elo import update_elo, get_rank
from rooms import generate_room_id, room_keyboard, room_text, roles_keyboard, ROLE_NAMES, chat_exit_keyboard

TOKEN = os.getenv("TOKEN")

bot = Bot(token=TOKEN)
dp = Dispatcher()

queue = {}
queue_lock = asyncio.Lock()

RANGE_START = 50
RANGE_STEP = 50
WAIT_STEP = 5
MAX_RANGE = 500
search_queue = []
search_lock = asyncio.Lock()

def main_menu():
    kb = InlineKeyboardBuilder()
    kb.button(text="🎮 Играть 3x3", callback_data="search_3x3")
    kb.button(text="🏠 Создать комнату", callback_data="create_room")
    kb.button(text="📊 Профиль", callback_data="profile")
    kb.button(text="🏆 Топ игроков", callback_data="top")
    kb.adjust(1)
    return kb.as_markup()


@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user = await get_player(message.from_user.id)
    await set_username(message.from_user.id, message.from_user.first_name or "Игрок")

    await message.answer(
        f"Привет, {message.from_user.first_name}!\n"
        f"Твой ранг: {get_rank(user[2])} ({user[2]} очков)\n\n"
        "Жми «Играть», чтобы войти в очередь.",
        reply_markup=main_menu()
    )


@dp.callback_query(F.data == "profile")
async def cb_profile(cb: types.CallbackQuery):
    u = await get_player(cb.from_user.id)
    await cb.answer()
    await cb.message.answer(
        f"👤 {u[1]}\n"
        f"🏅 Ранг: {get_rank(u[2])} ({u[2]})\n"
        f"✅ Побед: {u[3]}\n"
        f"❌ Поражений: {u[4]}"
    )


@dp.callback_query(F.data == "top")
async def cb_top(cb: types.CallbackQuery):
    import aiosqlite
    async with aiosqlite.connect("game.db") as db:
        async with db.execute(
            "SELECT username, rating, wins FROM players ORDER BY rating DESC LIMIT 10"
        ) as cur:
            rows = await cur.fetchall()

    await cb.answer()
    if not rows:
        await cb.message.answer("Топ пока пуст.")
        return

    text = "🏆 Топ-10 игроков:\n\n"
    for i, (name, rating, wins) in enumerate(rows, 1):
        text += f"{i}. {name or 'Игрок'} — {rating} ({get_rank(rating)}), побед: {wins}\n"
    await cb.message.answer(text)


@dp.callback_query(F.data == "play")
async def cb_play(cb: types.CallbackQuery):
    user_id = cb.from_user.id
    user = await get_player(user_id)
    username = user[1] or "Игрок"
    rating = user[2]

    async with queue_lock:
        if user_id in queue:
            await cb.answer("Ты уже в очереди!", show_alert=True)
            return

        opponent_id = None
        for other_id, (_, other_rating, _) in queue.items():
            if abs(other_rating - rating) <= RANGE_START:
                opponent_id = other_id
                break

        if opponent_id:
            opp_name, opp_rating, opp_msg_id = queue.pop(opponent_id)
            await cb.answer()
            await start_match(
                p1=(user_id, username, rating),
                p2=(opponent_id, opp_name, opp_rating),
                p1_msg=cb.message.message_id,
                p2_msg=opp_msg_id,
            )
            return

        queue[user_id] = (username, rating, cb.message.message_id)
        await cb.answer("Ищем соперника...", show_alert=False)
        await cb.message.edit_text(
            f"🔍 Поиск соперника...\nТвой рейтинг: {rating} ({get_rank(rating)})\n"
            "Диапазон поиска будет расширяться каждые 5 секунд.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="❌ Отменить", callback_data="cancel")]
            ])
        )

    asyncio.create_task(expand_search(user_id))


async def expand_search(user_id: int):
    for _ in range(10):
        await asyncio.sleep(WAIT_STEP)
        async with queue_lock:
            if user_id not in queue:
                return

            username, rating, msg_id = queue[user_id]
            current_range = RANGE_START + RANGE_STEP * (_ + 1)
            if current_range > MAX_RANGE:
                current_range = MAX_RANGE

            for other_id, (opp_name, opp_rating, opp_msg_id) in list(queue.items()):
                if other_id == user_id:
                    continue
                if abs(opp_rating - rating) <= current_range:
                    queue.pop(other_id)
                    queue.pop(user_id)
                    await start_match(
                        p1=(user_id, username, rating),
                        p2=(other_id, opp_name, opp_rating),
                        p1_msg=msg_id,
                        p2_msg=opp_msg_id,
                    )
                    return

            try:
                await bot.edit_message_text(
                    chat_id=user_id,
                    message_id=msg_id,
                    text=(
                        f"🔍 Поиск соперника...\n"
                        f"Твой рейтинг: {rating} ({get_rank(rating)})\n"
                        f"Диапазон: ±{current_range}"
                    ),
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="❌ Отменить", callback_data="cancel")]
                    ])
                )
            except Exception:
                pass


@dp.callback_query(F.data == "cancel")
async def cb_cancel(cb: types.CallbackQuery):
    async with queue_lock:
        queue.pop(cb.from_user.id, None)
    await cb.answer("Поиск отменён")
    await cb.message.edit_text("Ты вышел из очереди.", reply_markup=main_menu())


async def start_match(p1, p2, p1_msg, p2_msg):
    p1_id, p1_name, p1_rating = p1
    p2_id, p2_name, p2_rating = p2

    winner, loser = random.sample([p1, p2], 2)

    w_id, w_name, w_rating = winner
    l_id, l_name, l_rating = loser

    new_w_rating, new_l_rating = update_elo(w_rating, l_rating)

    await update_rating(w_id, new_w_rating, win=True)
    await update_rating(l_id, new_l_rating, win=False)

    try:
        await bot.edit_message_text(
            chat_id=w_id,
            message_id=p1_msg if w_id == p1_id else p2_msg,
            text=(
                f"🏆 Победа!\n\n"
                f"Соперник: {l_name}\n"
                f"Рейтинг: {w_rating} → {new_w_rating} (+{new_w_rating - w_rating})\n"
                f"Ранг: {get_rank(new_w_rating)}"
            ),
            reply_markup=main_menu()
        )
    except Exception:
        pass

    try:
        await bot.edit_message_text(
            chat_id=l_id,
            message_id=p1_msg if l_id == p1_id else p2_msg,
            text=(
                f"💀 Поражение\n\n"
                f"Соперник: {w_name}\n"
                f"Рейтинг: {l_rating} → {new_l_rating} ({new_l_rating - l_rating})\n"
                f"Ранг: {get_rank(new_l_rating)}"
            ),
            reply_markup=main_menu()
        )
    except Exception:
        pass


@dp.callback_query(F.data == "create_room")
async def cb_create_room(cb: types.CallbackQuery):
    room_id = generate_room_id()
    await create_room(room_id, cb.from_user.id)
    await add_player_to_room(room_id, cb.from_user.id, cb.from_user.first_name or "Игрок")

    await cb.answer("Комната создана!")
    await cb.message.edit_text(
        await room_text(room_id),
        reply_markup=room_keyboard(room_id, is_captain=True)
    )


@dp.message(Command("join"))
async def cmd_join(message: types.Message):
    args = message.text.split()
    if len(args) < 2:
        await message.answer("Использование: /join КОД (например, /join 1234)")
        return

    room_id = args[1]
    room = await get_room(room_id)
    if not room:
        await message.answer("Комната не найдена.")
        return

    players = await get_room_players(room_id)
    if len(players) >= 6:
        await message.answer("Комната заполнена.")
        return

    await add_player_to_room(room_id, message.from_user.id, message.from_user.first_name or "Игрок")
    await message.answer(
        await room_text(room_id),
        reply_markup=room_keyboard(room_id, is_captain=(room[1] == message.from_user.id))
    )


@dp.callback_query(F.data.startswith("leave_"))
async def cb_leave(cb: types.CallbackQuery):
    room_id = cb.data.split("_")[1]
    await remove_player_from_room(room_id, cb.from_user.id)

    players = await get_room_players(room_id)
    if not players:
        await delete_room(room_id)
        await cb.message.edit_text("Комната закрыта (все вышли).")
        return

    await cb.message.edit_text(
        await room_text(room_id),
        reply_markup=room_keyboard(room_id)
    )


@dp.callback_query(F.data.startswith("ready_"))
async def cb_ready(cb: types.CallbackQuery):
    room_id = cb.data.split("_")[1]
    import aiosqlite
    async with aiosqlite.connect("game.db") as db:
        await db.execute(
            "UPDATE room_players SET is_ready = 1 - is_ready WHERE room_id=? AND user_id=?",
            (room_id, cb.from_user.id)
        )
        await db.commit()

    await cb.answer("Статус изменён")
    room = await get_room(room_id)
    await cb.message.edit_text(
        await room_text(room_id),
        reply_markup=room_keyboard(room_id, is_captain=(room[1] == cb.from_user.id))
    )


@dp.callback_query(F.data.startswith("start_"))
async def cb_start(cb: types.CallbackQuery):
    room_id = cb.data.split("_")[1]
    room = await get_room(room_id)

    if room[1] != cb.from_user.id:
        await cb.answer("Только капитан может начать игру.", show_alert=True)
        return

    players = await get_room_players(room_id)
    if len(players) < 6:
        await cb.answer(f"Нужно 6 игроков, сейчас {len(players)}.", show_alert=True)
        return

    all_ready = all(p[3] for p in players)
    if not all_ready:
        not_ready = [p[1] for p in players if not p[3]]
        await cb.answer(f"Не готовы: {', '.join(not_ready)}", show_alert=True)
        return

    await cb.answer("Игра начинается!")
    await cb.message.edit_text("🎮 Игра началась! (бой появится в следующем шаге)")


@dp.callback_query(F.data.startswith("addbot_"))
async def cb_addbot(cb: types.CallbackQuery):
    room_id = cb.data.split("_")[1]
    room = await get_room(room_id)

    if room[1] != cb.from_user.id:
        await cb.answer("Только капитан может добавлять ботов.", show_alert=True)
        return

    added = await add_bot_to_room(room_id)
    if not added:
        await cb.answer("Комната уже полная.", show_alert=True)
        return

    await cb.answer("Бот добавлен")
    await cb.message.edit_text(
        await room_text(room_id),
        reply_markup=room_keyboard(room_id, is_captain=True)
    )

@dp.callback_query(F.data == "search_3x3")
async def cb_search_3x3(cb: types.CallbackQuery):
    user_id = cb.from_user.id
    name = cb.from_user.first_name or "Игрок"

    async with search_lock:
        if any(u[0] == user_id for u in search_queue):
            await cb.answer("Ты уже в поиске!", show_alert=True)
            return

        search_queue.append((user_id, name))
        count = len(search_queue)

        if count < 6:
            await cb.answer("Ищем игроков...", show_alert=False)
            await cb.message.edit_text(
                f"🔍 Поиск игроков 3x3\n\n"
                f"Найдено: {count}/6\n\n"
                f"Сейчас в очереди:\n" +
                "\n".join(f"• {u[1]}" for u in search_queue),
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_search")]
                ])
            )
            return

        # Набралось 6 — создаём комнату
        players = search_queue[:6]
        search_queue.clear()

    room_id = generate_room_id()
    captain_id = players[0][0]
    await create_room(room_id, captain_id)

    for uid, uname in players:
        await add_player_to_room(room_id, uid, uname)

    for uid, uname in players:
        try:
            is_captain = (uid == captain_id)
            await bot.send_message(
                uid,
                f"🎮 Команда найдена!\n\n" + await room_text(room_id),
                reply_markup=room_keyboard(room_id, is_captain=is_captain)
            )
        except Exception:
            pass

    await cb.answer("Команда найдена!")


@dp.callback_query(F.data == "cancel_search")
async def cb_cancel_search(cb: types.CallbackQuery):
    async with search_lock:
        search_queue[:] = [u for u in search_queue if u[0] != cb.from_user.id]
    await cb.answer("Поиск отменён")
    await cb.message.edit_text("Ты вышел из очереди.", reply_markup=main_menu())
@dp.callback_query(F.data.startswith("roles_"))
async def cb_roles(cb: types.CallbackQuery):
    room_id = cb.data.split("_")[1]
    await cb.answer()
    await cb.message.edit_text(
        f"🎭 Выбери свою роль для комнаты #{room_id}:\n\n"
        f"⚔️ Керри — 2 места\n"
        f"💚 Саппорт — 1 место",
        reply_markup=roles_keyboard(room_id)
    )


@dp.callback_query(F.data.startswith("setrole_"))
async def cb_setrole(cb: types.CallbackQuery):
    parts = cb.data.split("_")
    room_id = parts[1]
    role = parts[2]

    ok = await set_player_role(room_id, cb.from_user.id, role)
    if not ok:
        await cb.answer(f"{ROLE_NAMES[role]} — все места заняты!", show_alert=True)
        return

    await cb.answer(f"Ты выбрал {ROLE_NAMES[role]}")
    room = await get_room(room_id)
    await cb.message.edit_text(
        await room_text(room_id),
        reply_markup=room_keyboard(room_id, is_captain=(room[1] == cb.from_user.id))
    )


@dp.callback_query(F.data.startswith("back_"))
async def cb_back(cb: types.CallbackQuery):
    room_id = cb.data.split("_")[1]
    room = await get_room(room_id)
    await cb.answer()
    await cb.message.edit_text(
        await room_text(room_id),
        reply_markup=room_keyboard(room_id, is_captain=(room[1] == cb.from_user.id))
    )    
@dp.callback_query(F.data.startswith("back_"))
async def cb_back(cb: types.CallbackQuery):
    room_id = cb.data.split("_")[1]
    await clear_chat_state(cb.from_user.id)
    room = await get_room(room_id)
    await cb.answer()
    await cb.message.edit_text(
        await room_text(room_id),
        reply_markup=room_keyboard(room_id, is_captain=(room[1] == cb.from_user.id))
    )


@dp.callback_query(F.data.startswith("chat_"))
async def cb_chat(cb: types.CallbackQuery):
    room_id = cb.data.split("_")[1]
    await set_chat_state(cb.from_user.id, room_id)
    await cb.answer("Ты в чате комнаты")
    await cb.message.edit_text(
        f"💬 Чат комнаты #{room_id}\n\n"
        f"Пиши сюда — сообщение увидят все игроки.\n"
        f"Чтобы выйти — нажми кнопку ниже.",
        reply_markup=chat_exit_keyboard(room_id)
    )


@dp.message(F.text & ~F.text.startswith("/"))
async def chat_forward(message: types.Message):
    room_id = await get_chat_state(message.from_user.id)
    if not room_id:
        return

    players = await get_room_players(room_id)
    text = f"💬 {message.from_user.first_name}: {message.text}"

    for uid, uname, role, ready in players:
        if uid == message.from_user.id:
            continue
        if uid < 0:
            continue
        try:
            await bot.send_message(uid, text)
        except Exception:
            pass

    await message.answer("✅ Отправлено")    
# ---------- Flask для Render ----------
app = Flask('')


@app.route('/')
def home():
    return "Bot is running"


def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)


async def main():
    await init_db()
    await init_rooms_table()
    await dp.start_polling(bot)


if __name__ == "__main__":
    Thread(target=run_flask, daemon=True).start()
    asyncio.run(main())
