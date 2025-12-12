#!/usr/bin/env python3
"""
Conversation Stories Generator for Noticias del Día

Generates 6 daily conversation stories for Spanish practice:
- 2 stories at A2 level (simple vocab, present tense)
- 2 stories at B1 level (varied tenses, more complex)
- 2 stories at B2 level (advanced vocab, subjunctive)

Also generates two-host podcasts for 3 categories:
- Economía, Medio Ambiente, Gastronomía

Uses Google News RSS for story candidates, Claude for adaptation.
"""

import os
import sys
import json
import requests
import xml.etree.ElementTree as ET
import html
import re
import io
from datetime import datetime
from typing import List, Dict
from pathlib import Path
import anthropic
from openai import OpenAI

# Optional: pydub for audio concatenation (fallback to simple concatenation if not available)
try:
    from pydub import AudioSegment
    HAS_PYDUB = True
except ImportError:
    HAS_PYDUB = False
    print("  ⚠ pydub not installed - podcast audio will be concatenated without crossfades")

# Configuration
ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY')
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')
OUTPUT_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'conversation-stories-index.json')
AUDIO_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'audio', 'conversation-stories')
GITHUB_RAW_BASE = "https://raw.githubusercontent.com/gramnegrod/spanish-news-pdfs/main"

# Category configuration with emoji and gradient
CATEGORIES = [
    {"name": "Tecnología", "emoji": "🤖", "gradient": "blue", "query": "technology+AI+tech+companies"},
    {"name": "Deportes", "emoji": "⚽", "gradient": "green", "query": "sports+soccer+football+basketball"},
    {"name": "Cultura", "emoji": "🎬", "gradient": "orange", "query": "movies+music+entertainment+culture"},
    {"name": "Economía", "emoji": "💰", "gradient": "yellow", "query": "economy+business+markets+finance"},
    {"name": "Medio Ambiente", "emoji": "🌳", "gradient": "teal", "query": "environment+climate+nature+science"},
    {"name": "Gastronomía", "emoji": "🌮", "gradient": "red-orange", "query": "food+restaurants+cooking+cuisine"},
]

# Difficulty distribution: which categories get which level
DIFFICULTY_MAP = {
    "Tecnología": "A2",
    "Deportes": "A2",
    "Cultura": "B1",
    "Economía": "B1",
    "Medio Ambiente": "B2",
    "Gastronomía": "B2",
}

# Categories that get two-host podcast versions
PODCAST_CATEGORIES = ["Economía", "Medio Ambiente", "Gastronomía"]

# Voice instructions for podcast hosts
VOICE_INSTRUCTIONS = {
    "LAURA": """Speak Spanish with a fun Mexican accent. You're Laura, an
enthusiastic 28-year-old from Mexico City. You're bubbly, curious, and love
sharing interesting news with friends. Use expressions like '¡No manches!',
'¡Qué padre!', 'O sea...'. Sound like you're chatting at a café, not reading news.""",

    "CARLOS": """Speak Spanish with a relaxed Mexican accent. You're Carlos, a
chill 32-year-old from Guadalajara. You're thoughtful and often add interesting
perspectives. Use expressions like 'Fíjate que...', 'La neta...', 'Pues sí...'.
Sound like a friend who always has something interesting to add."""
}

# Category to filename slug mapping
CATEGORY_SLUGS = {
    "Tecnología": "tech",
    "Deportes": "sports",
    "Cultura": "culture",
    "Economía": "economy",
    "Medio Ambiente": "environment",
    "Gastronomía": "gastronomy"
}


def fetch_rss_candidates() -> Dict[str, List[Dict]]:
    """Fetch news candidates from Google News RSS for each category."""
    candidates = {}

    for cat in CATEGORIES:
        category = cat["name"]
        query = cat["query"]
        feed_url = f"https://news.google.com/rss/search?q={query}+when:1d&hl=en-US&gl=US&ceid=US:en"

        candidates[category] = []

        try:
            response = requests.get(feed_url, timeout=15, headers={
                'User-Agent': 'Mozilla/5.0 (compatible; SpanishNewsBot/1.0)'
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

                source_text = source.text if source is not None and source.text else "News"

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
    """Use Claude to select and adapt stories for each category/difficulty."""

    if not ANTHROPIC_API_KEY:
        raise ValueError("ANTHROPIC_API_KEY environment variable is required")

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    # Build prompt with all candidates
    prompt = """You are creating Spanish conversation stories for language learners.

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
            prompt += "No candidates available - create a realistic story about this topic.\n"

    prompt += """

OUTPUT FORMAT - Return valid JSON with exactly 6 stories:

{
  "stories": [
    {
      "id": "tech-YYYYMMDD",
      "category": "Tecnología",
      "difficulty": "A2",
      "emoji": "🤖",
      "gradient": "blue",
      "headline_es": "Spanish headline (compelling, level-appropriate)",
      "headline_en": "English translation",
      "summary_es": "1-2 sentence Spanish summary",
      "body_es": "Full Spanish story (100-150 words for A2, 150-200 for B1, 200-250 for B2)",
      "body_en": "English translation of body",
      "audio_url": "",
      "key_vocabulary": [
        {"word": "palabra", "definition_es": "definición simple", "definition_en": "English definition"},
        {"word": "otra", "definition_es": "otra definición", "definition_en": "another definition"},
        {"word": "tercera", "definition_es": "tercera definición", "definition_en": "third definition"},
        {"word": "cuarta", "definition_es": "cuarta definición", "definition_en": "fourth definition"}
      ]
    }
  ]
}

LEVEL GUIDELINES:

A2 (Tecnología, Deportes):
- Present tense mainly, simple past occasionally
- Short sentences (8-12 words)
- Concrete, everyday vocabulary
- Avoid subjunctive entirely

B1 (Cultura, Economía):
- Mix of tenses including imperfect and future
- Medium sentences (12-18 words)
- Some abstract vocabulary
- Simple conditional ("si + present, future")

B2 (Medio Ambiente, Gastronomía):
- Complex tenses including subjunctive
- Longer, compound sentences
- Advanced vocabulary and idioms
- Conditional and hypothetical structures

REQUIREMENTS:
1. Each story must have exactly 4 vocabulary words
2. Vocabulary should be words that actually appear in the story
3. Use today's date in the id field: """ + datetime.now().strftime("%Y%m%d") + """
4. Stories must be based on the actual news when available
5. Include specific names, numbers, and facts

Return ONLY the JSON, no other text."""

    print("\n  Calling Claude API for story generation...")

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
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

    # Category to filename mapping
    category_slugs = {
        "Tecnología": "tech",
        "Deportes": "sports",
        "Cultura": "culture",
        "Economía": "economy",
        "Medio Ambiente": "environment",
        "Gastronomía": "gastronomy"
    }

    for story in stories:
        category = story.get("category", "unknown")
        slug = category_slugs.get(category, "story")
        filename = f"{slug}.mp3"
        filepath = os.path.join(audio_date_dir, filename)

        try:
            # Generate TTS for the Spanish body text with Mexican accent
            response = client.audio.speech.create(
                model="gpt-4o-mini-tts",
                voice="coral",
                input=story["body_es"],
                instructions="Speak with a natural Mexican Spanish accent. Use clear pronunciation at a moderate pace suitable for Spanish language learners. Warm and friendly tone."
            )

            # Save the audio file
            response.stream_to_file(filepath)

            # Update story with audio URL
            story["audio_url"] = f"{GITHUB_RAW_BASE}/audio/conversation-stories/{date_str}/{filename}"
            print(f"    ✓ {category}: {filename}")

        except Exception as e:
            print(f"    ✗ {category}: TTS error - {e}")
            story["audio_url"] = ""

    return stories


def generate_podcast_script(client: OpenAI, story: Dict) -> str:
    """Generate a two-host podcast script from a story using GPT."""

    prompt = f"""Create a fun, casual 60-second Spanish podcast script.

Two friends discussing this news story:

HEADLINE: {story.get('headline_es', '')}
STORY: {story.get('body_es', '')}

HOSTS:
- LAURA: Bubbly, enthusiastic, starts the conversation
- CARLOS: Chill, thoughtful, adds interesting takes

STYLE:
- Like friends chatting at a café, NOT news anchors
- Playful banter and reactions ("¡No manches!", "¿En serio?", "¡Qué padre!")
- Natural interruptions and back-and-forth
- Keep it light and fun
- Mexican Spanish with natural expressions
- Include reactions to the news, not just facts

FORMAT (IMPORTANT - use exactly this format):
LAURA: [dialogue in Spanish]
CARLOS: [dialogue in Spanish]
LAURA: [dialogue in Spanish]
...

Keep it ~150-180 words total. 8-12 exchanges. End on a fun note."""

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}]
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"      Script generation error: {e}")
        return ""


def parse_podcast_script(script: str) -> List[Dict]:
    """Parse a podcast script into speaker lines."""
    lines = []
    for line in script.strip().split('\n'):
        line = line.strip()
        if line.startswith('LAURA:'):
            text = line[6:].strip()
            if text:
                lines.append({"speaker": "LAURA", "text": text})
        elif line.startswith('CARLOS:'):
            text = line[7:].strip()
            if text:
                lines.append({"speaker": "CARLOS", "text": text})
    return lines


def combine_audio_segments(segments: List[bytes], output_path: str) -> bool:
    """Combine multiple MP3 audio segments into one file."""
    if not segments:
        return False

    try:
        if HAS_PYDUB:
            # Use pydub for proper audio concatenation with small gaps
            combined = AudioSegment.empty()
            silence = AudioSegment.silent(duration=300)  # 300ms pause between speakers

            for i, segment_data in enumerate(segments):
                segment = AudioSegment.from_mp3(io.BytesIO(segment_data))
                combined += segment
                if i < len(segments) - 1:
                    combined += silence

            combined.export(output_path, format="mp3")
        else:
            # Simple concatenation fallback (works but no gaps)
            with open(output_path, 'wb') as f:
                for segment in segments:
                    f.write(segment)

        return True
    except Exception as e:
        print(f"      Audio combine error: {e}")
        return False


def generate_podcast_audio(stories: List[Dict], date_str: str) -> List[Dict]:
    """Generate two-host podcast audio for selected categories."""

    if not OPENAI_API_KEY:
        print("  ⚠ Skipping podcast generation - no API key")
        return stories

    client = OpenAI(api_key=OPENAI_API_KEY)
    audio_date_dir = os.path.join(AUDIO_DIR, date_str)
    Path(audio_date_dir).mkdir(parents=True, exist_ok=True)

    podcast_count = 0
    for story in stories:
        category = story.get("category", "")
        if category not in PODCAST_CATEGORIES:
            continue

        print(f"    🎙️ {category}: Generating podcast...")

        # 1. Generate two-host script with GPT
        script = generate_podcast_script(client, story)
        if not script:
            print(f"      ✗ Script generation failed")
            continue

        # 2. Parse into speaker lines
        lines = parse_podcast_script(script)
        if len(lines) < 4:
            print(f"      ✗ Script parsing failed (only {len(lines)} lines)")
            continue

        print(f"      Script: {len(lines)} exchanges")

        # 3. Generate audio for each line
        segments = []
        for i, line in enumerate(lines):
            voice = "nova" if line["speaker"] == "LAURA" else "onyx"
            instruction = VOICE_INSTRUCTIONS[line["speaker"]]

            try:
                response = client.audio.speech.create(
                    model="gpt-4o-mini-tts",
                    voice=voice,
                    input=line["text"],
                    instructions=instruction
                )
                segments.append(response.content)
            except Exception as e:
                print(f"      ✗ TTS error for line {i}: {e}")
                # Continue with partial audio if some lines fail

        if len(segments) < len(lines) // 2:
            print(f"      ✗ Too many TTS failures")
            continue

        # 4. Combine segments into one MP3
        slug = CATEGORY_SLUGS.get(category, "story")
        podcast_filename = f"{slug}-podcast.mp3"
        podcast_path = os.path.join(audio_date_dir, podcast_filename)

        if combine_audio_segments(segments, podcast_path):
            # 5. Add podcast URL and transcript to story
            story["podcast_url"] = f"{GITHUB_RAW_BASE}/audio/conversation-stories/{date_str}/{podcast_filename}"
            story["podcast_transcript"] = script
            podcast_count += 1
            print(f"      ✓ {podcast_filename}")
        else:
            print(f"      ✗ Audio combination failed")

    print(f"  Generated {podcast_count} podcasts")
    return stories


def generate_conversation_stories():
    """Main function to generate daily conversation stories."""
    print("=" * 60)
    print("CONVERSATION STORIES GENERATOR")
    print("=" * 60)

    # 1. Fetch RSS candidates
    print("\n[1/5] Fetching news candidates...")
    candidates = fetch_rss_candidates()

    # 2. Generate stories with Claude
    print("\n[2/5] Generating stories with Claude...")
    stories = generate_stories_with_claude(candidates)
    print(f"  Generated {len(stories)} stories")

    for story in stories:
        print(f"    - {story['category']} ({story['difficulty']}): {story['headline_es'][:40]}...")

    # 3. Generate single-voice TTS audio
    today = datetime.now()
    date_str = today.strftime("%Y-%m-%d")
    print("\n[3/5] Generating single-voice TTS audio...")
    stories = generate_tts_audio(stories, date_str)

    # 4. Generate two-host podcast audio for selected categories
    print("\n[4/5] Generating two-host podcast audio...")
    stories = generate_podcast_audio(stories, date_str)

    # 5. Save to JSON
    print("\n[5/5] Saving to conversation-stories-index.json...")

    today = datetime.now()
    output = {
        "date": today.strftime("%Y-%m-%d"),
        "generated_at": today.isoformat() + "Z",
        "description": "Daily conversation stories for Spanish practice",
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
        generate_conversation_stories()
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
