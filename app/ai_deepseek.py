"""
DeepSeek AI integration with SSL fix
"""
import os
import logging
import aiohttp
import asyncio
import ssl
import certifi
from typing import Optional

logger = logging.getLogger(__name__)

class DeepSeekAI:
    """DeepSeek AI client with SSL fix"""
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv('DEEPSEEK_API_KEY')
        self.base_url = "https://api.deepseek.com/v1"
        self.session: Optional[aiohttp.ClientSession] = None
        
        if not self.api_key:
            logger.warning("DEEPSEEK_API_KEY not set")
    
    async def __aenter__(self):
        # Create SSL context with certificate verification
        ssl_context = ssl.create_default_context(cafile=certifi.where())
        connector = aiohttp.TCPConnector(ssl=ssl_context)
        self.session = aiohttp.ClientSession(connector=connector)
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def generate_response(self, prompt: str, context: str = "") -> str:
        """Generate AI response using DeepSeek API"""
        if not self.api_key:
            logger.error("No DeepSeek API key available")
            return "❌ Сервис AI временно недоступен. Проверьте настройки API."
        
        if not self.session:
            # Lazy initialization with SSL context
            ssl_context = ssl.create_default_context(cafile=certifi.where())
            connector = aiohttp.TCPConnector(ssl=ssl_context)
            self.session = aiohttp.ClientSession(connector=connector)
        
        # Prepare the full prompt with context
        full_prompt = f"""
        {context}
        
        Пользователь спрашивает: {prompt}
        
        Ответь кратко и по делу на русском языке.
        """
        
        data = {
            "model": "deepseek-chat",
            "messages": [
                {
                    "role": "system", 
                    "content": "Ты - профессиональный инвестиционный советник. Отвечай точно и полезно."
                },
                {
                    "role": "user",
                    "content": full_prompt.strip()
                }
            ],
            "max_tokens": 500,
            "temperature": 0.7,
            "stream": False
        }
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        
        try:
            logger.info(f"Sending request to DeepSeek API: {prompt[:50]}...")
            
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
                        logger.info(f"DeepSeek response received: {message[:100]}...")
                        return message.strip()
                    else:
                        logger.error(f"Unexpected response format: {result}")
                        return "❌ Ошибка формата ответа от AI сервиса."
                
                else:
                    error_text = await response.text()
                    logger.error(f"DeepSeek API error {response.status}: {error_text}")
                    
                    if response.status == 401:
                        return "❌ Неверный API ключ DeepSeek."
                    elif response.status == 402:
                        return "❌ Недостаточно средств на счету DeepSeek."
                    elif response.status == 429:
                        return "❌ Превышен лимит запросов к AI сервису."
                    else:
                        return f"❌ Ошибка AI сервиса: {response.status}"
                        
        except asyncio.TimeoutError:
            logger.error("DeepSeek API timeout")
            return "❌ Таймаут запроса к AI сервису."
        except aiohttp.ClientError as e:
            logger.error(f"DeepSeek connection error: {e}")
            return "❌ Ошибка подключения к AI сервису."
        except Exception as e:
            logger.error(f"Unexpected DeepSeek error: {e}")
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
        
        return await self.generate_response(prompt)


# Install certifi if needed
try:
    import certifi
except ImportError:
    logger.warning("certifi not installed, SSL verification may fail")

# Singleton instance
_deepseek_ai: Optional[DeepSeekAI] = None

async def get_deepseek_ai() -> DeepSeekAI:
    """Get DeepSeek AI instance"""
    global _deepseek_ai
    if _deepseek_ai is None:
        _deepseek_ai = DeepSeekAI()
    return _deepseek_ai


async def test_deepseek():
    """Test function"""
    async with DeepSeekAI() as ai:
        response = await ai.generate_response("Привет! Как дела?")
        print(f"Test response: {response}")


if __name__ == "__main__":
    asyncio.run(test_deepseek())