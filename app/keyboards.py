from telegram import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

def get_main_menu():
    """Главное меню (нижние кнопки)"""
    keyboard = [
        [KeyboardButton("💼 Портфель"), KeyboardButton("⚡ Анализ ИИ")],
        [KeyboardButton("💵 Дивиденды/Купоны"), KeyboardButton("📰 Новости")],
        [KeyboardButton("⚙️ Настройки")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, input_field_placeholder="Выберите действие...")

def get_settings_menu():
    """Меню настроек (инлайн-кнопки поверх чата)"""
    keyboard = [
        [InlineKeyboardButton("🔑 API-ключи", callback_data="change_token")],
        [InlineKeyboardButton("🏦 Выбрать счет", callback_data="choose_account")],
        [InlineKeyboardButton("🌍 Часовой пояс", callback_data="set_timezone")],
        [InlineKeyboardButton("📰 Время новостей", callback_data="set_digest_time")],
        [InlineKeyboardButton("⬅️ Закрыть", callback_data="close_settings")]
    ]
    return InlineKeyboardMarkup(keyboard)

# --- Меню часовых поясов и времени (оставляем без изменений, только кнопки "назад") ---

def get_timezone_menu():
    tz_list = [
        [InlineKeyboardButton("Калининград", callback_data="tz_Europe/Kaliningrad"), InlineKeyboardButton("Москва", callback_data="tz_Europe/Moscow")],
        [InlineKeyboardButton("Самара", callback_data="tz_Europe/Samara"), InlineKeyboardButton("Екатеринбург", callback_data="tz_Asia/Yekaterinburg")],
        [InlineKeyboardButton("Омск", callback_data="tz_Asia/Omsk"), InlineKeyboardButton("Красноярск", callback_data="tz_Asia/Krasnoyarsk")],
        [InlineKeyboardButton("Иркутск", callback_data="tz_Asia/Irkutsk"), InlineKeyboardButton("Якутск", callback_data="tz_Asia/Yakutsk")],
        [InlineKeyboardButton("Владивосток", callback_data="tz_Asia/Vladivostok"), InlineKeyboardButton("Магадан", callback_data="tz_Asia/Magadan")],
        [InlineKeyboardButton("Камчатка", callback_data="tz_Asia/Kamchatka")],
        [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_settings")]
    ]
    return InlineKeyboardMarkup(tz_list)

def get_digest_time_menu():
    times = ["08:00", "09:00", "10:00", "12:00", "18:00", "20:00"]
    keyboard = []
    row = []
    for i, t in enumerate(times):
        row.append(InlineKeyboardButton(f"🕰 {t}", callback_data=f"dt_{t}"))
        if len(row) == 3:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="back_to_settings")])
    return InlineKeyboardMarkup(keyboard)
