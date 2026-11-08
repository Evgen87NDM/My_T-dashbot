from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def get_main_ai_keyboard():
    """Главная клавиатура AI функционала"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="📊 Анализ портфеля", 
                callback_data="ai_full_analysis"
            )
        ],
        [
            InlineKeyboardButton(
                text="🌐 Анализ рынка", 
                callback_data="ai_market_analysis"
            )
        ],
        [
            InlineKeyboardButton(
                text="🎯 Торговый план", 
                callback_data="ai_trading_plan"
            )
        ],
        [
            InlineKeyboardButton(
                text="🔒 Инфо о режиме", 
                callback_data="mode_info"
            )
        ]
    ])

def get_analysis_options_keyboard():
    """Клавиатура опций анализа"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="🔍 Полный анализ", 
                callback_data="ai_full_analysis"
            )
        ],
        [
            InlineKeyboardButton(
                text="⚡ Быстрый анализ", 
                callback_data="ai_quick_analysis"
            )
        ],
        [
            InlineKeyboardButton(
                text="📈 Только сигналы", 
                callback_data="ai_signals_only"
            )
        ],
        [
            InlineKeyboardButton(
                text="⬅️ Назад", 
                callback_data="ai_main_menu"
            )
        ]
    ])

def get_strategy_actions_keyboard():
    """Клавиатура действий со стратегией"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="🔄 Выполнить рекомендации", 
                callback_data="execute_ai_strategy"
            )
        ],
        [
            InlineKeyboardButton(
                text="📋 Детальный отчет", 
                callback_data="detailed_report"
            )
        ],
        [
            InlineKeyboardButton(
                text="⚙️ Настроить стратегию", 
                callback_data="configure_strategy"
            )
        ],
        [
            InlineKeyboardButton(
                text="🔄 Новый анализ", 
                callback_data="ai_full_analysis"
            )
        ],
        [
            InlineKeyboardButton(
                text="⬅️ Главное меню", 
                callback_data="ai_main_menu"
            )
        ]
    ])

def get_risk_level_keyboard():
    """Клавиатура выбора уровня риска"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="🟢 Консервативный", 
                callback_data="risk_conservative"
            )
        ],
        [
            InlineKeyboardButton(
                text="🟡 Умеренный", 
                callback_data="risk_moderate"
            )
        ],
        [
            InlineKeyboardButton(
                text="🔴 Агрессивный", 
                callback_data="risk_aggressive"
            )
        ],
        [
            InlineKeyboardButton(
                text="⬅️ Назад", 
                callback_data="ai_main_menu"
            )
        ]
    ])

def get_mode_info_keyboard():
    """Клавиатура информации о режиме"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="🔒 Sandbox информация", 
                callback_data="sandbox_info"
            )
        ],
        [
            InlineKeyboardButton(
                text="🔄 Перезагрузить", 
                callback_data="refresh_mode"
            )
        ],
        [
            InlineKeyboardButton(
                text="⬅️ Главное меню", 
                callback_data="ai_main_menu"
            )
        ]
    ])