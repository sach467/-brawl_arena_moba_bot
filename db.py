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
            )
        await db.commit()
