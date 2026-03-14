
import asyncio
import os
import sys

# Add the current directory to sys.path to import from core
sys.path.append(os.getcwd())

from core.database import get_db

async def check_schema():
    try:
        res = get_db().table("signals").select("*").limit(1).execute()
        if res.data:
            print("Full list of columns in signals table:")
            for col in res.data[0].keys():
                print(f" - {col}")
        else:
            print("Signals table is empty.")
        
        # Check specific columns
        for col_to_check in ["currency_pair", "affected_pairs", "primary_direction", "direction"]:
            try:
                get_db().table("signals").select(col_to_check).limit(1).execute()
                print(f"Column '{col_to_check}' EXISTS.")
            except Exception as e:
                print(f"Column '{col_to_check}' does NOT exist: {e}")
                
    except Exception as e:
        print(f"Error checking schema: {e}")

if __name__ == "__main__":
    asyncio.run(check_schema())
