
import asyncio
import os
import sys

# Add the current directory to sys.path to import from core
sys.path.append(os.getcwd())

from core.database import get_db

async def list_all_columns():
    try:
        # Try to get one row
        res = get_db().table("signals").select("*").limit(1).execute()
        if res.data:
            cols = list(res.data[0].keys())
            with open("all_columns.txt", "w") as f:
                f.write("\n".join(cols))
            print("Successfully listed columns from existing data.")
        else:
            # If no data, we might need another way. Supabase doesn't easily expose schema via client.
            # But we can try to guess or use the old check_db_schema logic with more names.
            common_names = ["id", "user_id", "currency_pair", "direction", "confidence", "reasoning", "magnitude", "time_horizon", "company_name", "transcript_excerpt", "created_at"]
            results = []
            for col in common_names:
                try:
                    get_db().table("signals").select(col).limit(1).execute()
                    results.append(col)
                except:
                    pass
            with open("all_columns.txt", "w") as f:
                f.write("\n".join(results))
            print("Listed columns via brute force (no data found).")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(list_all_columns())
