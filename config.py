from __future__ import annotations

TRANSLATIONS = {
    'ru': {
        'home': 'Главная',
        'chance': 'Шанс',
        'slots': 'Слоты',
        'dice': 'Кости',
        'blackjack': 'Блэкджек',
        'wheel': 'Колесо',
        'coinflip': 'Монетка',
        'rps': 'Камень-ножницы-бумага',
        'number_guess': 'Угадай число',
        'balance': 'Баланс',
        'logout': 'Выйти',
        'login': 'Войти',
        'register': 'Регистрация',
        'level': 'Ур.',
        'install_app': 'Установить приложение',
        'login_page_title': 'Вход',
        'login_header': 'Вход в казино',
        'username': 'Имя пользователя',
        'password': 'Пароль',
        'login_button': 'Войти',
        'no_account': 'Нет аккаунта?',
        'register_here': 'Зарегистрируйтесь',
        'register_title': 'Регистрация',
        'register_header': 'Регистрация',
        'username_hint': 'Не менее 3 символов',
        'password_hint': 'Не менее 4 символов',
        'code_label': 'Реферальный/промокод (если есть)',
        'code_placeholder': 'Введите код',
        'register_button': 'Зарегистрироваться',
        'have_account': 'Уже есть аккаунт?',
        'login_here': 'Войдите',
        'bet': 'Ставка',
        'choice': 'Выбор',
        'heads_label': 'Орёл',
        'tails_label': 'Решка',
        'flip_button': 'Бросить',
        'game_rules': 'Правила игры',
        'history_title': 'История игр',
        'win_msg': 'Вы выиграли!',
        'lose_msg': 'Вы проиграли.',
        'rules_coin': 'Выберите сторону монеты и сделайте ставку. Угадайте — получите удвоение ставки.'
    }

}
SLOT_SYMBOLS = ['🍒', '🍋', '🍊', '🍇', '🔔', '⭐', '💎', '7️⃣', '🍀', '🍉', '🥇', '🍌']
SUITS = ['♥', '♦', '♣', '♠']
RANKS = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']
DICE_SIDES = 6

PROMO_CODES = {
    'royal': 50,
    'test': 10000,
}

WHEEL_PRIZES = [
    {"text": "50 ₽", "value": 50, "color": "hsl(197 30% 43%)", "weight": 25},
    {"text": "100 ₽", "value": 100, "color": "hsl(173 58% 39%)", "weight": 20},
    {"text": "150 ₽", "value": 150, "color": "hsl(43 74% 66%)", "weight": 18},
    {"text": "200 ₽", "value": 200, "color": "hsl(27 87% 67%)", "weight": 15},
    {"text": "300 ₽", "value": 300, "color": "hsl(12 76% 61%)", "weight": 12},
    {"text": "500 ₽", "value": 500, "color": "hsl(350 60% 52%)", "weight": 8},
    {"text": "1000 ₽", "value": 1000, "color": "hsl(300 50% 50%)", "weight": 3},
    {"text": "5000 ₽", "value": 5000, "color": "hsl(60 80% 40%)", "weight": 1, "jackpot": True},
]

ACHIEVEMENTS = {
    'veteran': {
        'name': 'Ветеран',
        'description': 'Достигните 10 уровня',
        'icon': '🏆',
        'reward': 500
    },
    'rich': {
        'name': 'Богач',
        'description': 'Выиграйте 10,000 ₽',
        'icon': '💰',
        'reward': 1000
    },
    'gambler': {
        'name': 'Азартный игрок',
        'description': 'Сыграйте 100 игр',
        'icon': '🎲',
        'reward': 300
    },
    'lucky': {
        'name': 'Счастливчик',
        'description': 'Выиграйте с шансом 1%',
        'icon': '🍀',
        'reward': 1000
    },
    'dice_master': {
        'name': 'Мастер костей',
        'description': 'Выиграйте 25 раз в кости',
        'icon': '🎲',
        'reward': 400
    },
    'dice_high_roller': {
        'name': 'Крупный игрок в кости',
        'description': 'Выиграйте 1000+ ₽ за одну игру в кости',
        'icon': '💰',
        'reward': 500
    },
    'slots_master': {
        'name': 'Гуру слотов',
        'description': 'Выиграйте 50 раз в слоты',
        'icon': '🎰',
        'reward': 500
    },
    'referral_king': {
        'name': 'Реферальный король',
        'description': 'Пригласите 5 друзей',
        'icon': '👑',
        'reward': 800
    },
    'blackjack_master': {
        'name': 'Мастер блэкджека',
        'description': 'Выиграйте 20 раз в блэкджек',
        'icon': '🂡',
        'reward': 600
    },
    'wheel_ace': {
        'name': 'Колёсный ас',
        'description': 'Выиграйте 10 раз в колесе фортуны',
        'icon': '🎡',
        'reward': 300
    },
    'big_depositor': {
        'name': 'Инвестор',
        'description': 'Пополните счёт на 10000 ₽',
        'icon': '🏦',
        'reward': 300
    },
    'night_owl': {
        'name': 'Ночная сова',
        'description': 'Сыграйте после полуночи',
        'icon': '🌙',
        'reward': 200
    }
}
