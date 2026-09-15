# FrameByFrame

**How well do you actually know the things you watch and listen to?**

FrameByFrame is a collection of fast, visual guessing games built around movies, animation, music, and pop culture.

Instead of traditional trivia questions, each game tests recognition in a different way — cryptic descriptions, distorted artwork, visual clues, and progressively easier hints.

Currently featuring **Albumnesia** and **Badly Explained**.

---

## Games

### Albumnesia

Think you know an album just by looking at it?

Albumnesia takes recognizable album covers and removes or alters important visual information. Your job is to figure out the album before too much is revealed.

#### Daily Album

A new album challenge to solve.

Identify the album using the altered artwork and try to get it with as little help as possible.

#### Battle of the Bands

Put your music knowledge to the test across multiple albums and artists.

---

### Badly Explained

Movies explained terribly.

You're given increasingly useful clues about a single animated movie across **5 rounds**.

**Round 1 →** Extremely vague clue  
**Round 2 →** Another clue  
**Round 3 →** Things start becoming recognizable  
**Round 4 →** Strong final textual hint  
**Round 5 →** Image from the movie

You have **10 seconds per round** to make your guess.

Guess correctly as early as possible — the number of rounds it takes is your result.

---

## How It Works

FrameByFrame is designed around short game sessions.

1. Pick a game mode.
2. Receive a distorted image, strange description, or visual clue.
3. Enter your guess.
4. Get additional information when you're stuck.
5. Reveal the answer and see how well you did.
6. Try another challenge.

No 40-question trivia quizzes.

Just one question:

**Do you recognize it?**

---

## Tech Stack

### Frontend

- React / JavaScript
- HTML
- CSS
- Responsive web interface
- Vercel

### Backend

- REST API
- Render
- Server-side game logic

### Database

- PostgreSQL
- Render PostgreSQL

### Infrastructure

```text
                    Player
                       │
                       ▼
                  Vercel CDN
                       │
                       ▼
              FrameByFrame Frontend
                       │
                    HTTPS
                       │
                       ▼
                 Render API
                       │
                       ▼
              Render PostgreSQL
```

---

## Project Structure

```text
FrameByFrame
│
├── frontend
│   ├── components
│   ├── pages
│   ├── assets
│   └── game UI
│
├── backend
│   ├── API routes
│   ├── game logic
│   └── database access
│
└── database
    ├── albums
    ├── movies
    ├── hints
    └── game data
```

---

## Running Locally

Clone the repository:

```bash
git clone <repository-url>
cd framebyframe
```

Install dependencies:

```bash
npm install
```

Create the required environment variables:

```env
DATABASE_URL=your_database_url
```

Add any additional environment variables required by the frontend/backend.

Start the development server:

```bash
npm run dev
```

---

## Production Deployment

FrameByFrame currently uses:

```text
Frontend       → Vercel
Backend/API    → Render
Database       → Render PostgreSQL
```

Production deployments are connected to the GitHub repository, allowing new versions to be deployed after changes are pushed to the production branch.

---

## What's Next?

FrameByFrame is being built as a growing collection of recognition-based games.

Planned ideas include:

- More Albumnesia challenges
- Larger animated movie collection
- Additional movie guessing modes
- New music-based games
- Daily challenges
- Player statistics
- Streaks
- Leaderboards
- Shareable results
- More categories and difficulty levels

---

## Design Philosophy

FrameByFrame isn't meant to feel like another generic trivia website.

The interface uses a playful, hand-drawn visual language inspired by notebooks, doodles, posters, album artwork, and movie culture.

Every game mode is intended to have its own personality while still feeling like part of the same world.

---

## Status

**Public Beta**

Two game modes are currently playable:

`Albumnesia`  
`Badly Explained`

More experiments are coming.

---

## Author

Built by **Ashish Choudhary**

If you somehow guessed everything on Round 1, you either have incredible taste or spend far too much time on the internet.