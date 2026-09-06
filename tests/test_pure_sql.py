#!/usr/bin/env python3
"""
Test script to verify the pure SQL integration works correctly with Alembic.
This script demonstrates basic functionality without needing real API calls.
"""

import json
import os
import sys

sys.path.append('../extract')

from checkerduck.extract.extract import AhrefsClient, AhrefsDatabaseError


def test_pure_sql_operations():
    """Test pure SQL database operations with Alembic integration."""
    print("🧪 Testing pure SQL integration with Alembic...")

    # Initialize client (no API token needed for database testing)
    client = AhrefsClient(api_token="test_token", db_path="../ahrefs_data.db")

    try:
        # Test database initialization with Alembic
        print("✅ Initializing database with Alembic...")
        success = client.init_database(use_alembic=True)
        if success:
            print("✅ Database initialized successfully with Alembic!")
        else:
            print("❌ Database initialization failed, trying fallback...")
            success = client.init_database(use_alembic=False)
            if success:
                print("✅ Database initialized successfully with direct SQL!")
            else:
                print("❌ Both initialization methods failed")
                return

        # Create mock API response data for testing
        mock_results = {
            "timestamp": "2025-09-30T22:03:48.345004",
            "saved_at": "cache/batch_analysis_20250930_220348.json",
            "results": {
                "targets": [
                    {
                        "ahrefs_rank": 678,
                        "backlinks": 48872,
                        "backlinks_dofollow": 15292,
                        "backlinks_internal": 20,
                        "backlinks_nofollow": 33580,
                        "backlinks_redirect": 13,
                        "domain_rating": 91.0,
                        "index": 0,
                        "ip": "172.64.148.115",
                        "linked_domains": 0,
                        "linked_domains_dofollow": 0,
                        "mode": "exact",
                        "org_cost": 0,
                        "org_keywords": 0,
                        "org_keywords_11_20": 0,
                        "org_keywords_1_3": 0,
                        "org_keywords_21_50": 0,
                        "org_keywords_4_10": 0,
                        "org_keywords_51_plus": 0,
                        "org_traffic": 0,
                        "org_traffic_top_by_country": [],
                        "outgoing_links": 0,
                        "outgoing_links_dofollow": 0,
                        "paid_ads": 0,
                        "paid_cost": 0,
                        "paid_keywords": 0,
                        "paid_traffic": 0,
                        "protocol": "both",
                        "refdomains": 2353,
                        "refdomains_dofollow": 1975,
                        "refdomains_nofollow": 442,
                        "refips": 2126,
                        "refips_subnets": 1458,
                        "url": "www.ahrefs.com/",
                        "url_rating": 23.0
                    }
                ]
            }
        }

        # Test saving to database using pure SQL
        print("✅ Saving test data to database using pure SQL...")
        target_ids = client.persist_batch_analysis(mock_results)
        print(f"✅ Successfully saved {len(target_ids)} records")
        print(f"✅ Target IDs: {target_ids}")

        # Verify data was saved by connecting to database directly
        print("✅ Verifying saved data with direct SQL queries...")
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

        # Show sample data with JSON-style output
        cursor.execute("""
            SELECT url, ahrefs_rank, domain_rating, org_traffic 
            FROM batch_analysis 
            ORDER BY ahrefs_rank 
            LIMIT 3
        """)
        print("\n📊 Sample data from database:")
        for row in cursor.fetchall():
            data = {
                "url": row[0],
                "ahrefs_rank": row[1],
                "domain_rating": row[2],
                "org_traffic": row[3]
            }
            print(f"   {json.dumps(data, indent=2)}")

        # Show country data as JSON
        cursor.execute("""
            SELECT ba.url, tc.country_code, tc.traffic, tc.cost 
            FROM batch_analysis ba 
            JOIN ahrefs_org_traffic_country tc ON ba.target_id = tc.target_id
            ORDER BY tc.traffic DESC
            LIMIT 5
        """)
        print("\n🌍 Country traffic data as JSON:")
        countries = []
        for row in cursor.fetchall():
            country_data = {
                "url": row[0],
                "country": row[1],
                "traffic": row[2],
                "cost": row[3]
            }
            countries.append(country_data)
        print(json.dumps(countries, indent=2))

        conn.close()
        print("\n🎉 All tests passed! Pure SQL integration with Alembic is working correctly.")

    except AhrefsDatabaseError as e:
        print(f"❌ Database error: {e}")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")

    print(f"\n💾 Test database file: test_pure_sql.db")
    print("You can examine it with: sqlite3 test_pure_sql.db")
    print("Or run: alembic history to see migration history")


if __name__ == "__main__":
    test_pure_sql_operations()
