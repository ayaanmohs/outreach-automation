# Product Context: FetchUp

## The Mission
To stop "Silent Monetization Leakage" for content creators. FetchUp ensures every affiliate link in every video description is alive and healthy.

## The "Stealth MVP" Philosophy
- **Minimalist**: Focused on one core action—scanning links.
- **High UX**: Modern, dark theme, mobile-responsive, and extremely fast.
- **Reliable**: Uses official APIs to avoid bot detection.

## Technical Architecture
- **Backend**: Node.js / Express server.
- **Frontend**: Multi-page HTML (using Tailwind CSS for styling).
- **Core Logic**: `public/app.js` (Client-side batching and UI) and `server.js` (Backend API handling).
- **Data Source**: Official Google YouTube Data API v3.
- **Analytics**: PostHog (Event tracking + Session replay) + Google Analytics 4 (Traffic backup).
- **Deployment**: GitHub -> Koyeb (Auto-deploy on push to main).

## Current Feature Set
1. **Single Video Audit**: Full description scan for 404s and affiliate parameter loss.
2. **Channel Audit (WIP)**: Scanning the last 10 uploads for a creator handle.
3. **Usage Limit**: 3-scan limit for free users (tracked via `localStorage`).
4. **Revenue Leak Card**: Calculator that estimates lost income based on view counts.
5. **Monetization**: Whop integration ($15/mo Pro plan).
