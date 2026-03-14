
import asyncio
import os
import sys

# Add the current directory to sys.path to import from core
sys.path.append(os.getcwd())

from core.database import get_db

async def check_schema():
    cols_to_check = [
        "id", "user_id", "source_label", "base_currency", "primary_sentiment", 
        "primary_direction", "primary_strength", "affected_pairs", "confidence", 
        "hf_endpoint_id", "hf_model_version", "is_saved", "created_at"
    ]
    
    results = []
    for col in cols_to_check:
        try:
            get_db().table("signals").select(col).limit(1).execute()
            results.append(f"OK: {col}")
        except Exception as e:
            results.append(f"FAIL: {col} - {str(e)[:50]}")
    
    with open("schema_results.txt", "w") as f:
        f.write("\n".join(results))
    
    print("Results written to schema_results.txt")

if __name__ == "__main__":
    asyncio.run(check_schema())
