#!/usr/bin/env python
"""
Seed Production Database with Sample Articles
=============================================

Seeds PostgreSQL production database with sample articles.
Uses the API endpoints to ensure proper data validation.
"""

import os
import sys
import asyncio
from pathlib import Path

# Add backend directory to path
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

import httpx  # noqa: E402
from datetime import datetime, timedelta  # noqa: E402

# Production backend URL
BACKEND_URL = os.getenv("BACKEND_URL", "https://ai-tech-news-assistant-backend.onrender.com")

# Sample articles data
SAMPLE_ARTICLES = [
    {
        "title": "OpenAI Releases GPT-5 with Revolutionary Capabilities",
        "content": "OpenAI has announced the release of GPT-5, featuring unprecedented improvements in reasoning, multimodal understanding, and reduced hallucinations. The model demonstrates human-level performance across various benchmark tests.",
        "url": "https://techcrunch.com/2025/11/16/openai-gpt5-release",
        "source": "techcrunch",
        "author": "TechCrunch Staff",
        "published_at": (datetime.now() - timedelta(days=1)).isoformat()
    },
    {
        "title": "Google Announces Quantum Chip Breakthrough",
        "content": "Google's Quantum AI team has unveiled a new quantum chip achieving quantum advantage in practical problems. The advancement brings quantum computing closer to real-world applications.",
        "url": "https://theverge.com/2025/11/15/google-quantum-chip",
        "source": "theverge",
        "author": "The Verge Team",
        "published_at": (datetime.now() - timedelta(days=2)).isoformat()
    },
    {
        "title": "Critical Security Vulnerability in Popular Framework",
        "content": "Security researchers have discovered a critical zero-day vulnerability in a widely-used web framework affecting millions of applications. Patches have been released urgently.",
        "url": "https://wired.com/2025/11/14/security-vulnerability",
        "source": "wired",
        "author": "Security Desk",
        "published_at": (datetime.now() - timedelta(days=3)).isoformat()
    },
    {
        "title": "New Programming Language Gains Rapid Adoption",
        "content": "A new systems programming language combining performance of Rust with developer experience of Python has gained significant adoption among enterprise developers.",
        "url": "https://news.ycombinator.com/item?id=38234567",
        "source": "hackernews",
        "author": "HN Community",
        "published_at": (datetime.now() - timedelta(days=4)).isoformat()
    },
    {
        "title": "AI Models Show Promise in Drug Discovery",
        "content": "Researchers demonstrate that AI models can accelerate pharmaceutical drug discovery, identifying promising compounds 10x faster than traditional methods.",
        "url": "https://nature.com/articles/ai-drug-discovery-2025",
        "source": "nature",
        "author": "Nature Research",
        "published_at": (datetime.now() - timedelta(days=5)).isoformat()
    },
    {
        "title": "Cloud Provider Reports Record Q3 Growth",
        "content": "Major cloud provider reports record revenue growth driven by increased enterprise adoption of AI and machine learning services.",
        "url": "https://finance.yahoo.com/news/cloud-earnings-q3-2025",
        "source": "yahoo",
        "author": "Finance Team",
        "published_at": (datetime.now() - timedelta(days=6)).isoformat()
    },
    {
        "title": "Blockchain Powers New Supply Chain Solutions",
        "content": "Companies are leveraging blockchain for transparent supply chain tracking, reducing fraud and improving efficiency across industries.",
        "url": "https://forbes.com/2025/11/10/blockchain-supply-chain",
        "source": "forbes",
        "author": "Forbes Contributors",
        "published_at": (datetime.now() - timedelta(days=7)).isoformat()
    },
    {
        "title": "ML Reduces Energy Use in Data Centers by 40%",
        "content": "Tech giants deploy ML algorithms to optimize data center cooling, reducing energy consumption by 40% and cutting carbon emissions significantly.",
        "url": "https://arstechnica.com/2025/11/09/ml-datacenters-efficiency",
        "source": "arstechnica",
        "author": "Ars Technical Staff",
        "published_at": (datetime.now() - timedelta(days=8)).isoformat()
    }
]


async def seed_articles():
    """Seed articles using the news ingestion API endpoint."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        print(f"🌱 Seeding production database at {BACKEND_URL}")
        print(f"📝 Total articles to seed: {len(SAMPLE_ARTICLES)}\n")
        
        success_count = 0
        error_count = 0
        
        for idx, article in enumerate(SAMPLE_ARTICLES, 1):
            try:
                # Use the news ingestion endpoint
                response = await client.post(
                    f"{BACKEND_URL}/api/news/ingest",
                    json={
                        "articles": [article]
                    },
                    headers={"Content-Type": "application/json"}
                )
                
                if response.status_code in [200, 201]:
                    print(f"✅ [{idx}/{len(SAMPLE_ARTICLES)}] {article['title'][:60]}...")
                    success_count += 1
                else:
                    print(f"⚠️  [{idx}/{len(SAMPLE_ARTICLES)}] Failed: {response.status_code} - {article['title'][:60]}...")
                    print(f"    Response: {response.text[:100]}")
                    error_count += 1
                    
            except Exception as e:
                print(f"❌ [{idx}/{len(SAMPLE_ARTICLES)}] Error: {str(e)[:100]}")
                error_count += 1
        
        print(f"\n{'='*60}")
        print(f"✅ Successfully seeded: {success_count} articles")
        if error_count > 0:
            print(f"❌ Failed: {error_count} articles")
        print(f"{'='*60}\n")
        
        # Verify by fetching articles
        try:
            print("🔍 Verifying articles in database...")
            verify_response = await client.get(
                f"{BACKEND_URL}/api/news",
                params={"page": 1, "page_size": 10}
            )
            
            if verify_response.status_code == 200:
                data = verify_response.json()
                total = data.get("total", 0)
                print(f"✅ Database now contains {total} articles")
                
                if "items" in data and len(data["items"]) > 0:
                    print("\n📰 Sample articles:")
                    for article in data["items"][:3]:
                        print(f"   • {article.get('title', 'No title')[:60]}...")
            else:
                print(f"⚠️  Could not verify: Status {verify_response.status_code}")
                
        except Exception as e:
            print(f"⚠️  Verification error: {e}")


def main():
    """Main entry point."""
    print("\n" + "="*60)
    print("🚀 PRODUCTION DATABASE SEEDING")
    print("="*60 + "\n")
    
    asyncio.run(seed_articles())
    
    print("\n✅ Seeding complete!\n")
    print("🌐 View articles at:")
    print(f"   • API: {BACKEND_URL}/api/news?page=1&page_size=10")
    print(f"   • Docs: {BACKEND_URL}/docs")
    print()


if __name__ == "__main__":
    main()
