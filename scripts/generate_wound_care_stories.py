#!/usr/bin/env python3
"""
Wound Care Stories Generator for Noticias de Heridas

ACCUMULATIVE MODE: Only adds stories when real news exists.
- Loads existing stories from JSON
- Only generates new stories for categories with RSS candidates
- Skips categories with no news (no fabricated stories)
- Appends new stories to existing list (deduped by source URL)
- List grows over time, only shrinking via manual cleanup

Uses Google News RSS with medical queries for story candidates, Claude for adaptation.
7-day search window due to lower volume of wound care news.
"""

import os
import sys
import json
import requests
import xml.etree.ElementTree as ET
import html
import re
from datetime import datetime
from typing import List, Dict, Set
from pathlib import Path
import anthropic
from openai import OpenAI

# Configuration
ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY')
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')
OUTPUT_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'wound-care-stories-index.json')
AUDIO_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'audio', 'wound-care-stories')
GITHUB_RAW_BASE = "https://raw.githubusercontent.com/gramnegrod/spanish-news-pdfs/main"

# Wound care category configuration
CATEGORIES = [
    {"name": "Chronic Wounds", "emoji": "🩹", "gradient": "teal",
     "query": "chronic+wound+healing+treatment+ulcer"},
    {"name": "Pressure Ulcers", "emoji": "🛏️", "gradient": "rose",
     "query": "pressure+ulcer+bedsore+decubitus+prevention"},
    {"name": "Diabetic Foot", "emoji": "👣", "gradient": "amber",
     "query": "diabetic+foot+ulcer+amputation+prevention"},
    {"name": "Burn Care", "emoji": "🔥", "gradient": "orange",
     "query": "burn+wound+treatment+healing+skin+graft"},
    {"name": "Surgical Wounds", "emoji": "🏥", "gradient": "blue",
     "query": "surgical+wound+healing+post+operative+infection"},
    {"name": "Wound Research", "emoji": "🔬", "gradient": "purple",
     "query": "wound+healing+research+innovation+therapy"},
]

# Difficulty distribution - A2 for basic, B1 for more complex
DIFFICULTY_MAP = {
    "Chronic Wounds": "A2",
    "Pressure Ulcers": "A2",
    "Diabetic Foot": "B1",
    "Burn Care": "B1",
    "Surgical Wounds": "B1",
    "Wound Research": "B1",
}

# Category to filename slug mapping
CATEGORY_SLUGS = {
    "Chronic Wounds": "chronic-wounds",
    "Pressure Ulcers": "pressure-ulcers",
    "Diabetic Foot": "diabetic-foot",
    "Burn Care": "burn-care",
    "Surgical Wounds": "surgical-wounds",
    "Wound Research": "wound-research"
}


def load_existing_stories() -> tuple[List[Dict], Set[str]]:
    """Load existing stories from JSON file and extract source URLs for deduplication."""
    existing_stories = []
    existing_urls = set()

    if os.path.exists(OUTPUT_FILE):
        try:
            with open(OUTPUT_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                existing_stories = data.get("stories", [])
                # Extract source URLs for deduplication
                for story in existing_stories:
                    url = story.get("source_url", "")
                    if url:
                        existing_urls.add(url)
                print(f"  Loaded {len(existing_stories)} existing stories ({len(existing_urls)} unique URLs)")
        except Exception as e:
            print(f"  ⚠ Could not load existing stories: {e}")
    else:
        print("  No existing stories file found - starting fresh")

    return existing_stories, existing_urls


def fetch_rss_candidates(existing_urls: Set[str]) -> Dict[str, List[Dict]]:
    """Fetch news candidates from Google News RSS for each wound care category.
    Uses 7-day window due to lower volume of medical news.
    Filters out URLs that already exist in our stories."""
    candidates = {}

    for cat in CATEGORIES:
        category = cat["name"]
        query = cat["query"]
        # Use 7-day window for medical news (lower volume than general news)
        feed_url = f"https://news.google.com/rss/search?q={query}+when:7d&hl=en-US&gl=US&ceid=US:en"

        candidates[category] = []

        try:
            response = requests.get(feed_url, timeout=15, headers={
                'User-Agent': 'Mozilla/5.0 (compatible; WoundCareNewsBot/1.0)'
            })
            response.raise_for_status()

            root = ET.fromstring(response.content)
            items = root.findall('.//item')

            new_count = 0
            skipped_count = 0

            for item in items[:10]:  # Check up to 10 per category
                title = item.find('title')
                description = item.find('description')
                source = item.find('source')
                link = item.find('link')

                title_text = html.unescape(title.text) if title is not None and title.text else ""
                link_text = link.text if link is not None and link.text else ""

                # Skip if we already have this URL
                if link_text in existing_urls:
                    skipped_count += 1
                    continue

                # Skip if no URL (can't verify source)
                if not link_text:
                    continue

                desc_text = ""
                if description is not None and description.text:
                    desc_text = html.unescape(description.text)
                    desc_text = re.sub(r'<[^>]+>', '', desc_text)

                source_text = source.text if source is not None and source.text else "Medical News"

                if title_text:
                    candidates[category].append({
                        "title": title_text,
                        "description": desc_text,
                        "source": source_text,
                        "url": link_text
                    })
                    new_count += 1

                    # Only keep up to 3 NEW candidates per category
                    if new_count >= 3:
                        break

            if new_count > 0:
                print(f"  ✓ {category}: {new_count} NEW candidates (skipped {skipped_count} existing)")
            else:
                print(f"  - {category}: No new news (skipped {skipped_count} existing)")

        except Exception as e:
            print(f"  ✗ {category}: RSS error - {e}")

    return candidates


def repair_truncated_json(text: str) -> str:
    """Attempt to repair truncated JSON by closing open structures.

    This handles cases where Claude's response gets cut off mid-JSON,
    leaving unterminated strings, arrays, or objects.
    """
    # If already valid, return as-is
    try:
        json.loads(text)
        return text
    except json.JSONDecodeError:
        pass

    # Count unclosed structures
    in_string = False
    escape_next = False
    open_braces = 0
    open_brackets = 0

    for i, char in enumerate(text):
        if escape_next:
            escape_next = False
            continue
        if char == '\\':
            escape_next = True
            continue
        if char == '"' and not escape_next:
            in_string = not in_string
            continue
        if in_string:
            continue
        if char == '{':
            open_braces += 1
        elif char == '}':
            open_braces -= 1
        elif char == '[':
            open_brackets += 1
        elif char == ']':
            open_brackets -= 1

    # If we ended inside a string, close it
    if in_string:
        text += '"'

    # Close any open brackets/braces
    text += ']' * open_brackets
    text += '}' * open_braces

    return text


def generate_stories_with_claude(candidates: Dict[str, List[Dict]]) -> List[Dict]:
    """Use Claude to select and adapt wound care stories for categories with news."""

    if not ANTHROPIC_API_KEY:
        raise ValueError("ANTHROPIC_API_KEY environment variable is required")

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    # Build prompt with only categories that have NEW candidates
    prompt = """You are creating Spanish wound care news stories for healthcare professionals learning medical Spanish.

TARGET AUDIENCE: Nurses, wound care specialists, and healthcare workers who need to communicate about wound care in Spanish.

For each category below, select the best news story and adapt it to Spanish at the specified CEFR level.

NEWS CANDIDATES BY CATEGORY:
"""

    # Only include categories that have RSS candidates
    categories_with_news = []
    for cat in CATEGORIES:
        category = cat["name"]
        if category in candidates and candidates[category]:
            categories_with_news.append(cat)
            difficulty = DIFFICULTY_MAP[category]
            prompt += f"\n## {category} (Target: {difficulty} level)\n"
            for i, item in enumerate(candidates[category], 1):
                prompt += f"{i}. [{item['source']}] {item['title']}\n"
                prompt += f"   URL: {item['url']}\n"
                if item['description']:
                    prompt += f"   {item['description'][:150]}...\n"

    # If no categories have NEW news, return empty
    if not categories_with_news:
        print("  No NEW news candidates - nothing to generate")
        return []

    prompt += """

OUTPUT FORMAT - Return valid JSON with ONE story per category listed above (only categories with news candidates):

{
  "stories": [
    {
      "id": "chronic-wounds-YYYYMMDD",
      "category": "Chronic Wounds",
      "difficulty": "A2",
      "emoji": "🩹",
      "gradient": "teal",
      "headline_es": "Spanish headline (medical but accessible)",
      "headline_en": "English translation",
      "summary_es": "1-2 sentence Spanish summary",
      "body_es": "Full Spanish story (100-150 words for A2, 150-200 for B1)",
      "body_en": "English translation of body",
      "source_url": "REQUIRED - Copy the EXACT URL from the news candidate above",
      "audio_url": "",
      "key_vocabulary": [
        {"word": "herida", "definition_es": "lesión en la piel o tejido", "definition_en": "wound - injury to skin or tissue"},
        {"word": "vendaje", "definition_es": "material para cubrir heridas", "definition_en": "dressing - material to cover wounds"},
        {"word": "curación", "definition_es": "proceso de sanar", "definition_en": "healing - process of getting better"},
        {"word": "tratamiento", "definition_es": "método para curar", "definition_en": "treatment - method to cure"}
      ]
    }
  ]
}

LEVEL GUIDELINES:

A2 (Chronic Wounds, Pressure Ulcers):
- Present tense mainly, simple past occasionally
- Short sentences (8-12 words)
- Basic medical vocabulary with clear definitions
- Practical, concrete information
- Avoid subjunctive entirely

B1 (Diabetic Foot, Burn Care, Surgical Wounds, Wound Research):
- Mix of tenses including imperfect and future
- Medium sentences (12-18 words)
- More specialized medical terminology
- Treatment protocols and procedures
- Simple conditional for recommendations

MEDICAL VOCABULARY FOCUS:
Include vocabulary from these domains:
- Wound types: herida, úlcera, lesión, quemadura, escara
- Anatomy: piel, tejido, epidermis, dermis, cicatriz
- Assessment: evaluación, medición, exudado, granulación, epitelización
- Treatment: apósito, vendaje, desbridamiento, sutura, curación
- Conditions: infección, necrosis, edema, eritema, isquemia

REQUIREMENTS:
1. ONLY create stories for categories listed above (those with news candidates)
2. Each story must have exactly 4 vocabulary words
3. Vocabulary should be medical terms that appear in the story
4. Use today's date in the id field: """ + datetime.now().strftime("%Y%m%d") + """
5. Stories must be based on actual medical news - NO fabricated stories
6. Include specific statistics, hospital names, or study details from the source
7. Content should be professionally appropriate for healthcare settings
8. CRITICAL: Every story MUST have a real source_url copied EXACTLY from the candidate list

Return ONLY the JSON, no other text."""

    print(f"\n  Calling Claude API for {len(categories_with_news)} categories with new news...")

    # Retry logic for malformed JSON responses
    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=12000,  # Increased for 6 stories with Spanish text
                messages=[{"role": "user", "content": prompt}]
            )

            response_text = response.content[0].text

            # Clean up JSON
            if "```" in response_text:
                response_text = response_text.split("```")[1]
                if response_text.startswith("json"):
                    response_text = response_text[4:]
            response_text = response_text.strip()

            # Attempt to repair truncated JSON
            response_text = repair_truncated_json(response_text)

            result = json.loads(response_text)
            stories = result.get("stories", [])

            # Validate that all stories have source URLs
            valid_stories = []
            for story in stories:
                if story.get("source_url"):
                    valid_stories.append(story)
                else:
                    print(f"  ⚠ Skipping story without source_url: {story.get('category')}")

            print(f"  ✓ Generated {len(valid_stories)} valid stories")
            return valid_stories

        except json.JSONDecodeError as e:
            if attempt < max_retries - 1:
                print(f"  ⚠ JSON parse error (attempt {attempt + 1}/{max_retries}): {e}")
                print("  Retrying...")
                import time
                time.sleep(2)  # Brief pause before retry
            else:
                print(f"  ❌ JSON parse failed after {max_retries} attempts: {e}")
                raise


def generate_tts_audio(stories: List[Dict], date_str: str) -> List[Dict]:
    """Generate TTS audio for each story using OpenAI TTS API."""

    if not OPENAI_API_KEY:
        print("  ⚠ OPENAI_API_KEY not set - skipping TTS generation")
        return stories

    client = OpenAI(api_key=OPENAI_API_KEY)

    # Create date-specific audio directory
    audio_date_dir = os.path.join(AUDIO_DIR, date_str)
    Path(audio_date_dir).mkdir(parents=True, exist_ok=True)

    for story in stories:
        category = story.get("category", "unknown")
        slug = CATEGORY_SLUGS.get(category, "story")
        filename = f"{slug}.mp3"
        filepath = os.path.join(audio_date_dir, filename)

        try:
            # Generate TTS for the Spanish body text with clear medical pronunciation
            response = client.audio.speech.create(
                model="gpt-4o-mini-tts-2025-12-15",
                voice="coral",
                input=story["body_es"],
                instructions="Speak with a clear, professional Mexican Spanish accent. Pronounce medical terminology clearly and at a moderate pace suitable for Spanish language learners in healthcare settings. Warm but professional tone."
            )

            # Save the audio file
            response.stream_to_file(filepath)

            # Update story with audio URL
            story["audio_url"] = f"{GITHUB_RAW_BASE}/audio/wound-care-stories/{date_str}/{filename}"
            print(f"    ✓ {category}: {filename}")

        except Exception as e:
            print(f"    ✗ {category}: TTS error - {e}")
            story["audio_url"] = ""

    return stories


def generate_wound_care_stories():
    """Main function to generate daily wound care stories (accumulative mode)."""
    print("=" * 60)
    print("WOUND CARE STORIES GENERATOR (ACCUMULATIVE MODE)")
    print("=" * 60)

    # 1. Load existing stories for deduplication
    print("\n[1/5] Loading existing stories...")
    existing_stories, existing_urls = load_existing_stories()

    # 2. Fetch RSS candidates (only new URLs)
    print("\n[2/5] Fetching wound care news candidates (7-day window)...")
    candidates = fetch_rss_candidates(existing_urls)

    # Count categories with new news
    categories_with_news = sum(1 for cat in candidates.values() if cat)

    if categories_with_news == 0:
        print("\n  ℹ No new news stories found today")
        print("  Existing stories remain unchanged")
        print("\n" + "=" * 60)
        print("NO UPDATES TODAY - List unchanged")
        print("=" * 60)
        return

    # 3. Generate stories with Claude (only for new news)
    print("\n[3/5] Generating stories with Claude...")
    new_stories = generate_stories_with_claude(candidates)

    if not new_stories:
        print("\n  ℹ No new stories generated")
        print("\n" + "=" * 60)
        print("NO UPDATES TODAY - List unchanged")
        print("=" * 60)
        return

    print(f"  Generated {len(new_stories)} NEW stories:")
    for story in new_stories:
        print(f"    + {story['category']} ({story['difficulty']}): {story['headline_es'][:40]}...")

    # 4. Generate TTS audio for new stories only
    today = datetime.now()
    date_str = today.strftime("%Y-%m-%d")
    print("\n[4/5] Generating TTS audio for new stories...")
    new_stories = generate_tts_audio(new_stories, date_str)

    # 5. Merge and save to JSON
    print("\n[5/5] Merging and saving to wound-care-stories-index.json...")

    # Add timestamp to new stories
    for story in new_stories:
        story["added_at"] = today.isoformat() + "Z"

    # Combine: new stories first (most recent), then existing
    all_stories = new_stories + existing_stories

    output = {
        "date": today.strftime("%Y-%m-%d"),
        "generated_at": today.isoformat() + "Z",
        "description": "Accumulative wound care news for Spanish medical professionals",
        "content_type": "wound-care",
        "total_stories": len(all_stories),
        "new_today": len(new_stories),
        "stories": all_stories,
        "last_updated": today.isoformat() + "Z",
        "generated_by": "GitHub Actions + Anthropic API (accumulative mode)"
    }

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"  Saved {len(all_stories)} total stories ({len(new_stories)} new)")
    print(f"  File: {OUTPUT_FILE}")

    print("\n" + "=" * 60)
    print(f"SUCCESS! Added {len(new_stories)} new stories")
    print(f"Total stories in feed: {len(all_stories)}")
    print("=" * 60)


if __name__ == "__main__":
    try:
        generate_wound_care_stories()
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
