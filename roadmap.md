# spanish-news-pdfs roadmap

Failure registry and decision journal. Entries: `[YYYY-MM-DD HH:MM] CATEGORY - detail` (America/Chicago).

## Log

[2026-10-12 14:40] DECISION - Wound care feed limited to US and European news. Google News US edition (gl=US) still returned publishers and studies from India, Pakistan, South Africa, Australia. Fix: publisher domain filter in fetch_rss_candidates (generic or European TLD, minus known Indian/Pakistani .com outlets) plus a GEOGRAPHY rule in the story prompt that skips stories set outside the US/Europe. Existing 1240 stories in wound-care-stories-index.json were not cleaned.

## Next:

- Optional one-time cleanup of existing non-US/EU stories in wound-care-stories-index.json.
