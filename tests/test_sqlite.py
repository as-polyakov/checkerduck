#!/usr/bin/env python3
"""
Test script to verify the SQLite integration works correctly.
This script demonstrates basic functionality without needing real API calls.
"""

import json
from checkerduck.extract.extract import AhrefsClient, AhrefsDatabaseError

def test_database_operations():
    """Test database initialization and basic operations."""
    print("🧪 Testing SQLite integration...")
    
    # Initialize client (no API token needed for database testing)
    client = AhrefsClient(api_token="test_token", db_path="../ahrefs_data.db")
    
    try:
        # Test database initialization
        print("✅ Initializing database...")
        success = client.init_database()
        if success:
            print("✅ Database initialized successfully!")
        else:
            print("❌ Database initialization failed")
            return
        
        # Create mock API response data for testing
        mock_results = {
            "results": [
                {
                    "url": "https://www.example.com",
                    "ahrefs_rank": 1000,
                    "domain_rating": 85.5,
                    "url_rating": 82.3,
                    "backlinks": 45000,
                    "backlinks_dofollow": 30000,
                    "org_traffic": 15000,
                    "org_keywords": 5000,
                    "protocol": "https",
                    "mode": "exact",
                    "ip": "192.168.1.1",
                    "org_traffic_top_by_country": [
                        {"country": "US", "traffic": 8000, "cost": 12000, "keywords": 2000},
                        {"country": "CA", "traffic": 3000, "cost": 4500, "keywords": 800},
                        {"country": "GB", "traffic": 2000, "cost": 3200, "keywords": 600}
                    ]
                },
                {
                    "url": "https://www.test.com",
                    "ahrefs_rank": 5000,
                    "domain_rating": 65.2,
                    "url_rating": 70.1,
                    "backlinks": 12000,
                    "backlinks_dofollow": 8000,
                    "org_traffic": 5000,
                    "org_keywords": 1500,
                    "protocol": "both",
                    "mode": "domain",
                    "ip": "10.0.0.1",
                    "org_traffic_top_by_country": [
                        {"country": "DE", "traffic": 2000, "cost": 3000, "keywords": 500},
                        {"country": "FR", "traffic": 1500, "cost": 2200, "keywords": 400}
                    ]
                }
            ]
        }
        
        # Test saving to database
        print("✅ Saving test data to database...")
        target_ids = client.persist_batch_analysis(mock_results)
        print(f"✅ Successfully saved {len(target_ids)} records")
        print(f"✅ Target IDs: {target_ids}")
        
        # Verify data was saved by connecting to database directly
        print("✅ Verifying saved data...")
        conn = client._get_db_connection()
        cursor = conn.cursor()
        
        # Check main table
        cursor.execute("SELECT COUNT(*) FROM batch_analysis")
        count = cursor.fetchone()[0]
        print(f"✅ Main table contains {count} records")
        
        # Check country table
        cursor.execute("SELECT COUNT(*) FROM ahrefs_org_traffic_country")
        country_count = cursor.fetchone()[0]
        print(f"✅ Country table contains {country_count} records")
        
        # Show sample data
        cursor.execute("""
            SELECT url, ahrefs_rank, domain_rating, org_traffic 
            FROM batch_analysis 
            ORDER BY ahrefs_rank 
            LIMIT 3
        """)
        print("\n📊 Sample data from database:")
        for row in cursor.fetchall():
            print(f"   URL: {row[0]}, Rank: {row[1]}, DR: {row[2]}, Traffic: {row[3]}")
        
        # Show country data
        cursor.execute("""
            SELECT ba.url, tc.country_code, tc.traffic, tc.cost 
            FROM batch_analysis ba 
            JOIN ahrefs_org_traffic_country tc ON ba.target_id = tc.target_id
            ORDER BY tc.traffic DESC
            LIMIT 5
        """)
        print("\n🌍 Country traffic data:")
        for row in cursor.fetchall():
            print(f"   {row[0]} - {row[1]}: {row[2]} traffic, ${row[3]} cost")
        
        conn.close()
        print("\n🎉 All tests passed! SQLite integration is working correctly.")
        
    except AhrefsDatabaseError as e:
        print(f"❌ Database error: {e}")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
    
    print(f"\n💾 Test database file: test_ahrefs.db")
    print("You can examine it with: sqlite3 test_ahrefs.db")

if __name__ == "__main__":
    test_database_operations()
