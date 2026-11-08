from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
import logging
from datetime import datetime
from typing import Dict, Any

from app.keyboards.ai_strategy_kb import (
    get_main_ai_keyboard,
    get_analysis_options_keyboard,
    get_strategy_actions_keyboard,
    get_risk_level_keyboard
)

router = Router()
logger = logging.getLogger(__name__)

@router.message(Command("ai"))
async def cmd_ai_main(message: Message, tinkoff_client):
    """Главная команда AI функционала"""
    mode_info = []
    if tinkoff_client.is_configured:
        if tinkoff_client.use_sandbox:
            mode_info.append("🔒 SANDBOX")
        else:
            mode_info.append("⚡ REAL")
    else:
        mode_info.append("🎮 DEMO")
    
    mode_text = " | ".join(mode_info)
    
    await message.answer(
        f"🤖 <b>AI Ассистент для инвестиций</b>\n"
        f"<i>Режим: {mode_text}</i>\n\n"
        "Я помогу проанализировать ваш портфель, оценить рыночную ситуацию "
        "и сгенерировать персональные инвестиционные рекомендации.\n\n"
        "Выберите действие:",
        reply_markup=get_main_ai_keyboard(),
        parse_mode="HTML"
    )

@router.message(Command("ai_analysis"))
async def cmd_ai_analysis(message: Message, ai_strategy_manager):
    """AI анализ портфеля"""
    await message.answer("🤖 <b>Запускаю глубокий AI анализ вашего портфеля...</b>")
    
    try:
        result = await ai_strategy_manager.get_portfolio_analysis(message.from_user.id)
        
        if not result.success:
            error_msg = result.error or "Неизвестная ошибка"
            await message.answer(f"❌ <b>Ошибка анализа:</b>\n{error_msg}")
            return
        
        response = _format_portfolio_analysis(result.data)
        await message.answer(response, parse_mode="HTML")
        
    except Exception as e:
        logger.error(f"AI analysis error: {e}")
        await message.answer("❌ <b>Произошла ошибка при анализе портфеля</b>")

@router.message(Command("market_analysis"))
async def cmd_market_analysis(message: Message, ai_strategy_manager):
    """Анализ рыночной ситуации"""
    await message.answer("📊 <b>Анализирую текущую рыночную ситуацию...</b>")
    
    try:
        result = await ai_strategy_manager.get_market_analysis()
        
        if not result.success:
            error_msg = result.error or "Неизвестная ошибка"
            await message.answer(f"❌ Ошибка: {error_msg}")
            return
            
        response = _format_market_analysis(result.data)
        await message.answer(response, parse_mode="HTML")
        
    except Exception as e:
        logger.error(f"Market analysis error: {e}")
        await message.answer("❌ <b>Ошибка анализа рынка</b>")

@router.message(Command("ai_strategy"))
async def cmd_ai_strategy(message: Message):
    """Управление AI стратегией"""
    await message.answer(
        "🎯 <b>Управление AI стратегией</b>\n\n"
        "Выберите тип анализа для генерации персональной стратегии:",
        reply_markup=get_analysis_options_keyboard(),
        parse_mode="HTML"
    )

@router.callback_query(F.data == "ai_full_analysis")
async def handle_full_analysis(callback: CallbackQuery, ai_strategy_manager):
    """Полный AI анализ"""
    await callback.message.edit_text("🔍 <b>Запускаю комплексный AI анализ...</b>")
    
    result = await ai_strategy_manager.get_portfolio_analysis(callback.from_user.id)
    
    if not result.success:
        error_msg = result.error or "Неизвестная ошибка"
        await callback.message.edit_text(f"❌ Ошибка: {error_msg}")
        return
    
    response = _format_detailed_analysis(result.data)
    await callback.message.edit_text(
        response,
        reply_markup=get_strategy_actions_keyboard(),
        parse_mode="HTML"
    )

@router.callback_query(F.data == "ai_market_analysis")
async def handle_market_analysis(callback: CallbackQuery, ai_strategy_manager):
    """Анализ рынка"""
    await callback.message.edit_text("🌐 <b>Анализирую рыночную конъюнктуру...</b>")
    
    result = await ai_strategy_manager.get_market_analysis()
    
    if not result.success:
        error_msg = result.error or "Неизвестная ошибка"
        await callback.message.edit_text(f"❌ Ошибка: {error_msg}")
        return
    
    response = _format_market_analysis(result.data)
    await callback.message.edit_text(response, parse_mode="HTML")

@router.callback_query(F.data == "ai_trading_plan")
async def handle_trading_plan(callback: CallbackQuery):
    """Генерация торгового плана"""
    await callback.message.edit_text(
        "⚡ <b>Генерация торгового плана</b>\n\n"
        "Выберите ваш риск-профиль:",
        reply_markup=get_risk_level_keyboard(),
        parse_mode="HTML"
    )

@router.callback_query(F.data.startswith("risk_"))
async def handle_risk_level(callback: CallbackQuery, ai_strategy_manager):
    """Обработка выбора риск-профиля"""
    risk_level = callback.data.split("_")[1]
    
    # Validate risk level
    valid_risk_levels = ["conservative", "moderate", "aggressive"]
    if risk_level not in valid_risk_levels:
        await callback.message.edit_text("❌ Неверный уровень риска")
        return
    
    await callback.message.edit_text(f"📋 <b>Генерирую {risk_level} торговый план...</b>")
    
    result = await ai_strategy_manager.generate_trading_plan(
        callback.from_user.id, risk_level
    )
    
    if not result.success:
        error_msg = result.error or "Неизвестная ошибка"
        await callback.message.edit_text(f"❌ Ошибка: {error_msg}")
        return
    
    response = _format_trading_plan(result.data, risk_level)
    await callback.message.edit_text(response, parse_mode="HTML")

@router.callback_query(F.data == "execute_ai_strategy")
async def handle_execute_strategy(callback: CallbackQuery, ai_strategy_manager):
    """Выполнение AI стратегии"""
    await callback.message.edit_text("⚡ <b>Выполняю рекомендации AI стратегии...</b>")
    
    # Сначала получаем анализ
    analysis_result = await ai_strategy_manager.get_portfolio_analysis(callback.from_user.id)
    
    if not analysis_result.success:
        error_msg = analysis_result.error or "Неизвестная ошибка"
        await callback.message.edit_text(f"❌ Ошибка: {error_msg}")
        return
    
    # Выполняем рекомендации
    actions = analysis_result.data.get('rebalancing_recommendations', {}).get('actions', [])
    execution_result = await ai_strategy_manager.execute_strategy_actions(
        callback.from_user.id, actions
    )
    
    response = _format_execution_result(execution_result.data, len(actions))
    await callback.message.edit_text(response, parse_mode="HTML")

@router.callback_query(F.data == "ai_main_menu")
async def handle_main_menu(callback: CallbackQuery):
    """Возврат в главное меню"""
    await callback.message.edit_text(
        "🤖 <b>AI Ассистент для инвестиций</b>\n\n"
        "Выберите действие:",
        reply_markup=get_main_ai_keyboard(),
        parse_mode="HTML"
    )

@router.message(Command("sandbox_info"))
async def cmd_sandbox_info(message: Message, tinkoff_client):
    """Информация о sandbox режиме"""
    if not tinkoff_client.is_configured:
        await message.answer(
            "🔒 <b>Sandbox режим</b>\n\n"
            "Tinkoff API не настроен. Работаем в демо-режиме.\n\n"
            "Чтобы использовать sandbox:\n"
            "1. Получите токен в личном кабинете Tinkoff\n"
            "2. Добавьте TINKOFF_TOKEN в .env файл\n"
            "3. Установите USE_SANDBOX=true"
        )
        return
    
    if tinkoff_client.use_sandbox:
        await message.answer(
            "🔄 <b>Sandbox режим активен</b>\n\n"
            "✅ Все операции выполняются в тестовой среде\n"
            "✅ Используются виртуальные деньги\n"
            "✅ Без риска для реальных средств\n"
            "✅ Идеально для тестирования стратегий\n\n"
            "<i>Для перехода в реальный режим установите USE_SANDBOX=false в .env</i>"
        )
    else:
        await message.answer(
            "⚡ <b>Реальный режим активен</b>\n\n"
            "⚠️ Все операции выполняются с реальными деньгами\n"
            "⚠️ Будьте осторожны с исполнением ордеров\n"
            "⚠️ Рекомендуется тестировать в sandbox\n\n"
            "<i>Для перехода в sandbox установите USE_SANDBOX=true в .env</i>"
        )

def _format_portfolio_analysis(data: Dict[str, Any]) -> str:
    """Форматирование анализа портфеля"""
    portfolio_health = data.get('portfolio_health', {})
    market_analysis = data.get('market_analysis', {})
    recommendations = data.get('rebalancing_recommendations', {})
    
    # Информация о режиме
    mode_info = []
    if data.get('sandbox'):
        mode_info.append("🔒 SANDBOX")
    if data.get('demo_mode'):
        mode_info.append("🎮 DEMO")
    mode_text = " | ".join(mode_info) if mode_info else "⚡ REAL"
    
    health_scores = [
        f"• Общий счет: {portfolio_health.get('overall_score', 0)}/100",
        f"• Диверсификация: {portfolio_health.get('diversification_score', 0)}/100", 
        f"• Риск-менеджмент: {portfolio_health.get('risk_score', 0)}/100",
        f"• Ликвидность: {portfolio_health.get('liquidity_score', 0)}/100"
    ]
    
    actions = recommendations.get('actions', [])
    actions_text = "\n".join([
        f"• {action.get('action', '').upper()} {action.get('ticker', '')} ({action.get('amount_percent', 0)}%)"
        for action in actions[:3]
    ]) if actions else "• Значительных изменений не требуется"
    
    return (
        f"📊 <b>AI Анализ Портфеля</b>\n"
        f"<i>Режим: {mode_text}</i>\n\n"
        f"<b>Оценка портфеля:</b>\n" + "\n".join(health_scores) + f"\n\n"
        f"<b>Рыночная оценка:</b>\n"
        f"• Настроение: {market_analysis.get('current_sentiment', 'N/A')}\n"
        f"• Уровень риска: {market_analysis.get('risk_level', 'N/A')}\n\n"
        f"<b>Ключевые рекомендации:</b>\n{actions_text}\n\n"
        f"<i>Обновлено: {datetime.now().strftime('%H:%M %d.%m.%Y')}</i>"
    )

def _format_market_analysis(data: Dict[str, Any]) -> str:
    """Форматирование анализа рынка"""
    # Информация о режиме
    mode_info = []
    if data.get('sandbox'):
        mode_info.append("🔒 SANDBOX")
    if data.get('demo_mode'):
        mode_info.append("🎮 DEMO")
    mode_text = " | ".join(mode_info) if mode_info else "⚡ REAL"
    
    key_drivers = data.get('key_drivers', [])[:3]
    recommended_actions = data.get('recommended_actions', [])[:3]
    
    return (
        f"🌐 <b>AI Анализ Рынка</b>\n"
        f"<i>Режим: {mode_text}</i>\n\n"
        f"<b>Общий настрой:</b> {data.get('market_sentiment', 'N/A').title()}\n"
        f"<b>Уверенность:</b> {data.get('confidence_level', 0) * 100:.1f}%\n"
        f"<b>Уровень риска:</b> {data.get('risk_assessment', 'N/A')}\n\n"
        f"<b>Ключевые драйверы:</b>\n" +
        "\n".join([f"• {driver}" for driver in key_drivers]) + f"\n\n"
        f"<b>Рекомендации:</b>\n" +
        "\n".join([f"• {action}" for action in recommended_actions]) + f"\n\n"
        f"<i>Актуально на: {datetime.now().strftime('%H:%M %d.%m.%Y')}</i>"
    )

def _format_detailed_analysis(data: Dict[str, Any]) -> str:
    """Форматирование детального анализа"""
    portfolio_health = data.get('portfolio_health', {})
    recommendations = data.get('rebalancing_recommendations', {})
    target_alloc = recommendations.get('target_allocation', {})
    
    actions = recommendations.get('actions', [])
    high_priority_actions = [a for a in actions if a.get('urgency') == 'high']
    
    actions_text = "\n".join([
        f"• {action.get('action', '').upper()} {action.get('ticker', '')} - {action.get('reason', '')}"
        for action in high_priority_actions[:5]
    ]) if high_priority_actions else "• Срочных действий не требуется"
    
    return (
        f"🔍 <b>Детальный AI Анализ</b>\n\n"
        f"<b>Оценка здоровья портфеля:</b> {portfolio_health.get('overall_score', 0)}/100\n"
        f"<b>Приоритет ребалансировки:</b> {recommendations.get('priority', 'low')}\n\n"
        f"<b>Целевое распределение:</b>\n"
        f"• Акции: {target_alloc.get('stocks', 0)}%\n"
        f"• Облигации: {target_alloc.get('bonds', 0)}%\n"
        f"• Кэш: {target_alloc.get('cash', 0)}%\n\n"
        f"<b>Срочные действия:</b>\n{actions_text}\n\n"
        f"<i>Для выполнения стратегии нажмите 'Выполнить рекомендации'</i>"
    )

def _format_trading_plan(data: Dict[str, Any], risk_level: str) -> str:
    """Форматирование торгового плана"""
    recommendations = data.get('rebalancing_recommendations', {})
    actions = recommendations.get('actions', [])
    
    actions_text = "\n".join([
        f"• {action.get('action', '').upper()} {action.get('ticker', '')} ({action.get('amount_percent', 0)}%)"
        for action in actions[:6]
    ]) if actions else "• Портфель оптимален для выбранного риск-профиля"
    
    target_alloc = recommendations.get('target_allocation', {})
    
    return (
        f"🎯 <b>Торговый План ({risk_level.title()})</b>\n\n"
        f"<b>Рекомендуемые операции:</b>\n{actions_text}\n\n"
        f"<b>Целевое распределение:</b>\n"
        f"• Акции: {target_alloc.get('stocks', 0)}%\n"
        f"• Облигации: {target_alloc.get('bonds', 0)}%\n"
        f"• Кэш: {target_alloc.get('cash', 0)}%\n\n"
        f"<i>План сгенерирован: {datetime.now().strftime('%d.%m.%Y')}</i>"
    )

def _format_execution_result(data: Dict[str, Any], total_recommendations: int) -> str:
    """Форматирование результата выполнения"""
    executed = data.get('executed_actions', [])
    executed_count = len(executed)
    
    executed_text = "\n".join([
        f"• {action.get('action', '')} {action.get('ticker', '')} - {action.get('status', '')}"
        for action in executed[:3]
    ]) if executed else "• Действия не выполнялись (режим анализа)"
    
    # Информация о режиме выполнения
    mode_info = "Симуляция"
    for action in executed:
        if action.get('sandbox'):
            mode_info = "SANDBOX"
            break
        elif not action.get('simulated', True):
            mode_info = "REAL"
            break
    
    return (
        f"⚡ <b>Результат Выполнения Стратегии</b>\n"
        f"<i>Режим: {mode_info}</i>\n\n"
        f"<b>Статус выполнения:</b>\n"
        f"• Рекомендаций получено: {total_recommendations}\n"
        f"• Выполнено действий: {executed_count}\n\n"
        f"<b>Детали выполнения:</b>\n{executed_text}\n\n"
        f"<i>Время: {datetime.now().strftime('%H:%M %d.%m.%Y')}</i>"
    )