# Decision Log: FetchUp History

## 2026-04-24: Unified Identity & Web Analytics Fix
- **Decision**: Re-enable PostHog automatic pageview capture and sync `distinct_id` between client and server.
- **Why**: Manual pageview capture was losing browser metadata, resulting in "0 pageviews" in PostHog dashboards. Hardcoded `distinctId: 'server'` was making all users look like one person.

## 2026-04-24: The "WWW-First" Domain Strategy
- **Decision**: Redirect `getfetchup.com` to `www.getfetchup.com` using a Permanent (301) redirect in Namecheap.
- **Why**: Standard DNS "Apex CNAME" issues made connecting the root domain to Koyeb unreliable. The `www` subdomain is a CNAME and works instantly.

## 2026-04-24: Analytics Backup
- **Decision**: Add Google Analytics (GA4) alongside PostHog.
- **Why**: PostHog is great for behavior, but GA4 provides a more robust, "standard" backup for traffic and acquisition tracking.

## 2026-04-24: Clean URL Infrastructure
- **Decision**: Serve `.html` files without extensions using Express `extensions` config and update all internal links.
- **Why**: Improves credibility and brand professionality (e.g., `/onboarding` vs `/onboarding.html`).
