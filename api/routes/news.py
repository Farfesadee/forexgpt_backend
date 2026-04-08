import logging
import requests
import xml.etree.ElementTree as ET
from fastapi import APIRouter
import random

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/news", tags=["News"])

@router.get("")
def get_news():
    """
    Fetches real-time Forex news from DailyFX RSS and mixes in 
    ForexGPT Intelligence notifications.
    """
    try:
        # Fetch real news
        response = requests.get("https://www.dailyfx.com/feeds/forex-market-news", timeout=8)
        response.raise_for_status()
        
        # Parse XML
        root = ET.fromstring(response.content)
        news_items = []
        
        # Extract items
        for item in root.findall(".//item")[:10]:
            title = item.find("title").text if item.find("title") is not None else "Forex Market Update"
            link = item.find("link").text if item.find("link") is not None else "#"
            news_items.append({
                "title": title.strip(),
                "link": link,
                "source": "DailyFX",
                "type": "market"
            })
        
        # Inject ForexGPT branded alerts
        forexgpt_alerts = [
            {
                "title": "ForexGPT Neural Engine: High confluence detected on GBP/JPY 4H timeframe.", 
                "source": "AI Intelligence", 
                "link": "/dashboard/signals",
                "type": "ai"
            },
            {
                "title": "Institutional Flow: Significant buy orders clustering around 1.0850 (EUR/USD).", 
                "source": "Smart Money", 
                "link": "/dashboard/mentor",
                "type": "ai"
            },
            {
                "title": "Strategy Update: Neural Blueprints v2.2 integration complete in Logic Architect.", 
                "source": "System", 
                "link": "/dashboard/codegen",
                "type": "ai"
            }
        ]
        
        # Combine and shuffle slightly (keeping AI alerts prominent)
        final_news = forexgpt_alerts + news_items
        # random.shuffle(final_news) # Keep AI alerts first for now or shuffle if desired
        
        return final_news
        
    except Exception as e:
        logger.error(f"Error fetching news: {e}")
        # Dynamic fallback if news fails
        return [
            {"title": "ForexGPT Intelligence: Real-time market analysis engine active.", "source": "System", "link": "/dashboard/signals", "type": "ai"},
            {"title": "High Volatility Warning: Major USD economic releases pending.", "source": "Market Watch", "link": "#", "type": "market"},
            {"title": "AI Mentor: New educational models uploaded for Advanced Backtesting.", "source": "Education", "link": "/dashboard/mentor", "type": "ai"}
        ]
