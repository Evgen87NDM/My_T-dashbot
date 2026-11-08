import logging
import aiohttp
import json
from decimal import Decimal
from typing import Dict, List, Optional
from datetime import datetime
import re

logger = logging.getLogger(__name__)


class AutoPortfolioManager:
    """Автоматическое управление портфелем через DeepSeek AI"""
    
    def __init__(self, config):
        self.config = config
        self.api_key = config.DEEPSEEK_API_KEY
        self.api_url = config.DEEPSEEK_API_URL
        self.russian_instruments = self._load_russian_instruments()
        
    def _load_russian_instruments(self) -> Dict:
        """Загрузка списка российских инструментов"""
        return {
            "stocks": {
                "SBER": {"name": "Сбербанк", "sector": "Финансы"},
                "VTBR": {"name": "ВТБ", "sector": "Финансы"},
                "GAZP": {"name": "Газпром", "sector": "Энергетика"},
                "LKOH": {"name": "Лукойл", "sector": "Энергетика"},
                "ROSN": {"name": "Роснефть", "sector": "Энергетика"},
                "YNDX": {"name": "Яндекс", "sector": "IT"},
                "TCSG": {"name": "TCS Group", "sector": "Финансы"},
                "GMKN": {"name": "ГМК Норникель", "sector": "Металлургия"},
                "POLY": {"name": "Полиметалл", "sector": "Металлургия"},
                "MOEX": {"name": "Московская биржа", "sector": "Финансы"},
                "AFKS": {"name": "АФК Система", "sector": "Холдинги"},
                "MTSS": {"name": "МТС", "sector": "Телеком"},
                "MGNT": {"name": "Магнит", "sector": "Ритейл"},
                "RTKM": {"name": "Ростелеком", "sector": "Телеком"},
                "HYDR": {"name": "РусГидро", "sector": "Энергетика"},
                "FEES": {"name": "ФСК ЕЭС", "sector": "Энергетика"},
                "TRNFP": {"name": "Транснефть", "sector": "Энергетика"},
            },
            "bonds": {
                "SU26230": {"name": "ОФЗ-26230", "type": "гос. облигации"},
                "SU26238": {"name": "ОФЗ-26238", "type": "гос. облигации"},
                "SU26242": {"name": "ОФЗ-26242", "type": "гос. облигации"},
                "RU000A105UY6": {"name": "ОФЗ-29021", "type": "гос. облигации"},
                "RU000A106UY5": {"name": "ОФЗ-29022", "type": "гос. облигации"},
            }
        }
        
    async def generate_trading_decisions(self, portfolio_data: Dict, market_context: str = "") -> List[Dict]:
        """Генерация торговых решений через AI"""
        try:
            # Получаем решения от AI
            ai_decisions = await self._get_ai_trading_decisions(portfolio_data, market_context)
            if ai_decisions:
                logger.info(f"AI generated {len(ai_decisions)} trading decisions")
                return ai_decisions
            else:
                logger.warning("AI не смог сгенерировать торговые решения")
                return []
            
        except Exception as e:
            logger.error(f"Error generating trading decisions: {e}")
            return []
    
    async def _get_ai_trading_decisions(self, portfolio_data: Dict, market_context: str) -> List[Dict]:
        """Получение торговых решений от AI"""
        try:
            analysis_prompt = self._create_analysis_prompt(portfolio_data, market_context)
            ai_response = await self._get_ai_trading_advice(analysis_prompt)
            
            if ai_response:
                decisions = self._parse_trading_decisions(ai_response, portfolio_data)
                if decisions:
                    return decisions
            
            return []
            
        except Exception as e:
            logger.error(f"Error in AI trading decisions: {e}")
            return []
    
    def _create_analysis_prompt(self, portfolio_data: Dict, market_context: str) -> str:
        """Создает промпт для анализа и принятия решений"""
        
        prompt = f"""АНАЛИЗ ПОРТФЕЛЯ ДЛЯ АВТОМАТИЧЕСКОЙ ТОРГОВЛИ:

ДАННЫЕ ПОРТФЕЛЯ:
{self._format_portfolio_for_ai(portfolio_data)}

ДОСТУПНЫЕ ИНСТРУМЕНТЫ:
{self._format_available_instruments()}

РЫНОЧНЫЙ КОНТЕКСТ:
{market_context if market_context else "Российский рынок акций и облигаций"}

ЗАДАЧА: Проанализируй текущий портфель и сгенерируй 3-5 конкретных торговых решений для оптимизации и максимизации доходности.

КРИТЕРИИ АНАЛИЗА:
1. Диверсификация по секторам
2. Баланс между риском и доходностью  
3. Текущая доходность позиций
4. Доступные средства для инвестиций
5. Рыночные тенденции

ФОРМАТ ОТВЕТА (строго соблюдай):
BUY/SELL [ТИКЕР] [СУММА_В_РУБЛЯХ] [КРАТКОЕ_ОБОСНОВАНИЕ] [ОЖИДАЕМАЯ_ДОХОДНОСТЬ%]

ПРИМЕРЫ:
BUY YNDX 15000 РОСТ_IT_СЕКТОРА_И_ВЫСОКАЯ_ДОХОДНОСТЬ 18.5
SELL GAZP 8000 СТАГНАЦИЯ_ЭНЕРГЕТИКИ_И_НИЗКАЯ_ДОХОДНОСТЬ 5.2
BUY SU26230 12000 ДИВЕРСИФИКАЦИЯ_И_ЗАЩИТА_КАПИТАЛА 8.5

РЕШЕНИЯ:"""
        
        return prompt
    
    def _format_available_instruments(self) -> str:
        """Форматирует список доступных инструментов"""
        text = "АКЦИИ:\n"
        for ticker, info in self.russian_instruments["stocks"].items():
            text += f"- {ticker}: {info['name']} ({info['sector']})\n"
        
        text += "\nОБЛИГАЦИИ:\n"
        for ticker, info in self.russian_instruments["bonds"].items():
            text += f"- {ticker}: {info['name']}\n"
            
        return text
    
    async def _get_ai_trading_advice(self, prompt: str) -> str:
        """Получает торговые рекомендации от DeepSeek AI"""
        if not self.api_key:
            logger.warning("DeepSeek API key not configured")
            return ""
            
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": "deepseek-chat",
            "messages": [
                {
                    "role": "system", 
                    "content": """Ты - профессиональный алгоритмический торговый робот для российского рынка. 

ТВОЯ ЗАДАЧА: Анализировать данные портфеля и генерировать КОНКРЕТНЫЕ торговые решения.

ПРАВИЛА:
1. Используй ТОЛЬКО российские инструменты из предоставленного списка
2. Генерируй 3-5 решений максимум
3. Суммы должны быть реалистичными относительно доступных средств
4. Учитывай диверсификацию и риск-профиль
5. Обоснование должно быть кратким и конкретным
6. Указывай реалистичную ожидаемую доходность

ФОРМАТ СТРОГО:
ACTION TICKER AMOUNT RATIONALE EXPECTED_YIELD%

Не добавляй никаких пояснений, только список решений."""
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "max_tokens": 1000,
            "temperature": 0.3,
            "stream": False
        }
        
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
                async with session.post(
                    f"{self.api_url}/chat/completions",
                    json=payload,
                    headers=headers
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        content = data['choices'][0]['message']['content']
                        logger.info(f"AI Response: {content}")
                        return content
                    else:
                        error_text = await response.text()
                        logger.error(f"AI API error: {response.status} - {error_text}")
                        return ""
        except Exception as e:
            logger.error(f"AI request failed: {e}")
            return ""
    
    def _format_portfolio_for_ai(self, portfolio: Dict) -> str:
        """Форматирует данные портфеля для AI"""
        text = f"💰 Общая стоимость: {portfolio['total_value']:,.0f} ₽\n"
        text += f"📈 Общая доходность: {portfolio['total_yield']:+,.0f} ₽ ({portfolio['yield_percentage']:+.1f}%)\n"
        text += f"💳 Доступные средства: {portfolio['available_cash']:,.0f} ₽\n\n"
        
        text += "📊 Текущие позиции:\n"
        for position in portfolio['positions']:
            text += f"- {position['name']} ({position['ticker']}): {position['value']:,.0f} ₽ "
            text += f"(доходность: {position['percentage']:+.1f}%)\n"
        
        allocation = self._calculate_allocation(portfolio['positions'])
        text += f"\n🎯 Распределение:\n"
        for asset_type, percentage in allocation.items():
            text += f"- {asset_type}: {percentage:.1f}%\n"
            
        sectors = self._analyze_sectors(portfolio['positions'])
        text += f"\n🏢 Секторальное распределение:\n"
        for sector, percentage in sectors.items():
            text += f"- {sector}: {percentage:.1f}%\n"
            
        return text
    
    def _parse_trading_decisions(self, ai_response: str, portfolio_data: Dict) -> List[Dict]:
        """Парсит торговые решения из AI ответа"""
        decisions = []
        lines = ai_response.split('\n')
        
        for line in lines:
            line = line.strip()
            if not line or line.startswith('#') or 'ПРИМЕР' in line.upper():
                continue
                
            # Пробуем разные форматы парсинга
            decision = self._parse_decision_line(line, portfolio_data)
            if decision:
                decisions.append(decision)
        
        logger.info(f"Parsed {len(decisions)} decisions from AI response")
        return decisions
    
    def _parse_decision_line(self, line: str, portfolio_data: Dict) -> Optional[Dict]:
        """Парсит одну строку с решением"""
        try:
            # Упрощенный парсинг для разных форматов
            parts = line.upper().split()
            if len(parts) < 4:
                return None
                
            # Ищем действие
            action = None
            if 'BUY' in parts[0]:
                action = 'BUY'
            elif 'SELL' in parts[0]:
                action = 'SELL'
            else:
                return None
            
            # Ищем тикер (второй элемент или следующий после действия)
            ticker = parts[1] if len(parts[1]) <= 10 else None
            if not ticker or ticker not in self._get_all_tickers():
                # Пробуем найти тикер в строке
                for part in parts[2:6]:
                    if part in self._get_all_tickers():
                        ticker = part
                        break
            
            if not ticker:
                return None
            
            # Ищем сумму
            amount = self._extract_amount(line, portfolio_data['available_cash'])
            if amount <= 0:
                return None
            
            # Ищем доходность
            expected_yield = self._extract_yield(line)
            
            # Обоснование - остальная часть строки
            rationale_start = 2
            for i, part in enumerate(parts[2:], 2):
                if part.replace('₽', '').replace(',', '').replace('.', '').isdigit():
                    rationale_start = i + 1
                    break
            
            rationale_parts = parts[rationale_start:]
            rationale = ' '.join(rationale_parts)
            
            # Убираем процент доходности из обоснования
            rationale = re.sub(r'\d+\.?\d*%', '', rationale).strip()
            
            if not rationale:
                rationale = "Оптимизация портфеля"
            
            return {
                'action': action,
                'ticker': ticker,
                'amount': amount,
                'rationale': rationale,
                'expected_yield': expected_yield,
                'source': 'ai',
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error parsing decision line: {line} - {e}")
            return None
    
    def _get_all_tickers(self) -> set:
        """Возвращает все доступные тикеры"""
        tickers = set(self.russian_instruments["stocks"].keys())
        tickers.update(self.russian_instruments["bonds"].keys())
        return tickers
    
    def _extract_amount(self, text: str, available_cash: Decimal) -> Decimal:
        """Извлекает сумму из текста"""
        try:
            # Ищем числа с символами валюты
            matches = re.findall(r'(\d+[,\.]?\d*)\s*₽?', text)
            for match in matches:
                amount_str = match.replace(',', '').replace('.', '')
                amount = Decimal(amount_str)
                # Проверяем что сумма разумная (не больше 80% доступных средств)
                if amount > 0 and amount <= available_cash * Decimal('0.8'):
                    return amount
        except:
            pass
        
        return Decimal('0')
    
    def _extract_yield(self, text: str) -> float:
        """Извлекает ожидаемую доходность из текста"""
        try:
            matches = re.findall(r'(\d+[,\.]?\d*)%', text)
            if matches:
                yield_value = float(matches[0].replace(',', '.'))
                # Проверяем разумные пределы
                if -50 <= yield_value <= 100:
                    return yield_value
        except:
            pass
        
        return 0.0
    
    def _calculate_allocation(self, positions: List[Dict]) -> Dict[str, float]:
        """Рассчитывает распределение активов"""
        allocation = {}
        total_value = sum(pos['value'] for pos in positions)
        
        if total_value == 0:
            return {}
            
        for position in positions:
            asset_type = "Акции" if position['type'] == 'stock' else "Облигации"
            if asset_type not in allocation:
                allocation[asset_type] = 0
            allocation[asset_type] += float((position['value'] / total_value * 100))
                
        return allocation
    
    def _analyze_sectors(self, positions: List[Dict]) -> Dict[str, float]:
        """Анализ распределения по секторам"""
        sectors = {}
        total_value = sum(pos['value'] for pos in positions)
        
        if total_value == 0:
            return {}
            
        for position in positions:
            sector = position.get('sector', 'Другое')
            if sector not in sectors:
                sectors[sector] = 0
            sectors[sector] += float((position['value'] / total_value * 100))
                
        return sectors