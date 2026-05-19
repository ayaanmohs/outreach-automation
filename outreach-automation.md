# FetchUp Outreach Automation: The Lead Scraper

## Context: Why we are building this
FetchUp is a "Stealth MVP" designed to detect silent monetization leakage in YouTube descriptions (broken affiliate links, 404s, etc.). To grow the platform, we are currently using a high-intent manual outreach strategy.

### The Current Manual Process
1. **Search**: Find "Alternative" videos (e.g., "Obsidian alternatives").
2. **Filter**: Target creators with 10k–100k subscribers (the "Sweet Spot").
3. **Verify**: Manually check descriptions for affiliate links/revenue messages.
4. **Personalize**: Use AI (Gemini) to generate a customized comment/pitch based on their specific links.

To scale this "Manual Grind," we are building an automation system to handle the high-volume discovery phase.

---

## Module 1: The Lead Scraper (Data Source)
The goal of this module is to automate the "Hunting" phase—finding the right creators and extracting their data without manual searching.

### Technical Specifications
- **Tech Stack**: Python script utilizing the `google-api-python-client` (YouTube Data API v3).
- **Input**: A list of niche-specific keywords (e.g., "Productivity setup," "Obsidian workflow," "Tech alternatives").
- **Core Logic**:
    - Search YouTube for the provided keywords.
    - Filter results based on channel size (10k–100k subscribers).
    - Extract metadata from the most recent videos.
- **Output**: A `.csv` file containing:
    - **Video Title**
    - **Channel Name**
    - **Subscriber Count**
    - **Video Description** (Crucial for link analysis)
    - **Video URL**

### Implementation Strategy
- **Cadence**: Run once a week.
- **Volume Goal**: 100 high-quality leads per run.
- **Usage**: The resulting CSV serves as the input for the next phase (Link Analysis & AI Personalization).

---

## Strategic Vision
By automating the lead discovery, we move from "Search & Pitch" to "Verify & Pitch." This allows the founder to focus entirely on the creative part (refining the pitch and closing creators) while the "grind" of finding the videos is handled by the Scraper.
