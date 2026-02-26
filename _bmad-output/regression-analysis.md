# Regression Analysis — Phase 0

**Date:** 2026-02-27
**Site tested:** chiostrodisaronno.it
**Tool version:** Post YAML + SquirrelScan integration

## Previous Reports
No previous reports found in `output/` directory. Cannot do diff-based regression analysis.

## Current State
- YAML checklists: intact (5 files in `data/checklists/`)
- osmani-config.json: intact
- SquirrelScan integration: functional
- 14 bugs identified from manual review of chiostrodisaronno.it report

## Bugs Identified
1. Heading hierarchy regression — tree structure not shown
2. Schema markup superficial — no JSON-LD examples
3. Images without detail — missing URL+src listing
4. International SEO — hreflang extraction verified OK (not a regression)
5. Tone issues — catastrophic language, invented euro estimates
6. Duplicate data with different values — PSI fetched per-analysis
7. Section duplication — same finding in multiple sections
8. Sitemap numbers unverified — AI invents counts
9. Impractical fixes — "contact support" instead of actionable steps
10. Crawler errors reported as site problems
11. Best practices flagged as problems (robots.txt)
12. Irrelevant crawlers flagged
13. Tasks instead of answers — "verify manually"
14. CRO only analyzes homepage

## Best Practice Files
All intact — no files lost during refactoring.
