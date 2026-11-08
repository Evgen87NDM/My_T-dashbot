"""
Tinkoff client loader - ONLY REAL and SANDBOX modes
"""
import logging
from app.settings import settings

logger = logging.getLogger(__name__)

class TinkoffClientManager:
    """Manager for Tinkoff client with ONLY real and sandbox modes"""
    
    def __init__(self):
        self._initialized = False
        self._initialize_client()

    def _initialize_client(self):
        """Initialize Tinkoff client"""
        try:
            token = settings.get_tinkoff_token()
            
            from t_tech.invest import Client
            
            mode = "SANDBOX" if settings.TINKOFF_SANDBOX_MODE else "REAL"
            logger.info(f"🔧 Testing Tinkoff {mode} API connection...")
            
            with Client(token=token, app_name=settings.TINKOFF_APP_NAME) as client:
                accounts = client.users.get_accounts()
                logger.info(f"✅ Tinkoff {mode} connected: {len(accounts.accounts)} accounts")
                
                if settings.TINKOFF_SANDBOX_MODE and not accounts.accounts:
                    logger.info("🔄 Creating sandbox account...")
                    sandbox_account = client.sandbox.open_sandbox_account()
                    logger.info(f"✅ Sandbox account created: {sandbox_account.account_id}")
                elif not accounts.accounts:
                    logger.warning("⚠️ No investment accounts found in real mode")
            
            self._initialized = True
            
        except Exception as e:
            logger.error(f"❌ Tinkoff client initialization error: {e}")
            raise

    def get_client(self):
        """Get a new client instance for each operation"""
        if not self._initialized:
            raise ValueError("Tinkoff client not properly initialized")
        
        token = settings.get_tinkoff_token()
        from t_tech.invest import Client
        return Client(token=token, app_name=settings.TINKOFF_APP_NAME)
    
    def is_real_client(self):
        """Check if using real Tinkoff client"""
        return not settings.TINKOFF_SANDBOX_MODE
    
    def execute_operation(self, operation):
        """Execute operation with proper client management"""
        # Create new client for each operation
        try:
            with self.get_client() as client:
                return operation(client)
        except Exception as e:
            logger.error(f"Tinkoff operation failed: {e}")
            raise

# Global client manager instance
_client_manager = None

def get_tinkoff_client():
    """Get Tinkoff client via manager"""
    global _client_manager
    if _client_manager is None:
        _client_manager = TinkoffClientManager()
    return _client_manager.get_client()

def get_tinkoff_client_manager():
    """Get Tinkoff client manager"""
    global _client_manager
    if _client_manager is None:
        _client_manager = TinkoffClientManager()
    return _client_manager