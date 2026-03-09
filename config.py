"""
Configuration Management for Project Crystallized Momentum
Centralized configuration with validation and environment-specific settings
"""

import os
from dataclasses import dataclass
from typing import Optional, Dict, Any
from pathlib import Path
import json
import logging

# Configure logging before any other imports
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('crystallized_momentum.log')
    ]
)
logger = logging.getLogger(__name__)

@dataclass
class RiskParameters:
    """Risk management configuration"""
    max_position_size_usd: float = 5.0
    min_fee_to_gas_ratio: float = 3.0
    max_drawdown_pct: float = 15.0
    max_volatility_threshold: float = 2.0  # Annualized volatility ratio
    min_time_in_range_pct: float = 60.0
    daily_var_limit_pct: float = 5.0
    var_confidence_level: float = 0.95
    
@dataclass
class NetworkConfig:
    """Base L2 network configuration"""
    rpc_url: str
    chain_id: int = 8453  # Base mainnet
    gas_buffer_multiplier: float = 1.2
    max_gas_price_gwei: float = 50.0
    confirmations_required: int = 2

@dataclass
class DEXConfig:
    """DEX pool configuration for Base L2"""
    uniswap_v3_factory: str = "0x33128a8fC17869897dcE68Ed026d694621f6FDfD"
    fee_tiers: list = None  # Will be populated
    
    def __post_init__(self):
        if self.fee_tiers is None:
            self.fee_tiers = [100, 500, 3000, 10000]  # 0.01%, 0.05%, 0.3%, 1%

@dataclass
class FirebaseConfig:
    """Firebase configuration for state management"""
    credentials_path: str
    project_id: str
    collections: Dict[str, str] = None
    
    def __post_init__(self):
        if self.collections is None:
            self.collections = {
                'vaults': 'vaults',
                'positions': 'positions',
                'market_signals': 'market_signals',
                'keeper_tasks': 'keeper_tasks',
                'transactions': 'transactions'
            }

class Config:
    """Main configuration singleton"""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
            
        self.load_environment()
        self.validate_config()
        self._initialized = True
        
    def load_environment(self):
        """Load configuration from environment variables"""
        # Firebase configuration (CRITICAL)
        firebase_cred_path = os.getenv(
            'FIREBASE_CREDENTIALS_PATH', 
            './credentials/firebase-service-account.json'
        )
        
        # Verify Firebase credentials exist
        if not Path(firebase_cred_path).exists():
            logger.error(f"Firebase credentials not found at {firebase_cred_path}")
            # Attempt to create directory structure
            Path('./credentials').mkdir(exist_ok=True)
            raise FileNotFoundError(
                "Firebase credentials not found. Please download service account key from Firebase Console "
                "and save to ./credentials/firebase-service-account.json"
            )
        
        self.firebase = FirebaseConfig(
            credentials_path=firebase_cred_path,
            project_id=os.getenv('FIREBASE_PROJECT_ID', 'crystallized-momentum-dev')
        )
        
        # Network configuration
        rpc_url = os.getenv('BASE_RPC_URL')
        if not rpc_url:
            alchemy_key = os.getenv('ALCHEMY_API_KEY')
            if alchemy_key:
                rpc_url = f"https://base-mainnet.g.alchemy.com/v2/{alchemy_key}"
            else:
                rpc_url = "https://mainnet.base.org"
        
        self.network = NetworkConfig(rpc_url=rpc_url)
        
        # Trading parameters
        self.risk = RiskParameters(
            max_position_size_usd=float(os.getenv('MAX_POSITION_SIZE_USD', '5.0')),
            min_fee_to_gas_ratio=float(os.getenv('MIN_FEE_TO_GAS_RATIO', '3.0')),
            max_drawdown_pct=float(os.getenv('MAX_DRAWDOWN_PCT', '15.0'))
        )
        
        # DEX configuration
        self.dex = DEXConfig()
        
        # Trading addresses
        self.vault_address = os.getenv('VAULT_ADDRESS')
        self.private_key = os.getenv('PRIVATE_KEY')
        self.keeper_address = os.getenv('KEEPER_ADDRESS')
        
        # Telegram alerts
        self.telegram_bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
        self.telegram_chat_id = os.getenv('TELEGRAM_CHAT_ID')
        
        # Data collection intervals (seconds)
        self.data_intervals = {
            'price_update': 30,
            'volatility_calculation': 300,  # 5 minutes
            'position_review': 3600,  # 1 hour
            'full_rebalance': 86400  # 24 hours
        }
        
        # Initial target pairs (WETH/USDC + volatile memecoin)
        self.target_pairs = [
            {
                'base': 'WETH',
                'quote': 'USDC',
                'address': '0xYourWETHUSDCPoolAddress',  # Will be populated
                'default_fee_tier': 500  # 0.05%
            },
            {
                'base': 'MEME',  # Example memecoin
                'quote': 'WETH',
                'address': '0xYourMEMEWETHPoolAddress',
                'default_fee_tier': 3000  # 0.3% for volatile pairs
            }
        ]
        
        logger.info("Configuration loaded successfully")
    
    def validate_config(self):
        """Validate critical configuration parameters"""
        errors = []
        
        # Check Firebase configuration
        if not Path(self.firebase.credentials_path).exists():
            errors.append(f"Firebase credentials not found at {self.firebase.credentials_path}")
        
        # Check for trading private key if vault address is set
        if self.vault_address and not self.private_key:
            errors.append("PRIVATE_KEY required when VAULT_ADDRESS is set")
        
        # Validate RPC URL
        if not self.network.rpc_url.startswith('http'):
            errors.append(f"Invalid RPC URL: {self.network.rpc_url}")
        
        # Validate risk parameters
        if self.risk.max_position_size_usd <= 0:
            errors.append("MAX_POSITION_SIZE_USD must be positive")
        
        if self.risk.min_fee_to_gas_ratio < 1:
            errors.append("MIN_FEE_TO_GAS_RATIO must be >= 1")
        
        if errors:
            for error in errors:
                logger.error(f"Configuration error: {error}")
            raise ValueError(f"Configuration validation failed: {errors}")
        
        logger.info("Configuration validation passed")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary (excluding sensitive data)"""
        return {
            'firebase': {
                'project_id': self.firebase.project_id,
                'collections': self.firebase.collections
            },
            'network': {
                'rpc_url': '***' if 'alchemy' in self.network.rpc_url else self.network.rpc_url,
                'chain_id': self.network.chain_id
            },
            'risk': {
                'max_position_size_usd': self.risk.max_position_size_usd,
                'min_fee_to_gas_ratio': self.risk.min_fee_to_gas_ratio,
                'max_drawdown_pct': self.risk.max_drawdown_pct
            },
            'data_intervals': self.data_intervals,
            'target_pairs_count': len(self.target_pairs)
        }

# Global configuration instance
config = Config()