import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { App } from './App'
import { gameApi, preloadImage } from './api'
import type { GameResult, GameState } from './types'

vi.mock('./api', async () => {
  class ApiError extends Error { constructor(public status: number, value: string) { super(value) } }
  return {
    ApiError,
    preloadImage: vi.fn(),
    albumnesiaApi: {
      home: vi.fn().mockResolvedValue({ daily_date:'2026-09-15', active_album_count:5, daily_available:true, streak:0, completed_today:false }),
    },
    gameApi: {
      categories: vi.fn(), start: vi.fn(), state: vi.fn(), glimpse: vi.fn(), guess: vi.fn(),
      crypticHint: vi.fn(), titlePatternHint: vi.fn(), result: vi.fn(),
    },
  }
})

const state = (overrides: Partial<GameState> = {}): GameState => ({
  session_id: '00000000-0000-0000-0000-000000000001',
  category: 'superheroes', status: 'playing', current_round: 1, maximum_rounds: 5,
  reveal_duration_ms: 200, reveal_radius_percent: '14.00', show_full_image: false,
  hints_available: false, cryptic_hint_state: 'locked', title_pattern_hint_state: 'locked',
  image_url: '/api/v1/game/session/image', glimpse_consumed: true,
  guess_available_at: new Date(0).toISOString(), score_estimate: '50.00', score_scale: '50.00',
  time_penalty_per_second: '0.05', cryptic_hint_penalty: '2.50', title_pattern_hint_penalty: '5.00',
  ...overrides,
})

const result: GameResult = {
  status: 'won', canonical_movie_title: 'Ant-Man', final_score: '36.80', raw_final_score: '36.80',
  raw_score_scale: '50.00', score_scale: '50.00', solved_round: 3,
  wrong_guesses: [{ round_number: 1, submitted_title: 'Iron Man', response_time_ms: 900,
    applied_wrong_guess_penalty: '3.00', raw_applied_wrong_guess_penalty: '3.00', hints_used_count: 0 }],
  active_guess_ms: 2300, cryptic_hint_used: true, title_pattern_used: false,
  total_hint_penalty: '2.50', time_penalty: '0.12', full_image_url: '/api/v1/game/session/image', message: 'Nicely spotted.',
}

beforeEach(() => {
  vi.clearAllMocks()
  window.history.replaceState({}, '', '/game/superheroes')
  vi.mocked(gameApi.categories).mockResolvedValue([{ slug: 'superheroes', name: 'Superheroes' }])
  vi.mocked(gameApi.start).mockResolvedValue(state())
  vi.mocked(preloadImage).mockResolvedValue('blob:decoded-frame')
  vi.mocked(gameApi.state).mockResolvedValue(state())
  vi.mocked(gameApi.result).mockResolvedValue(result)
  vi.spyOn(window, 'confirm').mockReturnValue(true)
})

describe('player application', () => {
  it('opens Albumnesia directly at the root instead of the old category page', async () => {
    window.history.replaceState({}, '', '/')
    render(<App />)
    expect(await screen.findByRole('heading', { name: 'HOW WILL YOU DROP THE NEEDLE?' })).toBeVisible()
    expect(screen.queryByText('The daily movie-frame game')).not.toBeInTheDocument()
    expect(screen.queryByText('Coming soon')).not.toBeInTheDocument()
    expect(gameApi.categories).not.toHaveBeenCalled()
  })

  it('starts a game, preloads its image, and enables guessing after a consumed glimpse', async () => {
    render(<App />)
    expect(await screen.findByRole('heading', { name: 'Frame 1 of 5' })).toBeVisible()
    await waitFor(() => expect(preloadImage).toHaveBeenCalledWith('/api/v1/game/session/image', expect.any(AbortSignal)))
    expect(await screen.findByLabelText('Movie title')).toBeEnabled()
    expect(document.body).not.toHaveTextContent('Ant-Man')
  })

  it('submits a guess once and advances after an incorrect answer', async () => {
    vi.mocked(gameApi.guess).mockResolvedValue({
      correct: false, applied_wrong_guess_penalty: '3.00', raw_applied_wrong_guess_penalty: '3.00',
      state: state({ current_round: 2, score_estimate: '47.00' }), result: null,
    })
    render(<App />)
    const input = await screen.findByLabelText('Movie title')
    await waitFor(() => expect(input).toBeEnabled())
    await userEvent.type(input, 'Wrong movie{enter}')
    expect(await screen.findByRole('heading', { name: 'Frame 2 of 5' })).toBeVisible()
    expect(screen.getByText(/Incorrect — moving to Frame 2/)).toBeVisible()
    expect(gameApi.guess).toHaveBeenCalledTimes(1)
  })

  it('prevents duplicate guess submission while a request is pending', async () => {
    let resolve!: (value: never) => void
    vi.mocked(gameApi.guess).mockReturnValue(new Promise(value => { resolve = value }) as never)
    render(<App />)
    const input = await screen.findByLabelText('Movie title')
    await waitFor(() => expect(input).toBeEnabled())
    await userEvent.type(input, 'Wrong movie')
    const submit = screen.getByRole('button', { name: 'Submit guess' })
    fireEvent.click(submit)
    fireEvent.click(submit)
    await waitFor(() => expect(gameApi.guess).toHaveBeenCalledTimes(1))
    resolve({ correct: false, applied_wrong_guess_penalty: '3.00', raw_applied_wrong_guess_penalty: '3.00', state: state({ current_round: 2 }), result: null } as never)
  })

  it('keeps hints locked through round two and unlocks them in backend order', async () => {
    vi.mocked(gameApi.start).mockResolvedValue(state({
      current_round: 3, hints_available: true,
      cryptic_hint_state: 'available', title_pattern_hint_state: 'locked', score_estimate: '44.00',
    }))
    vi.mocked(gameApi.crypticHint).mockResolvedValue({ kind: 'cryptic', value: 'A cryptic clue', penalty: '2.50', newly_unlocked: true })
    vi.mocked(gameApi.titlePatternHint).mockResolvedValue({ kind: 'title-pattern', value: '___-___', penalty: '5.00', newly_unlocked: true })
    vi.mocked(gameApi.state)
      .mockResolvedValueOnce(state({ current_round: 3, hints_available: true, cryptic_hint_state: 'used', title_pattern_hint_state: 'available', score_estimate: '41.50' }))
      .mockResolvedValueOnce(state({ current_round: 3, hints_available: true, cryptic_hint_state: 'used', title_pattern_hint_state: 'used', score_estimate: '36.50' }))
    render(<App />)
    expect(await screen.findByRole('button', { name: /title pattern/i })).toBeDisabled()
    await userEvent.click(screen.getByRole('button', { name: /Unlock cryptic clue/i }))
    expect(await screen.findByText(/A cryptic clue/)).toBeVisible()
    const titleButton = await screen.findByRole('button', { name: /Unlock title pattern/i })
    expect(titleButton).toBeEnabled()
    await userEvent.click(titleButton)
    expect(await screen.findByText('___-___')).toBeVisible()
    expect(window.confirm).toHaveBeenCalledTimes(2)
  })

  it('renders a resumed completed game and its full result', async () => {
    vi.mocked(gameApi.start).mockResolvedValue(state({ status: 'won', current_round: 3, score_estimate: '36.80' }))
    window.history.replaceState({}, '', '/game/superheroes')
    render(<App />)
    expect(await screen.findByRole('heading', { name: 'Ant-Man' })).toBeVisible()
    expect(screen.getByText('36.80 / 50.00')).toBeVisible()
    expect(screen.getByText('Nicely spotted.')).toBeVisible()
    expect(gameApi.result).toHaveBeenCalledTimes(1)
  })

  it('shares the normalized score with two decimal places and keeps outcome separate', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText } })
    vi.mocked(gameApi.start).mockResolvedValue(state({ status: 'won', score_estimate: '0.00' }))
    vi.mocked(gameApi.result).mockResolvedValue({ ...result, final_score: '0.00', status: 'won' })
    window.history.replaceState({}, '', '/game/superheroes')
    render(<App />)
    expect(await screen.findByText('Won')).toBeVisible()
    expect(screen.getByText('0.00 / 50.00')).toBeVisible()
    await userEvent.click(screen.getByRole('button', { name: /Share spoiler-free result/i }))
    expect(writeText).toHaveBeenCalledWith(expect.stringContaining('Score: 0.00 / 50.00'))
  })

  it('resumes through the backend cookie flow after refresh', async () => {
    window.history.replaceState({}, '', '/game/superheroes')
    const first = render(<App />)
    await screen.findByRole('heading', { name: 'Frame 1 of 5' })
    first.unmount()
    render(<App />)
    await screen.findByRole('heading', { name: 'Frame 1 of 5' })
    expect(gameApi.start).toHaveBeenCalledTimes(2)
    expect(localStorage.length).toBe(0)
  })
})
