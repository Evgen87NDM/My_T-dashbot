"""
Tariff manager for automatic broker commission detection
"""
import logging
from typing import Dict, List, Optional
from app.settings import settings

logger = logging.getLogger(__name__)

class TariffManager:
    """Manager for automatic broker tariff detection"""
    
    def __init__(self, client_manager):
        self.client_manager = client_manager
        self.tariff_info = None
        self.commission_rates = None
        
    def get_tariff_info(self) -> Dict:
        """Get tariff information from Tinkoff API"""
        if self.tariff_info is not None:
            return self.tariff_info
            
        try:
            # Get user info which contains tariff information
            def get_user_info_operation(client):
                return client.users.get_info()
            
            user_info = self.client_manager.execute_operation(get_user_info_operation)
            
            # Get accounts to detect tariff type
            def get_accounts_operation(client):
                return client.users.get_accounts()
            
            accounts_response = self.client_manager.execute_operation(get_accounts_operation)
            
            # Analyze tariff based on available information
            self.tariff_info = self._analyze_tariff(user_info, accounts_response)
            logger.info(f"✅ Tariff detected: {self.tariff_info['name']}")
            
            return self.tariff_info
            
        except Exception as e:
            logger.error(f"Error getting tariff info: {e}")
            # Return default tariff info
            return self._get_default_tariff()
    
    def _analyze_tariff(self, user_info, accounts_response) -> Dict:
        """Analyze user tariff based on available data"""
        tariff_name = "Неизвестно"
        tariff_type = "unknown"
        
        # Try to detect tariff from user info
        if hasattr(user_info, 'premium_status') and user_info.premium_status:
            tariff_name = "Премиум"
            tariff_type = "premium"
        elif hasattr(user_info, 'tariff'):
            tariff_name = getattr(user_info.tariff, 'name', 'Стандартный')
            tariff_type = getattr(user_info.tariff, 'type', 'standard')
        else:
            # Fallback detection based on account types
            tariff_name, tariff_type = self._detect_tariff_by_accounts(accounts_response)
        
        commission_rates = self._get_commission_rates(tariff_type)
        
        return {
            'name': tariff_name,
            'type': tariff_type,
            'commission_rates': commission_rates,
            'monthly_fee': self._get_monthly_fee(tariff_type),
            'features': self._get_tariff_features(tariff_type)
        }
    
    def _detect_tariff_by_accounts(self, accounts_response) -> tuple:
        """Detect tariff based on account types"""
        if not accounts_response or not hasattr(accounts_response, 'accounts'):
            return "Стандартный", "standard"
        
        accounts = accounts_response.accounts
        has_iiis = any(hasattr(acc, 'type') and 'iiis' in str(acc.type).lower() for acc in accounts)
        has_brokerage = any(hasattr(acc, 'type') and 'brokerage' in str(acc.type).lower() for acc in accounts)
        
        # Simple heuristic based on account types
        if has_iiis and has_brokerage:
            return "Инвестор", "investor"
        elif len(accounts) > 2:
            return "Трейдер", "trader"
        else:
            return "Стандартный", "standard"
    
    def _get_commission_rates(self, tariff_type: str) -> Dict:
        """Get commission rates based on tariff type"""
        commission_rates = {
            'investor': {
                'buy': 0.3,      # 0.3%
                'sell': 0.3,     # 0.3%
                'min_commission': 0.0,
                'description': 'Комиссия за сделку от 0.3%. Обслуживание бесплатно'
            },
            'trader': {
                'buy': 0.04,     # 0.04%
                'sell': 0.04,    # 0.04%
                'min_commission': 0.0,
                'description': 'Комиссия от 0.04%. Обслуживание до 390 руб. в месяц'
            },
            'premium': {
                'buy': 0.025,    # 0.025%
                'sell': 0.025,   # 0.025%
                'min_commission': 0.0,
                'description': 'Премиальные условия'
            },
            'standard': {
                'buy': 0.05,     # 0.05%
                'sell': 0.05,    # 0.05%
                'min_commission': 1.0,
                'description': 'Стандартные условия'
            }
        }
        
        return commission_rates.get(tariff_type, commission_rates['standard'])
    
    def _get_monthly_fee(self, tariff_type: str) -> float:
        """Get monthly fee based on tariff type"""
        monthly_fees = {
            'investor': 0.0,
            'trader': 390.0,
            'premium': 0.0,
            'standard': 0.0
        }
        return monthly_fees.get(tariff_type, 0.0)
    
    def _get_tariff_features(self, tariff_type: str) -> List[str]:
        """Get tariff features"""
        features = {
            'investor': [
                "Комиссия за сделку от 0.3%",
                "Обслуживание бесплатно",
                "Подходит для долгосрочных инвестиций"
            ],
            'trader': [
                "Комиссия от 0.04% за сделку",
                "Обслуживание до 390 руб. в месяц",
                "Подходит для активной торговли",
                "Льготные условия для частых операций"
            ],
            'premium': [
                "Премиальные условия",
                "Персональный менеджер",
                "Минимальные комиссии"
            ],
            'standard': [
                "Стандартные условия",
                "Комиссия 0.05% за сделку",
                "Бесплатное обслуживание"
            ]
        }
        return features.get(tariff_type, features['standard'])
    
    def _get_default_tariff(self) -> Dict:
        """Get default tariff info when API fails"""
        return {
            'name': 'Стандартный',
            'type': 'standard',
            'commission_rates': self._get_commission_rates('standard'),
            'monthly_fee': 0.0,
            'features': self._get_tariff_features('standard')
        }
    
    def get_commission_rate(self, operation_type: str) -> float:
        """Get commission rate for specific operation type"""
        tariff_info = self.get_tariff_info()
        return tariff_info['commission_rates'].get(operation_type.lower(), 0.05)
    
    def get_min_commission(self) -> float:
        """Get minimum commission"""
        tariff_info = self.get_tariff_info()
        return tariff_info['commission_rates'].get('min_commission', 1.0)

# Global tariff manager instance
_tariff_manager = None

def get_tariff_manager(client_manager):
    """Get tariff manager instance"""
    global _tariff_manager
    if _tariff_manager is None:
        _tariff_manager = TariffManager(client_manager)
    return _tariff_manager