"""
Firebase Firestore Client for Project Crystallized Momentum
Handles all state management, market signals, and position tracking
"""

import firebase_admin
from firebase_admin import credentials, firestore, initialize_app
from typing import Dict, Any, List, Optional, Union
from datetime import datetime
import logging
from google.cloud.firestore_v1 import Client as FirestoreClient
from google.cloud.firestore_v1.document import DocumentReference
from google.cloud.firestore_v1.collection import CollectionReference
import asyncio
from concurrent.futures import ThreadPoolExecutor

from config import config

logger = logging.getLogger(__name__)

class FirebaseClient:
    """Firebase Firestore client for state management"""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
            
        try:
            # Initialize Firebase
            cred = credentials.Certificate(config.firebase.credentials_path)
            firebase_admin.initialize_app(cred, {
                'projectId': config.firebase.project_id
            })
            self.db: FirestoreClient = firestore.client()
            logger.info(f"Firebase initialized for project: {config.firebase.project_id}")
            
            # Initialize collections
            self.collections = {}
            for name, path in config.firebase.collections.items():
                self.collections[name] = self.db.collection(path)
                logger.debug(f"Initialized collection: {name} -> {path}")
            
            # Thread pool for async operations
            self.executor = ThreadPoolExecutor(max_workers=10)
            
            self._initialized = True
            
        except Exception as e:
            logger.error(f"Failed to initialize Firebase: {str(e)}")
            raise
    
    def get_collection(self, name: str) -> CollectionReference:
        """Get a collection by name"""
        if name not in self.collections:
            raise ValueError(f"Collection {name} not configured")
        return self.collections[name]
    
    async def set_market_signal(
        self, 
        pair_address: str, 
        signal_type: str, 
        value: Union[float, str, Dict],
        metadata: Optional[Dict] = None
    ) -> bool:
        """Set a market signal for a trading pair"""
        try:
            doc_ref = self.get_collection('market_signals').document(pair_address)
            
            update_data = {
                signal_type: value,
                'last_updated': firestore.SERVER_TIMESTAMP
            }
            
            if metadata:
                update_data['metadata'] = metadata
            
            # Use async wrapper for Firestore operation
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                self.executor,
                lambda: doc_ref.set(update_data, merge=True)
            )
            
            logger.debug(f"Updated market signal: {pair_address}.{signal_type} = {value}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to set market signal: {str(e)}")
            return False
    
    async def get_market_signal(
        self, 
        pair_address: str, 
        signal_type: Optional[str] = None
    ) -> Optional[Dict]:
        """Get market signal(s) for a trading pair"""
        try:
            doc_ref = self.get_collection('market_signals').document(pair_address)
            
            loop = asyncio.get_event_loop()
            doc = await loop.run_in_executor(self.executor, doc_ref.get)
            
            if not doc.exists:
                return None
            
            data = doc.to_dict()
            if signal_type:
                return data.get(signal_type)
            return data
            
        except Exception as e:
            logger.error(f"Failed to get market signal: {str(e)}")
            return None
    
    async def create_position(
        self,
        vault_id: str,
        pair_address: str,
        range_lower: float,
        range_upper: float,
        liquidity: float,
        initial_investment_usd: float,
        metadata: Optional[Dict] = None
    ) -> Optional[str]:
        """Create a new liquidity position record"""
        try:
            position_data = {
                'vault_id': vault_id,
                'pair_address': pair_address,
                'range_lower': range_lower,
                'range_upper': range_upper,
                'liquidity': liquidity,
                'initial_investment_usd': initial_investment_usd,
                'current_value_usd': initial_investment_usd,
                'fees_accrued_usd': 0.0,
                'impermanent_loss_pct': 0.0,