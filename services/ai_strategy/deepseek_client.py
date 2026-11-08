import aiohttp
import json
import logging
import re
import asyncio
from typing import Dict, Any, Optional

# Используем настройки из app.settings вместо config.deepseek
from app.settings import settings

logger = logging.getLogger(__name__)

class DeepSeekClient:
    """Клиент для работы с DeepSeek API"""
    
    def __init__(self):
        self.api_key = settings.DEEPSEEK_API_KEY
        self.base_url = settings.DEEPSEEK_API_URL
        self.timeout = aiohttp.ClientTimeout(total=30)
        
    async def analyze_investment_portfolio(self, portfolio_data: Dict, market_data: Dict) -> Dict[str, Any]:
        """
        Анализ инвестиционного портфеля с помощью AI
        """
        if not self._validate_api_key():
            return {"error": "DeepSeek API key not configured"}
            
        prompt = self._build_portfolio_analysis_prompt(portfolio_data, market_data)
        return await self._make_request(prompt)
    
    async def analyze_market_conditions(self) -> Dict[str, Any]:
        """
        Анализ текущих рыночных условий
        """
        if not self._validate_api_key():
            return {"error": "DeepSeek API key not configured"}
            
        prompt = """
        Ты - ведущий финансовый аналитик. Проанализируй текущую ситуацию 
        на финансовых рынках (российский и международный) и дай оценку.

        Верни JSON в формате:
        {
            "market_sentiment": "bullish|bearish|neutral",
            "confidence_level": 0.85,
            "key_drivers": ["фактор1", "фактор2", "фактор3"],
            "sector_analysis": {
                "technology": "positive|negative|neutral",
                "finance": "positive|negative|neutral", 
                "energy": "positive|negative|neutral",
                "healthcare": "positive|negative|neutral"
            },
            "risk_assessment": "low|medium|high",
            "recommended_actions": ["действие1", "действие2"],
            "market_commentary": "развернутый анализ ситуации"
        }

        Будь конкретен и опирайся на реальные рыночные данные.
        """
        return await self._make_request(prompt)
    
    def _validate_api_key(self) -> bool:
        """Validate API key"""
        return bool(self.api_key and self.api_key != "your_deepseek_api_key_here")
    
    def _build_portfolio_analysis_prompt(self, portfolio_data: Dict, market_data: Dict) -> str:
        """Построение промпта для анализа портфеля"""
        # Safe JSON serialization
        try:
            portfolio_json = json.dumps(portfolio_data, ensure_ascii=False, indent=2, default=str)
            market_json = json.dumps(market_data, ensure_ascii=False, indent=2, default=str)
        except (TypeError, ValueError) as e:
            logger.error(f"JSON serialization error: {e}")
            portfolio_json = "{}"
            market_json = "{}"

        return f"""
        Ты - опытный портфельный управляющий с 15-летним стажем. 
        Проанализируй предоставленный инвестиционный портфель и дай конкретные рекомендации.

        ДАННЫЕ ПОРТФЕЛЯ:
        {portfolio_json}

        РЫНОЧНЫЕ ДАННЫЕ:
        {market_json}

        Сгенерируй детальный JSON ответ со следующей структурой:
        {{
            "portfolio_health": {{
                "overall_score": 85,
                "diversification_score": 90,
                "risk_score": 75,
                "liquidity_score": 80
            }},
            "market_analysis": {{
                "current_sentiment": "bullish|bearish|neutral",
                "risk_level": "low|medium|high",
                "opportunities": ["возможность1", "возможность2"],
                "threats": ["угроза1", "угроза2"]
            }},
            "rebalancing_recommendations": {{
                "priority": "high|medium|low",
                "actions": [
                    {{
                        "ticker": "XXX",
                        "action": "buy|sell|hold",
                        "amount_percent": 5.0,
                        "urgency": "high|medium|low",
                        "reason": "детальное обоснование"
                    }}
                ],
                "target_allocation": {{
                    "stocks": 60.0,
                    "bonds": 25.0,
                    "cash": 10.0,
                    "other": 5.0
                }}
            }},
            "risk_management": {{
                "suggested_stop_loss": 8.0,
                "position_sizing_rules": "правила управления позициями",
                "hedging_suggestions": ["хеджирование1", "хеджирование2"]
            }}
        }}

        Будь максимально конкретным. Используй реальные цифры и давай actionable рекомендации.
        Учитывай диверсификацию, риск-профиль и рыночные условия.
        """

    async def _make_request(self, prompt: str) -> Dict[str, Any]:
        """
        Выполнение запроса к DeepSeek API
        """
        if not self._validate_api_key():
            return {"error": "DeepSeek API key not configured"}

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": "deepseek-chat",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3,
            "max_tokens": 4000,
            "stream": False
        }
        
        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                async with session.post(f"{self.base_url}/chat/completions", headers=headers, json=payload) as response:
                    if response.status == 200:
                        result = await response.json()
                        return self._parse_response(result)
                    else:
                        error_text = await response.text()
                        logger.error(f"DeepSeek API error {response.status}: {error_text}")
                        return {"error": f"API error {response.status}"}
                        
        except asyncio.TimeoutError:
            logger.error("DeepSeek API request timeout")
            return {"error": "Request timeout"}
        except aiohttp.ClientError as e:
            logger.error(f"DeepSeek API request failed: {e}")
            return {"error": f"Request failed: {str(e)}"}
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            return {"error": f"Unexpected error: {str(e)}"}
    
    def _parse_response(self, response: Dict) -> Dict[str, Any]:
        """
        Парсинг ответа от DeepSeek API
        """
        try:
            if 'choices' not in response or not response['choices']:
                return {"error": "Invalid API response format"}
                
            content = response['choices'][0]['message']['content']
            
            # Очистка и извлечение JSON
            cleaned_content = self._extract_json(content)
            
            if cleaned_content:
                return json.loads(cleaned_content)
            else:
                logger.error("No JSON found in AI response")
                return {"error": "No valid JSON in response", "raw_response": content}
                
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error: {e}")
            return {"error": f"JSON decode error: {str(e)}"}
        except KeyError as e:
            logger.error(f"Missing key in response: {e}")
            return {"error": f"Invalid response format: {str(e)}"}
        except Exception as e:
            logger.error(f"Response parsing error: {e}")
            return {"error": f"Parsing error: {str(e)}"}
    
    def _extract_json(self, text: str) -> Optional[str]:
        """Извлечение JSON из текста ответа"""
        if not text:
            return None
            
        # Попытка найти JSON в блоках кода
        json_match = re.search(r'```json\n(.*?)\n```', text, re.DOTALL)
        if json_match:
            return json_match.group(1)
        
        # Попытка найти JSON в обычных блоках
        code_match = re.search(r'```\n(.*?)\n```', text, re.DOTALL)
        if code_match:
            return code_match.group(1)
        
        # Попытка найти JSON объект напрямую
        brace_match = re.search(r'\{.*\}', text, re.DOTALL)
        if brace_match:
            return brace_match.group(0)
        
        return None