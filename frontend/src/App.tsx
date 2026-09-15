import { FormEvent, useEffect, useMemo, useRef, useState } from 'react'
import { ApiError, gameApi, preloadImage } from './api'
import { runGlimpseSequence, waitUntil } from './timing'
import { centsToScore, formatScore, SCORE_SCALE, scoreToCents } from './score'
import type { Category, GameResult, GameState, Glimpse, Hint } from './types'
import { AlbumnesiaApp } from './Albumnesia'
import { BadlyExplainedApp } from './BadlyExplained'

const ALL_CATEGORIES: Category[] = [
  { slug: 'anime', name: 'Anime' },
  { slug: 'superheroes', name: 'Superheroes' },
  { slug: 'disney-pixar', name: 'Disney & Pixar' },
  { slug: 'all-time-greats', name: 'All-Time Greats' },
]

function message(error: unknown): string {
  return error instanceof Error ? error.message : 'Something went wrong. Please try again.'
}

function Home({ onPlay }: { onPlay: (category: Category) => void }) {
  const [available, setAvailable] = useState<Set<string>>(new Set())
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    gameApi.categories()
      .then(categories => setAvailable(new Set(categories.map(category => category.slug))))
      .catch(reason => setError(message(reason)))
      .finally(() => setLoading(false))
  }, [])

  return <main className="home-shell">
    <header className="hero">
      <p className="eyebrow">The daily movie-frame game</p>
      <h1 className="wordmark">Frame<span>By</span>Frame</h1>
      <p className="tagline">How much of a movie do you need?</p>
    </header>
    <section className="category-grid" aria-labelledby="categories-heading">
      <h2 id="categories-heading" className="sr-only">Choose a category</h2>
      {ALL_CATEGORIES.map(category => {
        const playable = available.has(category.slug)
        return <button
          key={category.slug}
          className="category-card"
          disabled={!playable || loading}
          onClick={() => onPlay(category)}
          aria-describedby={`${category.slug}-status`}
        >
          <span>{category.name}</span>
          <small id={`${category.slug}-status`}>{loading ? 'Checking today’s puzzle…' : playable ? 'Play today’s frame' : 'Coming soon'}</small>
        </button>
      })}
    </section>
    <a className="album-entry-link" href="/albumnesia">Play Albumnesia · the five-cover memory game →</a>
    {error && <p className="notice error" role="alert">Could not check today’s categories. {error}</p>}
  </main>
}

function RevealImage({ source, glimpse, visible }: { source: string; glimpse: Glimpse | null; visible: boolean }) {
  const imageRef = useRef<HTMLImageElement>(null)
  const [clip, setClip] = useState('none')

  useEffect(() => {
    const image = imageRef.current
    if (!image || !glimpse || glimpse.show_full_image) {
      setClip('none')
      return
    }
    const measure = () => {
      const radius = Math.min(image.clientWidth, image.clientHeight) * Number(glimpse.radius_percent) / 100
      setClip(`circle(${radius}px at ${glimpse.reveal_x}% ${glimpse.reveal_y}%)`)
    }
    measure()
    const observer = new ResizeObserver(measure)
    observer.observe(image)
    return () => observer.disconnect()
  }, [glimpse, source])

  return <div className={`reveal-frame ${visible ? 'is-visible' : 'is-hidden'}`} aria-hidden={!visible}>
    <img ref={imageRef} src={source} style={{ clipPath: clip }} alt="Today’s movie frame glimpse" draggable={false} />
  </div>
}

function HintPanel({ game, cryptic, pattern, disabled, onUnlock }: {
  game: GameState
  cryptic: Hint | null
  pattern: Hint | null
  disabled: boolean
  onUnlock: (kind: 'cryptic' | 'title-pattern') => void
}) {
  return <section className="hint-panel" aria-labelledby="hints-heading">
    <h2 id="hints-heading">Hints</h2>
    {!game.hints_available && <p>Hints unlock after Round 2.</p>}
    <button
      disabled={disabled || game.cryptic_hint_state === 'locked' || game.cryptic_hint_state === 'used'}
      onClick={() => onUnlock('cryptic')}
    >
      {game.cryptic_hint_state === 'used' ? 'Cryptic clue unlocked' : `Unlock cryptic clue · −${formatScore(game.cryptic_hint_penalty)}`}
      <span className="control-state">{game.cryptic_hint_state}</span>
    </button>
    {cryptic && <p className="unlocked-hint"><strong>Cryptic clue:</strong> {cryptic.value}</p>}
    <button
      disabled={disabled || game.title_pattern_hint_state !== 'available'}
      onClick={() => onUnlock('title-pattern')}
    >
      {game.title_pattern_hint_state === 'used' ? 'Title pattern unlocked' : `Unlock title pattern · −${formatScore(game.title_pattern_hint_penalty)}`}
      <span className="control-state">{game.title_pattern_hint_state}</span>
    </button>
    {pattern && <p className="unlocked-hint"><strong>Title pattern:</strong> <span className="pattern">{pattern.value}</span></p>}
  </section>
}

function ResultScreen({ result, category, onBack }: { result: GameResult; category: Category; onBack: () => void }) {
  const [shareStatus, setShareStatus] = useState('')
  const hintSymbols = `${result.cryptic_hint_used ? '💡' : '🔒'}${result.title_pattern_used ? '🔤' : '🔒'}`
  const share = async () => {
    const solved = result.status === 'won' ? `${result.solved_round}/5` : 'Not solved'
    await navigator.clipboard.writeText(`FrameByFrame — ${category.name}\nSolved: ${solved}\nScore: ${formatScore(result.final_score)} / ${SCORE_SCALE}\nHints: ${hintSymbols}`)
    setShareStatus('Result copied without the movie title.')
  }
  return <main className="game-shell result-screen">
    <p className="eyebrow">Today’s result · {category.name}</p>
    <h1>{result.status === 'won' ? 'You got it.' : 'That was a tough one.'}</h1>
    <img className="result-image" src={result.full_image_url} alt={`Full frame from ${result.canonical_movie_title}`} draggable={false} />
    <h2>{result.canonical_movie_title}</h2>
    <dl className="result-stats">
      <div><dt>Outcome</dt><dd>{result.status === 'won' ? 'Won' : 'Lost'}</dd></div>
      <div><dt>Solved</dt><dd>{result.solved_round ? `Frame ${result.solved_round} of 5` : 'Not solved'}</dd></div>
      <div><dt>Score</dt><dd>{formatScore(result.final_score)} / {SCORE_SCALE}</dd></div>
      <div><dt>Guessing time</dt><dd>{(result.active_guess_ms / 1000).toFixed(1)}s</dd></div>
      <div><dt>Wrong guesses</dt><dd>{result.wrong_guesses.length}</dd></div>
      <div><dt>Hints used</dt><dd>{Number(result.cryptic_hint_used) + Number(result.title_pattern_used)}</dd></div>
    </dl>
    <section className="wrong-list" aria-labelledby="penalty-heading">
      <h3 id="penalty-heading">Penalty breakdown</h3>
      <ul>
        <li>Wrong guesses: −{formatScore(result.wrong_guesses.reduce((total, guess) => total + Number(guess.applied_wrong_guess_penalty), 0))}</li>
        <li>Active guessing time: −{formatScore(result.time_penalty)}</li>
        <li>Hints: −{formatScore(result.total_hint_penalty)}</li>
      </ul>
    </section>
    {result.wrong_guesses.length > 0 && <section className="wrong-list">
      <h3>Wrong guesses</h3>
      <ul>{result.wrong_guesses.map(guess => <li key={guess.round_number}>Frame {guess.round_number}: {guess.submitted_title} (−{formatScore(guess.applied_wrong_guess_penalty)})</li>)}</ul>
    </section>}
    {result.message && <p className="curated-message">{result.message}</p>}
    <div className="result-actions">
      <button onClick={share}>Share spoiler-free result</button>
      <button className="primary" onClick={onBack}>Back to categories</button>
    </div>
    <p className="notice" role="status">{shareStatus}</p>
  </main>
}

function GameScreen({ initial, category, onBack }: { initial: GameState; category: Category; onBack: () => void }) {
  const [game, setGame] = useState(initial)
  const [result, setResult] = useState<GameResult | null>(null)
  const [imageSource, setImageSource] = useState('')
  const [glimpse, setGlimpse] = useState<Glimpse | null>(null)
  const [countdown, setCountdown] = useState<number | null>(null)
  const [visible, setVisible] = useState(false)
  const [canGuess, setCanGuess] = useState(false)
  const [guess, setGuess] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [feedback, setFeedback] = useState('')
  const [error, setError] = useState('')
  const [cryptic, setCryptic] = useState<Hint | null>(null)
  const [pattern, setPattern] = useState<Hint | null>(null)
  const [hintLoading, setHintLoading] = useState(false)
  const [scoreEstimateCents, setScoreEstimateCents] = useState(scoreToCents(initial.score_estimate))

  useEffect(() => setScoreEstimateCents(scoreToCents(game.score_estimate)), [game.score_estimate])
  useEffect(() => {
    if (!canGuess || submitting) return
    const penaltyCents = scoreToCents(game.time_penalty_per_second)
    const timer = window.setInterval(() => setScoreEstimateCents(value => Math.max(0, value - penaltyCents)), 1000)
    return () => window.clearInterval(timer)
  }, [canGuess, submitting, game.time_penalty_per_second])

  useEffect(() => {
    if (game.status !== 'playing') {
      gameApi.result(game.session_id).then(setResult).catch(reason => setError(message(reason)))
    }
  }, [game.session_id, game.status])

  useEffect(() => {
    if (game.status !== 'playing') return
    if (game.cryptic_hint_state === 'used' && !cryptic) gameApi.crypticHint(game.session_id).then(setCryptic).catch(() => undefined)
    if (game.title_pattern_hint_state === 'used' && !pattern) gameApi.titlePatternHint(game.session_id).then(setPattern).catch(() => undefined)
  }, [game, cryptic, pattern])

  useEffect(() => {
    if (game.status !== 'playing') return
    const controller = new AbortController()
    let objectUrl = ''
    let active = true

    async function prepare() {
      setCanGuess(false)
      setVisible(false)
      setCountdown(null)
      setGlimpse(null)
      setError('')
      try {
        objectUrl = await preloadImage(game.image_url, controller.signal)
        if (!active) return
        setImageSource(objectUrl)
        if (game.glimpse_consumed) {
          setFeedback(current => current || 'This glimpse was already consumed. It will not be replayed; you can continue with your guess.')
          await waitUntil(game.guess_available_at)
          if (active) setCanGuess(true)
          return
        }
        const current = await gameApi.glimpse(game.session_id)
        if (!active) return
        setGlimpse(current)
        const availableAt = new Date(Date.now() + current.countdown_ms + current.duration_ms).toISOString()
        const sequence = await runGlimpseSequence({
          countdownMs: current.countdown_ms,
          durationMs: current.duration_ms,
          signal: controller.signal,
          onCountdown: setCountdown,
          onVisible: setVisible,
        })
        if (!active || sequence === 'cancelled') return
        if (sequence === 'interrupted') {
          setFeedback('The tab became hidden, so the glimpse was cancelled and cannot be replayed. Continue with your best guess.')
        }
        await waitUntil(availableAt)
        if (active) setCanGuess(true)
      } catch (reason) {
        if (!active) return
        if (reason instanceof ApiError && reason.status === 409) {
          const refreshed = await gameApi.state(game.session_id)
          setGame(refreshed)
          setFeedback(current => current || 'This glimpse was already consumed. It will not be replayed; continue with your guess.')
          await waitUntil(refreshed.guess_available_at)
          if (active) setCanGuess(true)
        } else {
          setError(message(reason))
        }
      }
    }
    void prepare()
    return () => {
      active = false
      controller.abort()
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [game.session_id, game.current_round, game.status])

  const submitGuess = async (event: FormEvent) => {
    event.preventDefault()
    if (!canGuess || submitting || !guess.trim()) return
    setSubmitting(true)
    setError('')
    try {
      const outcome = await gameApi.guess(game.session_id, guess.trim())
      setGuess('')
      setCanGuess(false)
      if (outcome.result) setResult(outcome.result)
      if (outcome.state) {
        setFeedback(`Incorrect — moving to Frame ${outcome.state.current_round} of 5.`)
        setGame(outcome.state)
      }
    } catch (reason) {
      setError(message(reason))
    } finally {
      setSubmitting(false)
    }
  }

  const unlock = async (kind: 'cryptic' | 'title-pattern') => {
    const cost = kind === 'cryptic' ? game.cryptic_hint_penalty : game.title_pattern_hint_penalty
    if (!window.confirm(`Unlock this hint for ${formatScore(cost)} points?`)) return
    setHintLoading(true)
    setError('')
    try {
      const hint = kind === 'cryptic' ? await gameApi.crypticHint(game.session_id) : await gameApi.titlePatternHint(game.session_id)
      if (kind === 'cryptic') setCryptic(hint); else setPattern(hint)
      setGame(await gameApi.state(game.session_id))
    } catch (reason) {
      setError(message(reason))
    } finally {
      setHintLoading(false)
    }
  }

  if (result) return <ResultScreen result={result} category={category} onBack={onBack} />

  return <main className="game-shell">
    <header className="game-header">
      <button className="text-button" onClick={onBack}>← Categories</button>
      <span className="mini-wordmark">FrameByFrame</span>
      <span className="score" aria-label={`Current score estimate ${centsToScore(scoreEstimateCents)} out of ${SCORE_SCALE}`}>Estimate {centsToScore(scoreEstimateCents)} / {SCORE_SCALE}</span>
    </header>
    <section className="play-area">
      <p className="eyebrow">{category.name}</p>
      <h1>Frame {game.current_round} of {game.maximum_rounds}</h1>
      <div className="stage" aria-live="assertive">
        {imageSource && <RevealImage source={imageSource} glimpse={glimpse} visible={visible} />}
        {!visible && <div className="stage-cover">
          {countdown !== null ? <span className="countdown" aria-label={`Glimpse in ${countdown}`}>{countdown}</span> :
            <span>{canGuess ? 'Glimpse complete' : imageSource ? 'Get ready…' : 'Loading and decoding frame…'}</span>}
        </div>}
      </div>
      <p className="notice" role="status">{feedback}</p>
      {error && <p className="notice error" role="alert">{error}</p>}
      <form className="guess-form" onSubmit={submitGuess}>
        <label htmlFor="movie-title">Movie title</label>
        <div>
          <input id="movie-title" value={guess} onChange={event => setGuess(event.target.value)} disabled={!canGuess || submitting} autoComplete="off" placeholder={canGuess ? 'Enter the complete title' : 'Available after the glimpse'} />
          <button className="primary" disabled={!canGuess || submitting || !guess.trim()}>{submitting ? 'Checking…' : 'Submit guess'}</button>
        </div>
      </form>
    </section>
    <HintPanel game={game} cryptic={cryptic} pattern={pattern} disabled={hintLoading || submitting} onUnlock={unlock} />
  </main>
}

function MovieApp() {
  const initialSlug = useMemo(() => window.location.pathname.match(/^\/game\/([^/]+)$/)?.[1] || null, [])
  const [route, setRoute] = useState<string | null>(initialSlug)
  const [game, setGame] = useState<GameState | null>(null)
  const [loading, setLoading] = useState(Boolean(initialSlug))
  const [error, setError] = useState('')

  const navigate = (slug: string | null) => {
    window.history.pushState({}, '', slug ? `/game/${slug}` : '/')
    setRoute(slug)
    setGame(null)
    setError('')
  }

  useEffect(() => {
    const pop = () => { setRoute(window.location.pathname.match(/^\/game\/([^/]+)$/)?.[1] || null); setGame(null) }
    window.addEventListener('popstate', pop)
    return () => window.removeEventListener('popstate', pop)
  }, [])

  useEffect(() => {
    if (!route) return
    setLoading(true)
    gameApi.start(route).then(setGame).catch(reason => setError(message(reason))).finally(() => setLoading(false))
  }, [route])

  if (!route) return <Home onPlay={category => navigate(category.slug)} />
  const category = ALL_CATEGORIES.find(item => item.slug === route) || { slug: route, name: route }
  if (loading) return <main className="centered" aria-live="polite">Starting today’s game…</main>
  if (error || !game) return <main className="centered"><p role="alert">{error || 'Unable to start this game.'}</p><button onClick={() => navigate(null)}>Back to categories</button></main>
  return <GameScreen initial={game} category={category} onBack={() => navigate(null)} />
}

export function App() {
  const [path, setPath] = useState(window.location.pathname)
  const navigate = (next: string) => { window.history.pushState({}, '', next); setPath(next) }
  useEffect(() => { const pop = () => setPath(window.location.pathname); window.addEventListener('popstate', pop); return () => window.removeEventListener('popstate', pop) }, [])
  if (path.startsWith('/albumnesia')) return <AlbumnesiaApp path={path} navigate={navigate}/>
  if (path.startsWith('/badly-explained')) return <BadlyExplainedApp path={path} navigate={navigate}/>
  return <MovieApp/>
}
