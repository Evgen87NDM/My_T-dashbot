"""
Telegram bot for Investment Advisor - Enhanced with account selection
"""
import logging
import asyncio
import json
import os
from app.keyboards import get_main_menu, get_settings_menu
from telegram import Update, BotCommand, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from typing import List, Dict
from app.database import db
from telegram.ext import ConversationHandler
from t_tech.invest import Client, AccountStatus
from app.loader import get_tinkoff_client, get_tinkoff_client_manager
from app.health_monitor import HealthMonitor
from app.ai_manager import get_ai_manager
from app.settings import settings
from app.tariff_manager import get_tariff_manager

logger = logging.getLogger(__name__)

class InvestmentTelegramBot:
    """Bot with AI Portfolio Management and account selection"""
    async def manual_digest(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Ручной вызов сводки"""
        class FakeJob:
            data = {'user_id': update.effective_user.id}
        class FakeContext:
            job = FakeJob()
            bot = context.bot
        await self.send_digest(FakeContext())

    async def show_timezone_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        from app.keyboards import get_timezone_menu
        query = update.callback_query
        await query.answer()
        await query.edit_message_text("🌍 Выберите ваш часовой пояс:", reply_markup=get_timezone_menu())

    async def save_timezone(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        tz = query.data.replace("tz_", "")
        db.save_user_data(query.from_user.id, timezone=tz)
        await query.edit_message_text(f"✅ Часовой пояс изменен на: {tz.split('/')[-1]}")

    async def show_digest_time_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        from app.keyboards import get_digest_time_menu
        query = update.callback_query
        await query.answer()
        await query.edit_message_text("📰 Выберите удобное время для сводки:", reply_markup=get_digest_time_menu())

    async def save_digest_time(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        time_str = query.data.replace("dt_", "")
        db.save_user_data(query.from_user.id, digest_time=time_str)
        await query.edit_message_text(f"✅ Время сводки изменено на: {time_str}")

    async def back_to_settings(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        from app.keyboards import get_settings_menu
        query = update.callback_query
        await query.answer()
        await query.edit_message_text("⚙️ Настройки бота\n\nВыберите, что хотите изменить:", reply_markup=get_settings_menu())

    async def close_settings(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        await query.delete_message()
    
    def __init__(self):
        self.token = settings.TELEGRAM_BOT_TOKEN
        if not self.token:
            raise ValueError("❌ TELEGRAM_BOT_TOKEN not set!")
            
        self.application = None
        self.client_manager = get_tinkoff_client_manager()
        self.ai_manager = None
        self.pending_actions = {}
        self.tariff_manager = get_tariff_manager(self.client_manager)
        
        # Initialize account selection storage
        self.selected_accounts_file = "selected_accounts.json"
        self.selected_accounts = self._load_selected_accounts()
        self.account_names = {}  # account_id -> account_name mapping
        
        logger.info("✅ Tinkoff client manager initialized")
        
        # Initialize AI manager
        asyncio.run(self._init_ai_manager())

    def _load_selected_accounts(self):
        """Load selected accounts from file"""
        try:
            if os.path.exists(self.selected_accounts_file):
                with open(self.selected_accounts_file, 'r') as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"Error loading selected accounts: {e}")
        return {}

    def _save_selected_accounts(self):
        """Save selected accounts to file"""
        try:
            with open(self.selected_accounts_file, 'w') as f:
                json.dump(self.selected_accounts, f)
        except Exception as e:
            logger.error(f"Error saving selected accounts: {e}")

    async def _init_ai_manager(self):
        """Initialize AI manager"""
        try:
            self.ai_manager = await get_ai_manager()
            logger.info("✅ AI Manager initialized")
        except Exception as e:
            logger.error(f"❌ AI Manager failed: {e}")
            self.ai_manager = None

    def _is_real_tinkoff_client(self):
        """Check if using real Tinkoff client"""
        return self.client_manager.is_real_client()

    def _get_operation_mode_info(self):
        """Get detailed operation mode information"""
        if settings.TINKOFF_SANDBOX_MODE:
            return "🔧 SANDBOX MODE", "Используется TINKOFF_TOKEN_SANDBOX"
        else:
            return "⚡ REAL TRADING MODE", "Используется TINKOFF_TOKEN"

    async def _execute_tinkoff_operation(self, operation):
        """Execute Tinkoff operation with proper lifecycle management"""
        return await asyncio.get_event_loop().run_in_executor(
            None, lambda: self.client_manager.execute_operation(operation)
        )

    async def _setup_bot_commands(self):
        """Оставляем только команду /start в меню для спасения"""
        try:
            commands = [
                BotCommand("start", "🏠 Главное меню"),
            ]
            await self.application.bot.set_my_commands(commands)
            logger.info("✅ Меню команд обновлено (только /start)")
        except Exception as e:
            logger.warning(f"⚠️ Could not update bot commands: {e}")

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        user_data = db.get_user(user.id)
        
        # ПРИНУДИТЕЛЬНО ОБНОВЛЯЕМ ИМЯ В БАЗЕ
        # Берем имя напрямую из Telegram и сохраняем
        db.save_user_data(user.id, user_name=user.first_name)
        
        if user_data and user_data.get('tinkoff_token'):
            name = user.first_name # Используем имя из Telegram
            await update.message.reply_text(
                f"С возвращением, {name}! Рад тебя видеть.\nВыбери действие в меню:",
                reply_markup=get_main_menu()
            )
            return ConversationHandler.END
            
        # Берем имя из Telegram и сразу просим токен
        context.user_data['temp_name'] = user.first_name
        
        welcome_text = (
            f"👋 Привет, {user.first_name}!\n\n"
            "Я — твой личный AI-ассистент по инвестициям.\n"
            "Что я умею:\n"
            "💼 Анализировать твой портфель простым языком\n"
            "💵 Следить за дивидендами и купонами\n"
            "📰 Присылать утреннюю сводку новостей\n\n"
            "Для начала работы отправь мне свой API-ключ от Т-Инвестиций (создай его с правами «Только для чтения»).\n\n"
            "Или нажми кнопку ниже, чтобы пропустить этот шаг (тогда я буду присылать только общие новости рынка)."
        )
        keyboard = [[InlineKeyboardButton("⏩ Пропустить", callback_data="skip_token")]]
        await update.message.reply_text(welcome_text, reply_markup=InlineKeyboardMarkup(keyboard))
        return "ASK_TOKEN"
        
    async def portfolio_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        user_data = db.get_user(user.id)
        token = user_data.get('tinkoff_token') if user_data else None

        if not token:
            await update.message.reply_text("❌ Не подключен API-ключ.\nНажмите ⚙️ Настройки.")
            return

        await update.message.reply_text("💼 Загружаю данные ваших портфелей...")

        try:
            with Client(token) as client:
                accounts_resp = client.users.get_accounts()
                all_ids = [a.id for a in accounts_resp.accounts if a.status == AccountStatus.ACCOUNT_STATUS_OPEN]

            selection = self._parse_selection(user_data.get('selected_account'))
            target_ids = all_ids if selection == "all" else [i for i in selection if i in all_ids]
            if not target_ids:
                target_ids = all_ids

            data = await self._get_portfolio_for_accounts(token, target_ids)
            if not data or not data['accounts']:
                await update.message.reply_text("❌ Не удалось загрузить портфели.")
                return

            all_positions = []
            for acc in data['accounts']:
                for pos in acc['positions']:
                    all_positions.append(pos)
            all_positions.sort(key=lambda p: p['value'], reverse=True)

            positions_text = ""
            for pos in all_positions:
                emoji = "🟢" if pos['real_yield'] >= 0 else "🔴"
                positions_text += f"{emoji} <b>{pos['name']}</b>: {pos['quantity']:.4g} шт. | {pos['value']:,.0f} ₽ ({pos['yield_percentage']:+.1f}%)\n"

            acc_names = ", ".join(acc['account_name'] for acc in data['accounts'])

            response = (
                f"📈 <b>Ваш портфель</b>\n\n"
                f"🏦 Счета ({len(data['accounts'])}): {acc_names}\n"
                f"💰 Стоимость: <b>{data['total_portfolio_value']:,.2f} ₽</b>\n"
                f"📊 Доходность: {data['total_real_yield']:+,.2f} ₽ ({data['total_yield_percentage']:+.2f}%)\n\n"
                f"{positions_text}"
            )
            await update.message.reply_text(response, parse_mode="HTML")

        except Exception as e:
            logger.error(f"Portfolio error: {e}")
            await update.message.reply_text("❌ Ошибка при загрузке портфеля.")

    async def accounts_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /accounts command with account selection from DB"""
        user = update.effective_user
        user_data = db.get_user(user.id)
        token = user_data.get('tinkoff_token') if user_data else None
        
        if not token:
            await update.message.reply_text("❌ У вас не подключен токен. Нажмите ⚙️ Настройки.")
            return

        await update.message.reply_text("📋 Загружаю список ваших счетов...")
        
        try:
            with Client(token) as client:
                accounts_response = client.users.get_accounts()
                
                if not accounts_response or not accounts_response.accounts:
                    await update.message.reply_text("❌ Не найдено счетов")
                    return
                
                keyboard = []
                for account in accounts_response.accounts:
                    # 1. Фильтр по статусу: только открытые
                    if account.status != AccountStatus.ACCOUNT_STATUS_OPEN:
                        continue
                        
                    # 2. Фильтр по наличию средств
                    portfolio = client.operations.get_portfolio(account_id=account.id)
                    total_value = portfolio.total_amount_portfolio.units + (portfolio.total_amount_portfolio.nano / 1e9)
                    
                    if total_value <= 0:
                        continue # Пропускаем пустой счет

                    account_name = getattr(account, 'name', 'Счет')
                    account_id = getattr(account, 'id', 'N/A')
                    
                    keyboard.append([
                        InlineKeyboardButton(
                            f"💳 {account_name}", 
                            callback_data=f"select_acc_{account_id}"
                        )
                    ])
                
                if not keyboard:
                    await update.message.reply_text("❌ У вас нет действующих счетов с активами.")
                    return
                
                reply_markup = InlineKeyboardMarkup(keyboard)
                await update.message.reply_text("Выберите счет для анализа:", reply_markup=reply_markup)
                
        except Exception as e:
            logger.error(f"Accounts error: {e}")
            await update.message.reply_text(f"❌ Ошибка загрузки счетов. Проверьте токен.")

    async def _get_all_accounts_portfolio_data(self):
        """Get portfolio data from all accounts"""
        try:
            def get_accounts_operation(client):
                return client.users.get_accounts()
            
            accounts_response = await self._execute_tinkoff_operation(get_accounts_operation)
                
            if not accounts_response or not accounts_response.accounts:
                logger.error("No accounts found")
                return None
            
            all_accounts_data = []
            total_portfolio_value = 0
            total_invested = 0
            total_cash = 0
            
            for account in accounts_response.accounts:
                account_id = account.id
                account_name = getattr(account, 'name', f'Счет {account_id[-4:]}')
                account_type = getattr(account, 'type', 'Неизвестно')
                account_status = getattr(account, 'status', 'Неизвестно')
                
                logger.info(f"Processing account: {account_name} ({account_id})")
                
                # Get portfolio data for this account
                account_data = await self._get_account_portfolio_data(account_id)
                if account_data:
                    account_data['account_name'] = account_name
                    account_data['account_type'] = account_type
                    account_data['account_status'] = account_status
                    all_accounts_data.append(account_data)
                    
                    total_portfolio_value += account_data['total_value']
                    total_invested += account_data['total_invested']
                    total_cash += account_data['available_cash']
            
            # РЕАЛЬНАЯ общая доходность
            total_real_yield = total_portfolio_value - total_invested
            total_yield_percentage = 0
            if total_invested > 0:
                total_yield_percentage = (total_real_yield / total_invested) * 100
            
            logger.info(f"Total portfolio: value={total_portfolio_value}, invested={total_invested}, yield={total_real_yield}")
            
            return {
                'accounts': all_accounts_data,
                'total_portfolio_value': total_portfolio_value,
                'total_invested': total_invested,
                'total_cash': total_cash,
                'total_real_yield': total_real_yield,
                'total_yield_percentage': total_yield_percentage,
                'account_count': len(all_accounts_data),
                'is_real_data': self._is_real_tinkoff_client(),
                'is_sandbox': settings.TINKOFF_SANDBOX_MODE
            }
            
        except Exception as e:
            logger.error(f"All accounts portfolio data error: {e}")
            return None

    async def _get_account_portfolio_data(self, account_id):
        """Get portfolio data for specific account"""
        try:
            # Get portfolio data
            def get_portfolio_operation(client):
                return client.operations.get_portfolio(account_id=account_id)
            
            portfolio = await self._execute_tinkoff_operation(get_portfolio_operation)
            
            if not portfolio:
                logger.warning(f"No portfolio data for account {account_id}")
                return None
            
            # Get positions data
            def get_positions_operation(client):
                return client.operations.get_positions(account_id=account_id)
            
            positions = await self._execute_tinkoff_operation(get_positions_operation)
            
            total_value = 0
            total_invested = 0
            positions_list = []
            
            # Process positions from portfolio
            if hasattr(portfolio, 'positions') and portfolio.positions:
                for position in portfolio.positions:
                    try:
                        # Get quantity
                        quantity = position.quantity.units if hasattr(position.quantity, 'units') else 0
                        
                        # Get current price
                        current_price = 0
                        if hasattr(position, 'current_price'):
                            if hasattr(position.current_price, 'units') and hasattr(position.current_price, 'nano'):
                                current_price = position.current_price.units + position.current_price.nano / 1e9
                            elif hasattr(position.current_price, 'units'):
                                current_price = position.current_price.units
                        
                        # Get average price (цена покупки)
                        average_price = 0
                        if hasattr(position, 'average_position_price'):
                            if hasattr(position.average_position_price, 'units') and hasattr(position.average_position_price, 'nano'):
                                average_price = position.average_position_price.units + position.average_position_price.nano / 1e9
                            elif hasattr(position.average_position_price, 'units'):
                                average_price = position.average_position_price.units
                        
                        position_value = quantity * current_price
                        invested_value = quantity * average_price
                        
                        total_value += position_value
                        total_invested += invested_value
                        
                        # РЕАЛЬНАЯ доходность позиции
                        real_yield = position_value - invested_value
                        
                        # Calculate yield percentage
                        yield_percentage = 0
                        if invested_value > 0:
                            yield_percentage = (real_yield / invested_value) * 100
                        
                        # Get instrument info for name and ticker
                        name = "Unknown"
                        ticker = "N/A"
                        instrument_type = "Unknown"
                        if hasattr(position, 'figi'):
                            try:
                                def get_instrument_operation(instrument_client):
                                    return instrument_client.instruments.get_instrument_by(id_type=1, id=position.figi)
                                
                                instrument_response = self.client_manager.execute_operation(get_instrument_operation)
                                if instrument_response and hasattr(instrument_response, 'instrument'):
                                    name = getattr(instrument_response.instrument, 'name', 'Unknown')
                                    ticker = getattr(instrument_response.instrument, 'ticker', 'N/A')
                                    instrument_type = getattr(instrument_response.instrument, 'instrument_type', 'Unknown')
                            except Exception as e:
                                logger.warning(f"Could not get instrument info for FIGI {position.figi}: {e}")
                                if hasattr(position, 'name'):
                                    name = position.name
                                if hasattr(position, 'ticker'):
                                    ticker = position.ticker
                                if hasattr(position, 'instrument_type'):
                                    instrument_type = position.instrument_type
                        
                        positions_list.append({
                            'name': name,
                            'ticker': ticker,
                            'instrument_type': instrument_type,
                            'quantity': quantity,
                            'value': position_value,
                            'invested_value': invested_value,
                            'current_price': current_price,
                            'average_price': average_price,
                            'real_yield': real_yield,
                            'yield_percentage': yield_percentage
                        })
                    except Exception as e:
                        logger.warning(f"Error processing position: {e}")
                        continue
            
            # Process cash from positions
            available_cash = 0
            if positions and hasattr(positions, 'money') and positions.money:
                for money in positions.money:
                    if hasattr(money, 'currency') and money.currency == 'rub':
                        if hasattr(money, 'units') and hasattr(money, 'nano'):
                            cash_amount = money.units + money.nano / 1e9
                        elif hasattr(money, 'units'):
                            cash_amount = money.units
                        else:
                            cash_amount = 0
                        available_cash += cash_amount
            
            # РЕАЛЬНАЯ совокупная доходность счета
            total_real_yield = total_value - total_invested
            total_yield_percentage = 0
            if total_invested > 0:
                total_yield_percentage = (total_real_yield / total_invested) * 100
            
            logger.info(f"Account {account_id}: value={total_value}, invested={total_invested}, yield={total_real_yield}")
            
            return {
                'account_id': account_id,
                'total_value': total_value,
                'total_invested': total_invested,
                'available_cash': available_cash,
                'total_real_yield': total_real_yield,
                'total_yield_percentage': total_yield_percentage,
                'positions': positions_list,
                'positions_count': len(positions_list)
            }
            
        except Exception as e:
            logger.error(f"Account portfolio data error for {account_id}: {e}")
            return None

    def _format_portfolio_response(self, portfolio_data):
        """Format portfolio data for display - все счета, ВСЕ позиции"""
        total_value = portfolio_data['total_portfolio_value']
        total_invested = portfolio_data['total_invested']
        total_cash = portfolio_data['total_cash']
        total_yield = portfolio_data['total_real_yield']
        total_yield_percentage = portfolio_data['total_yield_percentage']
        accounts = portfolio_data['accounts']
        
        if portfolio_data['is_sandbox']:
            data_source = "🔧 SANDBOX DATA (TINKOFF_TOKEN_SANDBOX)"
        else:
            data_source = "⚡ REAL TRADING DATA (TINKOFF_TOKEN)"
        
        parts = []
        
        # Часть 1: Общая сводка
        summary_part = f"""
📈 ПОЛНЫЙ ОБЗОР ПОРТФЕЛЯ

{data_source}

💰 Общая стоимость: {total_value:,.2f} ₽
💼 Сумма вложений: {total_invested:,.2f} ₽
📈 Совокупный доход: {total_yield:+,.2f} ₽ ({total_yield_percentage:+.2f}%)
💳 Денежные средства: {total_cash:,.2f} ₽
🏦 Количество счетов: {len(accounts)}

{'='*50}
"""
        parts.append(summary_part)

        total_positions_count = 0
        
        # Обрабатываем каждый счет
        for i, account in enumerate(accounts, 1):
            account_name = account['account_name']
            account_type = account['account_type']
            account_value = account['total_value']
            account_invested = account['total_invested']
            account_cash = account['available_cash']
            account_yield = account['total_real_yield']
            account_yield_percentage = account['total_yield_percentage']
            positions = account['positions']
            
            total_positions_count += len(positions)
            
            # Account weight in total portfolio
            account_weight = (account_value / total_value * 100) if total_value > 0 else 0
            
            account_header = f"""
🏦 СЧЕТ {i}: {account_name}
   Тип: {account_type}
   Стоимость: {account_value:,.2f} ₽ ({account_weight:.1f}% от общего портфеля)
   Сумма вложений: {account_invested:,.2f} ₽
   Доходность: {account_yield:+,.2f} ₽ ({account_yield_percentage:+.2f}%)
   Денежные средства: {account_cash:,.2f} ₽
   Позиций: {len(positions)}
"""
            
            # Если позиций нет, добавляем информацию о счете в текущую часть
            if not positions:
                if len(parts[-1] + account_header) < 4000:
                    parts[-1] += account_header + "\n   💰 Только денежные средства\n" + "   " + "-"*40 + "\n"
                else:
                    parts.append(account_header + "\n   💰 Только денежные средства\n" + "   " + "-"*40 + "\n")
                continue
            
            # Добавляем заголовок счета
            if len(parts[-1] + account_header) < 4000:
                parts[-1] += account_header + "\n   📊 ВСЕ ПОЗИЦИИ:\n"
            else:
                parts.append(account_header + "\n   📊 ВСЕ ПОЗИЦИИ:\n")
            
            # Добавляем ВСЕ позиции этого счета
            for pos_idx, pos in enumerate(positions, 1):
                pos_weight = (pos['value'] / account_value * 100) if account_value > 0 else 0
                
                position_text = f"""
   {pos_idx:2d}. {pos['name']} ({pos['ticker']})
       Тип: {pos['instrument_type']}
       Кол-во: {pos['quantity']:,} шт. × {pos['current_price']:,.2f} ₽
       Текущая стоимость: {pos['value']:,.2f} ₽ ({pos_weight:.1f}%)
       Средняя цена: {pos['average_price']:,.2f} ₽
       Сумма вложений: {pos['invested_value']:,.2f} ₽"""
                
                if pos['real_yield'] != 0:
                    position_text += f"""
       Доходность: {pos['real_yield']:+,.2f} ₽ ({pos['yield_percentage']:+.2f}%)"""
                
                # Проверяем, помещается ли позиция в текущую часть
                if len(parts[-1] + position_text) < 4000:
                    parts[-1] += position_text
                else:
                    # Если не помещается, создаем новую часть
                    parts.append(position_text)
            
            # Добавляем разделитель после счета
            if len(parts[-1] + "\n   " + "-"*40 + "\n") < 4000:
                parts[-1] += "\n   " + "-"*40 + "\n"
            else:
                parts.append("\n   " + "-"*40 + "\n")
        
        # Финальная сводка
        final_summary = f"""
💎 ИТОГОВАЯ СВОДКА:

   • Общая стоимость: {total_value:,.2f} ₽
   • Сумма вложений: {total_invested:,.2f} ₽
   • Совокупный доход: {total_yield:+,.2f} ₽ ({total_yield_percentage:+.2f}%)
   • Денежные средства: {total_cash:,.2f} ₽
   • Всего счетов: {len(accounts)}
   • Всего позиций: {total_positions_count}

📊 Отчет содержит полный список всех позиций без сокращений.
"""
        
        # Добавляем финальную сводку в последнюю часть
        if len(parts[-1] + final_summary) < 4000:
            parts[-1] += final_summary
        else:
            parts.append(final_summary)
        
        return parts

    async def handle_account_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle account selection callbacks and save to DB"""
        query = update.callback_query
        await query.answer()
        
        data = query.data
        user_id = query.from_user.id
        
        try:
            if data.startswith("select_acc_"):
                account_id = data.replace("select_acc_", "")
                
                # Сохраняем счет в базу данных!
                db.save_user_data(user_id, selected_account=account_id)
                
                # Создаем кнопку для возврата в настройки
                keyboard = [[InlineKeyboardButton("⚙️ Вернуться в настройки", callback_data="back_to_settings")]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await query.edit_message_text(
                    "✅ <b>Счет успешно выбран!</b>\n\nТеперь я буду анализировать и присылать отчеты именно по этому счету.", 
                    reply_markup=reply_markup,
                    parse_mode="HTML"
                )
                return
            
        except Exception as e:
            logger.error(f"Error in account selection: {e}")
            await query.edit_message_text("❌ Произошла ошибка при выборе счета")

    async def _execute_auto_trade_from_callback(self, query, account_selector, mode_name):
        """Execute auto trade from callback selection"""
        try:
            if not self.ai_manager:
                await query.edit_message_text(
                    "❌ AI сервис недоступен\n\n"
                    "Проверьте настройки API ключей:\n"
                    "• DEEPSEEK_API_KEY\n"
                    "• OPENROUTER_API_KEY"
                )
                return
            
            account_text = "выбранным счетом" if mode_name == "selected" else "всеми счетами"
            
            # Update message to show progress
            await query.edit_message_text(
                f"🤖 ЗАПУСК AI УПРАВЛЕНИЯ {account_text.upper()}\n\n"
                "⚡ Анализирую текущий портфель...\n"
                "📊 Оцениваю рыночные условия...\n"
                "🎯 Генерирую стратегию для максимальной доходности..."
            )
            
            # Get portfolio data for specific account(s)
            if account_selector == "all":
                portfolio_data = await self._get_all_accounts_portfolio_data()
            else:
                portfolio_data = await self._get_single_account_portfolio_data(account_selector)
            
            if not portfolio_data:
                await query.edit_message_text("❌ Не удалось получить данные портфеля")
                return
            
            # Generate AI strategy
            strategy = await self.ai_manager.generate_portfolio_strategy(portfolio_data)
            
            if not strategy:
                await query.edit_message_text("❌ Не удалось сгенерировать стратегию")
                return
            
            # Display strategy with commission calculations
            strategy_text = self._format_strategy_response(strategy, account_selector)
            
            # Split long messages if needed
            if len(strategy_text) > 4000:
                parts = [strategy_text[i:i+4000] for i in range(0, len(strategy_text), 4000)]
                for i, part in enumerate(parts):
                    if i == 0:
                        await query.edit_message_text(part)
                    else:
                        await query.message.reply_text(part)
            else:
                await query.edit_message_text(strategy_text)
            
            # Handle trading actions based on mode
            if strategy.get('actions'):
                if settings.AUTO_TRADING_MODE:
                    # Fully automated mode - execute immediately
                    await self._execute_automated_actions_from_callback(query, strategy['actions'], account_selector)
                else:
                    # Manual mode - request confirmation
                    await self._request_action_confirmation_from_callback(query, strategy['actions'], query.from_user.id, account_selector)
            
        except Exception as e:
            logger.error(f"Auto trade error in callback: {e}")
            await query.edit_message_text(f"❌ Ошибка AI управления: {str(e)}")

    async def _execute_automated_actions_from_callback(self, query, actions: List[Dict], account_selector: str):
        """Execute actions in fully automated mode from callback"""
        executed_actions = []
        failed_actions = []
        total_commission_paid = 0
        
        for action in actions:
            try:
                if action['urgency'] == 'high':  # Execute only high urgency in auto mode
                    result = await self._execute_trading_action(action, account_selector)
                    if result['success']:
                        executed_actions.append(action)
                        # Calculate commission for reporting
                        current_price = self._get_typical_price(action['ticker'])
                        commission = self._calculate_commission(action['action'], action['quantity'], current_price)
                        total_commission_paid += commission
                    else:
                        failed_actions.append(action)
            except Exception as e:
                logger.error(f"Action execution failed: {e}")
                failed_actions.append(action)
        
        account_text = "выбранным счетом" if account_selector != "all" else "всеми счетами"
        
        # Send execution report with commission info
        report = f"🤖 АВТОМАТИЧЕСКОЕ ИСПОЛНЕНИЕ ({account_text.upper()}) ЗАВЕРШЕНО:\n\n"
        report += f"✅ Успешно: {len(executed_actions)}\n"
        report += f"❌ Ошибки: {len(failed_actions)}\n"
        report += f"💰 Уплачено комиссий: {total_commission_paid:,.1f} руб.\n"
        
        if executed_actions:
            report += "\nИсполненные действия:\n"
            for action in executed_actions:
                report += f"• {action['action']} {action['ticker']} ({action['quantity']} шт.)\n"
        
        await query.message.reply_text(report)

    async def _request_action_confirmation_from_callback(self, query, actions: List[Dict], user_id: int, account_selector: str):
        """Request confirmation for trading actions from callback"""
        self.pending_actions[user_id] = actions
        
        # Calculate commissions for each action
        actions_with_commissions = []
        total_commission = 0
        
        for action in actions:
            current_price = self._get_typical_price(action['ticker'])
            cost_calc = self._calculate_total_cost(action, current_price)
            actions_with_commissions.append({
                **action,
                'cost_calculation': cost_calc
            })
            total_commission += cost_calc['commission']
        
        self.pending_actions[user_id] = actions_with_commissions
        
        account_text = "выбранным счетом" if account_selector != "all" else "всеми счетами"
        
        keyboard = []
        for i, action in enumerate(actions_with_commissions):
            btn_text = f"{action['action']} {action['ticker']} ({action['quantity']} шт.) - {action['cost_calculation']['total_cost']:,.0f} руб."
            keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"confirm_{i}")])
        
        keyboard.append([InlineKeyboardButton("✅ ПОДТВЕРДИТЬ ВСЕ", callback_data="confirm_all")])
        keyboard.append([InlineKeyboardButton("❌ ОТМЕНИТЬ ВСЕ", callback_data="cancel_all")])
        keyboard.append([InlineKeyboardButton("💰 ДЕТАЛИ КОМИССИЙ", callback_data="show_commissions")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        commission_info = f"\n💰 Общая сумма комиссий: {total_commission:,.1f} руб."
        
        await query.message.reply_text(
            f"🤖 ТРЕБУЕТСЯ ПОДТВЕРЖДЕНИЕ ДЕЙСТВИЙ ({account_text.upper()}):\n\n"
            "Выберите действия для исполнения:" + commission_info,
            reply_markup=reply_markup
        )

    async def health_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /health command"""
        user = update.effective_user
        logger.info(f"HEALTH from {user.first_name}")
        
        try:
            await update.message.reply_text("🔍 Проверяю статус системы...")
            
            health_monitor = HealthMonitor(self.client_manager, self)
            report = await health_monitor.perform_health_check()
            
            await update.message.reply_text(report)
            
        except Exception as e:
            logger.error(f"Health error: {e}")
            await update.message.reply_text(f"❌ Ошибка проверки здоровья: {str(e)}")

    async def commission_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /commission command - автоматическое определение тарифа"""
        user = update.effective_user
        logger.info(f"COMMISSION from {user.first_name}")
        
        try:
            # Get tariff info automatically
            tariff_info = self.tariff_manager.get_tariff_info()
            commission_rates = tariff_info['commission_rates']
            
            current_commission_info = f"""
💰 АВТОМАТИЧЕСКИ ОПРЕДЕЛЕННЫЙ ТАРИФ:

🎯 **Тариф**: {tariff_info['name']}
📝 **Описание**: {commission_rates['description']}

💸 **КОМИССИИ**:
📥 Покупка: {commission_rates['buy']}%
📤 Продажа: {commission_rates['sell']}%
💰 Минимальная комиссия: {commission_rates.get('min_commission', 0.0)} руб.

📅 **ЕЖЕМЕСЯЧНОЕ ОБСЛУЖИВАНИЕ**: {tariff_info['monthly_fee']} руб.

🎁 **ОСОБЕННОСТИ ТАРИФА**:
"""
            
            for feature in tariff_info['features']:
                current_commission_info += f"• {feature}\n"
            
            current_commission_info += """
💡 *Информация получена автоматически от брокера*
🔄 Для обновления данных используйте команду снова
            """
            
            await update.message.reply_text(current_commission_info)
            
        except Exception as e:
            logger.error(f"Commission error: {e}")
            await update.message.reply_text(f"❌ Ошибка получения информации о тарифе: {str(e)}")

    async def auto_trade_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /auto_trade with selected account"""
        user = update.effective_user
        logger.info(f"AUTO_TRADE from {user.first_name}")
        
        user_id = str(user.id)
        selected_account = self.selected_accounts.get(user_id)
        
        logger.info(f"User {user_id} selected account: {selected_account}")
        
        if not selected_account:
            await update.message.reply_text(
                "❌ Счет не выбран!\n\n"
                "Используйте команду /accounts чтобы выбрать счет для управления."
            )
            return
        
        await self._execute_auto_trade(update, selected_account, "selected")

    async def auto_trade_all_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /auto_trade_all with all accounts"""
        user = update.effective_user
        logger.info(f"AUTO_TRADE_ALL from {user.first_name}")
        
        await self._execute_auto_trade(update, "all", "all")

    async def _execute_auto_trade(self, update: Update, account_selector, mode_name):
        """Execute auto trade for specific account(s)"""
        try:
            if not self.ai_manager:
                await update.message.reply_text(
                    "❌ AI сервис недоступен\n\n"
                    "Проверьте настройки API ключей:\n"
                    "• DEEPSEEK_API_KEY\n"
                    "• OPENROUTER_API_KEY"
                )
                return
            
            account_text = "выбранным счетом" if mode_name == "selected" else "всеми счетами"
            
            await update.message.reply_text(
                f"🤖 ЗАПУСК AI УПРАВЛЕНИЯ {account_text.upper()}\n\n"
                "⚡ Анализирую текущий портфель...\n"
                "📊 Оцениваю рыночные условия...\n"
                "🎯 Генерирую стратегию для максимальной доходности..."
            )
            
            # Get portfolio data for specific account(s)
            if account_selector == "all":
                portfolio_data = await self._get_all_accounts_portfolio_data()
            else:
                portfolio_data = await self._get_single_account_portfolio_data(account_selector)
            
            if not portfolio_data:
                await update.message.reply_text("❌ Не удалось получить данные портфеля")
                return
            
            # Generate AI strategy
            strategy = await self.ai_manager.generate_portfolio_strategy(portfolio_data)
            
            if not strategy:
                await update.message.reply_text("❌ Не удалось сгенерировать стратегию")
                return
            
            # Display strategy with commission calculations
            strategy_text = self._format_strategy_response(strategy, account_selector)
            await update.message.reply_text(strategy_text)
            
            # Handle trading actions based on mode
            if strategy.get('actions'):
                if settings.AUTO_TRADING_MODE:
                    # Fully automated mode - execute immediately
                    await self._execute_automated_actions(update, strategy['actions'], account_selector)
                else:
                    # Manual mode - request confirmation
                    await self._request_action_confirmation(update, strategy['actions'], user.id, account_selector)
            
        except Exception as e:
            logger.error(f"Auto trade error: {e}")
            await update.message.reply_text(f"❌ Ошибка AI управления: {str(e)}")

    async def _get_single_account_portfolio_data(self, account_id):
        """Get portfolio data for specific account only"""
        try:
            def get_accounts_operation(client):
                return client.users.get_accounts()
            
            accounts_response = await self._execute_tinkoff_operation(get_accounts_operation)
                
            if not accounts_response or not accounts_response.accounts:
                logger.error("No accounts found")
                return None
            
            # Find the specific account
            target_account = None
            for account in accounts_response.accounts:
                if account.id == account_id:
                    target_account = account
                    break
            
            if not target_account:
                logger.error(f"Account {account_id} not found")
                return None
            
            account_name = getattr(target_account, 'name', f'Счет {account_id[-4:]}')
            account_type = getattr(target_account, 'type', 'Неизвестно')
            account_status = getattr(target_account, 'status', 'Неизвестно')
            
            logger.info(f"Processing account: {account_name} ({account_id})")
            
            # Get portfolio data for this account
            account_data = await self._get_account_portfolio_data(account_id)
            if not account_data:
                return None
            
            account_data['account_name'] = account_name
            account_data['account_type'] = account_type
            account_data['account_status'] = account_status
            
            return {
                'accounts': [account_data],
                'total_portfolio_value': account_data['total_value'],
                'total_invested': account_data['total_invested'],
                'total_cash': account_data['available_cash'],
                'total_real_yield': account_data['total_real_yield'],
                'total_yield_percentage': account_data['total_yield_percentage'],
                'account_count': 1,
                'is_real_data': self._is_real_tinkoff_client(),
                'is_sandbox': settings.TINKOFF_SANDBOX_MODE,
                'selected_account_id': account_id
            }
            
        except Exception as e:
            logger.error(f"Single account portfolio data error: {e}")
            return None

    def _format_strategy_response(self, strategy: Dict, account_selector: str) -> str:
        """Format AI strategy for display with account info"""
        # Get tariff info for display
        tariff_info = self.tariff_manager.get_tariff_info()
        
        account_text = "выбранным счетом" if account_selector != "all" else "всеми счетами"
        
        text = f"🎯 **AI СТРАТЕГИЯ УПРАВЛЕНИЯ ({account_text.upper()})**: {strategy['strategy_name']}\n\n"
        text += f"📈 **Целевая доходность**: {strategy['target_return']}%\n"
        text += f"⚡ **Уровень риска**: {strategy['risk_level']}\n"
        text += f"⏱️ **Горизонт**: {strategy['time_horizon']}\n\n"
        
        text += "**РЕКОМЕНДУЕМЫЕ ДЕЙСТВИЯ**:\n"
        
        total_commission = 0
        total_trade_volume = 0
        
        for action in strategy.get('actions', []):
            # Get current price for commission calculation
            current_price = action.get('current_price', 0)
            if current_price == 0:
                current_price = self._get_typical_price(action['ticker'])
            
            cost_calculation = self._calculate_total_cost(action, current_price)
            
            text += f"• {action['action']} {action['ticker']} ({action['quantity']} шт.)\n"
            text += f"  💰 Стоимость: {cost_calculation['base_cost']:,.0f} руб.\n"
            text += f"  📊 Комиссия: {cost_calculation['commission']:,.1f} руб. ({cost_calculation['commission_percent']:.2f}%)\n"
            
            if action['action'].upper() == 'BUY':
                text += f"  💸 ИТОГО к оплате: {cost_calculation['total_cost']:,.0f} руб.\n"
            else:  # SELL
                text += f"  💸 ИТОГО к получению: {cost_calculation['total_cost']:,.0f} руб.\n"
                
            text += f"  📝 Причина: {action['reason']}\n"
            text += f"  🎯 Эффект: {action['expected_impact']} ({action['urgency']})\n\n"
            
            total_commission += cost_calculation['commission']
            total_trade_volume += cost_calculation['base_cost']
        
        # Add commission summary
        text += f"**📊 СВОДКА ПО КОМИССИЯМ**:\n"
        text += f"• Общий объем сделок: {total_trade_volume:,.0f} руб.\n"
        text += f"• Сумма комиссий: {total_commission:,.1f} руб.\n"
        text += f"• Средняя комиссия: {(total_commission/total_trade_volume*100) if total_trade_volume > 0 else 0:.2f}%\n\n"
        
        allocation = strategy.get('portfolio_optimization', {}).get('target_allocation', {})
        text += f"**ЦЕЛЕВОЕ РАСПРЕДЕЛЕНИЕ**:\n"
        text += f"• Акции: {allocation.get('stocks', 0)}%\n"
        text += f"• Облигации: {allocation.get('bonds', 0)}%\n"
        text += f"• Денежные средства: {allocation.get('cash', 0)}%\n\n"
        
        if settings.AUTO_TRADING_MODE:
            text += "🤖 **РЕЖИМ**: ПОЛНОСТЬЮ АВТОМАТИЧЕСКИЙ\n"
        else:
            text += "👤 **РЕЖИМ**: С РУЧНЫМ ПОДТВЕРЖДЕНИЕМ\n"
        
        # Add tariff info
        text += f"\n💰 **АКТУАЛЬНЫЙ ТАРИФ**: {tariff_info['name']}\n"
        text += f"📈 Комиссии: покупка {tariff_info['commission_rates']['buy']}%, продажа {tariff_info['commission_rates']['sell']}%\n"
        text += "💡 Используйте /commission для детальной информации"
        
        return text

    async def _execute_automated_actions(self, update: Update, actions: List[Dict], account_selector: str):
        """Execute actions in fully automated mode for specific account"""
        executed_actions = []
        failed_actions = []
        total_commission_paid = 0
        
        for action in actions:
            try:
                if action['urgency'] == 'high':  # Execute only high urgency in auto mode
                    result = await self._execute_trading_action(action, account_selector)
                    if result['success']:
                        executed_actions.append(action)
                        # Calculate commission for reporting
                        current_price = self._get_typical_price(action['ticker'])
                        commission = self._calculate_commission(action['action'], action['quantity'], current_price)
                        total_commission_paid += commission
                    else:
                        failed_actions.append(action)
            except Exception as e:
                logger.error(f"Action execution failed: {e}")
                failed_actions.append(action)
        
        account_text = "выбранным счетом" if account_selector != "all" else "всеми счетами"
        
        # Send execution report with commission info
        report = f"🤖 АВТОМАТИЧЕСКОЕ ИСПОЛНЕНИЕ ({account_text.upper()}) ЗАВЕРШЕНО:\n\n"
        report += f"✅ Успешно: {len(executed_actions)}\n"
        report += f"❌ Ошибки: {len(failed_actions)}\n"
        report += f"💰 Уплачено комиссий: {total_commission_paid:,.1f} руб.\n"
        
        if executed_actions:
            report += "\nИсполненные действия:\n"
            for action in executed_actions:
                report += f"• {action['action']} {action['ticker']} ({action['quantity']} шт.)\n"
        
        await update.message.reply_text(report)

    async def _request_action_confirmation(self, update: Update, actions: List[Dict], user_id: int, account_selector: str):
        """Request confirmation for trading actions with commission details"""
        self.pending_actions[user_id] = actions
        
        # Calculate commissions for each action
        actions_with_commissions = []
        total_commission = 0
        
        for action in actions:
            current_price = self._get_typical_price(action['ticker'])
            cost_calc = self._calculate_total_cost(action, current_price)
            actions_with_commissions.append({
                **action,
                'cost_calculation': cost_calc
            })
            total_commission += cost_calc['commission']
        
        self.pending_actions[user_id] = actions_with_commissions
        
        account_text = "выбранным счетом" if account_selector != "all" else "всеми счетами"
        
        keyboard = []
        for i, action in enumerate(actions_with_commissions):
            btn_text = f"{action['action']} {action['ticker']} ({action['quantity']} шт.) - {action['cost_calculation']['total_cost']:,.0f} руб."
            keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"confirm_{i}")])
        
        keyboard.append([InlineKeyboardButton("✅ ПОДТВЕРДИТЬ ВСЕ", callback_data="confirm_all")])
        keyboard.append([InlineKeyboardButton("❌ ОТМЕНИТЬ ВСЕ", callback_data="cancel_all")])
        keyboard.append([InlineKeyboardButton("💰 ДЕТАЛИ КОМИССИЙ", callback_data="show_commissions")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        commission_info = f"\n💰 Общая сумма комиссий: {total_commission:,.1f} руб."
        
        await update.message.reply_text(
            f"🤖 ТРЕБУЕТСЯ ПОДТВЕРЖДЕНИЕ ДЕЙСТВИЙ ({account_text.upper()}):\n\n"
            "Выберите действия для исполнения:" + commission_info,
            reply_markup=reply_markup
        )

    async def handle_confirmation_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle confirmation callbacks with commission details"""
        query = update.callback_query
        await query.answer()
        
        user_id = query.from_user.id
        actions = self.pending_actions.get(user_id, [])
        
        if not actions:
            await query.edit_message_text("❌ Действия не найдены или устарели")
            return
        
        if query.data == "show_commissions":
            # Show detailed commission breakdown
            commission_details = "💰 **ДЕТАЛЬНЫЙ РАСЧЕТ КОМИССИЙ**:\n\n"
            total_commission = 0
            total_volume = 0
            
            for i, action in enumerate(actions, 1):
                cost_calc = action['cost_calculation']
                commission_details += f"{i}. {action['action']} {action['ticker']}:\n"
                commission_details += f"   • Сумма: {cost_calc['base_cost']:,.0f} руб.\n"
                commission_details += f"   • Комиссия: {cost_calc['commission']:,.1f} руб. ({cost_calc['commission_percent']:.2f}%)\n"
                commission_details += f"   • Итого: {cost_calc['total_cost']:,.0f} руб.\n\n"
                
                total_commission += cost_calc['commission']
                total_volume += cost_calc['base_cost']
            
            commission_details += f"**ОБЩАЯ СВОДКА**:\n"
            commission_details += f"• Объем сделок: {total_volume:,.0f} руб.\n"
            commission_details += f"• Сумма комиссий: {total_commission:,.1f} руб.\n"
            commission_details += f"• Средняя комиссия: {(total_commission/total_volume*100) if total_volume > 0 else 0:.2f}%\n"
            
            await query.edit_message_text(commission_details)
            return
        
        if query.data == "confirm_all":
            # Execute all actions with commission tracking
            executed = []
            total_commission_paid = 0
            
            for action in actions:
                result = await self._execute_trading_action(action, "all")  # Use all for simplicity
                if result['success']:
                    executed.append(action)
                    # Add commission to result
                    current_price = self._get_typical_price(action['ticker'])
                    commission = self._calculate_commission(action['action'], action['quantity'], current_price)
                    total_commission_paid += commission
            
            report = f"✅ Исполнено {len(executed)} из {len(actions)} действий\n"
            report += f"💰 Уплачено комиссий: {total_commission_paid:,.1f} руб."
            
            await query.edit_message_text(report)
            
        elif query.data == "cancel_all":
            await query.edit_message_text("❌ Все действия отменены")
            
        elif query.data.startswith("confirm_"):
            action_index = int(query.data.split("_")[1])
            if 0 <= action_index < len(actions):
                action = actions[action_index]
                result = await self._execute_trading_action(action, "all")  # Use all for simplicity
                
                if result['success']:
                    # Calculate commission for this action
                    current_price = self._get_typical_price(action['ticker'])
                    commission = self._calculate_commission(action['action'], action['quantity'], current_price)
                    
                    report = f"✅ Действие исполнено: {action['action']} {action['ticker']}\n"
                    report += f"💰 Комиссия: {commission:,.1f} руб."
                    await query.edit_message_text(report)
                else:
                    await query.edit_message_text(f"❌ Ошибка исполнения: {action['action']} {action['ticker']}")
        
        # Clean up
        if user_id in self.pending_actions:
            del self.pending_actions[user_id]

    def _calculate_commission(self, action_type: str, quantity: int, price: float) -> float:
        """Calculate broker commission for trade using automatic tariff detection"""
        # Get commission rates from tariff manager
        commission_rate = self.tariff_manager.get_commission_rate(action_type.lower())
        min_commission = self.tariff_manager.get_min_commission()
        
        trade_amount = quantity * price
        commission = trade_amount * (commission_rate / 100)
        
        # Apply minimum commission
        return max(commission, min_commission)

    def _calculate_total_cost(self, action: Dict, current_price: float) -> Dict:
        """Calculate total cost including commission"""
        quantity = action['quantity']
        action_type = action['action']
        
        # Calculate base cost
        base_cost = quantity * current_price
        
        # Calculate commission
        commission = self._calculate_commission(action_type, quantity, current_price)
        
        # Calculate total cost
        if action_type.upper() == 'BUY':
            total_cost = base_cost + commission
            net_cost = base_cost
        else:  # SELL
            total_cost = base_cost - commission
            net_cost = base_cost
        
        return {
            'base_cost': base_cost,
            'commission': commission,
            'total_cost': total_cost,
            'net_cost': net_cost,
            'commission_percent': (commission / base_cost * 100) if base_cost > 0 else 0
        }

    def _get_typical_price(self, ticker: str) -> float:
        """Get typical price for ticker for commission calculation"""
        typical_prices = {
            'SBER': 300.0, 'GAZP': 160.0, 'LKOH': 760.0, 'ROSN': 580.0,
            'YNDX': 3500.0, 'TCSG': 3500.0, 'VTBR': 0.028, 'GMKN': 16000.0,
            'NVTK': 1700.0, 'POLY': 1200.0, 'MTSS': 270.0, 'MGNT': 5500.0,
            'AFKS': 0.15, 'RTKM': 70.0, 'HYDR': 0.80, 'FEES': 0.20,
            'TRNFP': 170000.0, 'MOEX': 150.0, 'OZON': 2300.0, 'PHOR': 5000.0
        }
        return typical_prices.get(ticker.upper(), 100.0)  # Default 100 rub if unknown

    async def _execute_trading_action(self, action: Dict, account_selector: str) -> Dict:
        """Execute a single trading action for specific account"""
        try:
            # Get FIGI from ticker
            figi = await self._get_figi_by_ticker(action['ticker'])
            if not figi:
                return {'success': False, 'error': 'FIGI not found'}
            
            # Execute via Tinkoff API
            def execute_order(client):
                from t_tech.invest import OrderDirection, OrderType
                
                direction = (OrderDirection.ORDER_DIRECTION_BUY 
                           if action['action'] == 'BUY' 
                           else OrderDirection.ORDER_DIRECTION_SELL)
                
                # Get account ID based on selector
                accounts = client.users.get_accounts()
                if not accounts.accounts:
                    raise ValueError("No accounts found")
                
                if account_selector == "all":
                    # Use first account for all mode (simplified)
                    account_id = accounts.accounts[0].id
                else:
                    # Find specific account
                    account_id = account_selector
                    account_found = False
                    for account in accounts.accounts:
                        if account.id == account_id:
                            account_found = True
                            break
                    
                    if not account_found:
                        raise ValueError(f"Account {account_id} not found")
                
                # Execute market order
                order = client.orders.post_order(
                    figi=figi,
                    quantity=action['quantity'],
                    direction=direction,
                    account_id=account_id,
                    order_type=OrderType.ORDER_TYPE_MARKET
                )
                
                return order
            
            result = await self._execute_tinkoff_operation(execute_order)
            return {'success': True, 'order_id': result.order_id}
            
        except Exception as e:
            logger.error(f"Trading action execution failed: {e}")
            return {'success': False, 'error': str(e)}

    async def _get_figi_by_ticker(self, ticker: str) -> str:
        """Get FIGI by ticker symbol"""
        # Simplified implementation - in real app, use Tinkoff instruments service
        figi_map = {
            'SBER': 'BBG004730N88',
            'GAZP': 'BBG004730RP0',
            'YNDX': 'BBG006L8G4H1',
            'VTBR': 'BBG004730ZJ9',
            'LKOH': 'BBG004731032',
            'ROSN': 'BBG004731354',
            'TCSG': 'BBG00QPYJ5H0'
        }
        return figi_map.get(ticker.upper(), '')

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command"""
        trading_mode = "🤖 ПОЛНОСТЬЮ АВТОМАТИЧЕСКИЙ" if settings.AUTO_TRADING_MODE else "👤 С РУЧНЫМ ПОДТВЕРЖДЕНИЕМ"
        
        help_text = f"""
📋 ПОМОЩЬ ПО КОМАНДАМ

🎯 **КОМАНДЫ УПРАВЛЕНИЯ ПОРТФЕЛЕМ**:
/auto_trade - AI управление выбранным счетом
/auto_trade_all - AI управление всеми счетами
/accounts - Выбор счета для управления (автоматически запускает AI)

📊 **ОСНОВНЫЕ КОМАНДЫ**:
/portfolio - Анализ портфеля (ВСЕ СЧЕТА, ВСЕ ПОЗИЦИИ)
/health - Статус системы
/commission - Информация о тарифе и комиссиях
/help - Эта справка

🔧 **РЕЖИМЫ РАБОТЫ**:
• REAL MODE - TINKOFF_TOKEN
• SANDBOX MODE - TINKOFF_TOKEN_SANDBOX

🤖 **AI УПРАВЛЕНИЕ**:
• DeepSeek API + OpenRouter API
• Максимизация доходности портфеля
• Автоматическая оптимизация распределения
• Учет брокерских комиссий в расчетах

💰 **АВТОМАТИЧЕСКОЕ ОПРЕДЕЛЕНИЕ ТАРИФА**:
• Инвестор: комиссия 0.3%, бесплатное обслуживание
• Трейдер: комиссия 0.04%, обслуживание 390 руб./мес
• Определяется автоматически от брокера

🎯 **РЕЖИМ ТОРГОВЛИ**: {trading_mode}

💡 Настройте соответствующие токены в .env файле!
        """
        
        await update.message.reply_text(help_text)

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle text messages with AI"""
        user_message = update.message.text
        user = update.effective_user
        
        logger.info(f"MESSAGE from {user.first_name}: {user_message}")
        
        if not self.ai_manager:
            await update.message.reply_text(
                "🤖 Используйте команды:\n"
                "/portfolio - анализ портфеля\n" 
                "/accounts - список счетов\n"
                "/health - статус системы\n"
                "/auto_trade - AI управление портфелем\n"
                "/commission - информация о тарифе"
            )
            return
        
        try:
            # Get portfolio context for AI from all accounts
            portfolio_context = ""
            portfolio_data = await self._get_all_accounts_portfolio_data()
            if portfolio_data:
                mode, token_info = self._get_operation_mode_info()
                portfolio_context = f"Портфель пользователя ({mode}): {portfolio_data['total_portfolio_value']:,.0f} RUB, {portfolio_data['account_count']} счетов, {sum(acc['positions_count'] for acc in portfolio_data['accounts'])} позиций"
            
            response = await self.ai_manager.generate_response(user_message, portfolio_context)
            await update.message.reply_text(response)
            
        except Exception as e:
            logger.error(f"AI message error: {e}")
            await update.message.reply_text("❌ Ошибка обработки сообщения")

    def setup_handlers(self):
        """Setup command handlers with account selection"""
        # Настройка пошагового диалога (Onboarding + Смена токена)
        conv_handler = ConversationHandler(
            entry_points=[
                CommandHandler("start", self.start_command),
                CallbackQueryHandler(self.change_token_start, pattern="^change_token$")
            ],
            states={
                "ASK_TOKEN": [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.ask_token),
                    CallbackQueryHandler(self.ask_token, pattern="^skip_token$")
                ],
            },
            fallbacks=[CommandHandler("start", self.start_command)]
        )
        self.application.add_handler(conv_handler)
        
        # --- Обработчики для кнопок главного меню ---
        self.application.add_handler(
            MessageHandler(filters.Regex("^💼 Портфель$"), self.portfolio_command)
        )
        self.application.add_handler(
            MessageHandler(filters.Regex("^📰 Новости$"), self.manual_digest)
        )
        self.application.add_handler(
            MessageHandler(filters.Regex("^⚙️ Настройки$"), self.show_settings)
        )
        self.application.add_handler(
            MessageHandler(filters.Regex("^💵 Выплаты$"), self.show_dividends)
        )
        self.application.add_handler(
            MessageHandler(filters.Regex("^⚡ Анализ ИИ$"), self.analyze_ai_command)
        )
        
        # --- Обработчики для настроек (инлайн-кнопки) ---
        self.application.add_handler(CallbackQueryHandler(self.show_timezone_menu, pattern="^set_timezone$"))
        self.application.add_handler(CallbackQueryHandler(self.show_digest_time_menu, pattern="^set_digest_time$"))
        
        self.application.add_handler(CallbackQueryHandler(self.choose_account_start, pattern="^choose_account$"))
        self.application.add_handler(CallbackQueryHandler(self.back_to_settings, pattern="^back_to_settings$"))
        self.application.add_handler(CallbackQueryHandler(self.close_settings, pattern="^close_settings$"))
        self.application.add_handler(CallbackQueryHandler(self.save_timezone, pattern="^tz_"))
        self.application.add_handler(CallbackQueryHandler(self.save_digest_time, pattern="^dt_"))
        # --- НОВЫЕ обработчики для мультивыбора ---
        self.application.add_handler(CallbackQueryHandler(self.toggle_account_selection, pattern="^toggle_acc_"))
        self.application.add_handler(CallbackQueryHandler(self.save_accounts_selection, pattern="^save_accounts$"))
        # -------------------------------------------
        
        self.application.add_handler(CallbackQueryHandler(self.handle_account_selection, pattern="^select_acc_"))
        # Этот обработчик должен быть САМЫМ ПОСЛЕДНИМ (он ловит весь остальной текст)
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
        
    async def show_settings(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик кнопки 'Настройки'"""
        await update.message.reply_text(
            "⚙️ **Настройки бота**\n\nВыберите, что хотите изменить:",
            reply_markup=get_settings_menu(),
            parse_mode="Markdown"
        )
    async def change_token_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка кнопки изменения токена в настройках"""
        query = update.callback_query
        await query.answer()
        await query.edit_message_text("Отправьте мне новый API-ключ от Т-Инвестиций (с правами «Только для чтения»).")
        # Возвращаемся к шагу ожидания токена
        return "ASK_TOKEN"
        
    async def show_dividends(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик кнопки 'Выплаты' - дивиденды и купоны"""
        user = update.effective_user
        user_data = db.get_user(user.id)
        token = user_data.get('tinkoff_token') if user_data else None

        if not token:
            await update.message.reply_text("❌ Не подключен API-ключ.\nНажмите ⚙️ Настройки.")
            return

        await update.message.reply_text("⏳ Собираю информацию о ближайших выплатах...")

        try:
            from datetime import datetime, timedelta
            from t_tech.invest import InstrumentType

            with Client(token) as client:
                accounts_resp = client.users.get_accounts()
                all_ids = [a.id for a in accounts_resp.accounts if a.status == AccountStatus.ACCOUNT_STATUS_OPEN]

            selection = self._parse_selection(user_data.get('selected_account'))
            target_ids = all_ids if selection == "all" else [i for i in selection if i in all_ids]
            if not target_ids:
                target_ids = all_ids

            # Собираем позиции
            data = await self._get_portfolio_for_accounts(token, target_ids)
            if not data:
                await update.message.reply_text("❌ Не удалось загрузить портфель.")
                return

            tickers = set()
            figis = set()
            for acc in data['accounts']:
                for pos in acc['positions']:
                    tickers.add(pos['ticker'])
                    # Для точного поиска дивидендов нужен FIGI, но мы его не сохраняли в data.
                    # Упростим задачу: запросим дивиденды по всем акциям счета.

            now = datetime.now()
            future_limit = now + timedelta(days=30) # Ищем выплаты на месяц вперед
            dividends_text = ""
            coupons_text = ""
            
            total_div = 0
            total_cou = 0

            with Client(token) as client:
                for acc_id in target_ids:
                    # Получаем дивиденды
                    try:
                        divs = client.operations.get_dividends(account_id=acc_id)
                        for div in divs.dividends:
                            div_date = div.dividend_net_date if hasattr(div, 'dividend_net_date') else div.payment_date
                            if now <= div_date.replace(tzinfo=None) <= future_limit:
                                name = getattr(div, 'ticker', 'Акция')
                                amount = div.dividend_net.units + div.dividend_net.nano / 1e9
                                dividends_text += f"• {name}: {amount:,.2f} ₽ (до {div_date.strftime('%d.%m')})\n"
                                total_div += amount
                    except Exception as e:
                        pass # Нет дивидендов или ошибка

                    # Получаем купоны
                    try:
                        coups = client.operations.get_coupons(account_id=acc_id)
                        for coup in coups.events:
                            coup_date = coup.coupon_date
                            if now <= coup_date.replace(tzinfo=None) <= future_limit:
                                name = getattr(coup, 'figi', 'Облигация')[:4]
                                amount = coup.pay_one_bond.units + coup.pay_one_bond.nano / 1e9
                                coupons_text += f"• {name}...: {amount:,.2f} ₽ (до {coup_date.strftime('%d.%m')})\n"
                                total_cou += amount
                    except Exception as e:
                        pass

            if not dividends_text and not coupons_text:
                await update.message.reply_text("📭 В ближайшие 30 дней выплат по вашему портфелю не ожидается.")
                return

            response = "💵 <b>Ближайшие выплаты (30 дней)</b>\n\n"
            
            if dividends_text:
                response += f"📈 <b>Дивиденды:</b>\n{dividends_text}\n"
            if coupons_text:
                response += f"🏛 <b>Купоны:</b>\n{coupons_text}\n"
                
            response += f"💰 <b>Итого ожидается: {total_div + total_cou:,.2f} ₽</b>"

            await update.message.reply_text(response, parse_mode="HTML")

        except Exception as e:
            logger.error(f"Dividends error: {e}")
            await update.message.reply_text("❌ Ошибка при загрузке данных о выплатах.")
        
    async def ask_token(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.callback_query:
            await update.callback_query.answer()
            await update.callback_query.edit_message_text("Хорошо, пропускаем подключение портфеля.")
            token = None
            message = update.callback_query.message
        else:
            token = update.message.text
            await update.message.reply_text("✅ API-ключ принят! Проверю его позже.")
            message = update.message
        
        user_id = message.chat.id
        name = update.effective_user.first_name
        
        # Сохраняем в базу (по умолчанию Москва и 09:00)
        db.save_user_data(user_id, user_name=name, tinkoff_token=token, timezone="Europe/Moscow", digest_time="09:00")
        
        await message.reply_text(
            f"🎉 Отлично, {name}! Настройка завершена.\n"
            "По умолчанию я буду присылать сводку в 09:00 по Москве.\n"
            "Вы можете изменить это в ⚙️ Настройках.\n\n"
            "Используй кнопки внизу, чтобы управлять ботом:",
            reply_markup=get_main_menu()
        )
        return ConversationHandler.END
        
    async def finish_onboarding(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        
        timezone = query.data.replace("tz_", "")
        user_id = query.from_user.id
        name = context.user_data.get('temp_name', query.from_user.first_name)
        token = context.user_data.get('temp_token')
        
        db.save_user_data(user_id, user_name=name, tinkoff_token=token, timezone=timezone)
        
        await query.message.reply_text(
            f"🎉 Отлично, {name}! Настройка завершена.\n"
            "Теперь я буду присылать тебе дайджест каждое утро.\n\n"
            "Используй кнопки внизу, чтобы управлять ботом:",
            reply_markup=get_main_menu()
        )
        return ConversationHandler.END
        
    async def send_digest(self, context: ContextTypes.DEFAULT_TYPE):
        """Формирует новостную сводку (пока заглушка)"""
        user_id = context.job.data['user_id']
        user_data = db.get_user(user_id)
        if not user_data:
            return
            
        name = user_data.get('user_name', 'Инвестор')
        
        # В будущем здесь будет парсинг новостей по тикерам из портфеля
        digest_text = (
            f"📰 <b>Привет, {name}</b>\n\n"
            f"Сводка актуальных новостей на сегодня:\n\n"
            f"🇷🇺 <b>Рынок РФ:</b> Индекс Мосбиржи показывает рост на фоне новостей.\n"
            f"💵 <b>Курсы валют:</b> USD 82.75 (+0.75%), EUR 92.39 (+0.22%).\n"
            f"🛢 <b>Нефть:</b> Brent $91.62 (-1.03%).\n\n"
            f"<i>Это тестовое сообщение. Скоро здесь будут новости по вашим акциям.</i>"
        )
        await context.bot.send_message(chat_id=user_id, text=digest_text, parse_mode="HTML")
        
    async def analyze_ai_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        user_data = db.get_user(user_id)
        token = user_data.get('tinkoff_token') if user_data else None

        if not token:
            await update.message.reply_text("❌ Сначала подключите API-ключ в настройках.")
            return

        await update.message.reply_text("🧠 Запускаю AI-анализ (5-10 сек)...")

        try:
            with Client(token) as client:
                accounts_resp = client.users.get_accounts()
                all_ids = [a.id for a in accounts_resp.accounts if a.status == AccountStatus.ACCOUNT_STATUS_OPEN]

            selection = self._parse_selection(user_data.get('selected_account'))
            target_ids = all_ids if selection == "all" else [i for i in selection if i in all_ids]
            if not target_ids:
                target_ids = all_ids

            data = await self._get_portfolio_for_accounts(token, target_ids)
            if not data or not data['accounts']:
                await update.message.reply_text("❌ Не удалось загрузить портфели.")
                return

            if not self.ai_manager:
                await update.message.reply_text("❌ ИИ временно недоступен.")
                return

            positions = []
            for acc in data['accounts']:
                for pos in acc['positions']:
                    positions.append(f"{pos['name']} ({pos['ticker']}): {pos['value']:,.0f} руб. (доходность {pos['yield_percentage']:+.1f}%)")

            portfolio_str = "\n".join(positions) if positions else "Портфель пуст"

            prompt = (
                f"Ты — профессиональный инвестиционный советник. Вот портфель пользователя:\n{portfolio_str}\n\n"
                f"Общая стоимость: {data['total_portfolio_value']:,.0f} руб.\n"
                f"Напиши краткий анализ (3-4 абзаца).\n"
                f"1. Оцени диверсификацию (какие сектора преобладают).\n"
                f"2. Укажи на потенциальные риски.\n"
                f"3. Дай 1-2 идеи по улучшению (без призывов 'покупай сейчас').\n"
                f"В конце добавь: 'Это не индивидуальная инвестиционная рекомендация.'"
            )

            response = await self.ai_manager.generate_response(prompt, "")
            if len(response) > 4000:
                response = response[:3900] + "..."
            await update.message.reply_text(f"🤖 <b>AI-Анализ:</b>\n\n{response}", parse_mode="HTML")
        except Exception as e:
            logger.error(f"AI Analysis error: {e}")
            await update.message.reply_text("❌ Ошибка при генерации анализа.")
            
    async def post_init(self, application: Application) -> None:
        """Выполняется при запуске бота перед началом polling"""
        await self._setup_bot_commands()

    def _parse_selection(self, value):
        """Парсит сохраненный выбор счетов из БД"""
        if not value or value == "all":
            return "all"
        return [a.strip() for a in value.split(",") if a.strip()]

    async def _get_portfolio_for_accounts(self, token, account_ids):
        """Загружает и объединяет портфели для выбранных счетов"""
        try:
            with Client(token) as client:
                all_data = []
                total_value = 0
                total_invested = 0
                total_cash = 0

                accounts_response = client.users.get_accounts()

                for acc_id in account_ids:
                    acc_info = next((a for a in accounts_response.accounts if a.id == acc_id), None)
                    if not acc_info:
                        continue
                    acc_name = getattr(acc_info, 'name', f'Счет {acc_id[-4:]}')

                    portfolio = client.operations.get_portfolio(account_id=acc_id)
                    positions_data = client.operations.get_positions(account_id=acc_id)

                    positions_list = []
                    acc_value = 0
                    acc_invested = 0

                    for pos in portfolio.positions:
                        qty = pos.quantity.units + (pos.quantity.nano / 1e9)
                        if qty == 0:
                            continue

                        price = pos.current_price.units + (pos.current_price.nano / 1e9)
                        value = qty * price

                        avg_price = pos.average_position_price.units + (pos.average_position_price.nano / 1e9)
                        invested = qty * avg_price
                        pnl = value - invested
                        pnl_pct = (pnl / invested * 100) if invested > 0 else 0

                        name = pos.ticker
                        ticker = pos.ticker
                        try:
                            instr = client.instruments.get_instrument_by(id_type=1, id=pos.figi)
                            if instr and hasattr(instr, 'instrument'):
                                name = instr.instrument.name
                                ticker = instr.instrument.ticker
                        except:
                            pass

                        positions_list.append({
                            'name': name, 'ticker': ticker, 'quantity': qty,
                            'value': value, 'invested_value': invested,
                            'real_yield': pnl, 'yield_percentage': pnl_pct
                        })
                        acc_value += value
                        acc_invested += invested

                    acc_cash = 0
                    if positions_data.money:
                        for m in positions_data.money:
                            if m.currency == 'rub':
                                acc_cash += m.units + (m.nano / 1e9)

                    all_data.append({
                        'account_id': acc_id, 'account_name': acc_name,
                        'total_value': acc_value, 'total_invested': acc_invested,
                        'available_cash': acc_cash,
                        'total_real_yield': acc_value - acc_invested,
                        'total_yield_percentage': ((acc_value - acc_invested) / acc_invested * 100) if acc_invested > 0 else 0,
                        'positions': positions_list, 'positions_count': len(positions_list)
                    })
                    total_value += acc_value
                    total_invested += acc_invested
                    total_cash += acc_cash

                total_pnl = total_value - total_invested
                total_pnl_pct = (total_pnl / total_invested * 100) if total_invested > 0 else 0

                return {
                    'accounts': all_data,
                    'total_portfolio_value': total_value,
                    'total_invested': total_invested,
                    'total_cash': total_cash,
                    'total_real_yield': total_pnl,
                    'total_yield_percentage': total_pnl_pct,
                    'account_count': len(all_data),
                }
        except Exception as e:
            logger.error(f"Portfolio for accounts error: {e}")
            return None

    async def _render_accounts_menu(self, query, context):
        """Отрисовывает меню с чекбоксами"""
        active = context.user_data.get('temp_active_accounts', [])
        selected = context.user_data.get('temp_acc_selection', [])

        keyboard = []
        for acc_id, acc_name in active:
            icon = "☑" if acc_id in selected else "☐"
            keyboard.append([InlineKeyboardButton(f"{icon} {acc_name}", callback_data=f"toggle_acc_{acc_id}")])

        keyboard.append([InlineKeyboardButton("💾 Сохранить выбор", callback_data="save_accounts")])
        keyboard.append([InlineKeyboardButton("⬅️ Отмена", callback_data="back_to_settings")])

        await query.edit_message_text(
            "🏦 <b>Выберите счета для анализа</b>\n\n"
            "Вы можете отметить сразу несколько счетов (например, акции — на одном, облигации — на другом).\n\n"
            "Нажмите на счет, чтобы отметить/снять отметку:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="HTML"
        )

    async def toggle_account_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Переключает чекбокс счета"""
        query = update.callback_query
        await query.answer()
        acc_id = query.data.replace("toggle_acc_", "")
        selected = context.user_data.get('temp_acc_selection', [])
        if acc_id in selected:
            selected.remove(acc_id)
        else:
            selected.append(acc_id)
        context.user_data['temp_acc_selection'] = selected
        await self._render_accounts_menu(query, context)

    async def save_accounts_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Сохраняет выбор в БД"""
        query = update.callback_query
        selected = context.user_data.get('temp_acc_selection', [])
        if not selected:
            await query.answer("⚠️ Выберите хотя бы один счет", show_alert=True)
            return
        await query.answer()

        db.save_user_data(query.from_user.id, selected_account=",".join(selected))

        context.user_data.pop('temp_active_accounts', None)
        context.user_data.pop('temp_acc_selection', None)

        await query.edit_message_text(
            f"✅ <b>Выбрано счетов: {len(selected)}</b>\n\n"
            "Теперь я буду анализировать данные по всем выбранным счетам вместе.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⚙️ В настройки", callback_data="back_to_settings")]]),
            parse_mode="HTML"
        )

    async def choose_account_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка кнопки выбора счета в настройках (мультивыбор)"""
        query = update.callback_query
        await query.answer()
        user_id = query.from_user.id
        user_data = db.get_user(user_id)
        token = user_data.get('tinkoff_token') if user_data else None

        if not token:
            await query.edit_message_text("❌ Сначала добавьте API-ключ.")
            return

        await query.edit_message_text("📋 Загружаю список ваших счетов...")

        try:
            with Client(token) as client:
                accounts_response = client.users.get_accounts()
                active_accounts = []

                for account in accounts_response.accounts:
                    if account.status != AccountStatus.ACCOUNT_STATUS_OPEN:
                        continue
                    try:
                        positions = client.operations.get_positions(account_id=account.id)
                        has_assets = False
                        if positions.securities:
                            has_assets = True
                        if positions.money:
                            for m in positions.money:
                                if m.currency == 'rub' and (m.units > 0 or m.nano > 0):
                                    has_assets = True
                                    break
                        if not has_assets:
                            continue
                    except:
                        continue
                    active_accounts.append((account.id, getattr(account, 'name', 'Счет')))

                if not active_accounts:
                    await query.edit_message_text("❌ У вас нет счетов с активами.")
                    return

                # Загружаем текущий выбор
                current = self._parse_selection(user_data.get('selected_account'))
                if current == "all":
                    current = [acc_id for acc_id, _ in active_accounts]

                context.user_data['temp_active_accounts'] = active_accounts
                context.user_data['temp_acc_selection'] = current
                await self._render_accounts_menu(query, context)

        except Exception as e:
            logger.error(f"Accounts error: {e}")
            await query.edit_message_text("❌ Ошибка загрузки счетов. Проверьте API-ключ.")

    def run(self):
        """Run the bot"""
        # Подключаем post_init
        self.application = Application.builder().token(self.token).post_init(self.post_init).build()
        self.setup_handlers()
        
        # --- ПЛАНИРОВЩИК УТРЕННЕЙ СВОДКИ ---
        # Мы ставим задачу каждый день в 09:00 (по времени сервера, обычно это UTC или МСК)
        import datetime as dt
        import pytz
        moscow_tz = pytz.timezone('Europe/Moscow')
        
        # Для теста давайте поставим время через 2 минуты от текущего момента, 
        # чтобы вы могли увидеть, как это работает прямо сейчас!
        current_time = dt.datetime.now(moscow_tz) + dt.timedelta(minutes=2)
        
        # (Для реальной работы раскомментируйте строку ниже и закомментируйте строку выше)
        # current_time = dt.datetime.now(moscow_tz).replace(hour=9, minute=0, second=0, microsecond=0)

        async def daily_digest_job(context: ContextTypes.DEFAULT_TYPE):
            """Задача для рассылки сводки всем пользователям из БД"""
            try:
                # В реальности тут нужно получать список всех пользователей из db
                # Для теста возьмем вас (ваш ID нужно знать)
                # ВАЖНО: Замените 123456789 на ваш реальный Telegram ID
                class FakeJob:
                    data = {'user_id': 407202902} # <--- ВАШ ID
                class FakeContext:
                    job = FakeJob()
                    bot = context.bot
                
                # Вызываем функцию отправки сводки
                await self.send_digest(FakeContext())
                logger.info("✅ Утренняя сводка отправлена")
            except Exception as e:
                logger.error(f"Digest job error: {e}")

        # Планируем задачу
        if self.application.job_queue:
            self.application.job_queue.run_daily(
                daily_digest_job,
                time=current_time.time(),
                days=(0, 1, 2, 3, 4, 5, 6),
                name="morning_digest"
            )
            logger.info(f"⏰ Планировщик сводки запущен на {current_time.strftime('%H:%M')}")

        mode, token_info = self._get_operation_mode_info()
        ai_status = "AVAILABLE" if self.ai_manager else "UNAVAILABLE"
        
        logger.info("🤖 Investment Bot starting...")
        print("=" * 60)
        print("🤖 INVESTMENT ADVISOR BOT")
        print("=" * 60)
        print(f"🔧 {mode}")
        print(f"🤖 AI: {ai_status}")
        print("📍 Бот запущен и слушает сообщения...")
        print("-" * 60)

        # Простой запуск
        self.application.run_polling(drop_pending_updates=True)
