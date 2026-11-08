"""
OpenRouter AI integration with DeepSeek models and SSL fix
"""
import os
import logging
import aiohttp
import asyncio
import ssl
import certifi
from typing import Optional

logger = logging.getLogger(__name__)

class OpenRouterAI:
    """OpenRouter AI client with DeepSeek models and SSL fix"""
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv('OPENROUTER_API_KEY')
        self.base_url = "https://openrouter.ai/api/v1"
        self.session: Optional[aiohttp.ClientSession] = None
        
        # DeepSeek models available on OpenRouter
        self.available_models = {
            "deepseek-chat": "deepseek/deepseek-chat",
            "deepseek-coder": "deepseek/deepseek-coder", 
        }
        
        if not self.api_key:
            logger.warning("OPENROUTER_API_KEY not set")
        else:
            logger.info("✅ OpenRouter AI initialized")
    
    async def _get_ssl_context(self):
        """Create SSL context with proper certificate verification"""
        try:
            # Use certifi for certificate verification
            ssl_context = ssl.create_default_context(cafile=certifi.where())
            return ssl_context
        except Exception as e:
            logger.warning(f"SSL context creation failed: {e}, using default")
            return ssl.create_default_context()
    
    async def __aenter__(self):
        ssl_context = await self._get_ssl_context()
        connector = aiohttp.TCPConnector(ssl=ssl_context)
        self.session = aiohttp.ClientSession(connector=connector)
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
    
    async def _ensure_session(self):
        """Ensure session exists with SSL context"""
        if self.session is None:
            ssl_context = await self._get_ssl_context()
            connector = aiohttp.TCPConnector(ssl=ssl_context)
            self.session = aiohttp.ClientSession(connector=connector)
    
    async def generate_response(self, prompt: str, context: str = "", model: str = "deepseek-chat") -> str:
        """Generate AI response using OpenRouter"""
        if not self.api_key:
            logger.error("No OpenRouter API key available")
            return "❌ Сервис AI временно недоступен. Проверьте настройки API."
        
        await self._ensure_session()
        
        # Get model ID
        model_id = self.available_models.get(model)
        if not model_id:
            model_id = "deepseek/deepseek-chat"  # Default to DeepSeek Chat
        
        # Prepare the full prompt
        full_prompt = f"""
        Ты - профессиональный инвестиционный советник. Отвечай точно, полезно и на русском языке.
        
        {context}
        
        Вопрос пользователя: {prompt}
        """
        
        data = {
            "model": model_id,
            "messages": [
                {
                    "role": "system",
                    "content": "Ты опытный финансовый консультант и инвестиционный советник. Давай точные, полезные ответы на русском языке. Будь краток и по делу."
                },
                {
                    "role": "user",
                    "content": full_prompt.strip()
                }
            ],
            "max_tokens": 1000,
            "temperature": 0.7,
            "top_p": 0.9,
        }
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "HTTP-Referer": "https://github.com/investment-bot",
            "X-Title": "Investment Advisor Bot"
        }
        
        try:
            logger.info(f"Sending request to OpenRouter ({model}): {prompt[:50]}...")
            
            async with self.session.post(
                f"{self.base_url}/chat/completions",
                json=data,
                headers=headers,
                timeout=30
            ) as response:
                
                if response.status == 200:
                    result = await response.json()
                    
                    if 'choices' in result and len(result['choices']) > 0:
                        message = result['choices'][0]['message']['content']
                        logger.info(f"OpenRouter response received: {message[:100]}...")
                        
                        # Log usage if available
                        if 'usage' in result:
                            usage = result['usage']
                            logger.info(f"Tokens used: {usage.get('total_tokens', 'N/A')}")
                        
                        return message.strip()
                    else:
                        logger.error(f"Unexpected response format: {result}")
                        return "❌ Ошибка формата ответа от AI сервиса."
                
                else:
                    error_text = await response.text()
                    logger.error(f"OpenRouter API error {response.status}: {error_text}")
                    
                    if response.status == 401:
                        return "❌ Неверный API ключ OpenRouter."
                    elif response.status == 402:
                        return "❌ Недостаточно средств на счету OpenRouter."
                    elif response.status == 429:
                        return "❌ Превышен лимит запросов."
                    else:
                        return f"❌ Ошибка AI сервиса: {response.status}"
                        
        except asyncio.TimeoutError:
            logger.error("OpenRouter API timeout")
            return "❌ Таймаут запроса к AI сервису."
        except aiohttp.ClientSSLError as e:
            logger.error(f"OpenRouter SSL error: {e}")
            return "❌ Ошибка SSL соединения. Попробуйте обновить сертификаты."
        except aiohttp.ClientError as e:
            logger.error(f"OpenRouter connection error: {e}")
            return "❌ Ошибка подключения к AI сервису."
        except Exception as e:
            logger.error(f"Unexpected OpenRouter error: {e}")
            return "❌ Непредвиденная ошибка AI сервиса."
    
    async def analyze_portfolio(self, portfolio_data: dict) -> str:
        """Analyze portfolio data using AI"""
        prompt = f"""
        Проанализируй инвестиционный портфель и дай конкретные рекомендации:
        
        ДАННЫЕ ПОРТФЕЛЯ:
        - Общая стоимость: {portfolio_data.get('total_value', 0):,} руб.
        - Акции: {portfolio_data.get('stocks_value', 0):,} руб.
        - Облигации: {portfolio_data.get('bonds_value', 0):,} руб.
        - ETF: {portfolio_data.get('etf_value', 0):,} руб.
        - Количество позиций: {portfolio_data.get('positions_count', 0)}
        
        ПРОАНИЛИЗИРУЙ:
        1. Диверсификацию портфеля
        2. Соотношение риск/доходность  
        3. Конкретные рекомендации по оптимизации
        4. Потенциальные риски
        
        Будь конкретен, полезен и говори на русском.
        """
        
        return await self.generate_response(prompt, model="deepseek-chat")
    
    async def get_market_analysis(self) -> str:
        """Get current market analysis"""
        prompt = """
        Дай краткий и информативный анализ текущей ситуации на финансовых рынках.
        Особое внимание удели:
        - Российскому рынку акций
        - Валютным парам (USD/RUB, EUR/RUB)
        - Ключевым macroeconomic факторам
        - Краткосрочным и долгосрочным трендам
        
        Будь краток, но информативен. Выдели самое важное.
        """
        
        return await self.generate_response(prompt, model="deepseek-chat")
    
    async def close(self):
        """Close session explicitly"""
        if self.session:
            await self.session.close()
            self.session = None
            logger.debug("OpenRouter session closed")


async def test_openrouter():
    """Test function"""
    async with OpenRouterAI() as ai:
        # Test basic response
        response = await ai.generate_response("Привет! Как дела?")
        print(f"Test response: {response}")


if __name__ == "__main__":
    asyncio.run(test_openrouter())