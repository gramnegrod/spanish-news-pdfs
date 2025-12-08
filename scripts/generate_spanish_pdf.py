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
# Note: News fetching uses Google News RSS - no API key needed

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'pdfs')
INDEX_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'index.json')


# =============================================================================
# NEWS FETCHING (RSS + Claude Selection)
# =============================================================================
def fetch_rss_candidates() -> Dict[str, List[Dict]]:
    """
    Fetch multiple news candidates from Google News RSS feeds.
    Returns dict of category -> list of story candidates.
    """
    import xml.etree.ElementTree as ET
    import html
    import re

    # Google News RSS feeds for different topics
    feeds = [
        ("https://news.google.com/rss/search?q=US+politics+congress+government+when:1d&hl=en-US&gl=US&ceid=US:en", "Política"),
        ("https://news.google.com/rss/search?q=US+economy+business+markets+when:1d&hl=en-US&gl=US&ceid=US:en", "Economía"),
        ("https://news.google.com/rss/search?q=technology+AI+tech+companies+when:1d&hl=en-US&gl=US&ceid=US:en", "Tecnología"),
    ]

    candidates = {}

    for feed_url, category in feeds:
        candidates[category] = []
        try:
            response = requests.get(feed_url, timeout=15, headers={
                'User-Agent': 'Mozilla/5.0 (compatible; SpanishNewsPDF/1.0)'
            })
            response.raise_for_status()

            root = ET.fromstring(response.content)
            items = root.findall('.//item')

            # Get up to 8 items per category for Claude to choose from
            for item in items[:8]:
                title = item.find('title')
                description = item.find('description')
                source = item.find('source')
                pub_date = item.find('pubDate')

                title_text = html.unescape(title.text) if title is not None and title.text else ""

                desc_text = ""
                if description is not None and description.text:
                    desc_text = html.unescape(description.text)
                    desc_text = re.sub(r'<[^>]+>', '', desc_text)

                source_text = source.text if source is not None and source.text else "News"
                date_text = pub_date.text if pub_date is not None else ""

                if title_text:
                    candidates[category].append({
                        "title": title_text,
                        "description": desc_text,
                        "source": source_text,
                        "date": date_text
                    })

            print(f"  ✓ {category}: Found {len(candidates[category])} candidates")

        except Exception as e:
            print(f"  ✗ {category} RSS error: {e}")

    return candidates


def fetch_news_stories() -> List[Dict]:
    """
    Fetch news using RSS feeds, then let Claude pick the best story per category.
    Combines free RSS with intelligent Claude selection.
    """
    # Step 1: Get RSS candidates
    print("  Fetching RSS candidates...")
    candidates = fetch_rss_candidates()

    # Step 2: Let Claude pick the best story from each category
    print("  Asking Claude to select best stories...")

    if not ANTHROPIC_API_KEY:
        print("  ⚠ No Anthropic key - using first RSS item per category")
        return _fallback_first_items(candidates)

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    # Build prompt for Claude to select stories
    selection_prompt = """You are a news editor selecting stories for a Spanish language learning PDF.

For each category below, I'll give you several news candidates. Pick the ONE best story that:
1. Is most newsworthy and significant
2. Has clear, concrete facts (names, numbers, events)
3. Would be interesting for Spanish learners in the US
4. Is NOT a duplicate or slight variation of another story

CANDIDATES BY CATEGORY:

"""
    for category, items in candidates.items():
        selection_prompt += f"\n## {category}\n"
        for i, item in enumerate(items, 1):
            selection_prompt += f"{i}. [{item['source']}] {item['title']}\n"
            if item['description']:
                selection_prompt += f"   Summary: {item['description'][:200]}...\n"

    selection_prompt += """

RESPOND WITH JSON ONLY - pick one story number per category:
{
    "Política": {"pick": 1, "reason": "brief reason"},
    "Economía": {"pick": 2, "reason": "brief reason"},
    "Tecnología": {"pick": 1, "reason": "brief reason"}
}
"""

    try:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=500,
            messages=[{"role": "user", "content": selection_prompt}]
        )

        response_text = response.content[0].text

        # Clean up JSON response
        if "```" in response_text:
            response_text = response_text.split("```")[1]
            if response_text.startswith("json"):
                response_text = response_text[4:]
        response_text = response_text.strip()

        selections = json.loads(response_text)

        # Build final stories list based on Claude's picks
        stories = []
        for category in ["Política", "Economía", "Tecnología"]:
            if category in selections and category in candidates:
                pick_idx = selections[category].get("pick", 1) - 1  # Convert to 0-indexed
                if 0 <= pick_idx < len(candidates[category]):
                    item = candidates[category][pick_idx]
                    stories.append({
                        "category": category,
                        "raw_content": f"{item['title']}\n\n{item['description']}",
                        "source": item['source']
                    })
                    print(f"  ✓ {category}: Claude picked #{pick_idx+1} - {item['title'][:50]}...")
                    print(f"    Reason: {selections[category].get('reason', 'N/A')}")

        if stories:
            return stories

    except Exception as e:
        print(f"  ⚠ Claude selection error: {e}")

    # Fallback to first items
    return _fallback_first_items(candidates)


def _fallback_first_items(candidates: Dict[str, List[Dict]]) -> List[Dict]:
    """Fallback: just use first RSS item per category."""
    stories = []
    for category in ["Política", "Economía", "Tecnología"]:
        if category in candidates and candidates[category]:
            item = candidates[category][0]
            stories.append({
                "category": category,
                "raw_content": f"{item['title']}\n\n{item['description']}",
                "source": item['source']
            })

    if not stories:
        today = datetime.now().strftime("%B %d, %Y")
        stories = [
            {"category": "Política", "raw_content": f"US political developments on {today}.", "source": "News"},
            {"category": "Economía", "raw_content": f"Economic news on {today}.", "source": "News"},
            {"category": "Tecnología", "raw_content": f"Technology updates on {today}.", "source": "News"},
        ]

    return stories


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

    # Add new entry with full lesson content
    entry = {
        "date": date_str,
        "filename": os.path.basename(pdf_path),
        "path": f"pdfs/{os.path.basename(pdf_path)}",
        "stories": [
            {
                "category": s.get('category'),
                "headline_es": s.get('headline_es'),
                "headline_en": s.get('headline_en'),
                "body_es": s.get('body_es'),
                "body_en": s.get('body_en'),
                "source": s.get('source')
            }
            for s in lesson_content.get('stories', [])
        ],
        "vocabulary": lesson_content.get('vocabulary', []),
        "quiz": lesson_content.get('quiz', []),
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
