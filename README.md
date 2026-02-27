# NameVetter

An interactive tool for ideating and vetting company names. Generate brandable name suggestions from a company description, then check each name across domains, social media, government databases, and similar existing names.

## Features

- **Name Generation** -- 6 algorithmic strategies produce diverse, brandable names from your keywords, industry, and desired tone
- **Document Context** -- Upload markdown docs describing your company vision. Names get scored on alignment (keyword match, thematic echo, tone, uniqueness)
- **Domain Availability** -- Real checks across .com, .co, .io, .net, .org, .ai via RDAP, WHOIS, and DNS. Links to registrars for purchase
- **Social Media Handles** -- Automated availability checks on Instagram, TikTok, YouTube, X (Twitter), Facebook, LinkedIn, and Threads
- **Government Registration** -- Direct links to USPTO trademark search, state Secretary of State databases, and OpenCorporates
- **Similar Names** -- Levenshtein distance analysis flags close matches among registered domains
- **Favorites & Export** -- Star names you like, compare them side by side, export to CSV

## How It Works

The React frontend generates names and displays results. The Python backend handles the actual availability checks (domain lookups via RDAP/WHOIS/DNS, social media profile checks via HTTP). Without the backend running, the app still works in limited mode with manual check links.

**Status indicators:**
- Green checkmark = available
- Red X = taken
- Yellow ? = needs manual verification

## Quick Start

### 1. Start the backend

```bash
cd backend
pip install -r requirements.txt
python server.py
```

The server runs on `http://localhost:5111`.

### 2. Open the frontend

Open `frontend/index.html` in your browser. The app auto-detects whether the backend is running and adjusts accordingly.

For a dev server setup, you can also serve the frontend folder with any static file server:

```bash
cd frontend
npx serve .
```

## Project Structure

```
namevetter/
  backend/
    server.py           # Flask API server (domain + social checks)
    requirements.txt    # Python dependencies
  frontend/
    name-vetter.jsx     # React app (single-file, all UI + logic)
    index.html          # HTML shell to load the React app
  README.md
  .gitignore
```

## Backend API

| Endpoint | Method | Body | Description |
|---|---|---|---|
| `/api/check` | POST | `{"name": "MyCompany"}` | Full vetting: domains, social, similar names |
| `/api/check-domain` | POST | `{"domain": "example.com"}` | Single domain check |
| `/api/check-social` | POST | `{"platform": "Instagram", "handle": "myco"}` | Single platform check |
| `/api/health` | GET | -- | Server status |

## Deployment

The backend is a standard Flask app. Deploy it anywhere Python runs (Railway, Render, Fly.io, a VPS, etc.). Update the `BACKEND_URL` in the React app to point to your deployed backend URL instead of `localhost:5111`.

The frontend is static files. Host on GitHub Pages, Netlify, Vercel, or serve from the same server as the backend.

## Tech Stack

- **Frontend:** React 18, Tailwind CSS, Babel (in-browser JSX transform)
- **Backend:** Python 3, Flask, flask-cors, python-whois, requests
- **APIs:** RDAP (domain registry), domainsdb.info (similar domains), OpenCorporates (business names)
