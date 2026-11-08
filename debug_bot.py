#!/usr/bin/env python3
"""
Debug script to find exact issues
"""
import os
import sys
import logging

# Add current directory to path
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

logging.basicConfig(level=logging.DEBUG, format='%(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def debug_components():
    print("🔍 DEBUGGING BOT COMPONENTS...")
    
    # 1. Check settings
    try:
        from app.settings import settings
        print("✅ Settings loaded")
        print(f"   TELEGRAM_BOT_TOKEN: {'SET' if settings.TELEGRAM_BOT_TOKEN else 'NOT SET'}")
        print(f"   TINKOFF_TOKEN: {'SET' if settings.TINKOFF_TOKEN and settings.TINKOFF_TOKEN != 'your_tinkoff_invest_token_here' else 'NOT SET'}")
        print(f"   DEEPSEEK_API_KEY: {'SET' if settings.DEEPSEEK_API_KEY else 'NOT SET'}")
        print(f"   OPENROUTER_API_KEY: {'SET' if settings.OPENROUTER_API_KEY else 'NOT SET'}")
    except Exception as e:
        print(f"❌ Settings error: {e}")
        return False

    # 2. Check Tinkoff client
    try:
        from app.loader import get_tinkoff_client
        client = get_tinkoff_client()
        print(f"✅ Tinkoff client: {type(client).__name__}")
        
        # Test accounts
        accounts = client.get_accounts()
        print(f"✅ Accounts: {len(accounts.accounts)} found")
        
    except Exception as e:
        print(f"❌ Tinkoff client error: {e}")
        return False

    # 3. Check AI manager
    try:
        from app.ai_manager import get_ai_manager
        import asyncio
        
        async def test_ai():
            ai = await get_ai_manager()
            print(f"✅ AI Manager: {type(ai).__name__}")
            return True
        
        result = asyncio.get_event_loop().run_until_complete(test_ai())
        if result:
            print("✅ AI Manager working")
        
    except Exception as e:
        print(f"❌ AI Manager error: {e}")

    # 4. Check health monitor
    try:
        from app.health_monitor import HealthMonitor
        
        class MockBot:
            def __init__(self):
                self.application = type('App', (), {'bot': type('Bot', (), {'send_message': lambda *args, **kwargs: None})})()
        
        monitor = HealthMonitor(client, MockBot())
        print("✅ Health Monitor created")
        
    except Exception as e:
        print(f"❌ Health Monitor error: {e}")

    print("\n🎯 DIAGNOSTIC COMPLETE")
    return True

if __name__ == "__main__":
    debug_components()