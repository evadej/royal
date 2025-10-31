from __future__ import annotations

from flask import session, request, abort, redirect, url_for
from functools import wraps
from datetime import datetime
import secrets

from config import (
    ACHIEVEMENTS,
    SUITS,
    RANKS,
    DICE_SIDES,
    WHEEL_PRIZES,
    TRANSLATIONS,
)

_rand = secrets.SystemRandom()


def pick_wheel_prize() -> dict:
    total = sum(p["weight"] for p in WHEEL_PRIZES)
    r = _rand.randint(1, total)
    for p in WHEEL_PRIZES:
        r -= p["weight"]
        if r <= 0:
            return p
    return WHEEL_PRIZES[0]


def ensure_csrf_token() -> str:
    token = session.get("_csrf")
    if not token:
        token = secrets.token_urlsafe(16)
        session["_csrf"] = token
    return token


def csrf_protect():
    if request.method in ("POST", "PUT", "DELETE"):
        token = request.headers.get("X-CSRFToken") or request.form.get("csrf_token")
        if not token or token != session.get("_csrf"):
            abort(400, description="Неверный CSRF токен")


def inject_globals():
    lang = 'ru'
    return {
        "csrf_token": ensure_csrf_token(),
        "ACHIEVEMENTS": ACHIEVEMENTS,
        "t": TRANSLATIONS['ru'],
        "lang": lang
    }


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


def create_deck():
    deck = [{'suit': s, 'rank': r} for s in SUITS for r in RANKS]
    _rand.shuffle(deck)
    return deck


def card_value(card):
    r = card['rank']
    if r in ('J', 'Q', 'K'):
        return 10
    if r == 'A':
        return 11
    return int(r)


def hand_value(hand):
    total = sum(card_value(c) for c in hand)
    aces = sum(1 for c in hand if c['rank'] == 'A')
    while total > 21 and aces:
        total -= 10
        aces -= 1
    return total


def level_threshold(level: int) -> int:
    return level * level * 1000


def add_xp_and_level_up(user: dict, amount: int) -> None:
    user['xp'] = int(user.get('xp', 0)) + int(max(0, amount))
    while user['xp'] >= level_threshold(user.get('level', 1)):
        user['level'] = int(user.get('level', 1)) + 1


def _count_entries(history: list[dict]) -> int:
    return sum(item.get('times', 1) for item in history)


def count_total_games(user: dict) -> int:
    return (
        _count_entries(user.get('history', [])) +
        _count_entries(user.get('slots_history', [])) +
        _count_entries(user.get('blackjack_history', [])) +
        _count_entries(user.get('dice_history', [])) +
        _count_entries(user.get('wheel_history', [])) +
        _count_entries(user.get('coinflip_history', [])) +
        _count_entries(user.get('rps_history', [])) +
        _count_entries(user.get('number_history', []))
    )


def roll_dice():
    return _rand.randint(1, DICE_SIDES)


def check_achievements(user: dict) -> list[str]:
    new_ids = []
    user.setdefault('achievements', [])

    if user.get('level', 1) >= 10 and 'veteran' not in user['achievements']:
        user['achievements'].append('veteran')
        user['balance'] = round(float(user.get('balance', 0)) + ACHIEVEMENTS['veteran']['reward'], 2)
        new_ids.append('veteran')

    if float(user.get('total_winnings', 0)) >= 10_000 and 'rich' not in user['achievements']:
        user['achievements'].append('rich')
        user['balance'] = round(float(user.get('balance', 0)) + ACHIEVEMENTS['rich']['reward'], 2)
        new_ids.append('rich')

    if count_total_games(user) >= 100 and 'gambler' not in user['achievements']:
        user['achievements'].append('gambler')
        user['balance'] = round(float(user.get('balance', 0)) + ACHIEVEMENTS['gambler']['reward'], 2)
        new_ids.append('gambler')

    if 'lucky' not in user['achievements']:
        for game in user.get('history', []):
            if game.get('chance', 100) <= 1 and game.get('win'):
                user['achievements'].append('lucky')
                user['balance'] = round(float(user.get('balance', 0)) + ACHIEVEMENTS['lucky']['reward'], 2)
                new_ids.append('lucky')
                break

    dice_wins = sum(1 for g in user.get('dice_history', []) if g.get('win'))
    if dice_wins >= 25 and 'dice_master' not in user['achievements']:
        user['achievements'].append('dice_master')
        user['balance'] = round(float(user.get('balance', 0)) + ACHIEVEMENTS['dice_master']['reward'], 2)
        new_ids.append('dice_master')

    big_dice_wins = [g for g in user.get('dice_history', []) if g.get('win') and g.get('win_amount', 0) >= 1000]
    if big_dice_wins and 'dice_high_roller' not in user['achievements']:
        user['achievements'].append('dice_high_roller')
        user['balance'] = round(float(user['balance']) + 500, 2)
        new_ids.append('dice_high_roller')

    slots_wins = sum(1 for g in user.get('slots_history', []) if g.get('win'))
    if slots_wins >= 50 and 'slots_master' not in user['achievements']:
        user['achievements'].append('slots_master')
        user['balance'] = round(float(user['balance']) + ACHIEVEMENTS['slots_master']['reward'], 2)
        new_ids.append('slots_master')

    if len(user.get('referrals', [])) >= 5 and 'referral_king' not in user['achievements']:
        user['achievements'].append('referral_king')
        user['balance'] = round(float(user['balance']) + ACHIEVEMENTS['referral_king']['reward'], 2)
        new_ids.append('referral_king')

    if user.get('total_deposited', 0) >= 10000 and 'big_depositor' not in user['achievements']:
        user['achievements'].append('big_depositor')
        user['balance'] = round(float(user['balance']) + ACHIEVEMENTS['big_depositor']['reward'], 2)
        new_ids.append('big_depositor')

    blackjack_wins = sum(1 for g in user.get('blackjack_history', []) if g.get('win'))
    if blackjack_wins >= 20 and 'blackjack_master' not in user['achievements']:
        user['achievements'].append('blackjack_master')
        user['balance'] = round(float(user['balance']) + ACHIEVEMENTS['blackjack_master']['reward'], 2)
        new_ids.append('blackjack_master')

    if len(user.get('wheel_history', [])) >= 10 and 'wheel_ace' not in user['achievements']:
        user['achievements'].append('wheel_ace')
        user['balance'] = round(float(user['balance']) + ACHIEVEMENTS['wheel_ace']['reward'], 2)
        new_ids.append('wheel_ace')

    if 'night_owl' not in user['achievements']:
        now = datetime.now()
        if 0 <= now.hour < 5:
            user['achievements'].append('night_owl')
            user['balance'] = round(float(user['balance']) + ACHIEVEMENTS['night_owl']['reward'], 2)
            new_ids.append('night_owl')

    return new_ids


def sync_session_from_user(user_id: str, users: dict) -> None:
    u = users[user_id]
    session['user_id'] = user_id
    session['username'] = u['username']
    session['balance'] = u['balance']
    session['level'] = u.get('level', 1)
    session['xp'] = u.get('xp', 0)
    session['referral_code'] = u.get('referral_code', '')
    session['promo_level'] = u.get('promo_level', 1)

