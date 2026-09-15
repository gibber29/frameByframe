import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AlbumnesiaApp } from './Albumnesia'
import { albumnesiaApi, preloadImage } from './api'
import type { AlbumAttempt } from './types'

vi.mock('./api', () => ({
  preloadImage: vi.fn(),
  albumnesiaApi: {
    home: vi.fn(), startDaily: vi.fn(), titles: vi.fn(), createRoom: vi.fn(),
    room: vi.fn(), joinRoom: vi.fn(), leaderboard: vi.fn(), state: vi.fn(),
    continueRoom: vi.fn(), ready: vi.fn(), submit: vi.fn(),
  },
}))

const attempt = (changes: Partial<AlbumAttempt> = {}): AlbumAttempt => ({
  attempt_id: '10000000-0000-0000-0000-000000000001', mode: 'daily', room_code: null,
  status: 'playing', phase: 'ready', round_number: 1, total_rounds: 5,
  phase_deadline: null, server_time: new Date().toISOString(), image_url: '/private-cover',
  distortion: 'pixel_hangover', distortion_seed: 42, text_mask_regions: [], subject_mask_regions: [],
  clues: null, revealed_title: null, revealed_artist: null, last_correct: null, last_score: null,
  correct_count: 0, total_score: '0.00', max_score: '50.00', legacy_score:false, streak: 0, results: null,
  ...changes,
})

beforeEach(() => {
  vi.clearAllMocks(); localStorage.clear()
  class TestImage {
    naturalWidth = 100; naturalHeight = 100; onload: (() => void) | null = null; onerror: (() => void) | null = null
    set src(_value: string) { queueMicrotask(() => this.onload?.()) }
  }
  vi.stubGlobal('Image', TestImage)
  const context = { drawImage:vi.fn(), clearRect:vi.fn(), fillRect:vi.fn(), beginPath:vi.fn(), rect:vi.fn(), lineTo:vi.fn(), moveTo:vi.fn(), closePath:vi.fn(), clip:vi.fn(), save:vi.fn(), restore:vi.fn(), stroke:vi.fn(), imageSmoothingEnabled:true, fillStyle:'', strokeStyle:'', lineWidth:1 }
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(context as unknown as CanvasRenderingContext2D)
  vi.spyOn(HTMLCanvasElement.prototype, 'toDataURL').mockReturnValue('data:image/webp;base64,processed')
  vi.mocked(albumnesiaApi.home).mockResolvedValue({ daily_date:'2026-09-14', active_album_count:5, daily_available:true, streak:3, completed_today:false })
  vi.mocked(albumnesiaApi.startDaily).mockResolvedValue(attempt())
  vi.mocked(albumnesiaApi.titles).mockResolvedValue(['Blue Train', 'Kind of Blue'])
  vi.mocked(preloadImage).mockResolvedValue('blob:decoded')
})

describe('Albumnesia player', () => {
  it('copies results without opening native sharing even when available', async () => {
    const nativeShare=vi.fn().mockResolvedValue(undefined)
    const writeText=vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator,'clipboard',{value:{writeText},configurable:true})
    Object.defineProperty(navigator,'share',{value:nativeShare,configurable:true})
    vi.mocked(albumnesiaApi.state).mockResolvedValue(attempt({
      status:'completed',phase:'results',total_rounds:1,correct_count:1,
      total_score:'6.40',max_score:'10.00',results:[],
    }))
    render(<AlbumnesiaApp path="/albumnesia/play/10000000-0000-0000-0000-000000000001" navigate={vi.fn()}/>)
    await userEvent.click(await screen.findByRole('button',{name:'SHARE RESULT'}))
    expect(writeText).toHaveBeenCalledWith(expect.stringContaining('6.40 / 10.00'))
    expect(nativeShare).not.toHaveBeenCalled()
    expect(await screen.findByRole('status')).toHaveTextContent('Copied successfully.')
  })
  it('estimates two points per remaining second without an eight-point floor', async () => {
    const now = Date.now()
    const clock = vi.spyOn(Date, 'now').mockReturnValue(now)
    try {
      vi.mocked(albumnesiaApi.state).mockResolvedValue(attempt({
        phase:'guess', image_url:null, server_time:new Date(now).toISOString(),
        phase_deadline:new Date(now+3200).toISOString(),
      }))
      render(<AlbumnesiaApp path="/albumnesia/play/10000000-0000-0000-0000-000000000001" navigate={vi.fn()}/>)
      expect(await screen.findByText('Correct now: 6.40 points')).toBeVisible()
      expect(screen.getByText(/Lose 2.00 points per guessing second/)).toBeVisible()
      expect(screen.queryByText(/at least eight points/)).not.toBeInTheDocument()
    } finally { clock.mockRestore() }
  })
  it('provides game switching through the responsive navigation', async () => {
    const navigate = vi.fn()
    render(<AlbumnesiaApp path="/albumnesia" navigate={navigate}/>)
    const links = document.querySelector('.album-nav .game-nav-links')
    expect(links).toHaveTextContent('BADLY EXPLAINED')
    expect(links).toHaveTextContent('ALBUMNESIA')
    expect(screen.getByRole('button', {name:'ALBUMNESIA'})).toHaveAttribute('aria-current', 'page')
    await userEvent.click(screen.getByRole('button', {name:'BADLY EXPLAINED'}))
    expect(navigate).toHaveBeenCalledWith('/badly-explained')
  })
  it('starts the deterministic daily from the reference-style landing page', async () => {
    const navigate = vi.fn(); render(<AlbumnesiaApp path="/albumnesia" navigate={navigate}/>)
    expect(await screen.findByText(/3 DAY STREAK/)).toBeVisible()
    expect(screen.queryByRole('button', { name:'SUPERHEROES' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name:'ANIMATION' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name:'Sound control' })).toBeVisible()
    expect(screen.getByRole('button', { name:'Profile' })).toBeVisible()
    expect(document.querySelector('.album-side-copy.left.upper')).toHaveTextContent('GOOD')
    await userEvent.click(screen.getByRole('button', { name: /PLAY TODAY/ }))
    expect(albumnesiaApi.startDaily).toHaveBeenCalledTimes(1)
    expect(navigate).toHaveBeenCalledWith('/albumnesia/play/10000000-0000-0000-0000-000000000001')
  })

  it('renders a daily game as one album on a ten-point scale', async () => {
    vi.mocked(albumnesiaApi.state).mockResolvedValue(attempt({ total_rounds:1, max_score:'10.00' }))
    render(<AlbumnesiaApp path="/albumnesia/play/10000000-0000-0000-0000-000000000001" navigate={vi.fn()}/>)
    expect(await screen.findByText('ROUND 01 / 01')).toBeVisible()
    expect(screen.getByText('MAX SCORE 10.00')).toBeVisible()
  })

  it('creates an asynchronous room and stores the display name', async () => {
    vi.mocked(albumnesiaApi.createRoom).mockResolvedValue({ code:'JAZZ234', name:'Friday', host_name:'Ada', status:'open', expires_at:new Date().toISOString(), participant_count:1, joined:true, current_player_name:'Ada', attempt_id:null })
    const navigate = vi.fn(); render(<AlbumnesiaApp path="/albumnesia" navigate={navigate}/>)
    await userEvent.click(screen.getByRole('button', { name: /CREATE A ROOM/ }))
    expect(document.querySelector('.album-landing')).toHaveClass('is-expanded')
    await userEvent.type(screen.getByLabelText('Player name'), 'Ada')
    const room = screen.getByLabelText('Lobby name'); await userEvent.clear(room); await userEvent.type(room, 'Friday')
    await userEvent.click(screen.getByRole('button', { name: 'CREATE ROOM' }))
    expect(albumnesiaApi.createRoom).toHaveBeenCalledWith('Friday', 'Ada')
    expect(navigate).toHaveBeenCalledWith('/albumnesia/room/JAZZ234')
  })

  it('decodes the private cover before telling the server a round is ready', async () => {
    vi.mocked(albumnesiaApi.state).mockResolvedValue(attempt())
    vi.mocked(albumnesiaApi.ready).mockResolvedValue(attempt({ phase:'guess', image_url:null, distortion:null, distortion_seed:null, phase_deadline:new Date(Date.now()+5000).toISOString() }))
    render(<AlbumnesiaApp path="/albumnesia/play/10000000-0000-0000-0000-000000000001" navigate={vi.fn()}/>)
    await waitFor(() => expect(preloadImage).toHaveBeenCalledWith('/private-cover'))
    expect(albumnesiaApi.ready).not.toHaveBeenCalled()
    await userEvent.click(await screen.findByRole('button', { name:/DROP THE NEEDLE/ }))
    await waitFor(() => expect(albumnesiaApi.ready).toHaveBeenCalledTimes(1))
    expect(screen.getByRole('heading', { name:'WHAT WAS THE ALBUM?' })).toBeVisible()
  })

  it('asks once at room start then automatically begins later rounds after decoding', async () => {
    vi.mocked(albumnesiaApi.state).mockResolvedValue(attempt({ mode:'room', room_code:'JAZZ234' }))
    const first = render(<AlbumnesiaApp path="/albumnesia/play/10000000-0000-0000-0000-000000000001" navigate={vi.fn()}/>)
    expect(await screen.findByRole('button', { name:/DROP THE NEEDLE/ })).toBeVisible()
    expect(albumnesiaApi.ready).not.toHaveBeenCalled()
    first.unmount(); vi.clearAllMocks(); vi.mocked(preloadImage).mockResolvedValue('blob:decoded')

    vi.mocked(albumnesiaApi.state).mockResolvedValue(attempt({ mode:'room', room_code:'JAZZ234', round_number:2, image_url:'/private-cover-2' }))
    vi.mocked(albumnesiaApi.ready).mockResolvedValue(attempt({ mode:'room', room_code:'JAZZ234', phase:'memorize', round_number:2, image_url:'/private-cover-2', clues:{artist_initials:'JC',release_year:1957,recognizable_track:'Blue Train'} }))
    render(<AlbumnesiaApp path="/albumnesia/play/10000000-0000-0000-0000-000000000001" navigate={vi.fn()}/>)
    await waitFor(() => expect(preloadImage).toHaveBeenCalledWith('/private-cover-2'))
    await waitFor(() => expect(albumnesiaApi.ready).toHaveBeenCalledTimes(1))
    expect(screen.queryByRole('button', { name:/DROP THE NEEDLE/ })).not.toBeInTheDocument()
    expect(await screen.findByText('ALL YOUR CLUES')).toBeVisible()
  })

  it('offers title-only keyboard autocomplete and submits one answer', async () => {
    const guessing = attempt({ phase:'guess', image_url:null, distortion:null, distortion_seed:null, phase_deadline:new Date(Date.now()+5000).toISOString() })
    vi.mocked(albumnesiaApi.state).mockResolvedValue(guessing)
    vi.mocked(albumnesiaApi.submit).mockResolvedValue(attempt({ phase:'feedback', image_url:null, distortion:null, distortion_seed:null, revealed_title:'Blue Train', revealed_artist:'John Coltrane', last_correct:true, last_score:'9.25', phase_deadline:new Date(Date.now()+1500).toISOString() }))
    render(<AlbumnesiaApp path="/albumnesia/play/10000000-0000-0000-0000-000000000001" navigate={vi.fn()}/>)
    const input = await screen.findByLabelText('Album title'); await userEvent.click(input)
    expect(await screen.findByRole('button', { name:'Blue Train' })).toBeVisible()
    await userEvent.keyboard('{ArrowDown}{Enter}{Enter}')
    await waitFor(() => expect(albumnesiaApi.submit).toHaveBeenCalledWith(expect.any(String), 'Kind of Blue'))
    expect(await screen.findByRole('heading', { name:'Blue Train' })).toBeVisible()
  })

  it('keeps the host on the shareable room panel until Continue is clicked', async () => {
    const room = { code:'JAZZ234', name:'Weekend Vinyl Wars', host_name:'Ashish', status:'open', expires_at:new Date().toISOString(), participant_count:1, joined:true, current_player_name:'Ashish', attempt_id:null }
    vi.mocked(albumnesiaApi.room).mockResolvedValue(room)
    vi.mocked(albumnesiaApi.continueRoom).mockResolvedValue(attempt({mode:'room',room_code:'JAZZ234'}))
    const writeText=vi.fn().mockResolvedValue(undefined); Object.defineProperty(navigator,'clipboard',{configurable:true,value:{writeText}})
    const navigate=vi.fn(); render(<AlbumnesiaApp path="/albumnesia/room/JAZZ234" navigate={navigate}/>)
    expect(await screen.findByRole('heading',{name:'ROOM CREATED'})).toBeVisible()
    expect(albumnesiaApi.continueRoom).not.toHaveBeenCalled()
    await userEvent.click(screen.getByRole('button',{name:'COPY INVITE'}))
    expect(writeText).toHaveBeenCalledWith(`Join Ashish in Weekend Vinyl Wars to compete in Albumnesia!\n\n${window.location.origin}/albumnesia/room/JAZZ234`)
    expect(await screen.findByRole('button',{name:'INVITE COPIED'})).toBeVisible()
    await userEvent.click(screen.getByRole('button',{name:'CONTINUE TO GAME'}))
    expect(albumnesiaApi.continueRoom).toHaveBeenCalledWith('JAZZ234')
    expect(navigate).toHaveBeenCalledWith(expect.stringContaining('/albumnesia/play/'))
  })

  it('asks an invited player only for their name, then waits for Continue', async () => {
    const invited = { code:'JAZZ234', name:'Weekend Vinyl Wars', host_name:'Ashish', status:'open', expires_at:new Date().toISOString(), participant_count:1, joined:false, current_player_name:null, attempt_id:null }
    const joined = {...invited,participant_count:2,joined:true,current_player_name:'Maya'}
    vi.mocked(albumnesiaApi.room).mockResolvedValue(invited); vi.mocked(albumnesiaApi.joinRoom).mockResolvedValue(joined)
    vi.mocked(albumnesiaApi.continueRoom).mockResolvedValue(attempt({mode:'room',room_code:'JAZZ234'}))
    render(<AlbumnesiaApp path="/albumnesia/room/JAZZ234" navigate={vi.fn()}/>)
    expect(await screen.findByText('YOU’VE BEEN INVITED')).toBeVisible()
    expect(screen.getByText(/Join Ashish in Weekend Vinyl Wars/)).toBeVisible()
    await userEvent.type(screen.getByLabelText('Player name'),'Maya')
    await userEvent.click(screen.getByRole('button',{name:/JOIN LOBBY/}))
    expect(await screen.findByRole('heading',{name:/WELCOME, MAYA/i})).toBeVisible()
    expect(albumnesiaApi.continueRoom).not.toHaveBeenCalled()
    await userEvent.click(screen.getByRole('button',{name:'CONTINUE TO GAME'}))
    expect(albumnesiaApi.continueRoom).toHaveBeenCalledTimes(1)
  })
})
