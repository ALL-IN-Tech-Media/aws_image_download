# Required dependency: pip install sqlalchemy
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
import csv
import json
import datetime
import os
from typing import List, Dict, Any, Optional, Tuple, Union

# Database connection constants
DB_HOST = "localhost"
DB_PORT = 3306
DB_USER = "root"
DB_PASSWORD = "123456"
DB_NAME = "tiktok_creator"
DB_TABLE = "videos_links"

# SQLAlchemy database URL
DATABASE_URL = f"mysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

def create_database_engine():
    """
    Create SQLAlchemy database engine with error handling
    
    Returns:
        sqlalchemy.engine.Engine: Database engine object
    """
    try:
        # Try basic connection first
        engine = create_engine(DATABASE_URL)
        # Test connection
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        print(f"Successfully created database engine for: {DB_NAME}")
        return engine
    except SQLAlchemyError as e:
        print(f"Error with basic connection: {e}")
        print("Trying alternative connection with authentication parameters...")
        
        # Try with additional connection parameters for authentication
        try:
            engine = create_engine(
                DATABASE_URL,
                connect_args={
                    "auth_plugin": "mysql_native_password",
                    "charset": "utf8mb4"
                }
            )
            # Test connection
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            print(f"Successfully created database engine with auth params for: {DB_NAME}")
            return engine
        except SQLAlchemyError as e2:
            print(f"Error with auth parameters: {e2}")
            print("Try installing a MySQL driver: pip install PyMySQL or pip install mysqlclient")
            return None

def connect_to_database():
    """
    Create database connection using SQLAlchemy
    
    Returns:
        sqlalchemy.engine.Connection: Database connection object
    """
    engine = create_database_engine()
    if not engine:
        return None
    
    try:
        connection = engine.connect()
        print(f"Successfully connected to database: {DB_NAME}")
        return connection
    except SQLAlchemyError as e:
        print(f"Error connecting to database: {e}")
        return None

def parse_date_filter(date_filter: Union[str, Tuple[str, str], None]) -> Tuple[Optional[str], Optional[str]]:
    """
    Parse date filter into start_date and end_date
    
    Args:
        date_filter: Can be "last_X_days", tuple of (start_date, end_date), or None
    
    Returns:
        Tuple of (start_date, end_date) in YYYY-MM-DD format
    """
    if date_filter is None:
        return None, None
    
    if isinstance(date_filter, tuple) and len(date_filter) == 2:
        # Direct date range
        return date_filter[0], date_filter[1]
    
    if isinstance(date_filter, str):
        today = datetime.date.today()
        
        if date_filter == "last_7_days":
            start_date = today - datetime.timedelta(days=7)
            return start_date.strftime("%Y-%m-%d"), today.strftime("%Y-%m-%d")
        
        elif date_filter == "last_30_days":
            start_date = today - datetime.timedelta(days=30)
            return start_date.strftime("%Y-%m-%d"), today.strftime("%Y-%m-%d")
        
        elif date_filter == "last_90_days":
            start_date = today - datetime.timedelta(days=90)
            return start_date.strftime("%Y-%m-%d"), today.strftime("%Y-%m-%d")
        
        elif date_filter.startswith("last_") and date_filter.endswith("_days"):
            # Extract number of days
            try:
                days = int(date_filter.split("_")[1])
                start_date = today - datetime.timedelta(days=days)
                return start_date.strftime("%Y-%m-%d"), today.strftime("%Y-%m-%d")
            except (ValueError, IndexError):
                print(f"Invalid date filter format: {date_filter}")
                return None, None
    
    print(f"Unsupported date filter: {date_filter}")
    return None, None

def get_cover_urls(date_filter: Union[str, Tuple[str, str], None] = None, 
                   creator_filter: Union[str, List[str], None] = None) -> List[Dict[str, Any]]:
    """
    Get cover URLs from database with filtering
    
    Args:
        date_filter: Date filtering options
        creator_filter: Creator name(s) to filter by
    
    Returns:
        List of dictionaries with creator_name, cover_urls, created_at
    """
    connection = connect_to_database()
    if not connection:
        return []
    
    try:
        # Build SQL query with WHERE clauses
        base_query = f"SELECT creator_name, cover_urls, created_at FROM {DB_TABLE}"
        where_clauses = []
        params = {}
        
        # Add date filtering
        start_date, end_date = parse_date_filter(date_filter)
        if start_date and end_date:
            where_clauses.append("created_at BETWEEN :start_date AND :end_date")
            params.update({"start_date": start_date, "end_date": end_date})
            print(f"Filtering by date range: {start_date} to {end_date}")
        
        # Add creator filtering
        if creator_filter:
            if isinstance(creator_filter, str):
                where_clauses.append("creator_name LIKE :creator_name")
                params["creator_name"] = f"%{creator_filter}%"
                print(f"Filtering by creator: {creator_filter}")
            elif isinstance(creator_filter, list):
                # For IN clause with list, we need to handle it differently
                placeholders = ", ".join([f":creator_{i}" for i in range(len(creator_filter))])
                where_clauses.append(f"creator_name IN ({placeholders})")
                for i, creator in enumerate(creator_filter):
                    params[f"creator_{i}"] = creator
                print(f"Filtering by creators: {creator_filter}")
        
        # Add WHERE clause if filters exist
        if where_clauses:
            query = f"{base_query} WHERE {' AND '.join(where_clauses)}"
        else:
            query = base_query
        
        # Add ORDER BY for consistent results
        query += " ORDER BY created_at DESC"
        
        print(f"Executing query: {query}")
        print(f"With parameters: {params}")
        
        # Execute query using SQLAlchemy
        result = connection.execute(text(query), params)
        rows = result.fetchall()
        
        # Convert SQLAlchemy Row objects to dictionaries
        results = []
        for row in rows:
            results.append({
                "creator_name": row.creator_name,
                "cover_urls": row.cover_urls,
                "created_at": row.created_at
            })
        
        print(f"Found {len(results)} records")
        return results
        
    except SQLAlchemyError as e:
        print(f"Error executing query: {e}")
        return []
    
    finally:
        connection.close()
        print("Database connection closed")

def process_cover_urls(raw_data: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    """
    Process raw database results and flatten cover URLs
    
    Args:
        raw_data: List of dictionaries from database query
    
    Returns:
        List of flattened records with individual URLs
    """
    processed_data = []
    
    for record in raw_data:
        creator_name = record.get('creator_name', '')
        cover_urls_json = record.get('cover_urls', '')
        created_at = record.get('created_at', '')
        
        # Format date for CSV
        if created_at:
            if isinstance(created_at, datetime.datetime):
                formatted_date = created_at.strftime("%Y-%m-%d %H:%M:%S")
            else:
                formatted_date = str(created_at)
        else:
            formatted_date = ''
        
        # Parse cover URLs JSON
        try:
            if cover_urls_json:
                if isinstance(cover_urls_json, str):
                    cover_urls = json.loads(cover_urls_json)
                else:
                    cover_urls = cover_urls_json
                
                # Handle case where cover_urls is a list
                if isinstance(cover_urls, list):
                    for url in cover_urls:
                        if url:  # Skip empty URLs
                            processed_data.append({
                                'creator_name': creator_name,
                                'cover_url': url,
                                'created_at': formatted_date
                            })
                else:
                    # Handle case where it's a single URL (unlikely but possible)
                    processed_data.append({
                        'creator_name': creator_name,
                        'cover_url': str(cover_urls),
                        'created_at': formatted_date
                    })
            else:
                # No cover URLs, add record with empty URL
                processed_data.append({
                    'creator_name': creator_name,
                    'cover_url': '',
                    'created_at': formatted_date
                })
                
        except (json.JSONDecodeError, TypeError) as e:
            print(f"Error parsing cover URLs for {creator_name}: {e}")
            # Add record with error indicator
            processed_data.append({
                'creator_name': creator_name,
                'cover_url': f'ERROR: {str(e)}',
                'created_at': formatted_date
            })
    
    print(f"Processed {len(processed_data)} URL records from {len(raw_data)} database records")
    return processed_data

def save_to_csv(processed_data: List[Dict[str, str]], output_dir: str = None) -> str:
    """
    Save processed data to CSV file with timestamp-based filename
    
    Args:
        processed_data: List of processed URL records
        output_dir: Output directory (defaults to script directory)
    
    Returns:
        str: Path to created CSV file
    """
    if not processed_data:
        print("No data to save")
        return ""
    
    # Generate timestamp-based filename
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"cover_urls_{timestamp}.csv"
    
    # Use script directory if output_dir not specified
    if output_dir is None:
        output_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Ensure output directory exists
    os.makedirs(output_dir, exist_ok=True)
    
    filepath = os.path.join(output_dir, filename)
    
    try:
        with open(filepath, 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = ['creator_name', 'cover_url', 'created_at']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            
            # Write header
            writer.writeheader()
            
            # Write data
            writer.writerows(processed_data)
        
        print(f"Successfully saved {len(processed_data)} records to: {filepath}")
        return filepath
        
    except IOError as e:
        print(f"Error saving CSV file: {e}")
        return ""

def main():
    """
    Main function with example usage and testing scenarios
    """
    # print("=== TikTok Cover URLs Extraction Tool ===")
    # print()
    
    # # Example 1: Get all URLs from last 30 days
    # print("Example 1: Getting URLs from last 30 days...")
    # raw_data = get_cover_urls(date_filter="last_30_days")
    # if raw_data:
    #     processed_data = process_cover_urls(raw_data)
    #     if processed_data:
    #         csv_path = save_to_csv(processed_data)
    #         print(f"✓ Saved to: {csv_path}")
    # print()
    
    # # Example 2: Get URLs for specific date range
    # print("Example 2: Getting URLs for specific date range (2024-01-01 to 2024-01-31)...")
    # raw_data = get_cover_urls(date_filter=("2024-08-10", "2024-08-18"))
    # if raw_data:
    #     processed_data = process_cover_urls(raw_data)
    #     if processed_data:
    #         csv_path = save_to_csv(processed_data)
    #         print(f"✓ Saved to: {csv_path}")
    # print()
    
    # # Example 3: Get URLs for specific creator (last 7 days)
    # print("Example 3: Getting URLs for specific creator (last 7 days)...")
    # # Note: Replace 'example_creator' with actual creator name from your database
    # raw_data = get_cover_urls(date_filter="last_7_days", creator_filter="example_creator")
    # if raw_data:
    #     processed_data = process_cover_urls(raw_data)
    #     if processed_data:
    #         csv_path = save_to_csv(processed_data)
    #         print(f"✓ Saved to: {csv_path}")
    # else:
    #     print("No data found for this creator")
    # print()
    
    # Example 4: Get all URLs (no filtering) - limited for testing
    print("Example 4: Getting all URLs (limited to 100 records for testing)...")
    limit_number = 20
    raw_data = get_cover_urls()
    if raw_data:
        # Limit to first 100 records for testing
        limited_data = raw_data#[:limit_number] if len(raw_data) > limit_number else raw_data
        processed_data = process_cover_urls(limited_data)
        if processed_data:
            csv_path = save_to_csv(processed_data)
            print(f"✓ Saved to: {csv_path}")
    print()
    
    # print("=== Extraction Complete ===")

if __name__ == "__main__":
    main()
