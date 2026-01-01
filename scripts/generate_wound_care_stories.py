#!/usr/bin/env python3
"""
Wound Care Stories Generator for Noticias de Heridas

Generates daily wound care news stories for healthcare professionals learning medical Spanish:
- 2 stories at A2 level (chronic wounds, pressure ulcers)
- 4 stories at B1 level (diabetic foot, burns, surgical, research)

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
from typing import List, Dict
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
    {"name": "Pressure Ulcers", "emoji": "🛏️", "gradient": "blue",
     "query": "pressure+ulcer+bedsore+decubitus+prevention"},
    {"name": "Diabetic Foot", "emoji": "🦶", "gradient": "orange",
     "query": "diabetic+foot+ulcer+amputation+prevention"},
    {"name": "Burn Care", "emoji": "🔥", "gradient": "red-orange",
     "query": "burn+wound+treatment+healing+skin+graft"},
    {"name": "Surgical Wounds", "emoji": "🏥", "gradient": "purple",
     "query": "surgical+wound+healing+post+operative+infection"},
    {"name": "Wound Research", "emoji": "🔬", "gradient": "green",
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


def fetch_rss_candidates() -> Dict[str, List[Dict]]:
    """Fetch news candidates from Google News RSS for each wound care category.
    Uses 7-day window due to lower volume of medical news."""
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

            for item in items[:5]:  # Get up to 5 per category
                title = item.find('title')
                description = item.find('description')
                source = item.find('source')

                title_text = html.unescape(title.text) if title is not None and title.text else ""

                desc_text = ""
                if description is not None and description.text:
                    desc_text = html.unescape(description.text)
                    desc_text = re.sub(r'<[^>]+>', '', desc_text)

                source_text = source.text if source is not None and source.text else "Medical News"

                if title_text:
                    candidates[category].append({
                        "title": title_text,
                        "description": desc_text,
                        "source": source_text
                    })

            print(f"  ✓ {category}: {len(candidates[category])} candidates")

        except Exception as e:
            print(f"  ✗ {category}: RSS error - {e}")

    return candidates


def generate_stories_with_claude(candidates: Dict[str, List[Dict]]) -> List[Dict]:
    """Use Claude to select and adapt wound care stories for each category/difficulty."""

    if not ANTHROPIC_API_KEY:
        raise ValueError("ANTHROPIC_API_KEY environment variable is required")

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    # Build prompt with all candidates
    prompt = """You are creating Spanish wound care news stories for healthcare professionals learning medical Spanish.

TARGET AUDIENCE: Nurses, wound care specialists, and healthcare workers who need to communicate about wound care in Spanish.

For each category below, select the best news story and adapt it to Spanish at the specified CEFR level.

NEWS CANDIDATES BY CATEGORY:
"""

    for cat in CATEGORIES:
        category = cat["name"]
        difficulty = DIFFICULTY_MAP[category]
        prompt += f"\n## {category} (Target: {difficulty} level)\n"

        if category in candidates and candidates[category]:
            for i, item in enumerate(candidates[category], 1):
                prompt += f"{i}. [{item['source']}] {item['title']}\n"
                if item['description']:
                    prompt += f"   {item['description'][:150]}...\n"
        else:
            prompt += "No candidates available - create a realistic medical news story about this wound care topic.\n"

    prompt += """

OUTPUT FORMAT - Return valid JSON with exactly 6 stories:

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
1. Each story must have exactly 4 vocabulary words
2. Vocabulary should be medical terms that appear in the story
3. Use today's date in the id field: """ + datetime.now().strftime("%Y%m%d") + """
4. Stories must be based on actual medical news when available
5. Include specific statistics, hospital names, or study details when possible
6. Content should be professionally appropriate for healthcare settings

Return ONLY the JSON, no other text."""

    print("\n  Calling Claude API for wound care story generation...")

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=6000,
        messages=[{"role": "user", "content": prompt}]
    )

    response_text = response.content[0].text

    # Clean up JSON
    if "```" in response_text:
        response_text = response_text.split("```")[1]
        if response_text.startswith("json"):
            response_text = response_text[4:]
    response_text = response_text.strip()

    result = json.loads(response_text)
    return result.get("stories", [])


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
    """Main function to generate daily wound care stories."""
    print("=" * 60)
    print("WOUND CARE STORIES GENERATOR")
    print("=" * 60)

    # 1. Fetch RSS candidates (7-day window for medical news)
    print("\n[1/4] Fetching wound care news candidates (7-day window)...")
    candidates = fetch_rss_candidates()

    # 2. Generate stories with Claude
    print("\n[2/4] Generating stories with Claude...")
    stories = generate_stories_with_claude(candidates)
    print(f"  Generated {len(stories)} stories")

    for story in stories:
        print(f"    - {story['category']} ({story['difficulty']}): {story['headline_es'][:40]}...")

    # 3. Generate TTS audio
    today = datetime.now()
    date_str = today.strftime("%Y-%m-%d")
    print("\n[3/4] Generating TTS audio...")
    stories = generate_tts_audio(stories, date_str)

    # 4. Save to JSON
    print("\n[4/4] Saving to wound-care-stories-index.json...")

    output = {
        "date": today.strftime("%Y-%m-%d"),
        "generated_at": today.isoformat() + "Z",
        "description": "Daily wound care news for Spanish medical professionals",
        "content_type": "wound-care",
        "stories": stories,
        "last_updated": today.isoformat() + "Z",
        "generated_by": "GitHub Actions + Anthropic API"
    }

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"  Saved to {OUTPUT_FILE}")

    print("\n" + "=" * 60)
    print("SUCCESS!")
    print("=" * 60)


if __name__ == "__main__":
    try:
        generate_wound_care_stories()
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
