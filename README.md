# Spanish News Learning PDFs

Daily Spanish learning PDFs generated automatically from current US news stories.

## What This Does

Every day at 3:00 AM Central Time, a GitHub Action:
1. Fetches current US news (politics, economy, technology)
2. Adapts stories for A2-B1 Spanish learners using Claude API
3. Adds relevant images from Unsplash
4. Generates a polished educational PDF
5. Commits the PDF to this repo

## Accessing PDFs

### Direct URLs (Public Repo)

```
https://raw.githubusercontent.com/gramnegrod/spanish-news-pdfs/main/index.json
https://raw.githubusercontent.com/gramnegrod/spanish-news-pdfs/main/pdfs/spanish_lesson_2025-12-07.pdf
```

### From Your App

```javascript
const response = await fetch('https://raw.githubusercontent.com/gramnegrod/spanish-news-pdfs/main/index.json');
const index = await response.json();

// Get latest PDF
const latest = index.pdfs[0];
const pdfUrl = `https://raw.githubusercontent.com/gramnegrod/spanish-news-pdfs/main/${latest.path}`;
```

## PDF Contents

Each PDF includes:
- **Vocabulario Preparatorio**: 6-8 key words with context
- **3 News Stories**: Adapted for A2-B1 with images and translations
- **Prueba de Comprension**: 10-question quiz (4 vocab + 6 comprehension)
- **Respuestas**: Answer key

## Setup (For Forking)

1. Fork this repository
2. Add these secrets in Settings > Secrets:
   - `ANTHROPIC_API_KEY` (required)
   - `UNSPLASH_ACCESS_KEY` (required)
3. Enable GitHub Actions

## Manual Trigger

1. Go to Actions tab
2. Select "Generate Daily Spanish PDF"
3. Click "Run workflow"

## File Structure

```
spanish-news-pdfs/
├── pdfs/
│   └── spanish_lesson_YYYY-MM-DD.pdf
├── scripts/
│   ├── generate_spanish_pdf.py
│   └── pdf_builder.py
├── index.json
└── .github/workflows/daily-pdf.yml
```
