import logging
from typing import Dict, Any, Optional
from datetime import datetime

from t_tech.invest import (
    AsyncClient,
    RequestError,
    PortfolioResponse,
    PositionsResponse,
    PostOrderResponse,
    OrderDirection,
    OrderType
)
from config import config

logger = logging.getLogger(__name__)

class TinkoffInvestClient:
    """Клиент для работы с Tinkoff Invest API версии 0.2.0b117"""
    
    def __init__(self):
        self.token = config.TINKOFF_TOKEN
        self.is_configured = bool(self.token and self.token != "your_tinkoff_invest_token_here")
        
    async def get_portfolio(self) -> Dict[str, Any]:
        """
        Получение портфеля пользователя
        """
        if not self.is_configured:
            logger.warning("Tinkoff API not configured - returning demo portfolio")
            return self._get_demo_portfolio()
        
        try:
            async with AsyncClient(token=self.token) as client:
                # Получаем список счетов
                accounts = await client.users.get_accounts()
                if not accounts.accounts:
                    raise ValueError("No investment accounts found")
                
                # Используем первый счет
                account_id = accounts.accounts[0].id
                
                # Получаем портфель
                portfolio: PortfolioResponse = await client.operations.get_portfolio(
                    account_id=account_id
                )
                
                # Получаем позиции
                positions: PositionsResponse = await client.operations.get_positions(
                    account_id=account_id
                )
                
                return self._format_portfolio_response(portfolio, positions)
                
        except RequestError as e:
            logger.error(f"Tinkoff API request error: {e}")
            return self._get_demo_portfolio()
        except Exception as e:
            logger.error(f"Error getting portfolio from Tinkoff API: {e}")
            return self._get_demo_portfolio()
    
    async def get_market_data(self) -> Dict[str, Any]:
        """
        Получение рыночных данных
        """
        if not self.is_configured:
            return self._get_demo_market_data()
        
        try:
            async with AsyncClient(token=self.token) as client:
                # Получаем список акций
                shares_response = await client.instruments.shares()
                
                # Получаем список облигаций
                bonds_response = await client.instruments.bonds()
                
                market_data = {
                    "stocks_count": len(shares_response.instruments),
                    "bonds_count": len(bonds_response.instruments),
                    "timestamp": datetime.now().isoformat(),
                    "main_indices": self._get_main_indices()
                }
                
                return market_data
                
        except Exception as e:
            logger.error(f"Error getting market data from Tinkoff API: {e}")
            return self._get_demo_market_data()
    
    async def execute_order(self, figi: str, operation: str, quantity: int) -> Dict[str, Any]:
        """
        Выполнение ордера
        """
        if not self.is_configured:
            logger.warning("Tinkoff API not configured - order execution simulated")
            return {
                "status": "simulated",
                "figi": figi,
                "operation": operation,
                "quantity": quantity,
                "message": "Order execution simulated (demo mode)"
            }
        
        try:
            async with AsyncClient(token=self.token) as client:
                # Получаем список счетов
                accounts = await client.users.get_accounts()
                if not accounts.accounts:
                    raise ValueError("No investment accounts found")
                
                account_id = accounts.accounts[0].id
                
                # Определяем направление ордера
                direction = (
                    OrderDirection.ORDER_DIRECTION_BUY 
                    if operation.lower() == 'buy' 
                    else OrderDirection.ORDER_DIRECTION_SELL
                )
                
                # Создаем рыночный ордер
                order_response: PostOrderResponse = await client.orders.post_order(
                    figi=figi,
                    quantity=quantity,
                    direction=direction,
                    account_id=account_id,
                    order_type=OrderType.ORDER_TYPE_MARKET
                )
                
                return {
                    "status": "executed",
                    "figi": figi,
                    "operation": operation,
                    "quantity": quantity,
                    "order_id": order_response.order_id,
                    "executed_quantity": order_response.lots_executed,
                    "message": "Order executed successfully",
                    "executed_price": self._money_value_to_float(order_response.executed_order_price),
                    "total_executed": self._money_value_to_float(order_response.total_order_amount)
                }
                
        except RequestError as e:
            logger.error(f"Tinkoff API order error: {e}")
            return {
                "status": "failed",
                "figi": figi,
                "operation": operation,
                "quantity": quantity,
                "error": str(e)
            }
        except Exception as e:
            logger.error(f"Error executing order: {e}")
            return {
                "status": "failed",
                "figi": figi,
                "operation": operation,
                "quantity": quantity,
                "error": str(e)
            }
    
    def _money_value_to_float(self, money_value) -> float:
        """Конвертация MoneyValue в float"""
        if hasattr(money_value, 'units') and hasattr(money_value, 'nano'):
            return float(money_value.units) + float(money_value.nano) / 1e9
        return 0.0
    
    def _quotation_to_float(self, quotation) -> float:
        """Конвертация Quotation в float"""
        if hasattr(quotation, 'units') and hasattr(quotation, 'nano'):
            return float(quotation.units) + float(quotation.nano) / 1e9
        return 0.0
    
    def _get_main_indices(self) -> Dict[str, Any]:
        """Получение данных по основным индексам (демо)"""
        return {
            "IMOEX": {
                "value": 3200.0,
                "change": 25.6,
                "change_percent": 0.8
            },
            "RTSI": {
                "value": 1100.0,
                "change": 13.2,
                "change_percent": 1.2
            }
        }
    
    def _format_portfolio_response(self, portfolio: PortfolioResponse, positions: PositionsResponse) -> Dict[str, Any]:
        """Форматирование ответа портфеля"""
        total_amount = self._money_value_to_float(portfolio.total_amount_portfolio)
        expected_yield = self._money_value_to_float(portfolio.expected_yield)
        
        formatted_positions = []
        
        # Обрабатываем позиции из портфеля
        for position in portfolio.positions:
            current_price = self._quotation_to_float(position.current_price)
            average_price = self._quotation_to_float(position.average_position_price)
            quantity = self._quotation_to_float(position.quantity)
            position_yield = self._quotation_to_float(position.expected_yield)
            
            if total_amount > 0:
                weight = (current_price * quantity / total_amount) * 100
            else:
                weight = 0
                
            formatted_positions.append({
                "figi": position.figi,
                "instrument_type": position.instrument_type,
                "quantity": quantity,
                "current_price": current_price,
                "average_price": average_price,
                "expected_yield": position_yield,
                "weight": round(weight, 2)
            })
        
        return {
            "total_amount": {
                "currency": portfolio.total_amount_portfolio.currency,
                "value": total_amount
            },
            "expected_yield": {
                "currency": portfolio.expected_yield.currency,
                "value": expected_yield
            },
            "positions": formatted_positions
        }
    
    def _get_demo_portfolio(self) -> Dict[str, Any]:
        """Демо-данные портфеля"""
        return {
            "total_amount": {
                "currency": "rub",
                "value": 1500000.0
            },
            "expected_yield": {
                "currency": "rub", 
                "value": 85000.0
            },
            "positions": [
                {
                    "figi": "BBG004730N88",
                    "instrument_type": "share",
                    "quantity": 100.0,
                    "current_price": 300.0,
                    "average_price": 280.0,
                    "expected_yield": 2000.0,
                    "weight": 20.0,
                    "ticker": "SBER",
                    "name": "Сбербанк"
                },
                {
                    "figi": "BBG004730RP0",
                    "instrument_type": "share",
                    "quantity": 200.0,
                    "current_price": 160.0,
                    "average_price": 170.0,
                    "expected_yield": -2000.0,
                    "weight": 16.0,
                    "ticker": "GAZP",
                    "name": "Газпром"
                },
                {
                    "figi": "BBG00QPYJ5H0",
                    "instrument_type": "share", 
                    "quantity": 50.0,
                    "current_price": 3500.0,
                    "average_price": 3200.0,
                    "expected_yield": 15000.0,
                    "weight": 35.0,
                    "ticker": "TCS",
                    "name": "TCS Group"
                }
            ],
            "demo_mode": True
        }
    
    def _get_demo_market_data(self) -> Dict[str, Any]:
        """Демо-рыночные данные"""
        return {
            "market_indices": {
                "IMOEX": {
                    "value": 3200.0,
                    "change": 25.6,
                    "change_percent": 0.8
                },
                "RTSI": {
                    "value": 1100.0,
                    "change": 13.2, 
                    "change_percent": 1.2
                }
            },
            "currency_rates": {
                "USDRUB": 90.5,
                "EURRUB": 98.2
            },
            "timestamp": datetime.now().isoformat(),
            "stocks_count": 250,
            "bonds_count": 150,
            "demo_mode": True
        }