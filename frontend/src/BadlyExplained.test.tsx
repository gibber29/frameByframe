import {render,screen,waitFor} from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import {beforeEach,expect,it,vi} from 'vitest'
import {BadlyExplainedApp} from './BadlyExplained'
import {badlyApi,preloadImage} from './api'
import type {BadlyState} from './types'
vi.mock('./api',()=>({preloadImage:vi.fn(),badlyApi:{home:vi.fn(),titles:vi.fn(),startDaily:vi.fn(),state:vi.fn(),ready:vi.fn(),submit:vi.fn(),createRoom:vi.fn(),room:vi.fn(),join:vi.fn(),continue:vi.fn(),board:vi.fn()}}))
const state=(x:Partial<BadlyState>={}):BadlyState=>({attempt_id:'10000000-0000-0000-0000-000000000001',mode:'daily',room_code:null,lobby_name:null,status:'playing',phase:'ready',round_number:1,deadline:null,server_time:new Date().toISOString(),current_hint:null,previous_hints:[],image_url:null,last_correct:null,streak:0,result:null,...x})
beforeEach(()=>{vi.clearAllMocks();vi.mocked(badlyApi.home).mockResolvedValue({daily_date:'2026-09-14',active_count:3,daily_available:true,streak:3,completed_today:false});vi.mocked(badlyApi.titles).mockResolvedValue(['Finding Nemo','Toy Story']);vi.mocked(preloadImage).mockResolvedValue('blob:image')})
it('renders the corrected one-movie homepage and starts daily play',async()=>{const go=vi.fn();vi.mocked(badlyApi.startDaily).mockResolvedValue(state());render(<BadlyExplainedApp path="/badly-explained" navigate={go}/>);expect(await screen.findByText('Four terrible explanations. One suspicious image. One animated movie. Somehow, this is your problem now.')).toBeVisible();expect(screen.queryByText(/BADLY GUESSED/)).not.toBeInTheDocument();await userEvent.click(screen.getByRole('button',{name:'PLAY TODAY'}));expect(go).toHaveBeenCalledWith(expect.stringContaining('/badly-explained/play/'))})
it('expands the room details and creates only after the host continues',async()=>{const go=vi.fn();vi.mocked(badlyApi.createRoom).mockResolvedValue({code:'DRAW42',name:'Friday Draw','host_name':'Ada',status:'open',expires_at:'2026-09-15T00:00:00Z',participant_count:1,joined:true,current_player_name:'Ada',attempt_id:null});render(<BadlyExplainedApp path="/badly-explained" navigate={go}/>);await userEvent.click(await screen.findByRole('button',{name:'CREATE A ROOM'}));expect(badlyApi.createRoom).not.toHaveBeenCalled();await userEvent.type(screen.getByLabelText('PLAYER NAME'),'Ada');const lobby=screen.getByLabelText('LOBBY NAME');await userEvent.clear(lobby);await userEvent.type(lobby,'Friday Draw');await userEvent.click(screen.getByRole('button',{name:'CONTINUE'}));await waitFor(()=>expect(badlyApi.createRoom).toHaveBeenCalledWith('Friday Draw','Ada'));expect(go).toHaveBeenCalledWith('/badly-explained/room/DRAW42')})
it('shows ordered hints, title-only autocomplete and one guess',async()=>{vi.mocked(badlyApi.state).mockResolvedValue(state({phase:'active',current_hint:'A fish loses a child.',deadline:new Date(Date.now()+10000).toISOString()}));vi.mocked(badlyApi.submit).mockResolvedValue(state({phase:'feedback',current_hint:'A fish loses a child.',last_correct:false}));render(<BadlyExplainedApp path="/badly-explained/play/10000000-0000-0000-0000-000000000001" navigate={vi.fn()}/>);expect(await screen.findByText('A fish loses a child.')).toBeVisible();await userEvent.type(screen.getByLabelText('Movie title'),'Find');expect(await screen.findByRole('button',{name:'Finding Nemo'})).toBeVisible();await userEvent.click(screen.getByRole('button',{name:'Finding Nemo'}));await userEvent.click(screen.getByRole('button',{name:'LOCK IN GUESS'}));await waitFor(()=>expect(badlyApi.submit).toHaveBeenCalledTimes(1));expect(await screen.findByText('NOT EVEN CLOSE')).toBeVisible()})

it('only suggests related titles after typing and hides them when cleared',async()=>{
  vi.mocked(badlyApi.state).mockResolvedValue(state({phase:'active',current_hint:'A mystery.',deadline:new Date(Date.now()+10000).toISOString()}))
  render(<BadlyExplainedApp path="/badly-explained/play/10000000-0000-0000-0000-000000000001" navigate={vi.fn()}/>)
  const input=await screen.findByLabelText('Movie title')
  await new Promise(resolve=>setTimeout(resolve,150))
  expect(badlyApi.titles).not.toHaveBeenCalled()
  expect(screen.queryByRole('list')).not.toBeInTheDocument()
  expect(screen.queryByRole('button',{name:'VIEW ALL MOVIES'})).not.toBeInTheDocument()
  await userEvent.type(input,'Find')
  expect(await screen.findByRole('button',{name:'Finding Nemo'})).toBeVisible()
  expect(screen.queryByRole('button',{name:'Toy Story'})).not.toBeInTheDocument()
  await userEvent.clear(input)
  expect(screen.queryByRole('list')).not.toBeInTheDocument()
})

it('omits Superheroes and Animation navigation in Badly Explained',async()=>{
  const navigate=vi.fn()
  render(<BadlyExplainedApp path="/badly-explained" navigate={navigate}/>)
  expect(await screen.findByRole('button',{name:'BADLY EXPLAINED'})).toBeVisible()
  expect(screen.queryByRole('button',{name:'SUPERHEROES'})).not.toBeInTheDocument()
  expect(screen.queryByRole('button',{name:'ANIMATION'})).not.toBeInTheDocument()
  expect(screen.getByRole('button',{name:'ALBUMNESIA'})).toBeVisible()
  expect(document.querySelector('.bad-nav .game-nav-links')).toHaveTextContent('ALBUMNESIA')
  expect(screen.getByRole('button',{name:'BADLY EXPLAINED'})).toHaveAttribute('aria-current','page')
  await userEvent.click(screen.getByRole('button',{name:'ALBUMNESIA'}))
  expect(navigate).toHaveBeenCalledWith('/albumnesia')
})

it.each([
  [1,'SOLVED IN 1 HINT','Suspiciously competent.'],
  [2,'SOLVED IN 2 HINTS','Still annoyingly impressive.'],
  [3,'SOLVED IN 3 HINTS','Respectable recovery.'],
  [4,'SOLVED IN 4 HINTS','You crawled across the finish line.'],
  [5,'SOLVED ON THE IMAGE','The pixels personally rescued you.'],
] as const)('renders the persisted successful result for stage %s',async(round,heading,quality)=>{
  vi.mocked(badlyApi.state).mockResolvedValue(state({status:'completed',phase:'results',round_number:round,result:{title:'Finding Nemo',image_url:'/stored/finding-nemo.webp',successful_round:round,remaining_ms:4200,rank_value:6-round,daily_number:258,completed_at:'2026-09-14T12:00:00Z'}}))
  render(<BadlyExplainedApp path="/badly-explained/play/10000000-0000-0000-0000-000000000001" navigate={vi.fn()}/>)
  expect(await screen.findByRole('heading',{name:heading})).toBeVisible()
  expect(screen.getByText(quality)).toBeVisible()
  expect(screen.getByRole('img',{name:'Final image for Finding Nemo'})).toHaveAttribute('src','/stored/finding-nemo.webp')
  expect(screen.getByText('Finding Nemo')).toBeVisible()
  expect(screen.getAllByText('✓')).toHaveLength(2)
})

it('renders a full failed result without exposing a fake numerical score',async()=>{
  vi.mocked(badlyApi.state).mockResolvedValue(state({status:'completed',phase:'results',round_number:5,result:{title:'Toy Story',image_url:'/stored/toy-story.webp',successful_round:null,remaining_ms:0,rank_value:0,daily_number:258,completed_at:'2026-09-14T12:00:00Z'}}))
  render(<BadlyExplainedApp path="/badly-explained/play/10000000-0000-0000-0000-000000000001" navigate={vi.fn()}/>)
  expect(await screen.findByText('CASE COLD')).toBeVisible()
  expect(screen.getByRole('heading',{name:'YOU MISSED ALL FIVE'})).toBeVisible()
  expect(screen.getByText('Not solved after all five stages')).toBeVisible()
  expect(screen.queryByText('4 / 5')).not.toBeInTheDocument()
  expect(screen.queryByRole('button',{name:/friends/i})).not.toBeInTheDocument()
})

it('opens the room leaderboard below the result actions only on request',async()=>{
  vi.mocked(badlyApi.state).mockResolvedValue(state({mode:'room',room_code:'DRAW42',status:'completed',phase:'results',result:{title:'Toy Story',image_url:'/stored/toy-story.webp',successful_round:5,remaining_ms:3000,rank_value:1,daily_number:null,completed_at:'2026-09-14T12:00:00Z'}}))
  vi.mocked(badlyApi.board).mockResolvedValue({code:'DRAW42',room_name:'Doodle Club',entries:[{display_name:'Ada',finished:true,successful_round:5,remaining_ms:3000,completed_at:'2026-09-14T12:00:00Z',is_current:true}]})
  render(<BadlyExplainedApp path="/badly-explained/play/10000000-0000-0000-0000-000000000001" navigate={vi.fn()}/>)
  const button=await screen.findByRole('button',{name:'VIEW LEADERBOARD'})
  expect(badlyApi.board).not.toHaveBeenCalled()
  expect(screen.queryByRole('region',{name:'Room leaderboard'})).not.toBeInTheDocument()
  expect(screen.queryByText(/SEE HOW YOUR FRIENDS DID/)).not.toBeInTheDocument()
  await userEvent.click(button)
  const leaderboard=await screen.findByRole('region',{name:'Room leaderboard'})
  expect(leaderboard).toHaveTextContent('Ada')
  expect(button.compareDocumentPosition(leaderboard)&Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
})

it('copies a spoiler-free daily result',async()=>{
  const nativeShare=vi.fn().mockResolvedValue(undefined)
  const writeText=vi.fn().mockResolvedValue(undefined);Object.defineProperty(navigator,'clipboard',{value:{writeText},configurable:true});Object.defineProperty(navigator,'share',{value:nativeShare,configurable:true})
  vi.mocked(badlyApi.state).mockResolvedValue(state({status:'completed',phase:'results',round_number:3,result:{title:'Secret Movie',image_url:'/stored/secret.webp',successful_round:3,remaining_ms:3000,rank_value:3,daily_number:258,completed_at:'2026-09-14T12:00:00Z'}}))
  render(<BadlyExplainedApp path="/badly-explained/play/10000000-0000-0000-0000-000000000001" navigate={vi.fn()}/>);await userEvent.click(await screen.findByRole('button',{name:/SHARE RESULT/}));expect(writeText).toHaveBeenCalledWith(expect.stringContaining('Solved in 3 hints'));expect(writeText.mock.calls[0][0]).not.toContain('Secret Movie')
  expect(nativeShare).not.toHaveBeenCalled()
  expect(screen.getByRole('button',{name:/RESULT COPIED/})).toBeVisible()
})
