"""
Elasticsearch Query Builder
Provides functions for building Elasticsearch queries
"""
from datetime import datetime
from typing import Dict, Any, List, Optional, Union


def match_query(field: str, value: Any) -> Dict[str, Any]:
    """
    Create a match query
    
    Args:
        field: Field name
        value: Value to match
        
    Returns:
        Dict[str, Any]: Match query
    """
    return {
        "match": {
            field: value
        }
    }


def term_query(field: str, value: Any) -> Dict[str, Any]:
    """
    Create a term query
    
    Args:
        field: Field name
        value: Value to match exactly
        
    Returns:
        Dict[str, Any]: Term query
    """
    return {
        "term": {
            field: value
        }
    }


def terms_query(field: str, values: List[Any]) -> Dict[str, Any]:
    """
    Create a terms query (match any value in the list)
    
    Args:
        field: Field name
        values: List of values to match
        
    Returns:
        Dict[str, Any]: Terms query
    """
    return {
        "terms": {
            field: values
        }
    }


def range_query(
    field: str,
    gte: Optional[Any] = None,
    lte: Optional[Any] = None,
    gt: Optional[Any] = None,
    lt: Optional[Any] = None
) -> Dict[str, Any]:
    """
    Create a range query
    
    Args:
        field: Field name
        gte: Greater than or equal to
        lte: Less than or equal to
        gt: Greater than
        lt: Less than
        
    Returns:
        Dict[str, Any]: Range query
    """
    range_params = {}
    if gte is not None:
        range_params["gte"] = gte
    if lte is not None:
        range_params["lte"] = lte
    if gt is not None:
        range_params["gt"] = gt
    if lt is not None:
        range_params["lt"] = lt
    
    return {
        "range": {
            field: range_params
        }
    }


def date_range_query(
    field: str,
    start_date: Optional[Union[datetime, str]] = None,
    end_date: Optional[Union[datetime, str]] = None
) -> Dict[str, Any]:
    """
    Create a date range query
    
    Args:
        field: Date field name
        start_date: Start date (inclusive)
        end_date: End date (inclusive)
        
    Returns:
        Dict[str, Any]: Date range query
    """
    range_params = {}
    
    if start_date:
        if isinstance(start_date, datetime):
            start_date = start_date.isoformat()
        range_params["gte"] = start_date
    
    if end_date:
        if isinstance(end_date, datetime):
            end_date = end_date.isoformat()
        range_params["lte"] = end_date
    
    return {
        "range": {
            field: range_params
        }
    }


def bool_query(
    must: Optional[List[Dict[str, Any]]] = None,
    should: Optional[List[Dict[str, Any]]] = None,
    must_not: Optional[List[Dict[str, Any]]] = None,
    filter_: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """
    Create a bool query
    
    Args:
        must: Queries that must match
        should: Queries that should match (at least one)
        must_not: Queries that must not match
        filter_: Filters to apply
        
    Returns:
        Dict[str, Any]: Bool query
    """
    bool_params = {}
    
    if must:
        bool_params["must"] = must
    
    if should:
        bool_params["should"] = should
    
    if must_not:
        bool_params["must_not"] = must_not
    
    if filter_:
        bool_params["filter"] = filter_
    
    return {
        "query": {
            "bool": bool_params
        }
    }


def nested_query(path: str, query: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a nested query for nested fields
    
    Args:
        path: Path to the nested field
        query: Query to apply to the nested field
        
    Returns:
        Dict[str, Any]: Nested query
    """
    return {
        "nested": {
            "path": path,
            "query": query
        }
    }


def build_search_query(
    query_parts: List[Dict[str, Any]],
    sort: Optional[List[Dict[str, Any]]] = None,
    size: int = 10,
    from_: int = 0
) -> Dict[str, Any]:
    """
    Build a complete search query
    
    Args:
        query_parts: List of query parts to combine with bool query
        sort: Sort criteria
        size: Number of results to return
        from_: Starting offset
        
    Returns:
        Dict[str, Any]: Complete search query
    """
    search_query = {
        "size": size,
        "from": from_,
        "query": {
            "bool": {
                "must": query_parts
            }
        }
    }
    
    if sort:
        search_query["sort"] = sort
    
    return search_query


def build_aggregation_query(
    aggs: Dict[str, Any],
    query_parts: Optional[List[Dict[str, Any]]] = None,
    size: int = 0
) -> Dict[str, Any]:
    """
    Build a query with aggregations
    
    Args:
        aggs: Aggregations to perform
        query_parts: List of query parts to filter the aggregation
        size: Number of document results to return (0 for aggregations only)
        
    Returns:
        Dict[str, Any]: Aggregation query
    """
    agg_query = {
        "size": size,
        "aggs": aggs
    }
    
    if query_parts:
        # Create a bool query with must clause
        agg_query["query"] = {
            "bool": {
                "must": query_parts
            }
        }
    
    return agg_query


def terms_aggregation(field: str, size: int = 10) -> Dict[str, Any]:
    """
    Create a terms aggregation
    
    Args:
        field: Field to aggregate
        size: Number of buckets to return
        
    Returns:
        Dict[str, Any]: Terms aggregation
    """
    return {
        "terms": {
            "field": field,
            "size": size
        }
    }


def date_histogram_aggregation(
    field: str,
    interval: str = "day",
    format: str = "yyyy-MM-dd"
) -> Dict[str, Any]:
    """
    Create a date histogram aggregation
    
    Args:
        field: Date field to aggregate
        interval: Interval (year, quarter, month, week, day, hour, minute, second)
        format: Date format for the buckets
        
    Returns:
        Dict[str, Any]: Date histogram aggregation
    """
    return {
        "date_histogram": {
            "field": field,
            "calendar_interval": interval,
            "format": format
        }
    }