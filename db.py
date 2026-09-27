import aiosqlite

DB_PATH = "game.db"


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS players (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                rating INTEGER DEFAULT 0,
                wins INTEGER DEFAULT 0,
                losses INTEGER DEFAULT 0
            )
        """)
        await db.commit()


async def get_player(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT user_id, username, rating, wins, losses FROM players WHERE user_id=?",
            (user_id,)
        ) as cur:
            row = await cur.fetchone()
            if row:
                return row

        await db.execute(
            "INSERT INTO players (user_id) VALUES (?)", (user_id,)
        )
        await db.commit()
        return (user_id, None, 0, 0, 0)


async def set_username(user_id: int, username: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE players SET username=? WHERE user_id=?", (username, user_id)
        )
        await db.commit()


async def update_rating(user_id: int, new_rating: int, win: bool):
    async with aiosqlite.connect(DB_PATH) as db:
        if win:
            await db.execute(
                "UPDATE players SET rating=?, wins=wins+1 WHERE user_id=?",
                (new_rating, user_id)
            )
        else:
            await db.execute(
                "UPDATE players SET rating=?, losses=losses+1 WHERE user_id=?",
                (new_rating, user_id)
            )await db.commit()
await db.execute("""
    CREATE TABLE IF NOT EXISTS room_chat_state (
        user_id INTEGER PRIMARY KEY,
        room_id TEXT
    )
""")            
async def init_rooms_table():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS rooms (
                room_id TEXT PRIMARY KEY,
                captain_id INTEGER,
                created_at TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS room_players (
                room_id TEXT,
                user_id INTEGER,
                username TEXT,
                role TEXT,
                is_ready INTEGER DEFAULT 0,
                PRIMARY KEY (room_id, user_id)
            )
        """)
        await db.commit()


async def create_room(room_id: str, captain_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO rooms (room_id, captain_id, created_at) VALUES (?, ?, datetime('now'))",
            (room_id, captain_id)
        )
        await db.commit()


async def get_room(room_id: str):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT room_id, captain_id FROM rooms WHERE room_id=?", (room_id,)
        ) as cur:
            return await cur.fetchone()


async def delete_room(room_id: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM rooms WHERE room_id=?", (room_id,))
        await db.execute("DELETE FROM room_players WHERE room_id=?", (room_id,))
        await db.commit()


async def add_player_to_room(room_id: str, user_id: int, username: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO room_players (room_id, user_id, username) VALUES (?, ?, ?)",
            (room_id, user_id, username)
        )
        await db.commit()


async def get_room_players(room_id: str):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT user_id, username, role, is_ready FROM room_players WHERE room_id=?",
            (room_id,)
        ) as cur:
            return await cur.fetchall()


async def remove_player_from_room(room_id: str, user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM room_players WHERE room_id=? AND user_id=?",
            (room_id, user_id)
        )
        await db.commit()
async def add_bot_to_room(room_id: str):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT COUNT(*) FROM room_players WHERE room_id=?", (room_id,)
        ) as cur:
            count = (await cur.fetchone())[0]

        if count >= 6:
            return False

        bot_id = -1000000 - count
        bot_name = f"🤖 Бот {count}"
        await db.execute(
            "INSERT INTO room_players (room_id, user_id, username, is_ready) VALUES (?, ?, ?, 1)",
            (room_id, bot_id, bot_name)
        )
        await db.commit()
        return True
async def set_player_role(room_id: str, user_id: int, role: str):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT COUNT(*) FROM room_players WHERE room_id=? AND role=?",
            (room_id, role)
        ) as cur:
            count = (await cur.fetchone())[0]

        max_slots = {"carry": 2, "support": 1}
        limit = max_slots.get(role, 1)

        async with db.execute(
            "SELECT role FROM room_players WHERE room_id=? AND user_id=?",
            (room_id, user_id)
        ) as cur:
            current = await cur.fetchone()

        if current and current[0] == role:
            await db.execute(
                "UPDATE room_players SET role=NULL WHERE room_id=? AND user_id=?",
                (room_id, user_id)
            )
            await db.commit()
            return True

        if count >= limit:
            return False

        await db.execute(
            "UPDATE room_players SET role=? WHERE room_id=? AND user_id=?",
            (role, room_id, user_id)
        )
        await db.commit()
        return True        
