# Osmani Performance Patterns — Web Quality Reference
Version: 1.0 | Updated: 2026-02-27
Source: web-quality-skills (addyosmani, Chrome team)

## Performance Budgets
| Resource | Budget | Rationale |
|----------|--------|-----------|
| Total page weight | < 1.5 MB | 3G loads in ~4s |
| JavaScript (compressed) | < 300 KB | Parsing + execution time |
| CSS (compressed) | < 100 KB | Render blocking |
| Images (above-fold) | < 500 KB | LCP impact |
| Fonts | < 100 KB | FOIT/FOUT prevention |
| Third-party scripts | < 200 KB | Uncontrolled latency |

## Lighthouse Targets
| Metric | Target |
|--------|--------|
| Performance | >= 90 |
| Accessibility | 100 |
| Best Practices | >= 95 |
| SEO | >= 95 |

## Core Web Vitals (75th percentile)
| Metric | Good | Needs Work | Poor |
|--------|------|------------|------|
| LCP | <= 2.5s | 2.5-4s | > 4s |
| INP | <= 200ms | 200-500ms | > 500ms |
| CLS | <= 0.1 | 0.1-0.25 | > 0.25 |

INP replaced FID on March 12, 2024. FID fully removed Sept 9, 2024.

## LCP Subparts (Feb 2025 CrUX)
| Subpart | Measures | Target |
|---------|----------|--------|
| TTFB | Server response | < 800ms |
| Resource Load Delay | TTFB to request start | Minimize |
| Resource Load Time | Download LCP resource | Depends on size |
| Element Render Delay | Resource loaded to rendered | Minimize |

## Additional Metrics
| Metric | Target |
|--------|--------|
| TTFB | < 800ms |
| FCP | < 1.8s |
| Speed Index | < 3.4s |
| TBT | < 200ms |
| TTI | < 3.8s |

## Server Response Patterns
1. CDN with edge caching for HTML when possible
2. Brotli compression (15-20% smaller than Gzip)
3. HTTP/2 or HTTP/3 multiplexing
4. Cache-Control: HTML no-cache; hashed assets immutable 1yr; API private no-cache

## Critical Rendering Path
1. Inline critical CSS < 14KB (above-fold only)
2. Defer non-critical CSS with preload+onload pattern
3. Scripts: defer (preferred) or async (independent)
4. Preconnect to required origins
5. Preload LCP image with fetchpriority="high"
6. Preload critical font with crossorigin

## Image Optimization
| Format | Use Case | Support |
|--------|----------|---------|
| AVIF | Photos, best compression | 92%+ |
| WebP | Photos, good fallback | 97%+ |
| PNG | Graphics with transparency | Universal |
| SVG | Icons, logos, illustrations | Universal |

- LCP image: fetchpriority="high", loading="eager", decoding="sync"
- Below-fold: loading="lazy", decoding="async"
- Always set width/height or aspect-ratio (CLS prevention)
- Use <picture> with AVIF > WebP > JPEG fallback
- Use srcset + sizes for responsive images

## Font Optimization
- font-display: swap (prevent invisible text)
- Preload critical fonts: <link rel="preload" as="font" type="font/woff2" crossorigin>
- Variable fonts for multiple weights in one file
- Font subsetting for unused unicode ranges
- For CLS: font-display: optional OR size-adjust + ascent-override + descent-override

## JavaScript Optimization
- Code splitting: route-based, component-based, feature-based
- Tree shaking: import only what's needed
- Break long tasks into < 50ms chunks (yield with setTimeout(0) or scheduler.yield())
- Visual feedback before heavy work (requestAnimationFrame)
- Defer non-critical work with requestIdleCallback
- Use Web Workers for CPU-intensive operations
- Debounce scroll/resize handlers
- Virtualize long lists (content-visibility: auto)

## Third-Party Script Patterns
- Load async or defer
- Delay until user interaction
- Facade pattern: static placeholder until interaction (YouTube, chat widgets, maps)
- Use event delegation instead of per-element handlers

## Caching Strategy
| Resource | Cache-Control |
|----------|--------------|
| HTML | no-cache, must-revalidate |
| Hashed static assets | public, max-age=31536000, immutable |
| Unhashed static | public, max-age=86400, stale-while-revalidate=604800 |
| API responses | private, max-age=0, must-revalidate |

## Framework-Specific Quick Fixes

### Next.js
- LCP: Use next/image with priority prop
- INP: Use dynamic imports with next/dynamic
- CLS: Image component handles dimensions automatically

### React
- LCP: Preload hero images in head
- INP: React.memo, useTransition for heavy renders
- CLS: Always specify width/height on img

### Vue/Nuxt
- LCP: Use nuxt/image with preload
- INP: Use async components
- CLS: Use aspect-ratio CSS on images

### Svelte/SvelteKit
- Near-zero JS overhead by default
- Use loading="lazy" on below-fold images

### Astro
- Partial hydration (client:* directives)
- Zero JS by default on static pages
- Image component for automatic optimization

## Runtime Performance
- Batch DOM reads, then batch writes (avoid layout thrashing)
- Use requestAnimationFrame for visual updates
- Use transform + opacity for animations (not layout properties)
- AbortController for cleanup of event listeners
- Event delegation over per-element handlers

## Security & Best Practices (from web-quality-skills)
- HTTPS everywhere, no mixed content
- HSTS: max-age=31536000; includeSubDomains; preload
- CSP with nonces for inline scripts
- X-Frame-Options: DENY
- X-Content-Type-Options: nosniff
- Referrer-Policy: strict-origin-when-cross-origin
- Permissions-Policy: geolocation=(), microphone=(), camera=()
- No document.write, no sync XHR, no eval()
- Passive event listeners for scroll/touch
- npm audit regularly for vulnerable dependencies
- Error boundaries (React) + global error handlers
- No source maps in production (use hidden-source-map for error tracking)
- Semantic HTML5 elements (header, nav, main, article, section, footer)
