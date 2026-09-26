def expected_score(rating_a: int, rating_b: int) -> float:
    return 1 / (1 + 10 ** ((rating_b - rating_a) / 400))


def update_elo(winner: int, loser: int, k: int = 32) -> tuple[int, int]:
    exp_w = expected_score(winner, loser)
    exp_l = expected_score(loser, winner)

    new_winner = round(winner + k * (1 - exp_w))
    new_loser = round(loser + k * (0 - exp_l))
    return new_winner, new_loser


def get_rank(score: int) -> str:
    if score < 100:
        return "🥉 Бронза"
    elif score < 300:
        return "🥈 Серебро"
    elif score < 600:
        return "🥇 Золото"
    elif score < 1000:
        return "💎 Мифик"
    elif score < 1500:
        return "🔥 Легенда"
    else:
        return "👑 Про"
