"""
Reusable column-filter helper for list endpoints.

Frontend sends a JSON string like: {"nombre":"acme","activo":"true"}
This module parses it and applies WHERE clauses to a SQLAlchemy query.
"""

import json
from typing import Any

from sqlalchemy import Boolean, Date, DateTime, Enum, Integer, Numeric, String, Text, cast
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.sql import Select


def apply_column_filters(
    query: Select,
    model: type[DeclarativeBase],
    filters_json: str | None,
    *,
    allowed_columns: set[str] | None = None,
    extra_mappings: dict[str, Any] | None = None,
) -> Select:
    """
    Parse a JSON filters string and apply per-column WHERE clauses.

    Parameters
    ----------
    query : SQLAlchemy Select
    model : The ORM model class to filter on
    filters_json : Raw JSON string from the query parameter, e.g. '{"nombre":"foo"}'
    allowed_columns : If provided, only these column names are accepted
    extra_mappings : dict mapping filter key -> SQLAlchemy column expression
        for columns that live on a joined table (e.g. "cliente_nombre": Cliente.nombre)
    """
    if not filters_json:
        return query

    try:
        filters: dict[str, str] = json.loads(filters_json)
    except (json.JSONDecodeError, TypeError):
        return query

    if not isinstance(filters, dict):
        return query

    for key, raw_value in filters.items():
        if not raw_value and raw_value != "0":
            continue

        if allowed_columns and key not in allowed_columns:
            continue

        col = None

        if extra_mappings and key in extra_mappings:
            col = extra_mappings[key]
        elif hasattr(model, key):
            col = getattr(model, key)
        else:
            continue

        col_prop = col.property.columns[0] if hasattr(col, 'property') else col
        col_type = getattr(col_prop, 'type', None)

        if isinstance(col_type, Boolean):
            bool_val = raw_value.lower() in ('true', '1', 'si', 'yes')
            query = query.where(col == bool_val)
        elif isinstance(col_type, (Enum,)):
            query = query.where(col == raw_value)
        elif isinstance(col_type, (Integer, Numeric)):
            try:
                num_val = float(raw_value)
                if isinstance(col_type, Integer):
                    query = query.where(col == int(num_val))
                else:
                    query = query.where(col == num_val)
            except (ValueError, TypeError):
                pass
        elif isinstance(col_type, (Date, DateTime)):
            query = query.where(cast(col, String).ilike(f"%{raw_value}%"))
        elif isinstance(col_type, (String, Text)):
            query = query.where(col.ilike(f"%{raw_value}%"))
        else:
            try:
                query = query.where(cast(col, String).ilike(f"%{raw_value}%"))
            except Exception:
                pass

    return query
