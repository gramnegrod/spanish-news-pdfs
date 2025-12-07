#!/usr/bin/env python3
"""
Spanish News Learning PDF Generator - Production Version

Generates educational PDFs with:
- 3 US news stories adapted for A2-B1 Spanish learners
- Unsplash images with attribution
- VOCABULARIO PREPARATORIO section (context-first format)
- Story sections with images
- PRUEBA DE COMPRENSIÓN (10 questions: 4 vocab + 6 comprehension)
- RESPUESTAS answer key
"""

import os
import io
import requests
from datetime import datetime
from typing import List, Dict, Optional, Any
from urllib.parse import quote

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.colors import HexColor, white, black
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY, TA_RIGHT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, Image, KeepTogether, HRFlowable, ListFlowable, ListItem
)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont


# ============================================================================
# COLORS - Spanish flag inspired
# ============================================================================
SPANISH_RED = HexColor('#C60B1E')
SPANISH_YELLOW = HexColor('#FFC400')
DARK_GRAY = HexColor('#2D2D2D')
MEDIUM_GRAY = HexColor('#666666')
LIGHT_GRAY = HexColor('#F5F5F5')
CREAM = HexColor('#FAF9F6')
ACCENT_BLUE = HexColor('#1E5AA8')
SUCCESS_GREEN = HexColor('#2E7D32')


# ============================================================================
# UNSPLASH IMAGE FETCHING - Keys from environment only (no hardcoding)
# ============================================================================
def get_unsplash_api_key() -> str:
    """Get Unsplash API key from environment variables."""
    return os.environ.get('UNSPLASH_ACCESS_KEY') or os.environ.get('UNSPLASH_API_KEY')


def fetch_unsplash_image(
    query: str,
    api_key: Optional[str] = None,
    output_path: str = "/tmp/unsplash_image.jpg",
    width: int = 800,
    height: int = 450
) -> Optional[Dict]:
    """
    Fetch an image from Unsplash API and download it.

    AUTOMATICALLY uses UNSPLASH_ACCESS_KEY from environment if api_key not provided.

    Args:
        query: Search query (e.g., "soccer stadium", "government building")
        api_key: Unsplash API key (auto-detects from env if not provided)
        output_path: Where to save the downloaded image
        width: Target width in pixels
        height: Target height in pixels

    Returns:
        Dict with image_path and attribution, or None on failure.
    """
    # Auto-detect API key
    if not api_key:
        api_key = get_unsplash_api_key()

    if not api_key:
        print("ERROR: No Unsplash API key. Set UNSPLASH_ACCESS_KEY environment variable.")
        return None
    try:
        # Search for images
        search_url = "https://api.unsplash.com/search/photos"
        params = {
            "query": query,
            "per_page": 5,
            "orientation": "landscape"
        }
        headers = {"Authorization": f"Client-ID {api_key}"}

        response = requests.get(search_url, params=params, headers=headers, timeout=15)
        response.raise_for_status()
        data = response.json()

        if not data.get("results"):
            print(f"No images found for: {query}")
            return None

        # Get first result
        photo = data["results"][0]
        image_url = photo["urls"]["regular"]
        photographer = photo["user"]["name"]

        # Download image
        img_response = requests.get(image_url, timeout=30)
        img_response.raise_for_status()

        # Ensure directory exists
        os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)

        with open(output_path, 'wb') as f:
            f.write(img_response.content)

        # Resize with Pillow if available
        try:
            from PIL import Image as PILImage
            with PILImage.open(output_path) as img:
                img = img.resize((width, height), PILImage.LANCZOS)
                img.save(output_path, quality=85, optimize=True)
        except ImportError:
            pass

        return {
            "image_path": output_path,
            "attribution": f"Foto: {photographer} / Unsplash",
            "photographer": photographer
        }

    except Exception as e:
        print(f"Unsplash error for '{query}': {e}")
        return None


# ============================================================================
# PDF BUILDER CLASS
# ============================================================================
class SpanishLearningPDF:
    """
    Builds Spanish learning PDFs with proper structure:
    1. Title page
    2. VOCABULARIO PREPARATORIO
    3. Stories (3) with images
    4. PRUEBA DE COMPRENSIÓN
    5. RESPUESTAS
    """

    def __init__(
        self,
        title: str = "Español con Noticias",
        subtitle: str = "Noticias de Estados Unidos",
        date: str = None,
        level: str = "A2-B1"
    ):
        self.title = title
        self.subtitle = subtitle
        self.date = date or datetime.now().strftime("%d de %B de %Y").replace(
            "January", "enero").replace("February", "febrero").replace(
            "March", "marzo").replace("April", "abril").replace(
            "May", "mayo").replace("June", "junio").replace(
            "July", "julio").replace("August", "agosto").replace(
            "September", "septiembre").replace("October", "octubre").replace(
            "November", "noviembre").replace("December", "diciembre")
        self.level = level
        self.stories = []
        self.vocabulary = []
        self.quiz_questions = []
        self.styles = self._create_styles()

    def _create_styles(self) -> dict:
        """Create all paragraph styles."""
        styles = getSampleStyleSheet()

        styles.add(ParagraphStyle(
            name='MainTitle',
            fontName='Helvetica-Bold',
            fontSize=32,
            textColor=SPANISH_RED,
            alignment=TA_CENTER,
            spaceAfter=8
        ))

        styles.add(ParagraphStyle(
            name='Subtitle',
            fontName='Helvetica',
            fontSize=14,
            textColor=MEDIUM_GRAY,
            alignment=TA_CENTER,
            spaceAfter=12
        ))

        styles.add(ParagraphStyle(
            name='DateLine',
            fontName='Helvetica-Oblique',
            fontSize=12,
            textColor=MEDIUM_GRAY,
            alignment=TA_CENTER,
            spaceAfter=20
        ))

        styles.add(ParagraphStyle(
            name='SectionHeader',
            fontName='Helvetica-Bold',
            fontSize=18,
            textColor=SPANISH_RED,
            spaceBefore=20,
            spaceAfter=12,
            alignment=TA_LEFT
        ))

        styles.add(ParagraphStyle(
            name='StoryHeadline',
            fontName='Helvetica-Bold',
            fontSize=16,
            textColor=DARK_GRAY,
            spaceBefore=12,
            spaceAfter=4,
            leading=20
        ))

        styles.add(ParagraphStyle(
            name='StoryHeadlineEn',
            fontName='Helvetica-Oblique',
            fontSize=11,
            textColor=MEDIUM_GRAY,
            spaceAfter=10
        ))

        styles.add(ParagraphStyle(
            name='BodySpanish',
            fontName='Times-Roman',
            fontSize=12,
            textColor=DARK_GRAY,
            alignment=TA_JUSTIFY,
            leading=18,
            spaceAfter=8
        ))

        styles.add(ParagraphStyle(
            name='BodyEnglish',
            fontName='Times-Italic',
            fontSize=10,
            textColor=MEDIUM_GRAY,
            alignment=TA_JUSTIFY,
            leading=14,
            spaceAfter=12,
            leftIndent=10,
            rightIndent=10
        ))

        styles.add(ParagraphStyle(
            name='VocabContext',
            fontName='Times-Italic',
            fontSize=11,
            textColor=DARK_GRAY,
            leading=14
        ))

        styles.add(ParagraphStyle(
            name='VocabWord',
            fontName='Helvetica-Bold',
            fontSize=12,
            textColor=ACCENT_BLUE,
            leading=16
        ))

        styles.add(ParagraphStyle(
            name='VocabDef',
            fontName='Times-Roman',
            fontSize=10,
            textColor=DARK_GRAY,
            leading=13,
            leftIndent=15
        ))

        styles.add(ParagraphStyle(
            name='QuizQuestion',
            fontName='Times-Roman',
            fontSize=11,
            textColor=DARK_GRAY,
            leading=15,
            spaceBefore=8,
            spaceAfter=4
        ))

        styles.add(ParagraphStyle(
            name='QuizOption',
            fontName='Times-Roman',
            fontSize=10,
            textColor=DARK_GRAY,
            leading=13,
            leftIndent=25
        ))

        styles.add(ParagraphStyle(
            name='AnswerKey',
            fontName='Helvetica',
            fontSize=10,
            textColor=MEDIUM_GRAY,
            leading=14
        ))

        styles.add(ParagraphStyle(
            name='Attribution',
            fontName='Helvetica',
            fontSize=8,
            textColor=MEDIUM_GRAY,
            alignment=TA_RIGHT,
            spaceAfter=8
        ))

        styles.add(ParagraphStyle(
            name='CategoryTag',
            fontName='Helvetica-Bold',
            fontSize=9,
            textColor=white,
            alignment=TA_CENTER
        ))

        return styles

    def add_vocabulary(self, vocab_list: List[Dict]):
        self.vocabulary.extend(vocab_list)

    def add_story(self, story: Dict):
        self.stories.append(story)

    def add_quiz_question(self, question: Dict):
        self.quiz_questions.append(question)

    def _build_header(self) -> List:
        elements = []
        elements.append(HRFlowable(width="100%", thickness=8, color=SPANISH_RED, spaceAfter=25))
        elements.append(Paragraph(self.title, self.styles['MainTitle']))
        elements.append(Paragraph(self.subtitle, self.styles['Subtitle']))
        elements.append(Paragraph(f"{self.date} | Nivel {self.level}", self.styles['DateLine']))
        elements.append(HRFlowable(width="30%", thickness=4, color=SPANISH_YELLOW, spaceAfter=20))
        return elements

    def _build_vocabulary_section(self) -> List:
        elements = []
        elements.append(Paragraph("📚 VOCABULARIO PREPARATORIO", self.styles['SectionHeader']))
        elements.append(Paragraph("<i>Estudia estas palabras antes de leer las noticias.</i>", self.styles['BodyEnglish']))
        elements.append(Spacer(1, 10))

        for i, vocab in enumerate(self.vocabulary, 1):
            context = vocab.get('context', '')
            word = vocab.get('word', '')

            if word and context:
                context_highlighted = context.replace(word, f"<b><font color='#1E5AA8'>{word}</font></b>")
                context_highlighted = context_highlighted.replace(word.capitalize(), f"<b><font color='#1E5AA8'>{word.capitalize()}</font></b>")
            else:
                context_highlighted = context

            elements.append(Paragraph(f"<i>\"{context_highlighted}\"</i>", self.styles['VocabContext']))
            syllables = vocab.get('syllables', word.upper())
            pos = vocab.get('pos', '')
            elements.append(Paragraph(f"<b>{i}. {word}</b> [{syllables}] <i>({pos})</i>", self.styles['VocabWord']))
            def_es = vocab.get('definition_es', '')
            def_en = vocab.get('definition_en', '')
            elements.append(Paragraph(f"→ {def_es}<br/><i>English: {def_en}</i>", self.styles['VocabDef']))
            elements.append(Spacer(1, 8))

        return elements

    def _build_category_tag(self, category: str) -> Table:
        tag = Table([[Paragraph(category.upper(), self.styles['CategoryTag'])]], colWidths=[1.8*inch])
        tag.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), SPANISH_RED),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ('LEFTPADDING', (0, 0), (-1, -1), 10),
            ('RIGHTPADDING', (0, 0), (-1, -1), 10),
        ]))
        return tag

    def _build_story_section(self, story: Dict, story_num: int) -> List:
        elements = []
        elements.append(self._build_category_tag(story.get('category', 'Noticias')))
        elements.append(Spacer(1, 8))
        elements.append(Paragraph(f"Historia {story_num}: {story.get('headline_es', '')}", self.styles['StoryHeadline']))
        elements.append(Paragraph(story.get('headline_en', ''), self.styles['StoryHeadlineEn']))

        image_path = story.get('image_path')
        if image_path and os.path.exists(image_path):
            try:
                img = Image(image_path, width=6*inch, height=3.4*inch)
                elements.append(img)
                attribution = story.get('image_attribution', '')
                if attribution:
                    elements.append(Paragraph(attribution, self.styles['Attribution']))
            except Exception as e:
                print(f"Error loading image: {e}")

        elements.append(Spacer(1, 8))
        elements.append(Paragraph(story.get('body_es', ''), self.styles['BodySpanish']))
        elements.append(Paragraph(f"<b>Traducción:</b> {story.get('body_en', '')}", self.styles['BodyEnglish']))

        source = story.get('source', '')
        if source:
            elements.append(Paragraph(f"<i>Fuente: {source}</i>", self.styles['Attribution']))

        return elements

    def _build_quiz_section(self) -> List:
        elements = []
        elements.append(Paragraph("📝 PRUEBA DE COMPRENSIÓN", self.styles['SectionHeader']))
        elements.append(Paragraph("<i>Responde las siguientes preguntas basándote en las noticias.</i>", self.styles['BodyEnglish']))
        elements.append(Spacer(1, 10))

        elements.append(Paragraph("<b>Vocabulario (1-4)</b>", self.styles['QuizQuestion']))
        elements.append(Spacer(1, 5))
        for q in self.quiz_questions:
            if q.get('type') == 'vocab' or q.get('number', 0) <= 4:
                elements.extend(self._format_question(q))

        elements.append(Spacer(1, 15))
        elements.append(Paragraph("<b>Comprensión (5-10)</b>", self.styles['QuizQuestion']))
        elements.append(Spacer(1, 5))
        for q in self.quiz_questions:
            if q.get('type') == 'comprehension' or q.get('number', 0) > 4:
                elements.extend(self._format_question(q))

        return elements

    def _format_question(self, q: Dict) -> List:
        elements = []
        num = q.get('number', '?')
        question = q.get('question_es', '')
        options = q.get('options', [])

        elements.append(Paragraph(f"<b>{num}.</b> {question}", self.styles['QuizQuestion']))
        if options:
            for i, opt in enumerate(options):
                letter = chr(97 + i)
                elements.append(Paragraph(f"{letter}) {opt}", self.styles['QuizOption']))
        elements.append(Spacer(1, 8))
        return elements

    def _build_answer_key(self) -> List:
        elements = []
        elements.append(Paragraph("✅ RESPUESTAS", self.styles['SectionHeader']))
        elements.append(Spacer(1, 10))

        answers = []
        for q in sorted(self.quiz_questions, key=lambda x: x.get('number', 0)):
            num = q.get('number', '?')
            ans = q.get('answer', '?')
            if isinstance(ans, bool):
                ans = "Verdadero" if ans else "Falso"
            answers.append(f"{num}. {ans}")

        mid = (len(answers) + 1) // 2
        col1 = answers[:mid]
        col2 = answers[mid:]
        while len(col2) < len(col1):
            col2.append("")

        answer_data = list(zip(col1, col2))
        answer_table = Table(answer_data, colWidths=[2.5*inch, 2.5*inch])
        answer_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 11),
            ('TEXTCOLOR', (0, 0), (-1, -1), DARK_GRAY),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('BACKGROUND', (0, 0), (-1, -1), LIGHT_GRAY),
        ]))
        elements.append(answer_table)
        return elements

    def save(self, output_path: str):
        os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)
        doc = SimpleDocTemplate(
            output_path,
            pagesize=letter,
            rightMargin=0.75*inch,
            leftMargin=0.75*inch,
            topMargin=0.75*inch,
            bottomMargin=0.75*inch
        )

        elements = []
        elements.extend(self._build_header())

        if self.vocabulary:
            elements.extend(self._build_vocabulary_section())
            elements.append(PageBreak())

        for i, story in enumerate(self.stories, 1):
            elements.extend(self._build_story_section(story, i))
            if i < len(self.stories):
                elements.append(Spacer(1, 20))
                elements.append(HRFlowable(width="100%", thickness=1, color=MEDIUM_GRAY, spaceAfter=20))

        if self.quiz_questions:
            elements.append(PageBreak())
            elements.extend(self._build_quiz_section())

        if self.quiz_questions:
            elements.append(PageBreak())
            elements.extend(self._build_answer_key())

        doc.build(elements)
        print(f"PDF saved: {output_path}")
        return output_path


if __name__ == "__main__":
    print("SpanishLearningPDF module loaded. Import and use SpanishLearningPDF class.")
