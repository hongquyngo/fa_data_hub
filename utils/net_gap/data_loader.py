# utils/net_gap/data_loader.py - Production Ready Version

"""
Data Loader for GAP Analysis - Production Ready with All Fixes
- Uses correct logic from stable version (products/brands from views)
- Fixed missing avg_daily_demand column issue
- Fixed SQLAlchemy execute() syntax
- Added expired inventory support
"""

import pandas as pd
import streamlit as st
from datetime import datetime, date, timedelta
from typing import Optional, List, Dict, Any, Tuple
import logging
import re
from sqlalchemy import text, create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.pool import QueuePool
from contextlib import contextmanager
import numpy as np

import os
import sys
from pathlib import Path

project_root = os.environ.get('PROJECT_ROOT', Path(__file__).parent.parent.parent)
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))
from utils.db import get_db_engine

logger = logging.getLogger(__name__)

# Cache configuration
CACHE_TTL = {
    'data': 300,       # 5 minutes for main data
    'reference': 600,  # 10 minutes for reference data
    'safety': 900      # 15 minutes for safety stock
}

# Validation constants
MAX_ENTITY_NAME_LENGTH = 200
MAX_PRODUCT_IDS = 1000
MAX_BRANDS = 100
BATCH_SIZE = 500  # For batch processing large datasets


class DataLoadError(Exception):
    """Base exception for data loading errors"""
    pass


class ValidationError(DataLoadError):
    """Exception for input validation failures"""
    pass


class DatabaseConnectionError(DataLoadError):
    """Exception for database connection issues"""
    pass


class GAPDataLoader:
    """Production-ready data loader with all fixes applied"""
    
    def __init__(self):
        self._engine = None
        self._safety_stock_available = None
        self._entity_id_cache = {}
    
    @property
    def engine(self):
        """Lazy load database engine"""
        if self._engine is None:
            try:
                self._engine = get_db_engine()
                # Test connection
                with self._engine.connect() as conn:
                    conn.execute(text("SELECT 1"))
                logger.info("Database connection established")
            except Exception as e:
                logger.error(f"Failed to establish database connection: {e}", exc_info=True)
                raise DatabaseConnectionError(f"Cannot connect to database: {str(e)}")
        return self._engine
    
    @contextmanager
    def get_connection(self):
        """Context manager for database connections"""
        conn = None
        try:
            conn = self.engine.connect()
            yield conn
        except SQLAlchemyError as e:
            logger.error(f"Database error: {e}", exc_info=True)
            raise DatabaseConnectionError(f"Database operation failed: {str(e)}")
        finally:
            if conn:
                try:
                    conn.close()
                except:
                    pass
    
    def _normalize_text_field(self, value: Any, field_name: str = '') -> str:
        """Normalize text field for consistency"""
        if pd.isna(value) or value is None:
            return ''
        
        str_value = str(value).strip()
        
        if field_name == 'pt_code':
            return str_value.upper()
        elif field_name in ['brand', 'product_name', 'standard_uom']:
            return str_value.upper()
        else:
            return str_value
    
    # ==================== VALIDATION METHODS ====================
    
    def _validate_entity_name(self, entity_name: Optional[str]) -> None:
        """Validate entity name input"""
        if entity_name is None:
            return
        
        if not isinstance(entity_name, str):
            raise ValidationError(f"Entity name must be string, got {type(entity_name)}")
        
        if len(entity_name) == 0:
            raise ValidationError("Entity name cannot be empty")
        
        if len(entity_name) > MAX_ENTITY_NAME_LENGTH:
            raise ValidationError(f"Entity name too long (max {MAX_ENTITY_NAME_LENGTH} chars)")
        
        if re.search(r'[;\'"\\]', entity_name):
            raise ValidationError("Entity name contains invalid characters")
    
    def _validate_product_ids(self, product_ids: Optional[List[int]]) -> None:
        """Validate product IDs list"""
        if product_ids is None or len(product_ids) == 0:
            return
        
        if not isinstance(product_ids, (list, tuple)):
            raise ValidationError(f"Product IDs must be list or tuple, got {type(product_ids)}")
        
        if len(product_ids) > MAX_PRODUCT_IDS:
            raise ValidationError(f"Too many product IDs: {len(product_ids)} (max {MAX_PRODUCT_IDS})")
        
        for pid in product_ids:
            if not isinstance(pid, (int, np.integer)):
                raise ValidationError(f"Product ID must be integer, got {type(pid)}: {pid}")
            if pid <= 0:
                raise ValidationError(f"Invalid product ID: {pid}")
    
    def _validate_list_input(self, items: Optional[List[str]], name: str, max_items: int) -> None:
        """Validate string list inputs"""
        if items is None or len(items) == 0:
            return
        
        if not isinstance(items, (list, tuple)):
            raise ValidationError(f"{name} must be list or tuple, got {type(items)}")
        
        if len(items) > max_items:
            raise ValidationError(f"Too many {name}: {len(items)} (max {max_items})")
        
        for item in items:
            if not isinstance(item, str):
                raise ValidationError(f"{name} item must be string, got {type(item)}")
            if len(item) > 200:
                raise ValidationError(f"{name} item too long: {len(item)} chars")
    
    # ==================== ENTITY METHODS ====================
    
    @st.cache_data(ttl=CACHE_TTL['reference'])
    def get_entity_id(_self, entity_name: str) -> Optional[int]:
        """Map entity name to entity ID"""
        _self._validate_entity_name(entity_name)
        
        if entity_name in _self._entity_id_cache:
            return _self._entity_id_cache[entity_name]
        
        try:
            query = """
                SELECT id 
                FROM companies 
                WHERE english_name = :entity_name
                  AND delete_flag = 0
                LIMIT 1
            """
            
            with _self.get_connection() as conn:
                result = conn.execute(text(query), {'entity_name': entity_name}).fetchone()
                
                if result:
                    entity_id = int(result[0])
                    _self._entity_id_cache[entity_name] = entity_id
                    logger.info(f"Entity ID mapping: '{entity_name}' -> {entity_id}")
                    return entity_id
                else:
                    logger.warning(f"Entity not found: {entity_name}")
                    return None
                    
        except SQLAlchemyError as e:
            logger.error(f"Error mapping entity name to ID: {e}", exc_info=True)
            raise DataLoadError(f"Failed to get entity ID: {str(e)}")
    
    @st.cache_data(ttl=CACHE_TTL['reference'])
    def get_entities_formatted(_self) -> pd.DataFrame:
        """
        Get entities with company_code for formatted display
        Only returns entities that have actual data in supply/demand views
        """
        try:
            query = """
                SELECT DISTINCT 
                    c.english_name,
                    c.company_code
                FROM companies c
                WHERE c.delete_flag = 0
                  AND c.english_name IN (
                    SELECT DISTINCT entity_name FROM unified_supply_view
                    WHERE entity_name IS NOT NULL
                    UNION
                    SELECT DISTINCT entity_name FROM unified_demand_view
                    WHERE entity_name IS NOT NULL
                  )
                ORDER BY c.english_name
            """
            
            with _self.get_connection() as conn:
                df = pd.read_sql(text(query), conn)
            
            logger.info(f"Loaded {len(df)} formatted entities")
            return df
            
        except SQLAlchemyError as e:
            logger.error(f"Database error getting formatted entities: {e}", exc_info=True)
            # Return empty DataFrame on error
            return pd.DataFrame()
    
    @st.cache_data(ttl=CACHE_TTL['reference'])
    def get_entities(_self) -> List[str]:
        """Get simple list of entity names that have data"""
        try:
            query = """
                SELECT DISTINCT entity_name
                FROM (
                    SELECT DISTINCT entity_name FROM unified_supply_view
                    WHERE entity_name IS NOT NULL
                    UNION
                    SELECT DISTINCT entity_name FROM unified_demand_view
                    WHERE entity_name IS NOT NULL
                ) AS entities
                ORDER BY entity_name
            """
            
            with _self.get_connection() as conn:
                result = conn.execute(text(query)).fetchall()
            
            return [row[0] for row in result if row[0]]
            
        except Exception as e:
            logger.error(f"Error loading entities: {e}", exc_info=True)
            return []
    
    # ==================== PRODUCT METHODS ====================
    
    @st.cache_data(ttl=CACHE_TTL['reference'])
    def get_products(_self, entity_name: Optional[str] = None) -> pd.DataFrame:
        """
        Get list of products with package_size
        IMPORTANT: Gets products from supply/demand views to ensure they have data
        """
        try:
            _self._validate_entity_name(entity_name)
            
            params = {}
            entity_filter = ""
            
            if entity_name:
                entity_filter = "WHERE entity_name = :entity_name"
                params['entity_name'] = entity_name
            
            # Get products from UNION of supply and demand views (like stable version)
            query = f"""
                SELECT DISTINCT 
                    product_id, product_name, pt_code, package_size,
                    brand, standard_uom
                FROM (
                    SELECT product_id, product_name, pt_code, package_size, 
                           brand, standard_uom, entity_name
                    FROM unified_supply_view
                    WHERE product_id IS NOT NULL
                    UNION
                    SELECT product_id, product_name, pt_code, package_size, 
                           brand, standard_uom, entity_name
                    FROM unified_demand_view
                    WHERE product_id IS NOT NULL
                ) AS products
                {entity_filter}
                ORDER BY pt_code, product_name
            """
            
            with _self.get_connection() as conn:
                df = pd.read_sql(text(query), conn, params=params)
            
            # Normalize text fields
            text_cols = ['product_name', 'pt_code', 'package_size', 'brand', 'standard_uom']
            for col in text_cols:
                if col in df.columns:
                    df[col] = df[col].apply(lambda x: _self._normalize_text_field(x, col))
            
            logger.info(f"Loaded {len(df)} products")
            return df
            
        except ValidationError:
            raise
        except SQLAlchemyError as e:
            logger.error(f"Database error getting products: {e}", exc_info=True)
            return pd.DataFrame()
    
    # ==================== BRAND METHODS ====================
    
    @st.cache_data(ttl=CACHE_TTL['reference'])
    def get_brands(_self, entity_name: Optional[str] = None) -> List[str]:
        """
        Get list of unique brands
        Gets brands from supply/demand views to ensure they have data
        """
        try:
            _self._validate_entity_name(entity_name)
            
            params = {}
            entity_filter = ""
            
            if entity_name:
                entity_filter = "WHERE entity_name = :entity_name"
                params['entity_name'] = entity_name
            
            # Get brands from UNION of supply and demand views (like stable version)
            query = f"""
                SELECT DISTINCT brand
                FROM (
                    SELECT DISTINCT brand, entity_name FROM unified_supply_view 
                    WHERE brand IS NOT NULL
                    UNION
                    SELECT DISTINCT brand, entity_name FROM unified_demand_view 
                    WHERE brand IS NOT NULL
                ) AS brands
                {entity_filter}
                ORDER BY brand
            """
            
            with _self.get_connection() as conn:
                result = conn.execute(text(query), params)
                brands = []
                for row in result:
                    if row[0]:
                        normalized = _self._normalize_text_field(row[0], 'brand')
                        if normalized and normalized not in brands:
                            brands.append(normalized)
            
            brands.sort()
            logger.info(f"Loaded {len(brands)} brands")
            return brands
            
        except ValidationError:
            raise
        except SQLAlchemyError as e:
            logger.error(f"Database error getting brands: {e}", exc_info=True)
            return []
    
    # ==================== SAFETY STOCK METHODS ====================
    
    @st.cache_data(ttl=CACHE_TTL['reference'])
    def check_safety_stock_availability(_self) -> bool:
        """Check if safety stock data is available"""
        if _self._safety_stock_available is not None:
            return _self._safety_stock_available
        
        try:
            query = """
                SELECT COUNT(*) as count
                FROM safety_stock_levels
                WHERE delete_flag = 0
                  AND is_active = 1
                  AND CURRENT_DATE() >= effective_from
                  AND (effective_to IS NULL OR CURRENT_DATE() <= effective_to)
            """
            
            with _self.get_connection() as conn:
                result = conn.execute(text(query)).fetchone()
                
                count = result[0] if result else 0
                _self._safety_stock_available = count > 0
                
                logger.info(f"Safety stock availability: {_self._safety_stock_available} ({count} active records)")
                return _self._safety_stock_available
                
        except SQLAlchemyError as e:
            logger.error(f"Error checking safety stock: {e}", exc_info=True)
            _self._safety_stock_available = False
            return False
    
    @st.cache_data(ttl=CACHE_TTL['safety'])
    def load_safety_stock_data(
        _self,
        entity_name: Optional[str] = None,
        exclude_entity: bool = False,
        product_ids: Optional[Tuple[int, ...]] = None
    ) -> pd.DataFrame:
        """
        Load safety stock data with all necessary columns
        FIXED: Using COALESCE to handle missing columns safely
        """
        try:
            _self._validate_entity_name(entity_name)
            _self._validate_product_ids(product_ids)
            
            # Use COALESCE for potentially missing columns
            query_parts = ["""
                SELECT 
                    product_id,
                    product_name,
                    pt_code,
                    brand,
                    entity_name,
                    customer_name,
                    COALESCE(safety_stock_qty, 0) as safety_stock_qty,
                    COALESCE(reorder_point, 0) as reorder_point,
                    calculation_method,
                    -- Safely handle potentially missing calculation parameters
                    COALESCE(avg_daily_demand, 0) as avg_daily_demand,
                    COALESCE(safety_days, 0) as safety_days,
                    COALESCE(lead_time_days, 0) as lead_time_days,
                    COALESCE(service_level_percent, 95) as service_level_percent,
                    COALESCE(demand_std_deviation, 0) as demand_std_deviation,
                    COALESCE(priority_level, 99) as priority_level,
                    rule_type
                FROM safety_stock_current_view
                WHERE 1=1
            """]
            
            params = {}
            
            # Add entity filter
            if entity_name:
                if exclude_entity:
                    query_parts.append("AND entity_name != :entity_name")
                else:
                    query_parts.append("AND entity_name = :entity_name")
                params['entity_name'] = entity_name
            
            # Add product filter
            if product_ids:
                product_list = list(product_ids)
                placeholders = [f":prod_{i}" for i in range(len(product_list))]
                query_parts.append(f"AND product_id IN ({','.join(placeholders)})")
                
                for i, pid in enumerate(product_list):
                    params[f'prod_{i}'] = pid
            
            query_parts.append("ORDER BY priority_level, product_id")
            
            query = '\n'.join(query_parts)
            
            with _self.get_connection() as conn:
                df = pd.read_sql(text(query), conn, params=params)
            
            if df.empty:
                logger.warning("No safety stock data found for given filters")
                return pd.DataFrame()
            
            # Process dataframe - ensure numeric columns
            numeric_cols = [
                'safety_stock_qty', 'reorder_point', 'avg_daily_demand',
                'safety_days', 'lead_time_days', 'service_level_percent',
                'demand_std_deviation', 'priority_level'
            ]
            
            for col in numeric_cols:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
            
            # Normalize text fields
            text_cols = ['pt_code', 'product_name', 'brand', 'entity_name']
            for col in text_cols:
                if col in df.columns:
                    df[col] = df[col].apply(lambda x: _self._normalize_text_field(x, col))
            
            logger.info(f"Loaded {len(df)} safety stock records")
            return df
            
        except ValidationError:
            raise
        except SQLAlchemyError as e:
            logger.error(f"Database error loading safety stock data: {e}", exc_info=True)
            # Return empty dataframe instead of raising to not break the flow
            return pd.DataFrame()
    
    # ==================== SUPPLY DATA METHODS ====================
    
    @st.cache_data(ttl=CACHE_TTL['data'])
    def load_supply_data(
        _self,
        entity_name: Optional[str] = None,
        exclude_entity: bool = False,
        product_ids: Optional[Tuple[int, ...]] = None,
        brands: Optional[Tuple[str, ...]] = None,
        exclude_products: bool = False,
        exclude_brands: bool = False,
        exclude_expired: bool = True
    ) -> pd.DataFrame:
        """Load supply data from unified_supply_view"""
        try:
            _self._validate_entity_name(entity_name)
            _self._validate_product_ids(product_ids)
            _self._validate_list_input(brands, "brands", MAX_BRANDS)
            
            query, params = _self._build_supply_query(
                entity_name, exclude_entity, product_ids, brands,
                exclude_products, exclude_brands, exclude_expired
            )
            
            with _self.get_connection() as conn:
                df = pd.read_sql(text(query), conn, params=params)
            
            if df.empty:
                logger.warning("No supply data found for given filters")
                # Return empty DataFrame with proper schema to prevent KeyError
                return _self._get_empty_supply_dataframe()
            
            df = _self._process_supply_dataframe(df)
            
            logger.info(
                f"Loaded {len(df)} supply records | "
                f"Entity: {entity_name or 'All'} | "
                f"Products: {len(product_ids) if product_ids else 'All'} | "
                f"Exclude expired: {exclude_expired}"
            )
            
            return df
            
        except ValidationError:
            raise
        except SQLAlchemyError as e:
            logger.error(f"Database error loading supply data: {e}", exc_info=True)
            raise DataLoadError(f"Failed to load supply data: {str(e)}")
    
    # ==================== DEMAND DATA METHODS ====================
    
    @st.cache_data(ttl=CACHE_TTL['data'])
    def load_demand_data(
        _self,
        entity_name: Optional[str] = None,
        exclude_entity: bool = False,
        product_ids: Optional[Tuple[int, ...]] = None,
        brands: Optional[Tuple[str, ...]] = None,
        exclude_products: bool = False,
        exclude_brands: bool = False
    ) -> pd.DataFrame:
        """Load demand data from unified_demand_view"""
        try:
            _self._validate_entity_name(entity_name)
            _self._validate_product_ids(product_ids)
            _self._validate_list_input(brands, "brands", MAX_BRANDS)
            
            query, params = _self._build_demand_query(
                entity_name, exclude_entity, product_ids, brands,
                exclude_products, exclude_brands
            )
            
            with _self.get_connection() as conn:
                df = pd.read_sql(text(query), conn, params=params)
            
            if df.empty:
                logger.warning("No demand data found for given filters")
                # Return empty DataFrame with proper schema to prevent KeyError
                return _self._get_empty_demand_dataframe()
            
            df = _self._process_demand_dataframe(df)
            
            logger.info(
                f"Loaded {len(df)} demand records | "
                f"Entity: {entity_name or 'All'} | "
                f"Products: {len(product_ids) if product_ids else 'All'}"
            )
            
            return df
            
        except ValidationError:
            raise
        except SQLAlchemyError as e:
            logger.error(f"Database error loading demand data: {e}", exc_info=True)
            raise DataLoadError(f"Failed to load demand data: {str(e)}")
    
    # ==================== EXPIRED INVENTORY METHODS ====================
    
    @st.cache_data(ttl=CACHE_TTL['data'])
    def load_expired_inventory_details(
        _self,
        entity_name: Optional[str] = None,
        exclude_entity: bool = False,
        product_ids: Optional[Tuple[int, ...]] = None,
        brands: Optional[Tuple[str, ...]] = None,
        exclude_products: bool = False,
        exclude_brands: bool = False
    ) -> pd.DataFrame:
        """
        Load expired inventory details with batch information
        FIXED: GROUP BY only product_id to avoid duplicates
        """
        try:
            # First check if we have inventory data with expiry dates
            check_query = """
                SELECT COUNT(*) 
                FROM unified_supply_view
                WHERE supply_source = 'INVENTORY'
                AND expiry_date IS NOT NULL
                AND expiry_date < CURRENT_DATE()
            """
            
            with _self.get_connection() as conn:
                result = conn.execute(text(check_query)).fetchone()
                
                if not result or result[0] == 0:
                    logger.info("No expired inventory found in supply view")
                    return pd.DataFrame()
            
            # Build query for expired inventory from supply view
            # FIXED: Use MIN/MAX for text fields, GROUP BY only product_id
            query_parts = ["""
                SELECT 
                    product_id,
                    MIN(pt_code) as pt_code,
                    MIN(product_name) as product_name,
                    MIN(brand) as brand,
                    SUM(available_quantity) as expired_quantity,
                    GROUP_CONCAT(
                        CONCAT(
                            'Batch: ', IFNULL(batch_number, 'N/A'),
                            ' | Exp: ', DATE_FORMAT(expiry_date, '%Y-%m-%d'),
                            ' | Qty: ', available_quantity,
                            ' | WH: ', IFNULL(warehouse_name, 'N/A')
                        ) SEPARATOR '; '
                    ) as expired_batches_info
                FROM unified_supply_view
                WHERE supply_source = 'INVENTORY'
                AND expiry_date < CURRENT_DATE()
                AND available_quantity > 0
            """]
            
            params = {}
            
            # Add filters [same as before]
            if entity_name:
                if exclude_entity:
                    query_parts.append("AND entity_name != :entity_name")
                else:
                    query_parts.append("AND entity_name = :entity_name")
                params['entity_name'] = entity_name
            
            if product_ids:
                product_list = list(product_ids)
                placeholders = [f":prod_{i}" for i in range(len(product_list))]
                
                if exclude_products:
                    query_parts.append(f"AND product_id NOT IN ({','.join(placeholders)})")
                else:
                    query_parts.append(f"AND product_id IN ({','.join(placeholders)})")
                
                for i, pid in enumerate(product_list):
                    params[f'prod_{i}'] = pid
            
            if brands:
                brand_list = list(brands)
                placeholders = [f":brand_{i}" for i in range(len(brand_list))]
                
                if exclude_brands:
                    query_parts.append(f"AND brand NOT IN ({','.join(placeholders)})")
                else:
                    query_parts.append(f"AND brand IN ({','.join(placeholders)})")
                
                for i, brand in enumerate(brand_list):
                    params[f'brand_{i}'] = brand
            
            # FIXED: GROUP BY only product_id to ensure unique rows
            query_parts.append("GROUP BY product_id")
            
            query = '\n'.join(query_parts)
            
            with _self.get_connection() as conn:
                df = pd.read_sql(text(query), conn, params=params)
            
            if df.empty:
                logger.info("No expired inventory found for given filters")
                return pd.DataFrame()
            
            # Format batch info
            df['expired_batches_info'] = df['expired_batches_info'].apply(
                lambda x: _self._format_batch_info(x) if pd.notna(x) else ""
            )
            
            # Debug: Check for duplicates
            if df['product_id'].duplicated().any():
                logger.error("WARNING: Duplicate product_ids in expired inventory!")
                duplicates = df[df['product_id'].duplicated(keep=False)]
                logger.error(f"Duplicate products: {duplicates[['product_id', 'product_name']].to_dict('records')}")
            
            logger.info(f"Loaded expired inventory for {len(df)} products (unique)")
            return df
            
        except Exception as e:
            logger.error(f"Error loading expired inventory: {e}", exc_info=True)
            # Return empty dataframe on error to not break the main flow
            return pd.DataFrame()
    
    def _format_batch_info(self, batch_str: str, max_length: int = 200) -> str:
        """Format batch information string"""
        if not batch_str:
            return ""
        
        if len(batch_str) > max_length:
            batch_str = batch_str[:max_length] + "..."
        
        return batch_str
    
    # ==================== DATE RANGE METHODS ====================
    
    @st.cache_data(ttl=CACHE_TTL['reference'])
    def get_date_range(_self) -> Dict[str, Any]:
        """Get the date range of available data"""
        try:
            query = """
                SELECT 
                    MIN(date_val) as min_date,
                    MAX(date_val) as max_date,
                    CURRENT_DATE() as current_date
                FROM (
                    SELECT MIN(availability_date) as date_val 
                    FROM unified_supply_view 
                    WHERE availability_date IS NOT NULL
                    UNION ALL
                    SELECT MAX(availability_date) 
                    FROM unified_supply_view 
                    WHERE availability_date IS NOT NULL
                    UNION ALL
                    SELECT MIN(required_date) 
                    FROM unified_demand_view 
                    WHERE required_date IS NOT NULL
                    UNION ALL
                    SELECT MAX(required_date) 
                    FROM unified_demand_view 
                    WHERE required_date IS NOT NULL
                ) AS dates
            """
            
            with _self.get_connection() as conn:
                result = conn.execute(text(query)).fetchone()
            
            if result and result[0] and result[1]:
                return {
                    'min_date': result[0],
                    'max_date': result[1],
                    'current_date': result[2]
                }
            
            # Default values if no data
            current = datetime.now().date()
            return {
                'min_date': current - timedelta(days=30),
                'max_date': current + timedelta(days=90),
                'current_date': current
            }
            
        except Exception as e:
            logger.error(f"Error getting date range: {e}")
            current = datetime.now().date()
            return {
                'min_date': current - timedelta(days=30),
                'max_date': current + timedelta(days=90),
                'current_date': current
            }
    
    # ==================== QUERY BUILDERS ====================
    
    def _build_supply_query(
        self,
        entity_name: Optional[str],
        exclude_entity: bool,
        product_ids: Optional[Tuple[int, ...]],
        brands: Optional[Tuple[str, ...]],
        exclude_products: bool,
        exclude_brands: bool,
        exclude_expired: bool
    ) -> Tuple[str, Dict[str, Any]]:
        """Build supply query"""
        
        query_parts = ["""
            SELECT 
                supply_source,
                product_id,
                product_name,
                brand,
                pt_code,
                package_size,
                standard_uom,
                batch_number,
                expiry_date,
                days_to_expiry,
                available_quantity,
                availability_date,
                days_to_available,
                availability_status,
                warehouse_name,
                to_location,
                entity_name,
                unit_cost_usd,
                total_value_usd,
                supply_reference_id,
                supplier_name,
                completion_percentage
            FROM unified_supply_view
            WHERE 1=1
        """]
        
        params = {}
        
        # Add filters
        if entity_name:
            if exclude_entity:
                query_parts.append("AND entity_name != :entity_name")
            else:
                query_parts.append("AND entity_name = :entity_name")
            params['entity_name'] = entity_name
        
        if product_ids:
            product_list = list(product_ids)
            placeholders = [f":prod_{i}" for i in range(len(product_list))]
            
            if exclude_products:
                query_parts.append(f"AND product_id NOT IN ({','.join(placeholders)})")
            else:
                query_parts.append(f"AND product_id IN ({','.join(placeholders)})")
            
            for i, pid in enumerate(product_list):
                params[f'prod_{i}'] = pid
        
        if brands:
            brand_list = list(brands)
            placeholders = [f":brand_{i}" for i in range(len(brand_list))]
            
            if exclude_brands:
                query_parts.append(f"AND brand NOT IN ({','.join(placeholders)})")
            else:
                query_parts.append(f"AND brand IN ({','.join(placeholders)})")
            
            for i, brand in enumerate(brand_list):
                params[f'brand_{i}'] = brand
        
        if exclude_expired:
            query_parts.append("AND (expiry_date IS NULL OR expiry_date >= CURRENT_DATE())")
        
        query_parts.append("ORDER BY product_id, supply_priority, days_to_available")
        
        return '\n'.join(query_parts), params
    
    def _build_demand_query(
        self,
        entity_name: Optional[str],
        exclude_entity: bool,
        product_ids: Optional[Tuple[int, ...]],
        brands: Optional[Tuple[str, ...]],
        exclude_products: bool,
        exclude_brands: bool
    ) -> Tuple[str, Dict[str, Any]]:
        """Build demand query"""
        
        query_parts = ["""
            SELECT 
                demand_source,
                product_id,
                product_name,
                brand,
                pt_code,
                package_size,
                standard_uom,
                customer,
                customer_code,
                customer_po_number,
                required_quantity,
                required_date,
                days_to_required,
                demand_status,
                urgency_level,
                is_allocated,
                allocated_quantity,
                unallocated_quantity,
                selling_unit_price,
                total_value_usd,
                demand_reference_id,
                entity_name
            FROM unified_demand_view
            WHERE 1=1
        """]
        
        params = {}
        
        # Add filters
        if entity_name:
            if exclude_entity:
                query_parts.append("AND entity_name != :entity_name")
            else:
                query_parts.append("AND entity_name = :entity_name")
            params['entity_name'] = entity_name
        
        if product_ids:
            product_list = list(product_ids)
            placeholders = [f":prod_{i}" for i in range(len(product_list))]
            
            if exclude_products:
                query_parts.append(f"AND product_id NOT IN ({','.join(placeholders)})")
            else:
                query_parts.append(f"AND product_id IN ({','.join(placeholders)})")
            
            for i, pid in enumerate(product_list):
                params[f'prod_{i}'] = pid
        
        if brands:
            brand_list = list(brands)
            placeholders = [f":brand_{i}" for i in range(len(brand_list))]
            
            if exclude_brands:
                query_parts.append(f"AND brand NOT IN ({','.join(placeholders)})")
            else:
                query_parts.append(f"AND brand IN ({','.join(placeholders)})")
            
            for i, brand in enumerate(brand_list):
                params[f'brand_{i}'] = brand
        
        query_parts.append("ORDER BY product_id, demand_priority, days_to_required")
        
        return '\n'.join(query_parts), params
    
    # ==================== EMPTY DATAFRAME SCHEMAS ====================
    
    def _get_empty_supply_dataframe(self) -> pd.DataFrame:
        """Return empty supply DataFrame with proper schema to prevent KeyError"""
        return pd.DataFrame(columns=[
            'supply_source', 'product_id', 'product_name', 'brand', 'pt_code',
            'package_size', 'standard_uom', 'batch_number', 'expiry_date',
            'days_to_expiry', 'available_quantity', 'availability_date',
            'days_to_available', 'availability_status', 'warehouse_name',
            'to_location', 'entity_name', 'unit_cost_usd', 'total_value_usd',
            'supply_reference_id', 'supplier_name', 'completion_percentage'
        ])
    
    def _get_empty_demand_dataframe(self) -> pd.DataFrame:
        """Return empty demand DataFrame with proper schema to prevent KeyError"""
        return pd.DataFrame(columns=[
            'demand_source', 'demand_priority', 'product_id', 'product_name',
            'brand', 'pt_code', 'package_size', 'standard_uom', 'customer',
            'customer_code', 'customer_po_number', 'required_quantity',
            'required_date', 'days_to_required', 'demand_status', 'urgency_level',
            'is_allocated', 'allocation_count', 'allocation_coverage_percent',
            'allocated_quantity', 'unallocated_quantity', 'is_over_committed',
            'is_pending_over_allocated', 'over_committed_qty_standard',
            'pending_over_allocated_qty_standard', 'selling_unit_price',
            'total_value_usd', 'demand_reference_id', 'source_line_id',
            'source_document_number', 'source_document_date', 'entity_name',
            'aging_days', 'selling_uom', 'uom_conversion',
            'total_delivered_standard_quantity', 'original_standard_quantity'
        ])
    
    # ==================== DATA PROCESSING METHODS ====================
    
    def _process_supply_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """Process and normalize supply dataframe"""
        
        # Convert date columns
        date_cols = ['availability_date', 'expiry_date', 'source_document_date']
        for col in date_cols:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], errors='coerce')
        
        # Ensure numeric columns
        numeric_cols = [
            'product_id', 'available_quantity', 'days_to_available',
            'days_to_expiry', 'unit_cost_usd', 'total_value_usd',
            'completion_percentage'
        ]
        
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        
        # Normalize text fields
        text_cols = ['pt_code', 'product_name', 'brand', 'standard_uom', 'entity_name']
        for col in text_cols:
            if col in df.columns:
                df[col] = df[col].apply(lambda x: self._normalize_text_field(x, col))
        
        return df
    
    def _process_demand_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """Process and normalize demand dataframe"""
        
        # Convert date columns
        date_cols = ['required_date', 'source_document_date']
        for col in date_cols:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], errors='coerce')
        
        # Ensure numeric columns
        numeric_cols = [
            'product_id', 'required_quantity', 'allocated_quantity',
            'unallocated_quantity', 'days_to_required', 'selling_unit_price',
            'total_value_usd'
        ]
        
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        
        # Handle boolean columns
        bool_columns = ['is_allocated', 'is_over_committed']
        for col in bool_columns:
            if col in df.columns:
                df[col] = df[col].map({
                    'Yes': True, 'No': False,
                    1: True, 0: False,
                    True: True, False: False
                }).fillna(False)
        
        # Normalize text fields
        text_cols = ['pt_code', 'product_name', 'brand', 'standard_uom',
                     'customer', 'customer_code', 'entity_name']
        for col in text_cols:
            if col in df.columns:
                df[col] = df[col].apply(lambda x: self._normalize_text_field(x, col))
        
        return df