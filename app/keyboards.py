from telegram import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

def get_main_menu():
    """Главное меню бота (кнопки внизу экрана)"""
    keyboard = [
        [KeyboardButton("📊 Мой портфель"), KeyboardButton("🤖 Анализ ИИ")],
        [KeyboardButton("💰 Дивиденды"), KeyboardButton("⚙️ Настройки")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, input_field_placeholder="Выберите действие...")

def get_settings_menu():
    """Меню настроек (кнопки под сообщением)"""
    keyboard = [
        [InlineKeyboardButton("🔑 Изменить токен", callback_data="change_token")],
        [InlineKeyboardButton("🏦 Выбрать счет", callback_data="choose_account")],
        [InlineKeyboardButton("🌍 Часовой пояс", callback_data="set_timezone")]
    ]
    return InlineKeyboardMarkup(keyboard)
