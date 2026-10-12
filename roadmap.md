# spanish-news-pdfs roadmap

Failure registry and decision journal. Entries: `[YYYY-MM-DD HH:MM] CATEGORY - detail` (America/Chicago).

## Log

[2026-10-12 14:40] DECISION - Wound care feed limited to US and European news. Google News US edition (gl=US) still returned publishers and studies from India, Pakistan, South Africa, Australia. Fix: publisher domain filter in fetch_rss_candidates (generic or European TLD, minus known Indian/Pakistani .com outlets) plus a GEOGRAPHY rule in the story prompt that skips stories set outside the US/Europe. Existing 1240 stories in wound-care-stories-index.json were not cleaned.

[2026-10-12 15:05] FOLLOW-UP - PR #5 review (score 50): candidates rejected by the GEOGRAPHY prompt rule are not remembered; existing_urls only holds saved stories, so a rejected non-US/EU item is re-offered daily for up to 7 days and judged from its title alone. Fix idea: persist rejected URLs in the index.
[2026-10-12 15:05] FOLLOW-UP - PR #5 review (score 35): if all 3 candidates in a category are rejected, the same 3 refill the window and items ranked 4-10 never reach the model.
[2026-10-12 15:05] DECLINED - PR #5 review (score 10): wasted generations when everything is rejected; not a regression, the domain filter only removes candidates.
[2026-10-12 15:05] FAILURE - URL dedup misses the same article under a different Google News URL (pre-existing). The India M. fortuitum case series was adapted 3 days running (10-09 to 10-11); a bone infection story 4 days (09-28 to 10-01). Dedup by normalized headline or publisher URL would fix it.

## Next:

- Optional one-time cleanup of existing non-US/EU stories in wound-care-stories-index.json.
