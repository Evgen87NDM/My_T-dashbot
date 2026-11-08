"""
AI manager - Enhanced for maximum portfolio returns
"""
import logging
from typing import Optional, List, Dict
import asyncio
import json
import re
from datetime import datetime

logger = logging.getLogger(__name__)

class AIManager:
    """Enhanced AI manager with maximum returns optimization"""
    
    def __init__(self):
        self.fallback_ai = None
        self.providers = {}
        self.active_provider = "fallback"
        self.initialized = False
        
        self._init_providers()

    async def _get_fallback(self):
        """Lazy initialization of fallback AI"""
        if self.fallback_ai is None:
            try:
                from app.ai_fallback import get_fallback_ai
                self.fallback_ai = await get_fallback_ai()
            except Exception as e:
                logger.error(f"Failed to initialize fallback AI: {e}")
                from app.ai_fallback import FallbackAI
                self.fallback_ai = FallbackAI()
        return self.fallback_ai

    def _init_providers(self):
        """Initialize AI providers for maximum returns"""
        if self.initialized:
            return
            
        # Try OpenRouter first (often more reliable)
        try:
            from app.ai_openrouter import OpenRouterAI
            openrouter_ai = OpenRouterAI()
            if openrouter_ai.api_key and openrouter_ai.api_key.startswith('sk-or-'):
                self.providers["openrouter"] = openrouter_ai
                self.active_provider = "openrouter"
                logger.info("✅ OpenRouter AI initialized successfully")
            else:
                logger.warning("❌ OpenRouter API key not set or invalid")
        except Exception as e:
            logger.warning(f"❌ OpenRouter not available: {e}")

        # Try DeepSeek direct
        try:
            from app.ai_deepseek import DeepSeekAI
            deepseek_ai = DeepSeekAI()
            if deepseek_ai.api_key and deepseek_ai.api_key.startswith('sk-'):
                self.providers["deepseek"] = deepseek_ai
                if self.active_provider == "fallback":
                    self.active_provider = "deepseek"
                logger.info("✅ DeepSeek AI initialized successfully")
            else:
                logger.warning("❌ DeepSeek API key not set or invalid")
        except Exception as e:
            logger.warning(f"❌ DeepSeek not available: {e}")

        self.initialized = True
        logger.info(f"🎯 Active AI provider: {self.active_provider}")

    async def generate_portfolio_strategy(self, portfolio_data: dict, market_context: str = "") -> Dict:
        """Generate AI portfolio management strategy for MAXIMUM returns"""
        try:
            strategy_prompt = self._create_optimized_strategy_prompt(portfolio_data, market_context)
            
            # Try active provider first
            if self.active_provider in self.providers and self.active_provider != "fallback":
                try:
                    provider = self.providers[self.active_provider]
                    response = await provider.generate_response(strategy_prompt, "max_returns_strategy")
                    strategy = self._parse_optimized_strategy_response(response, portfolio_data)
                    if strategy and self._validate_strategy_quality(strategy):
                        return strategy
                except Exception as e:
                    logger.error(f"{self.active_provider} strategy error: {e}")

            # Try other providers
            for provider_name, provider in self.providers.items():
                if provider_name != self.active_provider:
                    try:
                        response = await provider.generate_response(strategy_prompt, "max_returns_strategy")
                        strategy = self._parse_optimized_strategy_response(response, portfolio_data)
                        if strategy and self._validate_strategy_quality(strategy):
                            self.active_provider = provider_name
                            return strategy
                    except Exception as e:
                        logger.error(f"{provider_name} strategy error: {e}")

            # Fallback to optimized strategy
            return await self._generate_optimized_fallback_strategy(portfolio_data)
            
        except Exception as e:
            logger.error(f"Portfolio strategy generation error: {e}")
            return await self._generate_optimized_fallback_strategy(portfolio_data)

    def _create_optimized_strategy_prompt(self, portfolio_data: dict, market_context: str) -> str:
        """Create optimized AI prompt for maximum returns"""
        total_value = portfolio_data.get('total_portfolio_value', 0)
        available_cash = portfolio_data.get('total_cash', 0)
        current_yield = portfolio_data.get('total_yield_percentage', 0)
        
        prompt = f"""
ТЫ - АГРЕССИВНЫЙ АЛГОРИТМИЧЕСКИЙ ТРЕЙДЕР С ФОКУСОМ НА МАКСИМАЛЬНУЮ ДОХОДНОСТЬ.
ЦЕЛЬ: МАКСИМИЗИРОВАТЬ ДОХОДНОСТЬ ПОРТФЕЛЯ В КРАТКОСРОЧНОЙ ПЕРСПЕКТИВЕ.

КРИТИЧЕСКИЕ ДАННЫЕ ПОРТФЕЛЯ:
- Общая стоимость: {total_value:,.0f} руб.
- Доступные средства: {available_cash:,.0f} руб.
- Текущая доходность: {current_yield:.1f}%
- Количество счетов: {portfolio_data.get('account_count', 1)}

ДЕТАЛЬНЫЙ АНАЛИЗ ПОЗИЦИЙ:
"""
        
        total_positions_value = 0
        for account in portfolio_data.get('accounts', []):
            for position in account.get('positions', []):
                position_value = position.get('value', 0)
                total_positions_value += position_value
                yield_pct = position.get('yield_percentage', 0)
                
                prompt += f"- {position['name']} ({position['ticker']}): "
                prompt += f"{position['quantity']} шт. × {position['current_price']:.2f} руб. = "
                prompt += f"{position_value:,.0f} руб. (доходность: {yield_pct:+.1f}%)\n"

        # Calculate cash percentage
        cash_percentage = (available_cash / total_value * 100) if total_value > 0 else 0
        prompt += f"\nАНАЛИЗ ЭФФЕКТИВНОСТИ:\n"
        prompt += f"- Денежные средства: {cash_percentage:.1f}% (неэффективное использование)\n"
        prompt += f"- Инвестированные средства: {100 - cash_percentage:.1f}%\n"

        prompt += f"""
АКТУАЛЬНЫЙ РЫНОЧНЫЙ КОНТЕКСТ:
{market_context if market_context else "Российский рынок - поиск максимальной доходности"}

СГЕНЕРИРУЙ АГРЕССИВНУЮ ТОРГОВУЮ СТРАТЕГИЮ ДЛЯ МАКСИМАЛЬНОЙ ДОХОДНОСТИ.

ТРЕБОВАНИЯ К СТРАТЕГИИ:
1. Минимизация денежных средств (<5%)
2. Фокус на высокодоходные акции роста
3. Активная ротация позиций
4. Умеренный-высокий уровень риска
5. Целевая доходность: 15-25% годовых

ФОРМАТ ОТВЕТА (JSON):
{{
    "strategy_name": "Агрессивная стратегия максимизации доходности",
    "target_return": 20.5,
    "risk_level": "high",
    "time_horizon": "1-2 months",
    "max_portfolio_utilization": 95.0,
    "actions": [
        {{
            "action": "BUY/SELL",
            "ticker": "SBER",
            "quantity": 15,
            "current_price": 300.0,
            "reason": "Высокая ликвидность и потенциал роста на 15%",
            "expected_impact": "увеличение доходности портфеля на 3.2%",
            "urgency": "high",
            "confidence": 0.85
        }}
    ],
    "portfolio_optimization": {{
        "target_allocation": {{
            "high_growth_stocks": 70.0,
            "dividend_stocks": 15.0,
            "bonds": 5.0,
            "cash": 5.0
        }},
        "sector_focus": {{
            "technology": 35.0,
            "finance": 25.0,
            "energy": 20.0,
            "consumer": 15.0
        }}
    }},
    "risk_management": {{
        "stop_loss_level": 12.0,
        "take_profit_level": 35.0,
        "max_position_size": 20.0,
        "daily_loss_limit": 3.0
    }},
    "performance_metrics": {{
        "expected_sharpe_ratio": 1.8,
        "max_drawdown": 15.0,
        "volatility": 25.0
    }}
}}

Будь агрессивен в рекомендациях! Фокус на максимальную доходность!
        """
        
        return prompt

    def _parse_optimized_strategy_response(self, response: str, portfolio_data: dict) -> Dict:
        """Parse AI strategy response with quality validation"""
        try:
            # Try to extract JSON from response
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                strategy_json = json_match.group(0)
                strategy = json.loads(strategy_json)
                
                # Enhance strategy with additional data
                strategy = self._enhance_strategy_with_portfolio_data(strategy, portfolio_data)
                return strategy
            else:
                # Fallback to structured response parsing
                return self._parse_structured_optimized_response(response, portfolio_data)
                
        except Exception as e:
            logger.error(f"Optimized strategy parsing error: {e}")
            return None

    def _enhance_strategy_with_portfolio_data(self, strategy: Dict, portfolio_data: dict) -> Dict:
        """Enhance strategy with portfolio-specific data"""
        total_value = portfolio_data.get('total_portfolio_value', 0)
        available_cash = portfolio_data.get('total_cash', 0)
        
        # Calculate realistic quantities based on portfolio size
        if 'actions' in strategy:
            for action in strategy['actions']:
                if 'quantity' in action and 'current_price' in action:
                    # Ensure quantity is realistic for portfolio size
                    position_value = action['quantity'] * action['current_price']
                    max_position_value = total_value * 0.15  # Max 15% per position
                    
                    if position_value > max_position_value:
                        # Adjust quantity to fit portfolio constraints
                        new_quantity = int(max_position_value / action['current_price'])
                        action['quantity'] = max(new_quantity, 1)
                        action['reason'] += " (скорректировано под размер портфеля)"
        
        # Add portfolio context
        strategy['portfolio_context'] = {
            'total_value': total_value,
            'available_cash': available_cash,
            'account_count': portfolio_data.get('account_count', 1),
            'optimization_timestamp': datetime.now().isoformat()
        }
        
        return strategy

    def _validate_strategy_quality(self, strategy: Dict) -> bool:
        """Validate strategy quality and completeness"""
        try:
            required_fields = ['strategy_name', 'target_return', 'risk_level', 'actions']
            for field in required_fields:
                if field not in strategy:
                    logger.warning(f"Strategy missing required field: {field}")
                    return False
            
            # Validate actions
            if not isinstance(strategy['actions'], list):
                return False
                
            # Validate target return is realistic but ambitious
            target_return = strategy.get('target_return', 0)
            if target_return < 5 or target_return > 50:  # 5% to 50% range
                logger.warning(f"Unrealistic target return: {target_return}%")
                return False
                
            return True
            
        except Exception as e:
            logger.error(f"Strategy validation error: {e}")
            return False

    async def _generate_optimized_fallback_strategy(self, portfolio_data: dict) -> Dict:
        """Generate optimized fallback portfolio strategy for maximum returns"""
        logger.info("Using optimized fallback portfolio strategy")
        
        total_value = portfolio_data.get('total_portfolio_value', 1000000)
        available_cash = portfolio_data.get('total_cash', 100000)
        
        # Calculate aggressive position sizes
        base_position_size = total_value * 0.08  # 8% per position
        
        return {
            "strategy_name": "Агрессивная стратегия роста",
            "target_return": 18.5,
            "risk_level": "high",
            "time_horizon": "1-3 months",
            "max_portfolio_utilization": 92.0,
            "actions": [
                {
                    "action": "BUY",
                    "ticker": "YNDX",
                    "quantity": max(1, int(base_position_size * 0.6 / 3500)),  # 60% of base size
                    "current_price": 3500.0,
                    "reason": "Лидер IT сектора с высоким потенциалом роста",
                    "expected_impact": "Потенциальный рост 20-30%",
                    "urgency": "high",
                    "confidence": 0.8
                },
                {
                    "action": "BUY",
                    "ticker": "TCSG", 
                    "quantity": max(1, int(base_position_size * 0.4 / 3500)),  # 40% of base size
                    "current_price": 3500.0,
                    "reason": "Финансовый технологический лидер",
                    "expected_impact": "Дивиденды + рост капитализации",
                    "urgency": "high",
                    "confidence": 0.75
                },
                {
                    "action": "SELL",
                    "ticker": "GAZP",
                    "quantity": 50,
                    "current_price": 160.0,
                    "reason": "Низкая динамика и доходность",
                    "expected_impact": "Высвобождение капитала для роста",
                    "urgency": "medium",
                    "confidence": 0.7
                }
            ],
            "portfolio_optimization": {
                "target_allocation": {
                    "high_growth_stocks": 65.0,
                    "dividend_stocks": 20.0,
                    "bonds": 5.0,
                    "cash": 8.0
                },
                "sector_focus": {
                    "technology": 40.0,
                    "finance": 30.0,
                    "energy": 15.0,
                    "consumer": 10.0
                }
            },
            "risk_management": {
                "stop_loss_level": 10.0,
                "take_profit_level": 30.0,
                "max_position_size": 15.0,
                "daily_loss_limit": 2.5
            },
            "performance_metrics": {
                "expected_sharpe_ratio": 1.6,
                "max_drawdown": 18.0,
                "volatility": 22.0
            },
            "portfolio_context": {
                "total_value": total_value,
                "available_cash": available_cash,
                "account_count": portfolio_data.get('account_count', 1),
                "optimization_timestamp": datetime.now().isoformat(),
                "fallback_strategy": True
            }
        }

    async def generate_response(self, prompt: str, context: str = "") -> str:
        """Generate AI response using best available provider"""
        # Try active provider first
        if self.active_provider in self.providers and self.active_provider != "fallback":
            try:
                provider = self.providers[self.active_provider]
                response = await provider.generate_response(prompt, context)
                if not self._is_error_response(response):
                    return response
            except Exception as e:
                logger.error(f"{self.active_provider} response error: {e}")

        # Try other providers
        for provider_name, provider in self.providers.items():
            if provider_name != self.active_provider:
                try:
                    response = await provider.generate_response(prompt, context)
                    if not self._is_error_response(response):
                        self.active_provider = provider_name
                        return response
                except Exception as e:
                    logger.error(f"{provider_name} response error: {e}")

        # Fallback to basic AI
        fallback = await self._get_fallback()
        return await fallback.generate_response(prompt, context)

    def _is_error_response(self, response: str) -> bool:
        """Check if response indicates an error"""
        if not response or not isinstance(response, str):
            return True
            
        error_indicators = [
            'недоступен', 'ошибка', 'error', '❌', 'ключ', 
            'средств', 'лимит', 'invalid', 'authentication',
            'ssl', 'certificate', 'таймаут', 'timeout', 'connection'
        ]
        
        response_lower = response.lower()
        return any(indicator in response_lower for indicator in error_indicators)

    def get_provider_info(self) -> dict:
        """Get information about available providers"""
        return {
            "active_provider": self.active_provider,
            "available_providers": list(self.providers.keys()),
            "fallback_available": True,
            "providers_count": len(self.providers),
            "initialized": self.initialized
        }

    async def close(self):
        """Close all provider sessions"""
        for provider_name, provider in self.providers.items():
            if hasattr(provider, 'close'):
                try:
                    await provider.close()
                    logger.info(f"Closed {provider_name} session")
                except Exception as e:
                    logger.error(f"Error closing {provider_name}: {e}")

# Global instance
_ai_manager: Optional[AIManager] = None

async def get_ai_manager():
    """Get AI manager instance"""
    global _ai_manager
    if _ai_manager is None:
        _ai_manager = AIManager()
    return _ai_manager