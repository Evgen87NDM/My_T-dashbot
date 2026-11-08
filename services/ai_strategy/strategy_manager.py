import logging
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
import json

logger = logging.getLogger(__name__)

@dataclass
class StrategyResult:
    """Результат выполнения стратегии"""
    success: bool
    data: Dict[str, Any]
    timestamp: datetime
    error: Optional[str] = None

class AIStrategyManager:
    """Менеджер AI стратегий для управления портфелем"""
    
    def __init__(self, deepseek_client, tinkoff_client=None):
        self.ai_client = deepseek_client
        self.tinkoff_client = tinkoff_client
        self.strategy_cache = {}
        self.cache_ttl = timedelta(minutes=15)
        
    async def get_portfolio_analysis(self, user_id: int) -> StrategyResult:
        """
        Получение AI анализа портфеля
        """
        try:
            # Получение данных портфеля
            portfolio_data = await self._get_user_portfolio(user_id)
            if not portfolio_data:
                return StrategyResult(
                    success=False,
                    data={},
                    timestamp=datetime.now(),
                    error="Не удалось получить данные портфеля"
                )
            
            # Получение рыночных данных
            market_data = await self._get_market_data()
            
            # Проверка кэша
            cache_key = f"analysis_{user_id}_{datetime.now().strftime('%Y%m%d%H')}"
            if cache_key in self.strategy_cache:
                cached_data = self.strategy_cache[cache_key]
                if datetime.now() - cached_data['timestamp'] < self.cache_ttl:
                    return StrategyResult(
                        success=True,
                        data=cached_data['data'],
                        timestamp=cached_data['timestamp']
                    )
            
            # Запрос к AI
            analysis_result = await self.ai_client.analyze_investment_portfolio(
                portfolio_data, market_data
            )
            
            if "error" in analysis_result:
                return StrategyResult(
                    success=False,
                    data=analysis_result,
                    timestamp=datetime.now(),
                    error=analysis_result["error"]
                )
            
            # Кэширование результата
            self.strategy_cache[cache_key] = {
                'data': analysis_result,
                'timestamp': datetime.now()
            }
            
            return StrategyResult(
                success=True,
                data=analysis_result,
                timestamp=datetime.now()
            )
            
        except Exception as e:
            logger.error(f"Portfolio analysis error: {e}")
            return StrategyResult(
                success=False,
                data={},
                timestamp=datetime.now(),
                error=str(e)
            )
    
    async def get_market_analysis(self) -> StrategyResult:
        """
        Получение анализа рыночной ситуации
        """
        try:
            cache_key = f"market_analysis_{datetime.now().strftime('%Y%m%d%H')}"
            if cache_key in self.strategy_cache:
                cached_data = self.strategy_cache[cache_key]
                if datetime.now() - cached_data['timestamp'] < timedelta(minutes=30):
                    return StrategyResult(
                        success=True,
                        data=cached_data['data'],
                        timestamp=cached_data['timestamp']
                    )
            
            analysis_result = await self.ai_client.analyze_market_conditions()
            
            if "error" in analysis_result:
                return StrategyResult(
                    success=False,
                    data=analysis_result,
                    timestamp=datetime.now(),
                    error=analysis_result["error"]
                )
            
            # Кэширование
            self.strategy_cache[cache_key] = {
                'data': analysis_result,
                'timestamp': datetime.now()
            }
            
            return StrategyResult(
                success=True,
                data=analysis_result,
                timestamp=datetime.now()
            )
            
        except Exception as e:
            logger.error(f"Market analysis error: {e}")
            return StrategyResult(
                success=False,
                data={},
                timestamp=datetime.now(),
                error=str(e)
            )
    
    async def generate_trading_plan(self, user_id: int, risk_level: str = "medium") -> StrategyResult:
        """
        Генерация торгового плана
        """
        try:
            portfolio_data = await self._get_user_portfolio(user_id)
            market_data = await self._get_market_data()
            
            # Добавляем уровень риска в данные
            analysis_data = {
                "portfolio": portfolio_data,
                "market": market_data,
                "risk_level": risk_level,
                "investment_horizon": "medium_term"
            }
            
            trading_plan = await self.ai_client.analyze_investment_portfolio(
                portfolio_data, analysis_data
            )
            
            if "error" in trading_plan:
                return StrategyResult(
                    success=False,
                    data=trading_plan,
                    timestamp=datetime.now(),
                    error=trading_plan["error"]
                )
            
            return StrategyResult(
                success=True,
                data=trading_plan,
                timestamp=datetime.now()
            )
            
        except Exception as e:
            logger.error(f"Trading plan generation error: {e}")
            return StrategyResult(
                success=False,
                data={},
                timestamp=datetime.now(),
                error=str(e)
            )
    
    async def execute_strategy_actions(self, user_id: int, actions: List[Dict]) -> StrategyResult:
        """
        Выполнение действий стратегии
        """
        try:
            executed_actions = []
            
            for action in actions:
                if action.get('action') in ['buy', 'sell'] and action.get('urgency') == 'high':
                    # Получаем FIGI по тикеру
                    figi = await self._get_figi_by_ticker(action.get('ticker', ''))
                    if figi:
                        execution_result = await self._execute_trade_action(
                            user_id, action, figi
                        )
                        executed_actions.append(execution_result)
            
            return StrategyResult(
                success=True,
                data={
                    "executed_actions": executed_actions,
                    "total_actions": len(executed_actions),
                    "timestamp": datetime.now()
                },
                timestamp=datetime.now()
            )
            
        except Exception as e:
            logger.error(f"Strategy execution error: {e}")
            return StrategyResult(
                success=False,
                data={},
                timestamp=datetime.now(),
                error=str(e)
            )
    
    async def _get_user_portfolio(self, user_id: int) -> Dict[str, Any]:
        """Получение портфеля пользователя"""
        try:
            if self.tinkoff_client and hasattr(self.tinkoff_client, 'is_configured') and self.tinkoff_client.is_configured:
                portfolio = await self.tinkoff_client.get_portfolio()
                return self._format_portfolio_for_ai(portfolio, user_id)
            else:
                # Демо-данные портфеля
                return self._get_demo_portfolio(user_id)
            
        except Exception as e:
            logger.error(f"Error getting user portfolio: {e}")
            return self._get_demo_portfolio(user_id)
    
    async def _get_market_data(self) -> Dict[str, Any]:
        """Получение рыночных данных"""
        try:
            if self.tinkoff_client and hasattr(self.tinkoff_client, 'is_configured') and self.tinkoff_client.is_configured:
                market_data = await self.tinkoff_client.get_market_data()
                return self._format_market_data_for_ai(market_data)
            else:
                # Демо-рыночные данные
                return self._get_demo_market_data()
            
        except Exception as e:
            logger.error(f"Error getting market data: {e}")
            return self._get_demo_market_data()
    
    def _format_portfolio_for_ai(self, portfolio: Dict, user_id: int) -> Dict[str, Any]:
        """Форматирование портфеля для AI"""
        # Упрощенная реализация - возвращаем демо-данные
        return self._get_demo_portfolio(user_id)
    
    def _format_market_data_for_ai(self, market_data: Dict) -> Dict[str, Any]:
        """Форматирование рыночных данных для AI"""
        # Упрощенная реализация - возвращаем демо-данные
        return self._get_demo_market_data()
    
    def _get_demo_portfolio(self, user_id: int) -> Dict[str, Any]:
        """Демо-данные портфеля"""
        return {
            "user_id": user_id,
            "total_value": 1500000.0,
            "currency": "RUB",
            "positions": [
                {
                    "ticker": "SBER",
                    "name": "Сбербанк",
                    "figi": "BBG004730N88",
                    "quantity": 100,
                    "current_price": 300.0,
                    "average_price": 280.0,
                    "weight": 20.0,
                    "type": "share",
                    "sector": "finance",
                    "expected_yield": 2000.0
                },
                {
                    "ticker": "GAZP", 
                    "name": "Газпром",
                    "figi": "BBG004730RP0",
                    "quantity": 200,
                    "current_price": 160.0,
                    "average_price": 170.0,
                    "weight": 16.0,
                    "type": "share",
                    "sector": "energy",
                    "expected_yield": -2000.0
                },
                {
                    "ticker": "TCS",
                    "name": "TCS Group",
                    "figi": "BBG00QPYJ5H0",
                    "quantity": 50,
                    "current_price": 3500.0,
                    "average_price": 3200.0,
                    "weight": 35.0,
                    "type": "share", 
                    "sector": "technology",
                    "expected_yield": 15000.0
                }
            ],
            "allocation": {
                "stocks": 71.0,
                "bonds": 0.0,
                "cash": 29.0
            },
            "performance": {
                "total_return": 8.5,
                "daily_change": 1.2
            },
            "demo_mode": True
        }
    
    def _get_demo_market_data(self) -> Dict[str, Any]:
        """Демо-рыночные данные"""
        return {
            "timestamp": datetime.now().isoformat(),
            "indices": {
                "IMOEX": {
                    "value": 3200.0,
                    "change": 0.8,
                    "name": "Индекс МосБиржи"
                },
                "RTSI": {
                    "value": 1100.0,
                    "change": 1.2,
                    "name": "Индекс РТС"
                }
            },
            "market_volatility": "medium",
            "currency_rates": {
                "USDRUB": 90.5,
                "EURRUB": 98.2
            },
            "stocks_count": 250,
            "bonds_count": 150,
            "demo_mode": True
        }
    
    def _calculate_allocation(self, positions: List[Dict]) -> Dict[str, float]:
        """Расчет распределения активов"""
        allocation = {"stocks": 0.0, "bonds": 0.0, "cash": 0.0, "other": 0.0}
        
        for position in positions:
            instrument_type = position.get('type', 'other')
            weight = float(position.get('weight', 0))
            
            if 'share' in instrument_type or 'stock' in instrument_type:
                allocation['stocks'] += weight
            elif 'bond' in instrument_type:
                allocation['bonds'] += weight
            elif 'currency' in instrument_type:
                allocation['cash'] += weight
            else:
                allocation['other'] += weight
        
        # Нормализуем до 100%
        total = sum(allocation.values())
        if total > 0:
            for key in allocation:
                allocation[key] = round(allocation[key] / total * 100, 1)
        
        return allocation
    
    def _classify_sector(self, ticker: str) -> str:
        """Классификация сектора по тикеру"""
        sector_map = {
            'SBER': 'finance',
            'VTBR': 'finance',
            'TCSG': 'finance',
            'GAZP': 'energy',
            'LKOH': 'energy',
            'ROSN': 'energy',
            'TCS': 'technology',
            'YNDX': 'technology',
            'OZON': 'technology'
        }
        return sector_map.get(ticker, 'other')
    
    async def _get_figi_by_ticker(self, ticker: str) -> Optional[str]:
        """Получение FIGI по тикеру"""
        figi_map = {
            'SBER': 'BBG004730N88',
            'GAZP': 'BBG004730RP0',
            'TCS': 'BBG00QPYJ5H0',
            'VTBR': 'BBG004730ZJ9',
            'LKOH': 'BBG004731032',
            'ROSN': 'BBG004731354',
            'YNDX': 'BBG006L8G4H1'
        }
        return figi_map.get(ticker.upper())
    
    async def _execute_trade_action(self, user_id: int, action: Dict, figi: str) -> Dict[str, Any]:
        """Выполнение торгового действия"""
        try:
            if self.tinkoff_client and hasattr(self.tinkoff_client, 'is_configured') and self.tinkoff_client.is_configured:
                # Реальное выполнение через Tinkoff API
                quantity = int(action.get('quantity', 1))
                result = await self.tinkoff_client.execute_order(
                    figi=figi,
                    operation=action.get('action', ''),
                    quantity=quantity
                )
                return {
                    "user_id": user_id,
                    "ticker": action.get('ticker', ''),
                    "figi": figi,
                    "action": action.get('action', ''),
                    "quantity": quantity,
                    "status": result.get('status', 'unknown'),
                    "order_id": result.get('order_id'),
                    "message": result.get('message', ''),
                    "timestamp": datetime.now().isoformat(),
                    "simulated": False
                }
            else:
                # Симуляция выполнения
                logger.info(f"Simulating trade for user {user_id}: {action}")
                
                return {
                    "user_id": user_id,
                    "ticker": action.get('ticker', ''),
                    "figi": figi,
                    "action": action.get('action', ''),
                    "quantity": action.get('quantity', 1),
                    "status": "simulated_execution",
                    "reason": action.get('reason', 'AI recommendation'),
                    "timestamp": datetime.now().isoformat(),
                    "simulated": True
                }
        except Exception as e:
            logger.error(f"Trade execution failed: {e}")
            return {
                "user_id": user_id,
                "ticker": action.get('ticker', ''),
                "figi": figi,
                "action": action.get('action', ''),
                "quantity": action.get('quantity', 1),
                "status": "failed",
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }