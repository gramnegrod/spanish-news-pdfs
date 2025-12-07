#!/usr/bin/env python3
"""
Standalone Spanish News PDF Generator for GitHub Actions

Generates daily Spanish learning PDFs automatically:
1. Fetches current US news via web search
2. Adapts stories for A2-B1 Spanish learners using Anthropic API
3. Fetches relevant images from Unsplash
4. Generates polished educational PDF
5. Updates index.json manifest
"""

import os
import sys
import json
import requests
from datetime import datetime
from typing import List, Dict, Optional
import anthropic

# Add the scripts directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pdf_builder import SpanishLearningPDF, fetch_unsplash_image


# =============================================================================
# CONFIGURATION - All keys from environment/secrets only
# =============================================================================
ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY')
UNSPLASH_API_KEY = os.environ.get('UNSPLASH_ACCESS_KEY')
PERPLEXITY_API_KEY = os.environ.get('PERPLEXITY_API_KEY')

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'pdfs')
INDEX_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'index.json')


# =============================================================================
# NEWS FETCHING
# =============================================================================
def fetch_news_stories() -> List[Dict]:
    """
    Fetch current US news stories using Perplexity API or fallback.
    Returns list of raw news stories with title, summary, category.
    """
    if PERPLEXITY_API_KEY:
        return fetch_news_perplexity()
    else:
        return fetch_news_fallback()


def fetch_news_perplexity() -> List[Dict]:
    """Fetch news using Perplexity API."""
    headers = {
        "Authorization": f"Bearer {PERPLEXITY_API_KEY}",
        "Content-Type": "application/json"
    }

    categories = [
        ("politics government", "Política"),
        ("economy business finance", "Economía"),
        ("technology science", "Tecnología")
    ]

    stories = []

    for search_term, category in categories:
        payload = {
            "model": "sonar",
            "messages": [
                {
                    "role": "user",
                    "content": f"What is the most important {search_term} news in the United States today? Give me ONE specific news story with: 1) A clear headline, 2) A 2-3 sentence summary of what happened. Be specific with names, numbers, and facts."
                }
            ]
        }

        try:
            response = requests.post(
                "https://api.perplexity.ai/chat/completions",
                headers=headers,
                json=payload,
                timeout=30
            )
            response.raise_for_status()
            data = response.json()
            content = data['choices'][0]['message']['content']

            stories.append({
                "category": category,
                "raw_content": content,
                "search_term": search_term
            })
        except Exception as e:
            print(f"Perplexity error for {category}: {e}")
            continue

    return stories


def fetch_news_fallback() -> List[Dict]:
    """
    Fallback news fetching using NewsAPI or hardcoded recent stories.
    """
    newsapi_key = os.environ.get('NEWSAPI_KEY')

    if newsapi_key:
        try:
            response = requests.get(
                "https://newsapi.org/v2/top-headlines",
                params={
                    "country": "us",
                    "pageSize": 10,
                    "apiKey": newsapi_key
                },
                timeout=15
            )
            response.raise_for_status()
            articles = response.json().get('articles', [])

            # Categorize and select 3 diverse stories
            stories = []
            categories_used = set()

            category_keywords = {
                "Política": ["congress", "president", "senate", "government", "election", "trump", "biden", "political"],
                "Economía": ["economy", "market", "stock", "business", "finance", "fed", "inflation", "jobs"],
                "Tecnología": ["tech", "ai", "apple", "google", "microsoft", "software", "app", "digital"]
            }

            for article in articles:
                if len(stories) >= 3:
                    break

                title = (article.get('title') or '').lower()
                desc = (article.get('description') or '').lower()
                combined = title + ' ' + desc

                for cat, keywords in category_keywords.items():
                    if cat not in categories_used:
                        if any(kw in combined for kw in keywords):
                            stories.append({
                                "category": cat,
                                "raw_content": f"{article.get('title')}\n\n{article.get('description', '')}",
                                "source": article.get('source', {}).get('name', 'News')
                            })
                            categories_used.add(cat)
                            break

            return stories

        except Exception as e:
            print(f"NewsAPI error: {e}")

    # Ultimate fallback - use date-based placeholder
    today = datetime.now().strftime("%B %d, %Y")
    return [
        {
            "category": "Política",
            "raw_content": f"Congress continues budget negotiations on {today}. Lawmakers are working to reach a bipartisan agreement on federal spending priorities.",
            "source": "Government News"
        },
        {
            "category": "Economía",
            "raw_content": f"Federal Reserve monitors economic indicators as of {today}. Markets respond to latest employment and inflation data.",
            "source": "Financial News"
        },
        {
            "category": "Tecnología",
            "raw_content": f"Tech companies announce new AI developments on {today}. Industry leaders showcase latest innovations in artificial intelligence.",
            "source": "Tech News"
        }
    ]


# =============================================================================
# STORY ADAPTATION (Anthropic API)
# =============================================================================
def adapt_stories_for_spanish_learners(raw_stories: List[Dict]) -> Dict:
    """
    Use Anthropic API to adapt news stories for A2-B1 Spanish learners.
    Returns structured content: vocabulary, adapted stories, quiz questions.
    """
    if not ANTHROPIC_API_KEY:
        raise ValueError("ANTHROPIC_API_KEY environment variable is required")

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    # Build the prompt
    stories_text = "\n\n".join([
        f"STORY {i+1} ({s['category']}):\n{s['raw_content']}"
        for i, s in enumerate(raw_stories)
    ])

    prompt = f"""You are an expert Spanish language teacher creating educational content for A2-B1 level learners.

Given these 3 US news stories, create a complete Spanish learning lesson:

{stories_text}

OUTPUT FORMAT (respond with valid JSON only):

{{
  "vocabulary": [
    {{
      "word": "Spanish word",
      "syllables": "stress-marked syllables like sor-TE-o",
      "pos": "sustantivo/verbo/adjetivo/etc",
      "context": "Example sentence from the stories using this word",
      "definition_es": "Simple Spanish definition",
      "definition_en": "English translation"
    }}
  ],
  "stories": [
    {{
      "category": "Política/Economía/Tecnología",
      "headline_es": "Spanish headline (compelling, A2-B1 level)",
      "headline_en": "English translation of headline",
      "body_es": "120-180 word Spanish adaptation of the story. Use simple sentences (10-20 words). Include key facts. A2-B1 vocabulary.",
      "body_en": "English translation of the adapted story",
      "image_query": "2-3 word English search query for Unsplash (e.g., 'congress building', 'stock market')",
      "source": "Original news source if known"
    }}
  ],
  "quiz": [
    {{
      "number": 1,
      "type": "vocab",
      "question_es": "Question in Spanish about vocabulary",
      "options": ["Option A", "Option B", "Option C", "Option D"],
      "answer": "A"
    }}
  ]
}}

REQUIREMENTS:
1. Include 6-8 vocabulary words that appear in the stories
2. Adapt all 3 stories to 120-180 words each at A2-B1 level
3. Create 10 quiz questions: 4 vocabulary (questions 1-4) + 6 comprehension (questions 5-10)
4. Comprehension questions should reference specific stories
5. All Spanish text should be appropriate for A2-B1 learners

Respond with ONLY the JSON, no other text."""

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4000,
        messages=[{"role": "user", "content": prompt}]
    )

    # Parse the response
    response_text = response.content[0].text

    # Clean up JSON if needed
    if response_text.startswith("```"):
        response_text = response_text.split("```")[1]
        if response_text.startswith("json"):
            response_text = response_text[4:]
    response_text = response_text.strip()

    return json.loads(response_text)


# =============================================================================
# PDF GENERATION
# =============================================================================
def generate_daily_pdf() -> str:
    """
    Main function: Generate the daily Spanish learning PDF.
    Returns the path to the generated PDF.
    """
    print("=" * 60)
    print("SPANISH NEWS PDF GENERATOR")
    print("=" * 60)

    # 1. Fetch news
    print("\n[1/5] Fetching current US news...")
    raw_stories = fetch_news_stories()
    print(f"  Found {len(raw_stories)} stories")
    for s in raw_stories:
        print(f"    - {s['category']}: {s['raw_content'][:50]}...")

    # 2. Adapt for Spanish learners
    print("\n[2/5] Adapting stories for Spanish learners (Anthropic API)...")
    lesson_content = adapt_stories_for_spanish_learners(raw_stories)
    print(f"  Vocabulary: {len(lesson_content.get('vocabulary', []))} words")
    print(f"  Stories: {len(lesson_content.get('stories', []))}")
    print(f"  Quiz questions: {len(lesson_content.get('quiz', []))}")

    # 3. Fetch images for each story
    print("\n[3/5] Fetching Unsplash images...")
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    for i, story in enumerate(lesson_content.get('stories', [])):
        query = story.get('image_query', story.get('category', 'news'))
        output_path = os.path.join(OUTPUT_DIR, f"story_{i+1}_image.jpg")

        print(f"  Story {i+1}: Searching '{query}'...")
        result = fetch_unsplash_image(
            query=query,
            api_key=UNSPLASH_API_KEY,
            output_path=output_path
        )

        if result:
            story['image_path'] = result['image_path']
            story['image_attribution'] = result['attribution']
            print(f"    ✓ Downloaded: {result['attribution']}")
        else:
            print(f"    ✗ No image found")

    # 4. Build PDF
    print("\n[4/5] Building PDF...")

    # Format date in Spanish
    today = datetime.now()
    months_es = {
        1: "enero", 2: "febrero", 3: "marzo", 4: "abril",
        5: "mayo", 6: "junio", 7: "julio", 8: "agosto",
        9: "septiembre", 10: "octubre", 11: "noviembre", 12: "diciembre"
    }
    date_es = f"{today.day} de {months_es[today.month]} de {today.year}"

    pdf = SpanishLearningPDF(
        title="Español con Noticias",
        subtitle="Noticias de Estados Unidos",
        date=date_es,
        level="A2-B1"
    )

    # Add vocabulary
    pdf.add_vocabulary(lesson_content.get('vocabulary', []))

    # Add stories
    for story in lesson_content.get('stories', []):
        pdf.add_story(story)

    # Add quiz questions
    for q in lesson_content.get('quiz', []):
        pdf.add_quiz_question(q)

    # Save PDF
    date_str = today.strftime("%Y-%m-%d")
    output_path = os.path.join(OUTPUT_DIR, f"spanish_lesson_{date_str}.pdf")
    pdf.save(output_path)

    # 5. Update index
    print("\n[5/5] Updating index.json...")
    update_index(date_str, output_path, lesson_content)

    print("\n" + "=" * 60)
    print(f"SUCCESS! PDF generated: {output_path}")
    print("=" * 60)

    return output_path


def update_index(date_str: str, pdf_path: str, lesson_content: Dict):
    """Update the index.json manifest file."""
    # Load existing index
    if os.path.exists(INDEX_FILE):
        with open(INDEX_FILE, 'r') as f:
            index = json.load(f)
    else:
        index = {"pdfs": [], "generated": datetime.now().isoformat()}

    # Add new entry
    entry = {
        "date": date_str,
        "filename": os.path.basename(pdf_path),
        "path": f"pdfs/{os.path.basename(pdf_path)}",
        "stories": [
            {
                "category": s.get('category'),
                "headline_es": s.get('headline_es'),
                "headline_en": s.get('headline_en')
            }
            for s in lesson_content.get('stories', [])
        ],
        "vocabulary_count": len(lesson_content.get('vocabulary', [])),
        "quiz_count": len(lesson_content.get('quiz', [])),
        "generated_at": datetime.now().isoformat()
    }

    # Remove existing entry for same date if exists
    index['pdfs'] = [p for p in index.get('pdfs', []) if p.get('date') != date_str]

    # Add new entry at the beginning
    index['pdfs'].insert(0, entry)
    index['last_updated'] = datetime.now().isoformat()

    # Save index
    with open(INDEX_FILE, 'w') as f:
        json.dump(index, f, indent=2, ensure_ascii=False)

    print(f"  Index updated: {len(index['pdfs'])} total PDFs")


# =============================================================================
# MAIN
# =============================================================================
if __name__ == "__main__":
    try:
        pdf_path = generate_daily_pdf()
        print(f"\nTo view: open {pdf_path}")
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
