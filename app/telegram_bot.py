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

from app.loader import get_tinkoff_client, get_tinkoff_client_manager
from app.health_monitor import HealthMonitor
from app.ai_manager import get_ai_manager
from app.settings import settings
from app.tariff_manager import get_tariff_manager

logger = logging.getLogger(__name__)

class InvestmentTelegramBot:
    """Bot with AI Portfolio Management and account selection"""
    
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
        """Setup bot commands menu in Telegram"""
        try:
            commands = [
                BotCommand("start", "Начать работу (показывает режим)"),
                BotCommand("portfolio", "Анализ портфеля (все счета)"),
                BotCommand("accounts", "Список счетов и выбор"),
                BotCommand("health", "Статус системы"),
                BotCommand("auto_trade", "AI управление выбранным счетом"),
                BotCommand("auto_trade_all", "AI управление всеми счетами"),
                BotCommand("commission", "Информация о тарифе и комиссиях"),
                BotCommand("help", "Помощь по командам"),
            ]
            
            await self.application.bot.set_my_commands(commands)
            logger.info("✅ Bot commands menu updated")
        except Exception as e:
            logger.warning(f"⚠️ Could not update bot commands: {e}")

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command with mode and tariff info"""
        user = update.effective_user
        logger.info(f"START from {user.first_name}")
        
        mode, token_info = self._get_operation_mode_info()
        ai_status = "✅ ДОСТУПЕН" if self.ai_manager else "❌ НЕДОСТУПЕН"
        trading_mode = "🤖 АВТОМАТИЧЕСКИЙ" if settings.AUTO_TRADING_MODE else "👤 С ПОДТВЕРЖДЕНИЕМ"
        
        # Get tariff info automatically
        tariff_info = self.tariff_manager.get_tariff_info()
        tariff_name = tariff_info['name']
        commission_rates = tariff_info['commission_rates']
        
        # Get current account selection
        user_id = str(user.id)
        current_selection = self.selected_accounts.get(user_id)
        selection_info = ""
        if current_selection:
            if current_selection == "all":
                selection_info = "✅ Выбраны: ВСЕ СЧЕТА"
            else:
                account_name = self.account_names.get(current_selection, f"Счет {current_selection[-4:]}")
                selection_info = f"✅ Выбран: {account_name}"
        else:
            selection_info = "⚠️ Счет не выбран. Используйте /accounts"
        
        welcome_text = f"""
🤖 Привет, {user.first_name}!

Я - ваш инвестиционный советник с AI управлением.

📊 РЕЖИМ РАБОТЫ: {mode}
💡 {token_info}
🤖 AI АССИСТЕНТ: {ai_status}
🎯 РЕЖИМ ТОРГОВЛИ: {trading_mode}

{selection_info}

💰 **АВТОМАТИЧЕСКИ ОПРЕДЕЛЕННЫЙ ТАРИФ**: {tariff_name}
📈 Комиссии: покупка {commission_rates['buy']}%, продажа {commission_rates['sell']}%

🎯 **КОМАНДЫ УПРАВЛЕНИЯ ПОРТФЕЛЕМ**:
/auto_trade - AI управление выбранным счетом
/auto_trade_all - AI управление всеми счетами
/accounts - Выбор счета для управления

📋 **ОСНОВНЫЕ КОМАНДЫ**:
/portfolio - Анализ портфеля (все счета)
/health - Статус системы
/commission - Информация о тарифе
/help - Помощь

💬 Задавайте вопросы про инвестиции!
        """
        
        await update.message.reply_text(welcome_text, reply_markup=get_main_menu())

    async def portfolio_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /portfolio command - все счета"""
        user = update.effective_user
        logger.info(f"PORTFOLIO from {user.first_name}")
        
        try:
            await update.message.reply_text("📊 Загружаю данные портфеля по всем счетам...")
            
            portfolio_data = await self._get_all_accounts_portfolio_data()
            if not portfolio_data:
                await update.message.reply_text("❌ Не удалось загрузить данные портфеля")
                return
            
            response_parts = self._format_portfolio_response(portfolio_data)
            
            # Отправляем все части сообщения
            for part in response_parts:
                await update.message.reply_text(part)
                await asyncio.sleep(0.3)  # Небольшая задержка между сообщениями
            
        except Exception as e:
            logger.error(f"Portfolio error: {e}")
            await update.message.reply_text(f"❌ Ошибка: {str(e)}")

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

    async def accounts_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /accounts command with account selection"""
        try:
            await update.message.reply_text("📋 Загружаю список счетов...")
            
            def get_accounts_operation(client):
                return client.users.get_accounts()
            
            accounts_response = await self._execute_tinkoff_operation(get_accounts_operation)
            
            if not accounts_response or not accounts_response.accounts:
                await update.message.reply_text("❌ Не найдено счетов")
                return
            
            user_id = str(update.effective_user.id)
            mode, token_info = self._get_operation_mode_info()
            
            response = f"📋 ВАШИ СЧЕТА\n\n{mode}\n{token_info}\n\n"
            
            keyboard = []
            for i, account in enumerate(accounts_response.accounts, 1):
                account_name = getattr(account, 'name', 'Счет')
                account_id = getattr(account, 'id', 'N/A')
                account_status = getattr(account, 'status', 'Неизвестно')
                account_type = getattr(account, 'type', 'Неизвестно')
                
                response += f"{i}. {account_name}\n"
                response += f"   ID: {account_id}\n"
                response += f"   Статус: {account_status}\n"
                response += f"   Тип: {account_type}\n\n"
                
                # Store account name for later use
                self.account_names[account_id] = account_name
                
                # Add button for account selection with auto-trade
                keyboard.append([
                    InlineKeyboardButton(
                        f"🎯 {account_name} → AI", 
                        callback_data=f"select_and_trade_{account_id}"
                    )
                ])
            
            # Add button for all accounts with auto-trade
            keyboard.append([
                InlineKeyboardButton(
                    "📊 ВСЕ СЧЕТА → AI", 
                    callback_data="select_and_trade_all"
                )
            ])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            # Show current selection
            current_account = self.selected_accounts.get(user_id)
            if current_account:
                if current_account == "all":
                    response += "✅ Сейчас выбраны: ВСЕ СЧЕТА"
                else:
                    account_name = self.account_names.get(current_account, current_account)
                    response += f"✅ Сейчас выбран: {account_name}"
            else:
                response += "🎯 Выберите счет для автоматического запуска AI управления:"
            
            await update.message.reply_text(response, reply_markup=reply_markup)
            
        except Exception as e:
            logger.error(f"Accounts error: {e}")
            await update.message.reply_text(f"❌ Ошибка загрузки счетов: {str(e)}")

    async def handle_account_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle account selection callbacks with auto-trade"""
        query = update.callback_query
        await query.answer()
        
        user_id = str(query.from_user.id)
        data = query.data
        
        logger.info(f"Account selection callback: user_id={user_id}, data={data}")
        
        try:
            if data == "select_and_trade_all":
                self.selected_accounts[user_id] = "all"
                self._save_selected_accounts()
                logger.info(f"User {user_id} selected ALL accounts")
                await query.edit_message_text("✅ Выбраны ВСЕ счета для управления\n\n🚀 Запускаю AI анализ...")
                # Automatically start auto_trade
                await self._execute_auto_trade_from_callback(query, "all", "all")
                return
            
            if data.startswith("select_and_trade_"):
                account_id = data.replace("select_and_trade_", "")
                self.selected_accounts[user_id] = account_id
                self._save_selected_accounts()
                
                # Get account name from stored mapping
                account_name = self.account_names.get(account_id, f"Счет {account_id[-4:]}")
                
                logger.info(f"User {user_id} selected account: {account_name} ({account_id})")
                await query.edit_message_text(f"✅ Выбран счет: {account_name}\n\n🚀 Запускаю AI анализ...")
                # Automatically start auto_trade
                await self._execute_auto_trade_from_callback(query, account_id, "selected")
                return
            
            # If we get here, something went wrong
            await query.edit_message_text("❌ Ошибка выбора счета")
            
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
                from tinkoff.invest import OrderDirection, OrderType
                
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
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("portfolio", self.portfolio_command))
        self.application.add_handler(CommandHandler("accounts", self.accounts_command))
        self.application.add_handler(CommandHandler("health", self.health_command))
        self.application.add_handler(CommandHandler("auto_trade", self.auto_trade_command))
        self.application.add_handler(CommandHandler("auto_trade_all", self.auto_trade_all_command))
        self.application.add_handler(CommandHandler("commission", self.commission_command))
        self.application.add_handler(CommandHandler("help", self.help_command))
        
        # --- Обработчики для кнопок главного меню ---

# Кнопка "⚙️ Настройки"
self.application.add_handler(
    MessageHandler(filters.Regex("^⚙️ Настройки$"), self.show_settings)
)

# Кнопка "📊 Мой портфель" (пока просто заглушка)
self.application.add_handler(
    MessageHandler(filters.Regex("^📊 Мой портфель$"), self.portfolio_command)
)

# Кнопка "💰 Дивиденды" (пока просто заглушка)
self.application.add_handler(
    MessageHandler(filters.Regex("^💰 Дивиденды$"), self.show_dividends)
)

        # Add callback handlers - UPDATED PATTERNS
        self.application.add_handler(CallbackQueryHandler(
            self.handle_account_selection, 
            pattern="^select_and_trade"
        ))
        
        self.application.add_handler(CallbackQueryHandler(
            self.handle_confirmation_callback, 
            pattern="^(confirm|cancel|show_commissions)"
        ))
        
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))

    def run(self):
        """Run the bot"""
        self.application = Application.builder().token(self.token).build()
        self.setup_handlers()
        
        # Setup bot commands menu асинхронно
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self._setup_bot_commands())
        except Exception as e:
            logger.warning(f"Could not setup bot commands: {e}")
        
        mode, token_info = self._get_operation_mode_info()
        ai_status = "AVAILABLE" if self.ai_manager else "UNAVAILABLE"
        trading_mode = "AUTO" if settings.AUTO_TRADING_MODE else "MANUAL"
        
        # Get tariff info for startup message
        tariff_info = self.tariff_manager.get_tariff_info()
        
        logger.info("🤖 Investment Bot starting...")
        print("=" * 60)
        print("🤖 INVESTMENT ADVISOR BOT")
        print("=" * 60)
        print(f"🔧 {mode}")
        print(f"💡 {token_info}")
        print(f"🤖 AI: {ai_status}")
        print(f"🎯 TRADING MODE: {trading_mode}")
        print(f"💰 TARIFF: {tariff_info['name']} ({tariff_info['commission_rates']['buy']}% commission)")
        print("📍 Бот запущен и слушает сообщения...")
        print("💬 РАБОТАЮЩИЕ КОМАНДЫ:")
        print("   /start - информация о режиме")
        print("   /portfolio - анализ портфеля (ВСЕ СЧЕТА)")
        print("   /accounts - выбор счета для управления (автоматически запускает AI)") 
        print("   /health - статус системы")
        print("   /auto_trade - AI управление выбранным счетом")
        print("   /auto_trade_all - AI управление всеми счетами")
        print("   /commission - информация о тарифе")
        print("   /help - помощь")
        print("⏹️  Ctrl+C для остановки")
        print("-" * 60)
        
        # Простой запуск без сложной логики event loop
        self.application.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    try:
        bot = InvestmentTelegramBot()
        bot.run()
    except Exception as e:
        print(f"❌ Bot failed: {e}")
        logging.error(f"Bot startup failed: {e}")
