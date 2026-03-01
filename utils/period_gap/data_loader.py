# utils/period_gap/data_loader.py
"""
Simplified Data Loader for Period GAP Analysis
With numeric safety and proper data handling
Version 2.0 - Added ETA/ETD selection support for OC
"""

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from typing import List, Optional
import logging
from sqlalchemy import text

# Import only shared core modules
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))
from utils.db import get_db_engine

logger = logging.getLogger(__name__)

class PeriodGAPDataLoader:
    """Simplified data loader for Period GAP with numeric safety"""
    
    def __init__(self):
        self._cache = {}
    
    # === CORE LOADING METHODS ===
    
    @st.cache_data(ttl=1800)
    def load_demand_oc(_self):
        """Load OC (Order Confirmation) pending delivery data"""
        engine = get_db_engine()
        query = "SELECT * FROM prostechvn.outbound_oc_pending_delivery_view;"
        df = pd.read_sql(text(query), engine)
        
        # Ensure numeric columns
        df = _self._ensure_numeric_columns(df, [
            'selling_quantity', 'standard_quantity', 
            'pending_selling_delivery_quantity', 'pending_standard_delivery_quantity',
            'total_amount_usd', 'outstanding_amount_usd', 'uom_conversion'
        ])
        
        logger.info(f"Loaded {len(df)} OC pending delivery records")
        return df

    @st.cache_data(ttl=1800)
    def load_demand_forecast(_self):
        """Load customer demand forecast data"""
        engine = get_db_engine()
        query = "SELECT * FROM prostechvn.customer_demand_forecast_full_view;"
        df = pd.read_sql(text(query), engine)
        
        # Ensure numeric columns
        df = _self._ensure_numeric_columns(df, [
            'selling_quantity', 'standard_quantity',
            'total_amount_usd', 'standard_unit_price_usd'
        ])
        
        logger.info(f"Loaded {len(df)} forecast records")
        return df
    
    @st.cache_data(ttl=1800)
    def load_inventory(_self):
        """Load current inventory data"""
        engine = get_db_engine()
        query = "SELECT * FROM prostechvn.inventory_detailed_view"
        df = pd.read_sql(text(query), engine)
        
        # Ensure numeric columns
        df = _self._ensure_numeric_columns(df, [
            'remaining_quantity', 'inventory_value_usd'
        ])
        
        logger.info(f"Loaded {len(df)} inventory records")
        return df

    @st.cache_data(ttl=1800)
    def load_pending_can(_self):
        """Load pending CAN (Container Arrival Note) data"""
        engine = get_db_engine()
        query = "SELECT * FROM prostechvn.can_pending_stockin_view"
        df = pd.read_sql(text(query), engine)
        
        # Ensure numeric columns
        df = _self._ensure_numeric_columns(df, [
            'pending_quantity', 'pending_value_usd'
        ])
        
        logger.info(f"Loaded {len(df)} pending CAN records")
        return df

    @st.cache_data(ttl=1800)
    def load_pending_po(_self):
        """Load pending PO data"""
        engine = get_db_engine()
        query = """
        SELECT * FROM prostechvn.purchase_order_full_view
        WHERE pending_standard_arrival_quantity > 0
        """
        df = pd.read_sql(text(query), engine)
        
        # Ensure numeric columns
        df = _self._ensure_numeric_columns(df, [
            'pending_standard_arrival_quantity', 'outstanding_arrival_amount_usd',
            'buying_quantity', 'purchase_unit_cost'
        ])
        
        logger.info(f"Loaded {len(df)} pending PO records")
        return df

    @st.cache_data(ttl=1800)
    def load_pending_wh_transfer(_self):
        """Load pending Warehouse Transfer data"""
        engine = get_db_engine()
        query = """
        SELECT * FROM prostechvn.warehouse_transfer_details_view wtdv
        WHERE wtdv.is_completed = 0
        """
        df = pd.read_sql(text(query), engine)
        
        # Ensure numeric columns
        df = _self._ensure_numeric_columns(df, [
            'transfer_quantity', 'warehouse_transfer_value_usd'
        ])
        
        logger.info(f"Loaded {len(df)} pending WH transfer records")
        return df
    
    # === NUMERIC SAFETY METHOD ===
    
    def _ensure_numeric_columns(self, df: pd.DataFrame, columns: List[str]) -> pd.DataFrame:
        """Ensure specified columns are numeric to prevent Arrow serialization errors"""
        for col in columns:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        return df

    # === STANDARDIZATION METHODS ===
    
    def _standardize_demand_df(self, df: pd.DataFrame, is_forecast: bool, 
                              oc_date_field: str = "ETA") -> pd.DataFrame:
        """
        Standardize demand dataframe with numeric safety
        
        Args:
            df: Demand dataframe
            is_forecast: Whether this is forecast data
            oc_date_field: Which date field to use for OC ("ETA" or "ETD")
        """
        df = df.copy()
        
        # Date columns handling - UNIFIED approach
        if is_forecast:
            # For Forecast, use ETD
            if 'etd' in df.columns:
                df["demand_date"] = pd.to_datetime(df["etd"], errors="coerce")
            # Keep original fields too
            if 'etd' in df.columns:
                df["etd"] = pd.to_datetime(df["etd"], errors="coerce")
        else:
            # For OC, use selected field (ETA or ETD)
            if oc_date_field == "ETA" and 'eta' in df.columns:
                df["demand_date"] = pd.to_datetime(df["eta"], errors="coerce")
            elif oc_date_field == "ETD" and 'etd' in df.columns:
                df["demand_date"] = pd.to_datetime(df["etd"], errors="coerce")
            else:
                # Fallback to ETD if selected field not available
                if 'etd' in df.columns:
                    df["demand_date"] = pd.to_datetime(df["etd"], errors="coerce")
            
            # Keep both original fields for reference
            if 'etd' in df.columns:
                df["etd"] = pd.to_datetime(df["etd"], errors="coerce")
            if 'eta' in df.columns:
                df["eta"] = pd.to_datetime(df["eta"], errors="coerce")
        
        if 'oc_date' in df.columns:
            df["oc_date"] = pd.to_datetime(df["oc_date"], errors="coerce")
        
        # Quantity and value columns with numeric safety
        if is_forecast:
            df['demand_quantity'] = pd.to_numeric(
                df.get('standard_quantity', 0), errors='coerce'
            ).fillna(0)
            df['value_in_usd'] = pd.to_numeric(
                df.get('total_amount_usd', 0), errors='coerce'
            ).fillna(0)
            df['demand_number'] = df.get('forecast_number', '')
            
            # Handle conversion status
            if 'is_converted_to_oc' in df.columns:
                df['is_converted_to_oc'] = df['is_converted_to_oc'].astype(str).str.strip()
            else:
                df['is_converted_to_oc'] = 'No'
            
            df['demand_line_id'] = df.get('forecast_line_id', '').astype(str) + '_FC'
        else:
            df['demand_quantity'] = pd.to_numeric(
                df.get('pending_standard_delivery_quantity', 0), errors='coerce'
            ).fillna(0)
            df['value_in_usd'] = pd.to_numeric(
                df.get('outstanding_amount_usd', 0), errors='coerce'
            ).fillna(0)
            df['demand_number'] = df.get('oc_number', '')
            df['is_converted_to_oc'] = 'N/A'
            df['demand_line_id'] = df.get('ocd_id', '').astype(str) + '_OC'
        
        # Clean string columns
        string_cols = ['product_name', 'pt_code', 'brand', 'legal_entity', 'customer']
        for col in string_cols:
            if col in df.columns:
                df[col] = df[col].astype(str).str.strip()
                df[col] = df[col].str.replace(r'\s+', ' ', regex=True)
                # Clean 'nan' strings
                df[col] = df[col].replace(['nan', 'None', ''], pd.NA)
            else:
                df[col] = ''
        
        # UOM and package size
        df['standard_uom'] = df.get('standard_uom', '').astype(str).str.strip().str.upper()
        df['package_size'] = df.get('package_size', '').astype(str).str.strip()
        
        # Final numeric safety check
        numeric_cols = ['demand_quantity', 'value_in_usd']
        df = self._ensure_numeric_columns(df, numeric_cols)
        
        return df

    def _prepare_inventory_data(self, inv_df: pd.DataFrame, today: pd.Timestamp, 
                                exclude_expired: bool) -> pd.DataFrame:
        """Prepare inventory data with numeric safety"""
        inv_df = inv_df.copy()
        inv_df["source_type"] = "Inventory"
        
        # Inventory is available NOW
        inv_df["date_ref"] = today
        
        # Map columns with numeric safety
        inv_df["quantity"] = pd.to_numeric(
            inv_df.get("remaining_quantity", 0), errors="coerce"
        ).fillna(0)
        
        inv_df["value_in_usd"] = pd.to_numeric(
            inv_df.get("inventory_value_usd", 0), errors="coerce"
        ).fillna(0)
        
        inv_df["legal_entity"] = inv_df.get("owning_company_name", '')
        inv_df["supply_number"] = inv_df.get("inventory_history_id", '').astype(str)
        
        # Handle expiry
        if 'expiry_date' in inv_df.columns:
            inv_df["expiry_date"] = pd.to_datetime(inv_df["expiry_date"], errors="coerce")
            inv_df["days_until_expiry"] = (inv_df["expiry_date"] - today).dt.days
            
            if exclude_expired:
                inv_df = inv_df[
                    (inv_df["expiry_date"].isna()) | (inv_df["expiry_date"] >= today)
                ]
        
        return inv_df

    def _prepare_can_data(self, can_df: pd.DataFrame) -> pd.DataFrame:
        """Prepare CAN data with numeric safety"""
        can_df = can_df.copy()
        can_df["source_type"] = "Pending CAN"
        
        # Use arrival_date
        if 'arrival_date' in can_df.columns:
            can_df["arrival_date"] = pd.to_datetime(can_df["arrival_date"], errors="coerce")
            can_df["date_ref"] = can_df["arrival_date"]
        else:
            can_df["date_ref"] = pd.NaT
        
        # Map columns with numeric safety
        can_df["quantity"] = pd.to_numeric(
            can_df.get("pending_quantity", 0), errors="coerce"
        ).fillna(0)
        
        can_df["value_in_usd"] = pd.to_numeric(
            can_df.get("pending_value_usd", 0), errors="coerce"
        ).fillna(0)
        
        can_df["legal_entity"] = can_df.get("consignee", '')
        can_df["supply_number"] = can_df.get("arrival_note_number", '').astype(str)
        
        return can_df

    def _prepare_po_data(self, po_df: pd.DataFrame) -> pd.DataFrame:
        """Prepare PO data with numeric safety"""
        po_df = po_df.copy()
        po_df["source_type"] = "Pending PO"
        
        # Use eta
        if 'eta' in po_df.columns:
            po_df["eta"] = pd.to_datetime(po_df["eta"], errors="coerce")
            po_df["date_ref"] = po_df["eta"]
        else:
            po_df["date_ref"] = pd.NaT
        
        # Map columns with numeric safety
        po_df["quantity"] = pd.to_numeric(
            po_df.get("pending_standard_arrival_quantity", 0), errors="coerce"
        ).fillna(0)
        
        po_df["value_in_usd"] = pd.to_numeric(
            po_df.get("outstanding_arrival_amount_usd", 0), errors="coerce"
        ).fillna(0)
        
        if 'legal_entity' not in po_df.columns:
            po_df["legal_entity"] = ''
        
        # Create supply number
        if 'po_line_id' in po_df.columns and 'po_number' in po_df.columns:
            po_df["supply_number"] = (
                po_df["po_number"].astype(str) + "_L" + po_df["po_line_id"].astype(str)
            )
        elif 'po_number' in po_df.columns:
            po_df["supply_number"] = po_df["po_number"].astype(str)
        else:
            po_df["supply_number"] = ''
        
        if 'vendor_name' in po_df.columns:
            po_df["vendor"] = po_df["vendor_name"]
        
        return po_df

    def _prepare_wh_transfer_data(self, wht_df: pd.DataFrame, today: pd.Timestamp, 
                                  exclude_expired: bool) -> pd.DataFrame:
        """Prepare warehouse transfer data with numeric safety"""
        wht_df = wht_df.copy()
        wht_df["source_type"] = "Pending WH Transfer"
        
        # Use transfer_date
        if 'transfer_date' in wht_df.columns:
            wht_df["transfer_date"] = pd.to_datetime(wht_df["transfer_date"], errors="coerce")
            wht_df["date_ref"] = wht_df["transfer_date"]
            wht_df["days_in_transfer"] = (today - wht_df["transfer_date"]).dt.days.fillna(0)
        else:
            wht_df["date_ref"] = pd.NaT
        
        # Map columns with numeric safety
        wht_df["quantity"] = pd.to_numeric(
            wht_df.get("transfer_quantity", 0), errors="coerce"
        ).fillna(0)
        
        wht_df["value_in_usd"] = pd.to_numeric(
            wht_df.get("warehouse_transfer_value_usd", 0), errors="coerce"
        ).fillna(0)
        
        wht_df["legal_entity"] = wht_df.get("owning_company_name", '')
        wht_df["supply_number"] = wht_df.get("warehouse_transfer_line_id", '').astype(str)
        
        # Handle expiry
        if 'expiry_date' in wht_df.columns:
            wht_df["expiry_date"] = pd.to_datetime(wht_df["expiry_date"], errors="coerce")
            
            if exclude_expired:
                wht_df = wht_df[
                    (wht_df["expiry_date"].isna()) | (wht_df["expiry_date"] >= today)
                ]
        
        # Transfer route
        if 'from_warehouse' in wht_df.columns and 'to_warehouse' in wht_df.columns:
            wht_df["transfer_route"] = (
                wht_df["from_warehouse"] + " → " + wht_df["to_warehouse"]
            )
        
        return wht_df

    def _standardize_supply_df(self, df: pd.DataFrame) -> pd.DataFrame:
        """Standardize supply dataframe with numeric safety"""
        df = df.copy()
        
        # Clean string columns
        string_cols = ["pt_code", "product_name", "brand"]
        for col in string_cols:
            if col in df.columns:
                df[col] = df[col].astype(str).str.strip()
                df[col] = df[col].str.replace(r'\s+', ' ', regex=True)
                # Clean 'nan' strings
                df[col] = df[col].replace(['nan', 'None', ''], pd.NA)
            else:
                df[col] = ''
        
        # UOM and package size
        df["standard_uom"] = df.get("standard_uom", '').astype(str).str.strip().str.upper()
        df["package_size"] = df.get("package_size", '').astype(str).str.strip()
        
        # Ensure numeric columns
        numeric_cols = ["value_in_usd", "quantity", "days_in_transfer", "days_since_arrival", "days_until_expiry"]
        df = self._ensure_numeric_columns(df, numeric_cols)
        
        # Ensure required columns exist
        for col in ["value_in_usd", "quantity", "legal_entity", "date_ref", "source_type"]:
            if col not in df.columns:
                df[col] = 0 if col in ["value_in_usd", "quantity"] else ''
        
        # Select standard columns
        standard_cols = [
            "source_type", "pt_code", "product_name", "brand", 
            "package_size", "standard_uom", "legal_entity", "date_ref", 
            "quantity", "value_in_usd"
        ]
        
        # Add optional columns if they exist
        optional_cols = [
            "supply_number", "expiry_date", "days_until_expiry", 
            "days_since_arrival", "vendor", "transfer_route", 
            "days_in_transfer", "from_warehouse", "to_warehouse",
            "arrival_date", "eta", "transfer_date",
            "po_number", "po_line_id", "buying_quantity", "buying_uom", 
            "purchase_unit_cost", "vendor_name"
        ]
        
        final_cols = standard_cols.copy()
        for col in optional_cols:
            if col in df.columns and col not in final_cols:
                final_cols.append(col)
        
        return df[final_cols]

    # === PUBLIC METHODS ===
    
    def get_demand_data(self, sources: List[str], include_converted: bool = False,
                       oc_date_field: str = "ETA") -> pd.DataFrame:
        """
        Get combined demand data with numeric safety
        
        Args:
            sources: List of demand sources
            include_converted: Whether to include converted forecasts
            oc_date_field: Which date field to use for OC ("ETA" or "ETD")
        """
        df_parts = []
        
        if "OC" in sources:
            df_oc = self.load_demand_oc()
            if not df_oc.empty:
                df_oc["source_type"] = "OC"
                df_oc = self._standardize_demand_df(df_oc, is_forecast=False, oc_date_field=oc_date_field)
                df_parts.append(df_oc)
        
        if "Forecast" in sources:
            df_fc = self.load_demand_forecast()
            if not df_fc.empty:
                df_fc["source_type"] = "Forecast"
                standardized_fc = self._standardize_demand_df(df_fc, is_forecast=True)
                
                if not include_converted and 'is_converted_to_oc' in standardized_fc.columns:
                    converted_values = ['Yes', 'yes', 'Y', 'y', '1', 1, True, 'True', 'true']
                    standardized_fc = standardized_fc[
                        ~standardized_fc["is_converted_to_oc"].isin(converted_values)
                    ]
                
                df_parts.append(standardized_fc)
        
        if df_parts:
            combined = pd.concat(df_parts, ignore_index=True)
            
            # Final numeric safety check
            numeric_cols = ['demand_quantity', 'value_in_usd']
            combined = self._ensure_numeric_columns(combined, numeric_cols)
            
            logger.info(f"Combined {len(combined)} demand records from {len(sources)} sources using {oc_date_field} for OC")
            return combined
        
        return pd.DataFrame()

    def get_supply_data(self, sources: List[str], exclude_expired: bool = True) -> pd.DataFrame:
        """Get combined supply data with numeric safety"""
        today = pd.to_datetime("today").normalize()
        df_parts = []
        
        if "Inventory" in sources:
            inv_df = self.load_inventory()
            if not inv_df.empty:
                inv_df = self._prepare_inventory_data(inv_df, today, exclude_expired)
                df_parts.append(inv_df)
        
        if "Pending CAN" in sources:
            can_df = self.load_pending_can()
            if not can_df.empty:
                can_df = self._prepare_can_data(can_df)
                df_parts.append(can_df)
        
        if "Pending PO" in sources:
            po_df = self.load_pending_po()
            if not po_df.empty:
                po_df = self._prepare_po_data(po_df)
                df_parts.append(po_df)
        
        if "Pending WH Transfer" in sources:
            wht_df = self.load_pending_wh_transfer()
            if not wht_df.empty:
                wht_df = self._prepare_wh_transfer_data(wht_df, today, exclude_expired)
                df_parts.append(wht_df)
        
        if not df_parts:
            return pd.DataFrame()
        
        # Standardize each part before combining
        standardized_parts = []
        for df in df_parts:
            if not df.empty:
                standardized_df = self._standardize_supply_df(df)
                standardized_parts.append(standardized_df)
        
        if standardized_parts:
            combined = pd.concat(standardized_parts, ignore_index=True, sort=False)
            combined = combined.reset_index(drop=True)
            
            # Final numeric safety check
            numeric_cols = ['quantity', 'value_in_usd']
            combined = self._ensure_numeric_columns(combined, numeric_cols)
            
            logger.info(f"Combined {len(combined)} supply records from {len(sources)} sources")
            return combined
        
        return pd.DataFrame()
    
    def clear_cache(self):
        """Clear data cache"""
        self._cache.clear()
        st.cache_data.clear()