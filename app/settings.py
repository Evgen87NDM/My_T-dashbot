"""
Application settings with simplified REAL/SANDBOX modes
"""
import os
import logging
from typing import List

logger = logging.getLogger(__name__)

class Settings:
    """Application settings with simplified modes"""
    
    def __init__(self):
        self._load_env_file()
        self._setup_telegram()
        self._setup_tinkoff()
        self._setup_ai()
        self._setup_trading()
        self._validate_settings()

    def _load_env_file(self):
        """Load environment variables from .env file"""
        try:
            from dotenv import load_dotenv
            load_dotenv()
            logger.info("✅ .env file loaded successfully")
        except ImportError:
            logger.error("❌ python-dotenv not installed! Please run: pip install python-dotenv")
        except Exception as e:
            logger.error(f"❌ Error loading .env file: {e}")

    def _setup_telegram(self):
        """Setup Telegram settings"""
        self.TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
        if not self.TELEGRAM_BOT_TOKEN:
            raise ValueError("TELEGRAM_BOT_TOKEN is required!")

    def _setup_tinkoff(self):
        """Setup Tinkoff Invest API settings - ONLY REAL and SANDBOX"""
        # Real trading token
        self.TINKOFF_TOKEN: str = os.getenv("TINKOFF_TOKEN", "")
        
        # Sandbox token
        self.TINKOFF_TOKEN_SANDBOX: str = os.getenv("TINKOFF_TOKEN_SANDBOX", "")
        
        self.TINKOFF_APP_NAME: str = os.getenv("TINKOFF_APP_NAME", "InvestmentAdvisor")
        
        # Mode handling - ONLY REAL and SANDBOX
        tinkoff_sandbox = os.getenv("TINKOFF_SANDBOX", "").lower()
        
        if tinkoff_sandbox in ["true", "1", "yes"]:
            self.TINKOFF_SANDBOX_MODE = True
            if not self.TINKOFF_TOKEN_SANDBOX:
                raise ValueError("TINKOFF_TOKEN_SANDBOX is required for sandbox mode!")
            logger.info("🔧 Режим: TINKOFF SANDBOX")
        else:
            self.TINKOFF_SANDBOX_MODE = False
            if not self.TINKOFF_TOKEN:
                raise ValueError("TINKOFF_TOKEN is required for real mode!")
            logger.info("🔧 Режим: REAL TINKOFF API")

    def _setup_ai(self):
        """Setup AI settings"""
        self.DEEPSEEK_API_KEY: str = os.getenv("DEEPSEEK_API_KEY", "")
        self.DEEPSEEK_API_URL: str = os.getenv("DEEPSEEK_API_URL", "https://api.deepseek.com/v1")
        self.OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "")
        self.OPENROUTER_API_URL: str = os.getenv("OPENROUTER_API_URL", "https://openrouter.ai/api/v1")
        
        if not self.DEEPSEEK_API_KEY and not self.OPENROUTER_API_KEY:
            logger.warning("❌ No AI API keys configured - AI portfolio management will not work")

    def _setup_trading(self):
        """Setup trading settings"""
        # Trading mode: manual (with confirmation) or auto (fully automated)
        trading_mode = os.getenv("TRADING_MODE", "manual").lower()
        self.AUTO_TRADING_MODE = trading_mode in ["auto", "automatic", "true", "1"]
        
        if self.AUTO_TRADING_MODE:
            logger.info("🤖 Режим торговли: ПОЛНОСТЬЮ АВТОМАТИЧЕСКИЙ")
        else:
            logger.info("🤖 Режим торговли: С РУЧНЫМ ПОДТВЕРЖДЕНИЕМ")

    def _validate_settings(self):
        """Validate critical settings"""
        if not self.TELEGRAM_BOT_TOKEN:
            raise ValueError("TELEGRAM_BOT_TOKEN is required!")
        
        if self.TINKOFF_SANDBOX_MODE and not self.TINKOFF_TOKEN_SANDBOX:
            raise ValueError("TINKOFF_TOKEN_SANDBOX is required for sandbox mode!")
        elif not self.TINKOFF_SANDBOX_MODE and not self.TINKOFF_TOKEN:
            raise ValueError("TINKOFF_TOKEN is required for real mode!")

    def get_tinkoff_token(self):
        """Get appropriate Tinkoff token based on mode"""
        if self.TINKOFF_SANDBOX_MODE:
            return self.TINKOFF_TOKEN_SANDBOX
        else:
            return self.TINKOFF_TOKEN

    def is_real_client(self):
        """Check if using real Tinkoff client"""
        return not self.TINKOFF_SANDBOX_MODE

# Create settings instance
settings = Settings()