# GEO — Generative Engine Optimization Framework
Version: 1.0 | Updated: 2026-02-27
Sources: claude-seo (AgriciDaniel), seo-geo-claude-skills (aaron-he-zhu)

## What is GEO?
Optimizing content for AI-generated answers (Google AI Overviews, ChatGPT, Perplexity, Bing Copilot).
Unlike SEO (rank in search results), GEO focuses on getting CITED in AI responses.

## Key Statistics (2025-2026)
- AI Overviews: 1.5B users/month, 200+ countries, 50%+ query coverage
- AI-referred sessions: +527% growth (Jan-May 2025)
- ChatGPT: 900M weekly active users
- Perplexity: 500M+ monthly queries
- Only 11% of domains cited by BOTH ChatGPT and Google AI Overviews for same query

## Critical Insight: Brand Mentions > Backlinks
Brand mentions correlate 3x more strongly with AI visibility than backlinks (Ahrefs Dec 2025).
- YouTube mentions: ~0.737 correlation (strongest)
- Reddit mentions: High correlation
- Wikipedia presence: High correlation
- Domain Rating (backlinks): ~0.266 (weak)

## SEO vs GEO Comparison
| Aspect | SEO | GEO |
|--------|-----|-----|
| Goal | Rank in search results | Get cited in AI responses |
| Signals | Backlinks, keywords, speed | Authority, clarity, citations |
| Content style | Keyword-optimized | Fact-rich, quotable statements |
| Structure | H1/H2 hierarchy | Q&A format, clear definitions |
| Metric | Click-through rate | Citation frequency |

## GEO Analysis Criteria (Scoring)

### 1. Citability Score (25%)
- Optimal passage length: 134-167 words for AI citation
- Clear, quotable sentences with specific facts/statistics
- Self-contained answer blocks (extractable without context)
- Direct answer in first 40-60 words of section
- Claims attributed with specific sources
- Definitions following "X is..." or "X refers to..." patterns

### 2. Structural Readability (20%)
- 92% of AI Overview citations from top-10 ranking pages
- 47% from pages ranking below position 5 (different selection logic)
- Clean H1→H2→H3 heading hierarchy
- Question-based headings (matches query patterns)
- Short paragraphs (2-4 sentences)
- Tables for comparative data
- FAQ sections with clear Q&A format

### 3. Multi-Modal Content (15%)
- Content with multi-modal elements: 156% higher selection rates
- Text + relevant images, video, infographics, interactive tools
- Structured data supporting media

### 4. Authority & Brand Signals (20%)
- Author byline with credentials
- Publication date and last-updated date
- Citations to primary sources
- Entity presence: Wikipedia, Wikidata, Reddit, YouTube, LinkedIn
- Expert quotes with attribution

### 5. Technical Accessibility (20%)
- AI crawlers do NOT execute JavaScript — SSR is critical
- AI crawler access in robots.txt
- llms.txt file presence

## AI Crawler Management
| Crawler | Owner | robots.txt Token | Purpose |
|---------|-------|-----------------|---------|
| GPTBot | OpenAI | GPTBot | Model training |
| ChatGPT-User | OpenAI | ChatGPT-User | Real-time browsing |
| ClaudeBot | Anthropic | ClaudeBot | Model training |
| PerplexityBot | Perplexity | PerplexityBot | Search index |
| Google-Extended | Google | Google-Extended | Gemini training (NOT search) |
| Bytespider | ByteDance | Bytespider | Model training |
| CCBot | Common Crawl | CCBot | Open dataset |

Blocking Google-Extended does NOT affect Google Search or AI Overviews.
Blocking GPTBot does NOT prevent ChatGPT from citing via browsing (ChatGPT-User).

## Platform-Specific Optimization
| Platform | Key Citation Sources | Focus |
|----------|---------------------|-------|
| Google AI Overviews | Top-10 ranking pages (92%) | Traditional SEO + passage optimization |
| ChatGPT | Wikipedia (47.9%), Reddit (11.3%) | Entity presence, authoritative sources |
| Perplexity | Reddit (46.7%), Wikipedia | Community validation, discussions |
| Bing Copilot | Bing index, authoritative sites | Bing SEO, IndexNow |

## Quick Wins for GEO
1. Add "What is [topic]?" definition in first 60 words
2. Create 134-167 word self-contained answer blocks
3. Add question-based H2/H3 headings
4. Include specific statistics with sources
5. Add publication/update dates
6. Implement Person schema for authors
7. Allow key AI crawlers in robots.txt
8. Structure data in tables (most extractable format)
9. Include FAQ sections with clear Q&A format
10. Build brand presence on YouTube, Reddit, Wikipedia, LinkedIn

## CORE-EEAT High-Impact Items for AI Citations
- C02: Direct Answer in first 150 words (all engines extract)
- C09: Structured FAQ with Schema (matches AI follow-ups)
- O02: Key Takeaways/Summary Box (first choice for AI summaries)
- O03: Data in tables (most extractable format)
- O05: JSON-LD Schema Markup (helps AI understand content)
- E01: Original first-party data (AI prefers exclusive sources)

## Content Optimization for GEO
- Include clear product specs, dimensions, materials in structured format
- Use ProductGroup schema for variant products
- Provide original photography with descriptive alt text
- Include genuine customer review content (AggregateRating schema)
- Maintain consistent entity data across all platforms
- Structure comparison content with clear feature tables
- Add detailed FAQ content for common questions
- Publish original case studies with citable metrics
- Use Person schema with sameAs links for team members
