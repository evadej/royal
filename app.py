from __future__ import annotations

from flask import (
    Flask,
    render_template,
    request,
    session,
    redirect,
    url_for,
    flash,
    jsonify,
    abort,
    send_from_directory,
)
from markupsafe import escape
from datetime import datetime, date, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
import os, secrets, math
from itertools import chain
from storage import load_users, save_users
from config import SLOT_SYMBOLS, WHEEL_PRIZES, ACHIEVEMENTS, DICE_SIDES, PROMO_CODES
from utils import (
    _rand,
    csrf_protect,
    inject_globals,
    login_required,
    create_deck,
    card_value,
    hand_value,
    level_threshold,
    add_xp_and_level_up,
    count_total_games,
    roll_dice,
    check_achievements,
    sync_session_from_user,
    pick_wheel_prize,
)

# -------------------- App setup --------------------

app = Flask(__name__, template_folder="templates", static_folder="static")
app.config.update(
    SECRET_KEY=os.environ.get("SECRET_KEY", "dev-secret-change-me"),
    JSON_AS_ASCII=False,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
)

app.before_request(csrf_protect)
app.context_processor(inject_globals)

# -------------------- Routes --------------------

@app.route("/")
def index():
    # Гостей отправляем на лендинг
    if "user_id" not in session:
        return render_template("landing.html")

    users = load_users()
    uid = session['user_id']
    user = users.get(uid)
    if not user:
        session.clear()
        return redirect(url_for("login"))

    # Последние игры
    recent_history = user.get("history", [])[:5]
    recent_slots = user.get("slots_history", [])[:5]
    recent_dice = user.get("dice_history", [])[:5]
    recent_wheel = user.get("wheel_history", [])[:5]
    recent_rps = user.get("rps_history", [])[:5]
    recent_guess = user.get("number_history", [])[:5]

    # Обновляем достижения (если есть)
    new_ach = check_achievements(user)
    if new_ach:
        save_users(users)
        sync_session_from_user(uid, users)

    top_achievements = list(ACHIEVEMENTS.items())[:3]

    return render_template(
        "dashboard.html",
        username=user['username'],
        balance=user['balance'],
        level=user.get('level', 1),
        xp=user.get('xp', 0),
        next_level_xp=level_threshold(user.get('level', 1)),
        recent_history=recent_history,
        recent_slots=recent_slots,
        recent_dice=recent_dice,
        recent_wheel=recent_wheel,
        recent_rps=recent_rps,
        recent_guess=recent_guess,
        achievements=user.get('achievements', []),
        new_achievements=new_ach,
        last_bonus_date=user.get('last_bonus_date'),
        current_date=date.today().isoformat(),
        user=user,
        top_achievements=top_achievements
    )

# --------- Auth ---------

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = escape(request.form.get("username", "")).strip()
        password = request.form.get("password", "")
        code = escape(request.form.get("code", "")).strip()

        if not username or not password:
            flash("Заполните все поля")
            return redirect(url_for("register"))
        if len(username) < 3:
            flash("Имя пользователя должно содержать не менее 3 символов")
            return redirect(url_for("register"))
        if len(password) < 4:
            flash("Пароль должен содержать не менее 4 символов")
            return redirect(url_for("register"))

        users = load_users()
        
        # Проверяем код: либо промо, либо реферал
        referred_by = None
        initial_balance = 0
        if code:
            lower_code = code.lower()
            if lower_code in PROMO_CODES:
                initial_balance = PROMO_CODES[lower_code]
            else:
                for uid2, u in users.items():
                    if u.get('referral_code') == code.upper():
                        referred_by = uid2
                        break
                if not referred_by:
                    flash("Неверный код")
                    return redirect(url_for("register"))

        uid = str(len(users) + 1)
        users[uid] = {
            "username": username,
            "password": generate_password_hash(password),
            "balance": initial_balance,
            "history": [],
            "slots_history": [],
            "blackjack_history": [],
            "dice_history": [],
            "wheel_history": [],
            "coinflip_history": [],
            "rps_history": [],
            "number_history": [],
            "last_chance": "",
            "last_bet": "",
            "last_slots_bet": "",
            "last_dice_bet": "",
            "last_rps_bet": "",
            "last_guess_bet": "",
            "last_rps_choice": "rock",
            "last_guess_number": 1,
            "registration_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "level": 1,
            "xp": 0,
            "total_winnings": 0.0,
            "achievements": [],
            "referral_code": secrets.token_hex(3).upper(),
            "promo_level": 1,
            "referred_by": referred_by,
            "referrals": [],
            "referral_earnings": 0,
            "login_streak": 0,
            "last_login_date": None,
            "total_deposited": 0,
            "total_withdrawn": 0,
            "last_wheel_spin": "",
            "transactions": []
        }

        # Фиксируем реферала без мгновенного бонуса
        if referred_by:
            users[referred_by].setdefault('referrals', []).append(uid)
            save_users(users)

        save_users(users)
        sync_session_from_user(uid, users)
        flash("Регистрация прошла успешно! Вы автоматически вошли в систему.")
        return redirect(url_for("index"))

    # Для GET-запроса
    ref_code = request.args.get('ref', '')
    return render_template("register.html", ref_code=ref_code)

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if session.get("login_attempts", 0) >= 5:
            flash("Превышено число попыток. Попробуйте позже.")
            return redirect(url_for("login"))
        username = escape(request.form.get("username", ""))
        password = request.form.get("password", "")
        users = load_users()

        for uid, u in users.items():
            if u['username'] == username and check_password_hash(u['password'], password):
                # Обновляем дату последнего входа
                u['last_login_date'] = date.today().isoformat()
                save_users(users)
                sync_session_from_user(uid, users)
                session.pop('login_attempts', None)
                flash("Вход выполнен успешно!")
                return redirect(url_for("index"))
        session['login_attempts'] = session.get('login_attempts', 0) + 1
        flash("Неверное имя пользователя или пароль")
    return render_template("login.html")

@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("Вы вышли из системы")
    return redirect(url_for("index"))

# --------- Games: Chance ---------

@app.route("/chance")
@login_required
def chance_game():
    users = load_users()
    uid = session['user_id']
    user = users[uid]
    return render_template(
        "chance.html",
        balance=user['balance'],
        history=user.get('history', []),
        last_chance=user.get('last_chance') or 50,
        last_bet=user.get('last_bet') or 100,
        username=user['username']
    )

@app.route("/play_chance", methods=["POST"])
@login_required
def play_chance():
    try:
        users = load_users()
        uid = session['user_id']
        user = users[uid]

        try:
            chance = int(request.form.get("chance", "0"))
            bet = int(request.form.get("bet", "0"))
        except ValueError:
            return jsonify(success=False, message="Пожалуйста, введите корректные числа")

        user['last_chance'] = chance
        user['last_bet'] = bet

        if not (1 <= chance <= 100):
            return jsonify(success=False, message="Шанс должен быть от 1 до 100")
        if bet <= 0 or bet > user['balance']:
            return jsonify(success=False, message="Неверная ставка")

        roll = _rand.randint(1, 100)
        win = roll <= chance
        win_amount = 0
        if win:
            win_amount = round(bet * (100 - chance) / chance, 2)
            user['balance'] = round(user['balance'] + win_amount, 2)
            user['total_winnings'] = round(user.get('total_winnings', 0.0) + win_amount, 2)
            add_xp_and_level_up(user, int(win_amount))
            if chance <= 1 and 'lucky' not in user.get('achievements', []):
                user.setdefault('achievements', []).append('lucky')
                user['balance'] = round(user['balance'] + 1000, 2)
            result_text = f"Поздравляем! Вы выиграли {win_amount:.2f}. Выпало число {roll}"
        else:
            user['balance'] = round(user['balance'] - bet, 2)
            result_text = f"К сожалению, вы проиграли. Выпало число {roll}"

        user.setdefault('history', []).insert(0, {
            "chance": chance,
            "bet": bet,
            "result": result_text,
            "win": win,
            "win_amount": win_amount,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "game": "chance"
        })

        new_ach = check_achievements(user)
        save_users(users)
        sync_session_from_user(uid, users)

        return jsonify(
            success=True,
            balance=user['balance'],
            result=result_text,
            win=win,
            win_amount=win_amount,
            bet=bet,
            random_number=roll,
            xp=user.get('xp', 0),
            level=user.get('level', 1),
            new_achievements=new_ach
        )
    except Exception:
        return jsonify(success=False, message="Серверная ошибка"), 500

# --------- Games: Slots ---------

@app.route("/slots")
@login_required
def slots_game():
    users = load_users()
    uid = session['user_id']
    user = users[uid]
    return render_template(
        "slots.html",
        balance=user['balance'],
        history=user.get('slots_history', []),
        last_bet=user.get('last_slots_bet') or 100,
        username=user['username']
    )

@app.route("/play_slots", methods=["POST"])
@login_required
def play_slots():
    try:
        users = load_users()
        uid = session['user_id']
        user = users[uid]

        try:
            bet = int(request.form.get("bet", "0"))
        except ValueError:
            return jsonify(success=False, message="Пожалуйста, введите корректное число")

        user['last_slots_bet'] = bet
        if bet <= 0 or bet > user['balance']:
            return jsonify(success=False, message="Неверная ставка")

        combo = [_rand.choice(SLOT_SYMBOLS) for _ in range(3)]
        win = False
        win_amount = 0

        # 20% шанс автоматически получить совпадение символов
        if _rand.random() < 0.2:
            symbol = _rand.choice(SLOT_SYMBOLS)
            combo = [symbol, symbol, symbol]

        if combo[0] == combo[1] == combo[2]:
            win = True
            if combo[0] == '💎':
                win_amount = bet * 10
            elif combo[0] == '7️⃣':
                win_amount = bet * 5
            else:
                win_amount = bet * 3

        if win:
            user['balance'] = round(user['balance'] + win_amount, 2)
            user['total_winnings'] = round(user.get('total_winnings', 0.0) + win_amount, 2)
            add_xp_and_level_up(user, int(win_amount))
            result_text = f"Поздравляем! Вы выиграли {win_amount:.2f}. Комбинация: {''.join(combo)}"
        else:
            user['balance'] = round(user['balance'] - bet, 2)
            result_text = f"К сожалению, вы проиграли. Комбинация: {''.join(combo)}"

        user.setdefault('slots_history', []).insert(0, {
            "bet": bet,
            "result": result_text,
            "win": win,
            "win_amount": win_amount if win else 0,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "game": "slots",
            "combination": ''.join(combo)
        })

        new_ach = check_achievements(user)
        save_users(users)
        sync_session_from_user(uid, users)

        return jsonify(
            success=True,
            balance=user['balance'],
            result=result_text,
            win=win,
            win_amount=win_amount,
            bet=bet,
            combination=combo,
            xp=user.get('xp', 0),
            level=user.get('level', 1),
            new_achievements=new_ach
        )
    except Exception:
        return jsonify(success=False, message="Серверная ошибка"), 500

# --------- Games: Blackjack ---------

@app.route("/blackjack")
@login_required
def blackjack_game():
    users = load_users()
    uid = session['user_id']
    user = users[uid]

    # Инициализируем партию при первом заходе
    session.setdefault('blackjack_deck', create_deck())
    session.setdefault('player_hand', [])
    session.setdefault('dealer_hand', [])
    session.setdefault('blackjack_bet', 0)
    session.setdefault('blackjack_game_state', 'betting')

    return render_template(
        "blackjack.html",
        balance=user['balance'],
        username=user['username'],
        game_state=session['blackjack_game_state'],
        player_hand=session['player_hand'],
        dealer_hand=session['dealer_hand'],
        player_score=hand_value(session['player_hand']),
        dealer_score=hand_value(session['dealer_hand']),
        bet=session['blackjack_bet'],
        history=user.get('blackjack_history', [])
    )

@app.route("/blackjack_bet", methods=["POST"])
@login_required
def blackjack_bet():
    users = load_users()
    uid = session['user_id']
    user = users[uid]

    try:
        bet = int(request.form.get("bet", "0"))
    except ValueError:
        return jsonify(success=False, message="Пожалуйста, введите корректную сумму")

    if bet <= 0 or bet > user['balance']:
        return jsonify(success=False, message="Неверная ставка")

    # Резервируем ставку и раздаем карты
    user['balance'] = round(user['balance'] - bet, 2)
    deck = create_deck()
    player = [deck.pop(), deck.pop()]
    dealer = [deck.pop(), deck.pop()]

    session['blackjack_deck'] = deck
    session['player_hand'] = player
    session['dealer_hand'] = dealer
    session['blackjack_bet'] = bet
    session['blackjack_game_state'] = 'player_turn'

    save_users(users)
    sync_session_from_user(uid, users)

    return jsonify(
        success=True,
        balance=user['balance'],
        player_hand=player,
        dealer_hand=dealer,
        player_score=hand_value(player),
        dealer_score=hand_value(dealer),
        game_state='player_turn'
    )

@app.route("/blackjack_hit", methods=["POST"])
@login_required
def blackjack_hit():
    if session.get('blackjack_game_state') != 'player_turn':
        return jsonify(success=False, message="Игра не активна")

    deck = session.get('blackjack_deck', [])
    player = session.get('player_hand', [])

    if not deck or not isinstance(player, list):
        return jsonify(success=False, message="Игра не инициализирована")

    player.append(deck.pop())
    session['player_hand'] = player
    session['blackjack_deck'] = deck

    p_score = hand_value(player)
    if p_score > 21:
        session['blackjack_game_state'] = 'game_over'
        result = "Перебор! Вы проиграли."
        win = False
        users = load_users()
        uid = session['user_id']
        user = users[uid]
        bet = int(session.get('blackjack_bet', 0))
        user.setdefault('blackjack_history', []).insert(0, {
            "bet": bet,
            "result": result,
            "win": win,
            "win_amount": 0,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "game": "blackjack",
            "player_score": p_score,
            "dealer_score": hand_value(session.get('dealer_hand', []))
        })
        new_ach = check_achievements(user)
        save_users(users)
        sync_session_from_user(uid, users)
        return jsonify(
            success=True,
            player_hand=player,
            player_score=p_score,
            dealer_score=hand_value(session.get('dealer_hand', [])),
            game_state='game_over',
            result=result,
            win=win,
            win_amount=0,
            balance=user['balance'],
            level=user.get('level', 1),
            xp=user.get('xp', 0),
            new_achievements=new_ach
        )
    else:
        result = ""
        win = None
        return jsonify(
            success=True,
            player_hand=player,
            player_score=p_score,
            dealer_score=hand_value(session.get('dealer_hand', [])),
            game_state=session['blackjack_game_state'],
            result=result,
            win=win
        )

@app.route("/blackjack_stand", methods=["POST"])
@login_required
def blackjack_stand():
    if session.get('blackjack_game_state') != 'player_turn':
        return jsonify(success=False, message="Игра не активна")

    users = load_users()
    uid = session['user_id']
    user = users[uid]

    deck = session.get('blackjack_deck', [])
    dealer = session.get('dealer_hand', [])
    player = session.get('player_hand', [])
    bet = int(session.get('blackjack_bet', 0))

    if not deck or not dealer or not player or bet <= 0:
        return jsonify(success=False, message="Игра не инициализирована")

    # Дилер добирает до 17
    while hand_value(dealer) < 17 and deck:
        dealer.append(deck.pop())

    session['dealer_hand'] = dealer
    session['blackjack_deck'] = deck
    session['blackjack_game_state'] = 'game_over'

    p = hand_value(player)
    d = hand_value(dealer)

    # Проверяем натуральный блэкджек (21 двумя картами) у игрока/дилера
    player_natural = (len(player) == 2 and p == 21)
    dealer_natural = (len(dealer) == 2 and d == 21)

    win = None
    win_amount = 0
    result = ""

    if d > 21:
        result = "Дилер перебрал! Вы выиграли."
        win = True
        win_amount = bet * 2
    elif dealer_natural and not player_natural:
        result = "У дилера блэкджек. Вы проиграли."
        win = False
    elif player_natural and not dealer_natural:
        result = "Блэкджек! Вы выиграли."
        win = True
        win_amount = int(bet * 2.5)
    elif d > p:
        result = "Дилер выиграл."
        win = False
    elif d < p:
        result = "Вы выиграли!"
        win = True
        win_amount = bet * 2
    else:
        result = "Ничья! Ставка возвращена."
        win = None
        win_amount = bet

    if win is True:
        user['balance'] = round(user['balance'] + win_amount, 2)
        user['total_winnings'] = round(user.get('total_winnings', 0.0) + win_amount, 2)
        add_xp_and_level_up(user, int(win_amount))
    elif win is None:
        user['balance'] = round(user['balance'] + win_amount, 2)
    # (при проигрыше ставка уже удержана)

    user.setdefault('blackjack_history', []).insert(0, {
        "bet": bet,
        "result": result,
        "win": win,
        "win_amount": win_amount,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "game": "blackjack",
        "player_score": p,
        "dealer_score": d
    })

    new_ach = check_achievements(user)
    save_users(users)
    sync_session_from_user(uid, users)

    return jsonify(
        success=True,
        balance=user['balance'],
        dealer_hand=dealer,
        dealer_score=d,
        player_score=p,
        game_state='game_over',
        result=result,
        win=win,
        win_amount=(win_amount if win else 0),
        xp=user.get('xp', 0),
        level=user.get('level', 1),
        new_achievements=new_ach
    )

@app.route("/blackjack_new", methods=["POST"])
@login_required
def blackjack_new():
    for k in ("blackjack_deck", "player_hand", "dealer_hand", "blackjack_bet", "blackjack_game_state"):
        session.pop(k, None)
    return jsonify(success=True)

# --------- Games: Dice ---------

@app.route("/dice")
@login_required
def dice_game():
    users = load_users()
    uid = session['user_id']
    user = users[uid]
    return render_template(
        "dice.html",
        balance=user['balance'],
        history=user.get('dice_history', [])[:10],
        last_bet=user.get('last_dice_bet') or 100,
        username=user['username']
    )

@app.route("/play_dice", methods=["POST"])
@login_required
def play_dice():
    users = load_users()
    uid = session['user_id']
    user = users[uid]

    try:
        bet = int(request.form.get("bet", "0"))
        bet_type = request.form.get("bet_type", "any_seven")
    except ValueError:
        return jsonify(success=False, message="Пожалуйста, введите корректные значения")

    user['last_dice_bet'] = bet
    
    if bet <= 0 or bet > user['balance']:
        return jsonify(success=False, message="Неверная ставка")

    # Бросок двух костей
    dice1 = roll_dice()
    dice2 = roll_dice()
    total = dice1 + dice2
    
    win = False
    win_amount = 0
    result_text = ""
    selected_number = None
    
    # Определяем результат в зависимости от типа ставки
    if bet_type == "any_seven":
        # Ставка на любое сочетание дающее 7
        if total == 7:
            win = True
            win_amount = bet * 4
            result_text = f"Поздравляем! Выпало 7 ({dice1}+{dice2}). Ваш выигрыш: {win_amount:.2f} ₽"
        else:
            result_text = f"К сожалению, выпало {total} ({dice1}+{dice2}), а не 7."
    
    elif bet_type == "hard_way":
        # Ставка на дубли (1+1, 2+2 и т.д.)
        selected_number = int(request.form.get("selected_number", "2"))
        if dice1 == dice2 and total == selected_number:
            win = True
            win_amount = bet * 8
            result_text = f"Поздравляем! Выпал дубль {dice1} ({dice1}+{dice2}). Ваш выигрыш: {win_amount:.2f} ₽"
        elif dice1 == dice2:
            result_text = f"К сожалению, выпал дубль {dice1}, а не {selected_number//2}."
        else:
            result_text = f"К сожалению, выпало {total} ({dice1}+{dice2}), а не дубль."
    
    elif bet_type == "any_craps":
        # Ставка на крабы
        if total in [2, 3, 12]:
            win = True
            win_amount = bet * 7
            result_text = f"Поздравляем! Выпали крабы: {total} ({dice1}+{dice2}). Ваш выигрыш: {win_amount:.2f} ₽"
        else:
            result_text = f"К сожалению, выпало {total} ({dice1}+{dice2}), а не крабы."
    
    elif bet_type == "field":
        # Ставка на поле (2, 3, 4, 9, 10, 11, 12)
        if total in [2, 3, 4, 9, 10, 11, 12]:
            win = True
            if total in [2, 12]:
                win_amount = bet * 3  # Удвоенный выигрыш для 2 и 12
            else:
                win_amount = bet * 2
            result_text = f"Поздравляем! Выпало поле: {total} ({dice1}+{dice2}). Ваш выигрыш: {win_amount:.2f} ₽"
        else:
            result_text = f"К сожалению, выпало {total} ({dice1}+{dice2}), а не поле (2,3,4,9,10,11,12)."
    
    elif bet_type == "specific_number":
        # Ставка на конкретное число
        selected_number = int(request.form.get("selected_number", "2"))
        if total == selected_number:
            win = True
            if selected_number in [2, 12]:
                win_amount = bet * 30
            elif selected_number in [3, 11]:
                win_amount = bet * 15
            elif selected_number in [4, 10]:
                win_amount = bet * 9
            elif selected_number in [5, 9]:
                win_amount = bet * 7
            elif selected_number in [6, 8]:
                win_amount = bet * 7
            result_text = f"Поздравляем! Выпало {total} ({dice1}+{dice2}). Ваш выигрыш: {win_amount:.2f} ₽"
        else:
            result_text = f"К сожалению, выпало {total} ({dice1}+{dice2}), а не {selected_number}."

    if win:
        user['balance'] = round(user['balance'] + win_amount, 2)
        user['total_winnings'] = round(user.get('total_winnings', 0.0) + win_amount, 2)
        add_xp_and_level_up(user, int(win_amount))
    else:
        user['balance'] = round(user['balance'] - bet, 2)

    # Добавляем в историю
    user.setdefault('dice_history', []).insert(0, {
        "bet": bet,
        "bet_type": bet_type,
        "selected_number": locals().get('selected_number'),
        "dice1": dice1,
        "dice2": dice2,
        "total": total,
        "result": result_text,
        "win": win,
        "win_amount": win_amount if win else 0,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "game": "dice"
    })

    # Проверяем достижения
    new_ach = check_achievements(user)
    save_users(users)
    sync_session_from_user(uid, users)

    return jsonify(
        success=True,
        balance=user['balance'],
        result=result_text,
        win=win,
        dice1=dice1,
        dice2=dice2,
        total=total,
        win_amount=win_amount,
        xp=user.get('xp', 0),
        level=user.get('level', 1),
        new_achievements=new_ach
    )

# --------- Games: Rock Paper Scissors ---------

@app.route("/rps")
@login_required
def rps_game():
    users = load_users()
    uid = session['user_id']
    user = users[uid]
    return render_template(
        "rps.html",
        balance=user['balance'],
        history=user.get('rps_history', [])[:10],
        last_bet=user.get('last_rps_bet') or 100,
        last_choice=user.get('last_rps_choice', 'rock')
    )


@app.route("/play_rps", methods=["POST"])
@login_required
def play_rps():
    users = load_users()
    uid = session['user_id']
    user = users[uid]
    try:
        bet = int(request.form.get("bet", "0"))
    except ValueError:
        return jsonify(success=False, message="Пожалуйста, введите корректные значения")

    choice = request.form.get("choice", "rock")
    valid_choices = {"rock", "paper", "scissors"}
    if choice not in valid_choices:
        return jsonify(success=False, message="Неверный выбор")
    if bet <= 0 or bet > user['balance']:
        return jsonify(success=False, message="Неверная ставка")

    user['last_rps_bet'] = bet
    user['last_rps_choice'] = choice

    opponent = _rand.choice(tuple(valid_choices))
    win = False
    tie = False
    win_amount = 0
    delta = 0

    winning_pairs = {
        ("rock", "scissors"),
        ("scissors", "paper"),
        ("paper", "rock"),
    }

    if choice == opponent:
        tie = True
    elif (choice, opponent) in winning_pairs:
        win = True
        delta = bet
        win_amount = bet
    else:
        delta = -bet

    user['balance'] = round(user['balance'] + delta, 2)

    if win:
        user['total_winnings'] = round(user.get('total_winnings', 0.0) + win_amount, 2)
        add_xp_and_level_up(user, bet)

    result = 'tie' if tie else ('win' if win else 'lose')

    user.setdefault('rps_history', []).insert(0, {
        "bet": bet,
        "choice": choice,
        "opponent": opponent,
        "win": win,
        "tie": tie,
        "delta": delta,
        "win_amount": win_amount,
        "result": result,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "game": "rps"
    })

    new_ach = check_achievements(user)
    save_users(users)
    sync_session_from_user(uid, users)

    return jsonify(
        success=True,
        balance=user['balance'],
        opponent=opponent,
        win=win,
        tie=tie,
        win_amount=win_amount,
        result=result,
        level=user.get('level', 1),
        xp=user.get('xp', 0),
        new_achievements=new_ach
    )


# --------- Games: Number Guess ---------

@app.route("/number-guess")
@login_required
def number_guess_game():
    users = load_users()
    uid = session['user_id']
    user = users[uid]
    return render_template(
        "number_guess.html",
        balance=user['balance'],
        history=user.get('number_history', [])[:10],
        last_bet=user.get('last_guess_bet') or 100,
        last_choice=user.get('last_guess_number', 1)
    )


@app.route("/play_number_guess", methods=["POST"])
@login_required
def play_number_guess():
    users = load_users()
    uid = session['user_id']
    user = users[uid]
    try:
        bet = int(request.form.get("bet", "0"))
        choice = int(request.form.get("choice", "0"))
    except ValueError:
        return jsonify(success=False, message="Пожалуйста, введите корректные значения")

    if bet <= 0 or bet > user['balance']:
        return jsonify(success=False, message="Неверная ставка")
    if choice < 1 or choice > 10:
        return jsonify(success=False, message="Выберите число от 1 до 10")

    user['last_guess_bet'] = bet
    user['last_guess_number'] = choice

    winning_number = _rand.randint(1, 10)
    payout = 9
    win = (choice == winning_number)
    win_amount = bet * payout if win else 0
    delta = win_amount if win else -bet

    user['balance'] = round(user['balance'] + delta, 2)

    if win:
        user['total_winnings'] = round(user.get('total_winnings', 0.0) + win_amount, 2)
        add_xp_and_level_up(user, bet * 2)

    user.setdefault('number_history', []).insert(0, {
        "bet": bet,
        "choice": choice,
        "winning_number": winning_number,
        "win": win,
        "win_amount": win_amount,
        "delta": delta,
        "payout": payout,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "game": "number_guess"
    })

    new_ach = check_achievements(user)
    save_users(users)
    sync_session_from_user(uid, users)

    return jsonify(
        success=True,
        balance=user['balance'],
        win=win,
        win_amount=win_amount,
        winning_number=winning_number,
        payout=payout,
        level=user.get('level', 1),
        xp=user.get('xp', 0),
        new_achievements=new_ach
    )

# --------- Games: Coinflip ---------

@app.route("/coinflip")
@login_required
def coinflip_game():
    users = load_users()
    uid = session['user_id']
    user = users[uid]
    return render_template(
        "coinflip.html",
        balance=user['balance'],
        history=user.get('coinflip_history', [])[:10]
    )


@app.route("/play_coinflip", methods=["POST"])
@login_required
def play_coinflip():
    users = load_users()
    uid = session['user_id']
    user = users[uid]
    try:
        bet = int(request.form.get("bet", "0"))
    except ValueError:
        return jsonify(success=False, message="Пожалуйста, введите корректные значения")

    choice = request.form.get("choice", "heads")
    if bet <= 0 or bet > user['balance']:
        return jsonify(success=False, message="Неверная ставка")

    flip = "heads" if _rand.getrandbits(1) == 0 else "tails"
    win = (choice == flip)
    delta = bet if win else -bet

    user['balance'] = round(user['balance'] + delta, 2)
    win_amount = bet if win else 0
    if win:
        user['total_winnings'] = round(user.get('total_winnings', 0.0) + bet, 2)
        add_xp_and_level_up(user, bet)

    user.setdefault('coinflip_history', []).insert(0, {
        "bet": bet,
        "choice": choice,
        "flip": flip,
        "win": win,
        "delta": delta,
        "win_amount": win_amount,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "game": "coinflip"
    })

    new_ach = check_achievements(user)
    save_users(users)
    sync_session_from_user(uid, users)

    return jsonify(success=True, balance=user['balance'], win=win, flip=flip,
                   win_amount=win_amount, level=user.get('level', 1),
                   new_achievements=new_ach)

# --------- Mini-games: Wheel of Fortune ---------

@app.route("/wheel")
@login_required
def wheel_of_fortune():
    users = load_users()
    uid = session['user_id']
    user = users[uid]
    return render_template(
        "wheel.html",
        balance=user['balance'],
        last_spin=user.get('last_wheel_spin'),
        today=date.today().isoformat(),
        prizes=[{k: v for k, v in p.items() if k != 'weight' and k != 'jackpot'} for p in WHEEL_PRIZES]
    )

@app.route("/spin_wheel", methods=["POST"])
@login_required
def spin_wheel():
    users = load_users()
    uid = session['user_id']
    user = users[uid]

    today = date.today().isoformat()
    if user.get('last_wheel_spin') == today:
        return jsonify(success=False, message="Колесо можно крутить раз в день")

    user['last_wheel_spin'] = today

    prize = pick_wheel_prize()
    amount = prize["value"]
    if prize.get("jackpot"):
        message = f"ДЖЕКПОТ! Вы выиграли {amount} ₽!"
    else:
        message = f"Вы выиграли {amount} ₽!"

    user['balance'] += amount
    user['total_winnings'] = round(user.get('total_winnings', 0.0) + amount, 2)

    # Записываем в историю
    user.setdefault('wheel_history', []).insert(0, {
        "prize": amount,
        "message": message,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })

    save_users(users)
    sync_session_from_user(uid, users)

    return jsonify(success=True, prize=amount, message=message, balance=user['balance'])

# --------- Autoplay ---------

@app.route("/auto_play", methods=["POST"])
@login_required
def auto_play():
    users = load_users()
    uid = session['user_id']
    user = users[uid]

    game_type = request.form.get("game_type")
    try:
        times = int(request.form.get("times", "0"))
    except ValueError:
        return jsonify(success=False, message="Пожалуйста, введите корректные значения")

    # Параметры ставок, используемые после цикла для записи истории
    chance = None
    bet = None

    results = []
    wins = 0
    losses = 0
    win_sum = 0
    loss_sum = 0

    for _ in range(times):
        if user['balance'] <= 0:
            break

        if game_type == "chance":
            if chance is None or bet is None:
                try:
                    chance = int(request.form.get("chance", "0"))
                    bet = int(request.form.get("bet", "0"))
                except ValueError:
                    break

            if bet > user['balance']:
                bet = int(user['balance'])
            if bet <= 0:
                break

            roll = _rand.randint(1, 100)
            win = roll <= chance
            if win:
                win_amount = round(bet * (100 - chance) / chance, 2)
                user['balance'] = round(user['balance'] + win_amount, 2)
                user['total_winnings'] = round(user.get('total_winnings', 0.0) + win_amount, 2)
                add_xp_and_level_up(user, int(win_amount))
                result_text = f"Поздравляем! Вы выиграли {win_amount:.2f}. Выпало число {roll}"
                wins += 1
                win_sum += win_amount
            else:
                user['balance'] = round(user['balance'] - bet, 2)
                result_text = f"К сожалению, вы проиграли. Выпало число {roll}"
                losses += 1
                loss_sum += bet

            results.append({"win": win, "result": result_text, "balance": user['balance']})

        elif game_type == "slots":
            if bet is None:
                try:
                    bet = int(request.form.get("bet", "0"))
                except ValueError:
                    break

            if bet > user['balance']:
                bet = int(user['balance'])
            if bet <= 0:
                break

            combo = [_rand.choice(SLOT_SYMBOLS) for _ in range(3)]
            win = False
            win_amount = 0

            if combo[0] == combo[1] == combo[2]:
                win = True
                if combo[0] == '💎':
                    win_amount = bet * 10
                elif combo[0] == '7️⃣':
                    win_amount = bet * 5
                else:
                    win_amount = bet * 3

            if win:
                user['balance'] = round(user['balance'] + win_amount, 2)
                user['total_winnings'] = round(user.get('total_winnings', 0.0) + win_amount, 2)
                add_xp_and_level_up(user, int(win_amount))
                result_text = f"Поздравляем! Вы выиграли {win_amount:.2f}. Комбинация: {''.join(combo)}"
                wins += 1
                win_sum += win_amount
            else:
                user['balance'] = round(user['balance'] - bet, 2)
                result_text = f"К сожалению, вы проиграли. Комбинация: {''.join(combo)}"
                losses += 1
                loss_sum += bet

            results.append({"win": win, "result": result_text, "balance": user['balance'], "combination": combo})

        elif game_type == "dice":
            try:
                bet = int(request.form.get("bet", "0"))
                bet_type = request.form.get("bet_type", "any_seven")
                selected_number = int(request.form.get("selected_number", "2"))
            except ValueError:
                break

            if bet > user['balance']:
                bet = int(user['balance'])
            if bet <= 0:
                break

            dice1 = roll_dice()
            dice2 = roll_dice()
            total = dice1 + dice2
            
            win = False
            win_amount = 0
            result_text = ""
            
            if bet_type == "any_seven":
                if total == 7:
                    win = True
                    win_amount = bet * 4
                    result_text = f"Поздравляем! Выпало 7 ({dice1}+{dice2}). Ваш выигрыш: {win_amount:.2f} ₽"
                else:
                    result_text = f"К сожалению, выпало {total} ({dice1}+{dice2}), а не 7."
            
            elif bet_type == "hard_way":
                if dice1 == dice2 and total == selected_number:
                    win = True
                    win_amount = bet * 8
                    result_text = f"Поздравляем! Выпал дубль {dice1} ({dice1}+{dice2}). Ваш выигрыш: {win_amount:.2f} ₽"
                elif dice1 == dice2:
                    result_text = f"К сожалению, выпал дубль {dice1}, а не {selected_number//2}."
                else:
                    result_text = f"К сожалению, выпало {total} ({dice1}+{dice2}), а не дубль."
            
            elif bet_type == "any_craps":
                if total in [2, 3, 12]:
                    win = True
                    win_amount = bet * 7
                    result_text = f"Поздравляем! Выпали крабы: {total} ({dice1}+{dice2}). Ваш выигрыш: {win_amount:.2f} ₽"
                else:
                    result_text = f"К сожалению, выпало {total} ({dice1}+{dice2}), а не крабы."
            
            elif bet_type == "field":
                if total in [2, 3, 4, 9, 10, 11, 12]:
                    win = True
                    if total in [2, 12]:
                        win_amount = bet * 3
                    else:
                        win_amount = bet * 2
                    result_text = f"Поздравляем! Выпало поле: {total} ({dice1}+{dice2}). Ваш выигрыш: {win_amount:.2f} ₽"
                else:
                    result_text = f"К сожалению, выпало {total} ({dice1}+{dice2}), а не поле (2,3,4,9,10,11,12)."
            
            elif bet_type == "specific_number":
                if total == selected_number:
                    win = True
                    if selected_number in [4, 10]:
                        win_amount = bet * 9
                    elif selected_number in [5, 9]:
                        win_amount = bet * 7
                    elif selected_number in [6, 8]:
                        win_amount = bet * 7
                    result_text = f"Поздравляем! Выпало {total} ({dice1}+{dice2}). Ваш выигрыш: {win_amount:.2f} ₽"
                else:
                    result_text = f"К сожалению, выпало {total} ({dice1}+{dice2}), а не {selected_number}."

            if win:
                user['balance'] = round(user['balance'] + win_amount, 2)
                user['total_winnings'] = round(user.get('total_winnings', 0.0) + win_amount, 2)
                add_xp_and_level_up(user, int(win_amount))
                wins += 1
                win_sum += win_amount
            else:
                user['balance'] = round(user['balance'] - bet, 2)
                losses += 1
                loss_sum += bet

            user.setdefault('dice_history', []).insert(0, {
                "bet": bet,
                "bet_type": bet_type,
                "selected_number": selected_number,
                "dice1": dice1,
                "dice2": dice2,
                "total": total,
                "result": result_text,
                "win": win,
                "win_amount": win_amount if win else 0,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "game": "dice"
            })

            results.append({"win": win, "result": result_text, "balance": user['balance'], "dice1": dice1, "dice2": dice2, "total": total})
        else:
            return jsonify(success=False, message="Неизвестный тип игры")
    played = len(results)
    if played:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if game_type == "chance":
            net = win_sum - loss_sum
            user.setdefault('history', []).insert(0, {
                "chance": chance,
                "bet": bet,
                "times": played,
                "win": net >= 0,
                "win_sum": win_sum,
                "loss_sum": loss_sum,
                "result": f"Авто-игра: {played} ставок, побед: {wins}, поражений: {losses}",
                "timestamp": timestamp,
                "game": "chance",
            })
        elif game_type == "slots":
            net = win_sum - loss_sum
            user.setdefault('slots_history', []).insert(0, {
                "bet": bet,
                "times": played,
                "win": net >= 0,
                "win_sum": win_sum,
                "loss_sum": loss_sum,
                "result": f"Авто-игра: {played} ставок, побед: {wins}, поражений: {losses}",
                "timestamp": timestamp,
                "game": "slots",
            })

    new_ach = check_achievements(user)
    save_users(users)
    sync_session_from_user(uid, users)

    return jsonify(
        success=True,
        results=results,
        final_balance=user['balance'],
        wins=wins,
        losses=losses,
        win_sum=win_sum,
        loss_sum=loss_sum,
        xp=user.get('xp', 0),
        level=user.get('level', 1),
        new_achievements=new_ach,
        times=played
    )

# --------- Bonuses & profile ---------

@app.route("/daily_bonus", methods=["POST"])
@login_required
def daily_bonus():
    users = load_users()
    uid = session['user_id']
    user = users[uid]

    today = date.today().isoformat()
    
    # Проверяем, получал ли пользователь бонус сегодня
    if user.get('last_bonus_date') == today:
        return jsonify(success=False, message="Вы уже получали бонус сегодня")

    bonus = 50
    user['balance'] = round(user['balance'] + bonus, 2)
    user['last_bonus_date'] = today

    save_users(users)
    sync_session_from_user(uid, users)
    return jsonify(success=True, message=f"Бонус {bonus} ₽ начислен", balance=user['balance'])

@app.route("/deposit", methods=["GET", "POST"])
@login_required
def deposit():
    users = load_users()
    uid = session['user_id']
    user = users[uid]

    if request.method == "POST":
        try:
            amount = int(request.form.get("amount", "0"))
        except ValueError:
            flash("Пожалуйста, введите корректную сумму")
            return redirect(url_for("deposit"))

        if amount <= 0:
            flash("Сумма пополнения должна быть положительной")
            return redirect(url_for("deposit"))

        user['balance'] = round(user['balance'] + amount, 2)
        prev_total = user.get('total_deposited', 0)
        user['total_deposited'] = prev_total + amount
        user.setdefault('transactions', []).insert(0, {
            "type": "deposit",
            "amount": amount,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })
        # Отчисления рефереру после порога 5000
        referrer_id = user.get('referred_by')
        if referrer_id:
            referrer = users.get(referrer_id)
            if referrer:
                if prev_total >= 5000 or user['total_deposited'] >= 5000:
                    percent = referrer.get('promo_level', 1)
                    bonus = int(amount * percent / 100)
                    if bonus > 0:
                        referrer['balance'] = round(referrer.get('balance', 0) + bonus, 2)
                        referrer['referral_earnings'] = referrer.get('referral_earnings', 0) + bonus
                        check_achievements(referrer)

        check_achievements(user)
        save_users(users)
        sync_session_from_user(uid, users)
        flash(f"Баланс успешно пополнен на {amount} ₽")
        return redirect(url_for("deposit"))

    return render_template("deposit.html", transactions=user.get('transactions', []), total_deposited=user.get('total_deposited', 0), total_withdrawn=user.get('total_withdrawn', 0))


@app.route("/withdraw", methods=["POST"])
@login_required
def withdraw():
    try:
        amount = int(request.form.get("amount", "0"))
    except ValueError:
        flash("Пожалуйста, введите корректную сумму")
        return redirect(url_for("deposit"))

    if amount <= 0:
        flash("Сумма вывода должна быть положительной")
        return redirect(url_for("deposit"))

    users = load_users()
    uid = session['user_id']
    user = users[uid]
    if amount > user['balance']:
        flash("Недостаточно средств")
        return redirect(url_for("deposit"))

    user['balance'] = round(user['balance'] - amount, 2)
    user['total_withdrawn'] = user.get('total_withdrawn', 0) + amount
    user.setdefault('transactions', []).insert(0, {
        "type": "withdraw",
        "amount": amount,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })
    save_users(users)
    sync_session_from_user(uid, users)
    flash(f"Вы успешно вывели {amount} ₽")
    return redirect(url_for("deposit"))

@app.route("/profile")
@login_required
def profile():
    users = load_users()
    uid = session['user_id']
    user = users[uid]

    total_games = count_total_games(user)
    chance_wins = sum(1 for g in user.get('history', []) if g.get('win'))
    slots_wins = sum(1 for g in user.get('slots_history', []) if g.get('win'))
    blackjack_wins = sum(1 for g in user.get('blackjack_history', []) if g.get('win'))
    dice_wins = sum(1 for g in user.get('dice_history', []) if g.get('win'))
    wheel_wins = len(user.get('wheel_history', []))

    wins = chance_wins + slots_wins + blackjack_wins + dice_wins + wheel_wins

    game_counts = {
        'chance': len(user.get('history', [])),
        'slots': len(user.get('slots_history', [])),
        'blackjack': len(user.get('blackjack_history', [])),
        'dice': len(user.get('dice_history', [])),
        'wheel': len(user.get('wheel_history', [])),
    }
    favorite_game = max(game_counts, key=game_counts.get) if total_games > 0 else 'Нет данных'

    biggest_win = max(
        chain(
            (h.get('win_amount', 0) for h in user.get('history', []) if h.get('win')),
            (h.get('win_amount', 0) for h in user.get('slots_history', []) if h.get('win')),
            (h.get('win_amount', 0) for h in user.get('dice_history', []) if h.get('win')),
            (h.get('prize', 0) for h in user.get('wheel_history', [])),
        ),
        default=0,
    )

    registration_date = user.get('registration_date')
    days_since_joined = (
        datetime.now() - datetime.fromisoformat(registration_date)
    ).days if registration_date else 0

    # Расширенная статистика
    stats = {
        'total_games': total_games,
        'win_rate': round((wins / total_games * 100) if total_games > 0 else 0, 2),
        'favorite_game': favorite_game,
        'biggest_win': biggest_win,
        'total_deposited': user.get('total_deposited', 0),
        'total_withdrawn': user.get('total_withdrawn', 0),
        'days_since_joined': days_since_joined,
    }
    check_achievements(user)
    save_users(users)

    return render_template(
        "profile.html",
        username=user['username'],
        balance=user['balance'],
        games_played=total_games,
        wins=wins,
        level=user.get('level', 1),
        xp=user.get('xp', 0),
        next_level_xp=level_threshold(user.get('level', 1)),
        registered_date=user.get('registration_date', 'Неизвестно'),
        chance_wins=chance_wins,
        slots_wins=slots_wins,
        blackjack_wins=blackjack_wins,
        dice_wins=dice_wins,
        wheel_wins=wheel_wins,
        achievements=user.get('achievements', []),
        total_winnings=user.get('total_winnings', 0.0),
        referral_code=user.get('referral_code', ''),
        referrals_count=len(user.get('referrals', [])),
        referral_earnings=user.get('referral_earnings', 0),
        promo_level=user.get('promo_level', 1),
        promo_upgrade_cost=(user.get('promo_level', 1) * 10000) if user.get('promo_level', 1) < 5 else None,
        stats=stats
    )

# --------- Referral promo code management ---------

@app.route("/set_promo_code", methods=["POST"])
@login_required
def set_promo_code():
    users = load_users()
    uid = session['user_id']
    user = users[uid]
    code = escape(request.form.get("code", "")).strip()
    if not (4 <= len(code) <= 12) or not code.isalnum():
        return jsonify(success=False, message="Некорректный код")
    if any(u.get('referral_code') == code for u in users.values()):
        return jsonify(success=False, message="Код уже занят")
    if user.get('referral_code'):
        cost = 10000
        if user['balance'] < cost:
            return jsonify(success=False, message=f"Недостаточно средств (нужно {cost} ₽)")
        user['balance'] = round(user['balance'] - cost, 2)
    user['referral_code'] = code
    save_users(users)
    sync_session_from_user(uid, users)
    return jsonify(success=True, code=code, balance=user['balance'])


@app.route("/upgrade_promo_code", methods=["POST"])
@login_required
def upgrade_promo_code():
    users = load_users()
    uid = session['user_id']
    user = users[uid]
    level = user.get('promo_level', 1)
    if level >= 5:
        return jsonify(success=False, message="Максимальный уровень промокода достигнут")
    cost = level * 10000
    if user['balance'] < cost:
        return jsonify(success=False, message="Недостаточно средств")
    user['balance'] = round(user['balance'] - cost, 2)
    user['promo_level'] = level + 1
    save_users(users)
    sync_session_from_user(uid, users)
    next_cost = user['promo_level'] * 10000 if user['promo_level'] < 5 else None
    return jsonify(success=True, promo_level=user['promo_level'], balance=user['balance'], next_cost=next_cost)

# --------- PWA Support ---------

@app.route('/manifest.json')
def serve_manifest():
    return send_from_directory('static', 'manifest.json')

@app.route('/sw.js')
def serve_sw():
    return send_from_directory('static', 'sw.js')

# -------------------- Error handlers --------------------

@app.errorhandler(400)
def bad_request(err):
    return jsonify(success=False, message=str(err.description)), 400

# -------------------- Entrypoint --------------------

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
