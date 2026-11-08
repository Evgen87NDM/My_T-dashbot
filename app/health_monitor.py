"""
Health monitoring system - EXTENDED portfolio information for ALL accounts
"""
import logging
from typing import List
from app.settings import settings

logger = logging.getLogger(__name__)

class HealthMonitor:
    """Health monitor with extended portfolio information for ALL accounts"""
    
    def __init__(self, client_manager, telegram_bot):
        self.client_manager = client_manager
        self.telegram_bot = telegram_bot
        self.status_messages = []
    
    def _is_real_tinkoff_client(self):
        """Check if using real Tinkoff client"""
        return self.client_manager.is_real_client()
    
    async def perform_health_check(self) -> str:
        """Perform health check with extended portfolio info for ALL accounts"""
        logger.info("🔍 Performing health check for ALL accounts...")
        
        self.status_messages = []
        
        # 1. Bot status
        self.status_messages.append("✅ Бот успешно запущен")
        
        # 2. Broker service check
        await self._check_broker_service()
        
        # 3. Extended portfolio data for ALL accounts
        await self._check_extended_portfolio_data_all_accounts()
        
        # 4. Trading mode and tariff info
        self._add_trading_mode_info()
        
        return self._format_health_report()
    
    async def _check_broker_service(self):
        """Check broker service"""
        try:
            if settings.TINKOFF_SANDBOX_MODE:
                mode_info = "🔧 SANDBOX MODE"
            else:
                mode_info = "⚡ REAL MODE"
            
            def get_accounts_operation(client):
                return client.users.get_accounts()
            
            accounts_response = self.client_manager.execute_operation(get_accounts_operation)
            account_count = len(accounts_response.accounts) if hasattr(accounts_response, 'accounts') else 0
            
            self.status_messages.append(f"✅ Брокерский сервис доступен ({mode_info})")
            self.status_messages.append(f"📋 Найдено счетов: {account_count}")
            
        except Exception as e:
            logger.error(f"Broker check error: {e}")
            self.status_messages.append("❌ Брокерский сервис недоступен")
            self.status_messages.append(f"📝 Ошибка: {str(e)}")
    
    async def _check_extended_portfolio_data_all_accounts(self):
        """Check extended portfolio data with detailed positions for ALL accounts"""
        try:
            def get_accounts_operation(client):
                return client.users.get_accounts()
            
            accounts_response = self.client_manager.execute_operation(get_accounts_operation)
                
            if not accounts_response.accounts:
                self.status_messages.append("💰 Данные портфеля: нет счетов")
                return
            
            total_balance_all_accounts = 0
            total_cash_all_accounts = 0
            total_positions_count = 0
            all_positions_details = []
            sectors_all = {}
            instrument_types_all = {}
            accounts_info = []
            
            # Process each account
            for account in accounts_response.accounts:
                account_id = account.id
                account_name = getattr(account, 'name', f'Счет {account_id[-4:]}')
                account_type = getattr(account, 'type', 'Неизвестно')
                
                logger.info(f"Processing portfolio for account: {account_name}")
                
                account_balance = 0
                account_cash = 0
                account_positions_count = 0
                account_positions_details = []
                
                # Get portfolio for this account
                def get_portfolio_operation(client):
                    return client.operations.get_portfolio(account_id=account_id)
                
                portfolio = self.client_manager.execute_operation(get_portfolio_operation)
                
                # Get positions for this account
                def get_positions_operation(client):
                    return client.operations.get_positions(account_id=account_id)
                
                positions = self.client_manager.execute_operation(get_positions_operation)
                
                # Process positions for this account
                if portfolio and hasattr(portfolio, 'positions'):
                    for position in portfolio.positions:
                        try:
                            quantity = position.quantity.units if hasattr(position.quantity, 'units') else 0
                            if quantity <= 0:
                                continue
                                
                            # Get current price and value
                            current_price = 0
                            if hasattr(position, 'current_price'):
                                if hasattr(position.current_price, 'units') and hasattr(position.current_price, 'nano'):
                                    current_price = position.current_price.units + position.current_price.nano / 1e9
                            
                            position_value = current_price * quantity
                            account_balance += position_value
                            account_positions_count += 1
                            total_positions_count += 1
                            
                            # Get instrument info
                            name = "Неизвестно"
                            ticker = "N/A"
                            instrument_type = "Неизвестно"
                            sector = "Другое"
                            
                            if hasattr(position, 'figi'):
                                try:
                                    def get_instrument_operation(instrument_client):
                                        return instrument_client.instruments.get_instrument_by(id_type=1, id=position.figi)
                                    
                                    instrument_response = self.client_manager.execute_operation(get_instrument_operation)
                                    if instrument_response and hasattr(instrument_response, 'instrument'):
                                        name = getattr(instrument_response.instrument, 'name', 'Неизвестно')
                                        ticker = getattr(instrument_response.instrument, 'ticker', 'N/A')
                                        instrument_type = getattr(instrument_response.instrument, 'instrument_type', 'Неизвестно')
                                        sector = self._classify_sector(ticker)
                                except Exception as e:
                                    logger.warning(f"Could not get instrument info: {e}")
                                    if hasattr(position, 'name'):
                                        name = position.name
                                    if hasattr(position, 'ticker'):
                                        ticker = position.ticker
                                    if hasattr(position, 'instrument_type'):
                                        instrument_type = position.instrument_type
                            
                            # Track sectors and instrument types for all accounts
                            if sector not in sectors_all:
                                sectors_all[sector] = 0
                            sectors_all[sector] += position_value
                            
                            if instrument_type not in instrument_types_all:
                                instrument_types_all[instrument_type] = 0
                            instrument_types_all[instrument_type] += position_value
                            
                            position_details = {
                                'name': name,
                                'ticker': ticker,
                                'type': instrument_type,
                                'quantity': quantity,
                                'value': position_value,
                                'sector': sector,
                                'account_name': account_name
                            }
                            
                            account_positions_details.append(position_details)
                            all_positions_details.append(position_details)
                            
                        except Exception as e:
                            logger.warning(f"Error processing position: {e}")
                            continue
                
                # Process cash for this account
                if positions and hasattr(positions, 'money') and positions.money:
                    for money in positions.money:
                        if hasattr(money, 'currency') and money.currency == 'rub':
                            if hasattr(money, 'units') and hasattr(money, 'nano'):
                                cash_amount = money.units + money.nano / 1e9
                            elif hasattr(money, 'units'):
                                cash_amount = money.units
                            else:
                                cash_amount = 0
                            account_cash += cash_amount
                
                account_balance += account_cash
                total_balance_all_accounts += account_balance
                total_cash_all_accounts += account_cash
                
                # Add account summary
                accounts_info.append({
                    'name': account_name,
                    'type': account_type,
                    'balance': account_balance,
                    'cash': account_cash,
                    'positions_count': account_positions_count,
                    'positions': account_positions_details
                })
            
            # Add overall portfolio summary
            self.status_messages.append(f"💰 Общая стоимость всех счетов: {total_balance_all_accounts:,.2f} руб.")
            self.status_messages.append(f"💳 Общие доступные средства: {total_cash_all_accounts:,.2f} руб.")
            self.status_messages.append(f"📊 Всего позиций во всех счетах: {total_positions_count}")
            
            # Add accounts breakdown
            if accounts_info:
                self.status_messages.append("\n🏦 ИНФОРМАЦИЯ ПО СЧЕТАМ:")
                for account in accounts_info:
                    account_percent = (account['balance'] / total_balance_all_accounts * 100) if total_balance_all_accounts > 0 else 0
                    account_info = f"• {account['name']} ({account['type']})"
                    account_info += f" - {account['balance']:,.0f} руб. ({account_percent:.1f}%)"
                    account_info += f" | Позиций: {account['positions_count']}"
                    account_info += f" | Денег: {account['cash']:,.0f} руб."
                    self.status_messages.append(account_info)
            
            # Add positions breakdown (top 15 across all accounts)
            if all_positions_details:
                self.status_messages.append("\n🎯 КРУПНЕЙШИЕ ПОЗИЦИИ (ВСЕ СЧЕТА):")
                
                # Sort by value (descending) across all accounts
                all_positions_details.sort(key=lambda x: x['value'], reverse=True)
                
                for i, pos in enumerate(all_positions_details[:15], 1):  # Show top 15 positions
                    pos_weight = (pos['value'] / total_balance_all_accounts * 100) if total_balance_all_accounts > 0 else 0
                    pos_info = f"{i}. {pos['name']} ({pos['ticker']})"
                    pos_info += f"\n   └ Счет: {pos['account_name']}"
                    pos_info += f" | Кол-во: {pos['quantity']:,} шт."
                    pos_info += f" | Стоимость: {pos['value']:,.0f} руб."
                    pos_info += f" | Доля: {pos_weight:.1f}%"
                    pos_info += f" | Тип: {pos['type']}"
                    pos_info += f" | Сектор: {pos['sector']}"
                    self.status_messages.append(pos_info)
                
                if len(all_positions_details) > 15:
                    self.status_messages.append(f"   ... и еще {len(all_positions_details) - 15} позиций")
            
            # Add sector allocation across all accounts
            if sectors_all and total_balance_all_accounts > 0:
                self.status_messages.append("\n🏢 ОБЩЕЕ РАСПРЕДЕЛЕНИЕ ПО СЕКТОРАМ:")
                for sector, value in sorted(sectors_all.items(), key=lambda x: x[1], reverse=True):
                    sector_percent = (value / total_balance_all_accounts * 100)
                    if sector_percent >= 1:  # Show only sectors with >1%
                        self.status_messages.append(f"   • {sector}: {sector_percent:.1f}%")
            
            # Add instrument type allocation across all accounts
            if instrument_types_all and total_balance_all_accounts > 0:
                self.status_messages.append("\n📈 ОБЩЕЕ РАСПРЕДЕЛЕНИЕ ПО ТИПАМ:")
                for inst_type, value in sorted(instrument_types_all.items(), key=lambda x: x[1], reverse=True):
                    type_percent = (value / total_balance_all_accounts * 100)
                    if type_percent >= 1:  # Show only types with >1%
                        self.status_messages.append(f"   • {inst_type}: {type_percent:.1f}%")
            
        except Exception as e:
            logger.error(f"Portfolio check error: {e}")
            self.status_messages.append("⚠️ Данные портфеля: ошибка загрузки")
            self.status_messages.append(f"📝 Ошибка: {str(e)}")
    
    def _classify_sector(self, ticker: str) -> str:
        """Classify instrument by sector based on ticker"""
        sector_map = {
            'SBER': 'Финансы', 'VTBR': 'Финансы', 'TCSG': 'Финансы',
            'GAZP': 'Энергетика', 'LKOH': 'Энергетика', 'ROSN': 'Энергетика', 'NVTK': 'Энергетика',
            'YNDX': 'IT', 'OZON': 'IT', 'TCS': 'IT',
            'GMKN': 'Металлургия', 'PLZL': 'Металлургия', 'ALRS': 'Металлургия',
            'MGNT': 'Ритейл', 'FIVE': 'Ритейл', 'DSKY': 'Ритейл',
            'MTSS': 'Телеком', 'RTKM': 'Телеком',
            'PHOR': 'Химия', 'TRNFP': 'Транспорт',
            'AFKS': 'Холдинги', 'RUAL': 'Металлургия'
        }
        return sector_map.get(ticker.upper(), 'Другое')
    
    def _add_trading_mode_info(self):
        """Add trading mode and tariff information"""
        if settings.AUTO_TRADING_MODE:
            trading_mode = "🤖 ПОЛНОСТЬЮ АВТОМАТИЧЕСКИЙ"
        else:
            trading_mode = "👤 С РУЧНЫМ ПОДТВЕРЖДЕНИЕМ"
        
        self.status_messages.append(f"\n🎯 РЕЖИМ ТОРГОВЛИ: {trading_mode}")
        
        # Add tariff information if available
        if hasattr(self.telegram_bot, 'tariff_manager'):
            try:
                tariff_info = self.telegram_bot.tariff_manager.get_tariff_info()
                self.status_messages.append(f"💰 ТАРИФ БРОКЕРА: {tariff_info['name']}")
                self.status_messages.append(f"📊 КОМИССИИ: покупка {tariff_info['commission_rates']['buy']}%, продажа {tariff_info['commission_rates']['sell']}%")
            except Exception as e:
                logger.warning(f"Could not get tariff info: {e}")
                self.status_messages.append("💰 ТАРИФ БРОКЕРА: информация недоступна")
        
        # AI status
        if hasattr(self.telegram_bot, 'ai_manager') and self.telegram_bot.ai_manager:
            ai_info = self.telegram_bot.ai_manager.get_provider_info()
            active_provider = ai_info.get('active_provider', 'unknown')
            providers_count = ai_info.get('providers_count', 0)
            
            if active_provider != 'fallback':
                self.status_messages.append(f"🤖 AI ПРОВАЙДЕР: {active_provider.upper()} ({providers_count} доступно)")
            else:
                self.status_messages.append("🤖 AI ПРОВАЙДЕР: FALLBACK (основные недоступны)")
        else:
            self.status_messages.append("🤖 AI ПРОВАЙДЕР: НЕДОСТУПЕН")
    
    def _format_health_report(self) -> str:
        """Format health report with extended information"""
        report = "🤖 РАСШИРЕННЫЙ ОТЧЕТ О СИСТЕМЕ\n\n"
        report += "\n".join(self.status_messages)
        report += "\n\n🟢 СИСТЕМА ГОТОВА К РАБОТЕ"
        
        return report
    
    async def send_health_report(self, admin_chat_id: str):
        """Send health report to admin"""
        try:
            health_report = await self.perform_health_check()
            await self.telegram_bot.application.bot.send_message(
                chat_id=admin_chat_id,
                text=health_report
            )
        except Exception as e:
            logger.error(f"Failed to send health report: {e}")