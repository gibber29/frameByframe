import { FormEvent, KeyboardEvent, useEffect, useMemo, useRef, useState } from 'react'
import { albumnesiaApi, preloadImage } from './api'
import type { AlbumAttempt, AlbumLeaderboard, AlbumRoom, MaskRegion } from './types'

const DISPLAY_NAME_KEY = 'framebyframe-albumnesia-name'

function errorMessage(value: unknown) { return value instanceof Error ? value.message : 'Something went wrong.' }
function score(value: string | number | null) { return Number(value || 0).toFixed(2) }

function seeded(seed: number) {
  return () => { seed |= 0; seed = seed + 0x6D2B79F5 | 0; let value = Math.imul(seed ^ seed >>> 15, 1 | seed); value = value + Math.imul(value ^ value >>> 7, 61 | value) ^ value; return ((value ^ value >>> 14) >>> 0) / 4294967296 }
}

function pathRegion(context: CanvasRenderingContext2D, region: MaskRegion, width: number, height: number) {
  context.beginPath()
  if (region.kind === 'rectangle' && region.points.length === 2) {
    const [a, b] = region.points
    context.rect(Math.min(a.x,b.x)*width, Math.min(a.y,b.y)*height, Math.abs(b.x-a.x)*width, Math.abs(b.y-a.y)*height)
    return
  }
  region.points.forEach((point, index) => index ? context.lineTo(point.x * width, point.y * height) : context.moveTo(point.x * width, point.y * height))
  context.closePath()
}

async function renderDistortedCover(source: string, method: NonNullable<AlbumAttempt['distortion']>, seed: number, masks: MaskRegion[], textMasks: MaskRegion[]): Promise<string> {
  return new Promise((resolve, reject) => {
    const image = new Image()
    image.src = source
    image.onload = () => {
      const target = document.createElement('canvas')
      const size = Math.min(image.naturalWidth, image.naturalHeight)
      target.width = 900; target.height = 900
      const context = target.getContext('2d', { willReadFrequently: true })!
      const random = seeded(seed)
      context.drawImage(image, (image.naturalWidth - size) / 2, (image.naturalHeight - size) / 2, size, size, 0, 0, 900, 900)
      if (method === 'pixel_hangover') {
        const small = document.createElement('canvas'); const pixels = Math.floor(17 + random()*15); small.width = pixels; small.height = pixels
        small.getContext('2d')!.drawImage(target, 0, 0, pixels, pixels)
        context.imageSmoothingEnabled = false; context.clearRect(0, 0, 900, 900); context.drawImage(small, 0, 0, 900, 900)
      } else if (method === 'sleeve_shredder') {
        const copy = document.createElement('canvas'); copy.width = copy.height = 900; copy.getContext('2d')!.drawImage(target, 0, 0)
        context.clearRect(0, 0, 900, 900)
        for (let y = 0; y < 900; y += 30) context.drawImage(copy, 0, y, 900, 30, (random() - .5) * 240, y, 900, 30)
      } else if (method === 'channel_damage') {
        context.globalCompositeOperation = 'screen'; context.globalAlpha = .62
        context.filter = 'sepia(1) saturate(8) hue-rotate(315deg)'; context.drawImage(target, -15, 0)
        context.filter = 'sepia(1) saturate(8) hue-rotate(125deg)'; context.drawImage(target, 15, 0)
        context.globalCompositeOperation = 'source-over'; context.globalAlpha = 1; context.filter = 'none'
      } else if (method === 'identity_crisis') {
        const copy = document.createElement('canvas'); copy.width = copy.height = 30; copy.getContext('2d')!.drawImage(target, 0, 0, 30, 30)
        masks.forEach(region => { context.save(); context.beginPath(); pathRegion(context, region, 900, 900); context.clip(); context.imageSmoothingEnabled = false; context.drawImage(copy, 0, 0, 900, 900); context.restore() })
      } else {
        context.filter = 'grayscale(1) contrast(2.8) brightness(1.3)'; context.drawImage(target, 0, 0); context.filter = 'none'
      }
      const maskColours: Record<string,[string,string]> = { pixel_hangover:['#151923','#59647a'], sleeve_shredder:['#151923','#d8dce6'], channel_damage:['#061018','#ef245d'], identity_crisis:['#18131d','#887b9d'], outline_only:['#05070b','#58d6d0'] }
      for (const region of textMasks) {
        context.save(); pathRegion(context, region, 900, 900); context.clip(); context.fillStyle=maskColours[method][0]; context.fillRect(0,0,900,900); context.strokeStyle=maskColours[method][1]; context.lineWidth=7
        for(let line=-900;line<1800;line+=13+Math.floor(random()*9)){ context.beginPath(); context.moveTo(line,0); context.lineTo(line-900,900); context.stroke() }
        context.restore()
      }
      context.fillStyle = 'rgba(245,232,201,.08)'
      for (let i = 0; i < 2500; i++) context.fillRect(random() * 900, random() * 900, 1, 1)
      resolve(target.toDataURL('image/webp', .9))
    }
    image.onerror = () => reject(new Error('Unable to transform the album cover'))
  })
}

function AlbumNav({ navigate }: { navigate: (path: string) => void }) {
  return <nav className="album-nav" aria-label="Main navigation">
    <button className="album-brand" onClick={() => navigate('/')}>FRAME <small>BY</small> FRAME</button>
    <div className="game-nav-links"><button onClick={() => navigate('/badly-explained')}>BADLY EXPLAINED</button><button className="active" aria-current="page" onClick={() => navigate('/albumnesia')}>ALBUMNESIA</button></div>
    <div className="album-nav-tools"><button type="button" aria-label="Sound control" className="sound-control"><span aria-hidden="true">◖))</span></button><i aria-hidden="true"/><button type="button" aria-label="Profile" className="profile-control"><span aria-hidden="true"/></button></div>
  </nav>
}

function DailyArtwork() {
  return <div className="vinyl-art daily-art" aria-hidden="true">
    <span className="card-star">✦</span><i className="record daily-record"><b /></i>
    <div className="abstract-sleeve"><i/><b/><span/></div>
    <small>TRACKS<br/>MAKE<br/>BETTER<br/>PEOPLE<i/></small>
  </div>
}

function BattleArtwork() {
  return <div className="vinyl-art versus" aria-hidden="true">
    <span className="spark spark-orange">✦</span><span className="spark spark-teal">✦</span>
    <i className="record first"><b /></i>
    <div className="versus-mark"><span className="wave orange-wave">{[1,2,3,4].map(value=><i key={value}/>)}</span><strong>VS</strong><span className="wave teal-wave">{[1,2,3,4].map(value=><i key={value}/>)}</span></div>
    <i className="record second"><b /></i>
    <small>SAME<br/>BEATS<br/>MORE<br/>FRIENDS<i/></small>
  </div>
}

function Vinyl() {
  return <div className="vinyl-art" aria-hidden="true"><i className="record"><b /></i></div>
}

function Landing({ navigate }: { navigate: (path: string) => void }) {
  const [home, setHome] = useState<{daily_available:boolean; streak:number; completed_today:boolean} | null>(null)
  const [showCreate, setShowCreate] = useState(false)
  const [name, setName] = useState(localStorage.getItem(DISPLAY_NAME_KEY) || '')
  const [roomName, setRoomName] = useState('Battle of the Bands')
  const [joinCode, setJoinCode] = useState('')
  const [error, setError] = useState('')
  const [creating, setCreating] = useState(false)
  const creatingRequest = useRef(false)
  useEffect(() => { albumnesiaApi.home().then(setHome).catch(reason => setError(errorMessage(reason))) }, [])
  const daily = async () => {
    try { const attempt = await albumnesiaApi.startDaily(); navigate(`/albumnesia/play/${attempt.attempt_id}`) } catch (reason) { setError(errorMessage(reason)) }
  }
  const create = async (event: FormEvent) => {
    event.preventDefault(); if (creatingRequest.current) return; setError('')
    if (name.trim().length < 2 || roomName.trim().length < 2) { setError('Player name and lobby name must each contain at least two characters.'); return }
    creatingRequest.current=true; setCreating(true)
    try { localStorage.setItem(DISPLAY_NAME_KEY, name.trim()); const room = await albumnesiaApi.createRoom(roomName.trim(), name.trim()); navigate(`/albumnesia/room/${room.code}`) } catch (reason) { creatingRequest.current=false; setError(errorMessage(reason)); setCreating(false) }
  }
  const join = (event: FormEvent) => { event.preventDefault(); if (joinCode.trim()) navigate(`/albumnesia/room/${joinCode.trim().toUpperCase()}`) }
  return <><AlbumNav navigate={navigate}/><main className={`album-page album-landing ${showCreate?'is-expanded':''}`}>
    <aside className="album-side-copy left upper" aria-hidden="true">GOOD<br/>MUSIC<br/>SHARPENS<br/>MINDS<i/></aside><aside className="album-side-copy left lower" aria-hidden="true">SPIN<br/>THINK<br/>PLAY<br/>REPEAT<i/></aside>
    <aside className="album-side-copy right upper" aria-hidden="true">A<br/>BRIGHTER<br/>DAY<br/>THROUGH<br/>MUSIC<i/></aside><aside className="album-side-copy right lower" aria-hidden="true">SAME<br/>COVERS<br/>DIFFERENT<br/>STORIES<i/></aside>
    <section className="album-board">
    <i className="crop-mark top-left" aria-hidden="true"/><i className="crop-mark top-right" aria-hidden="true"/><i className="crop-mark bottom-left" aria-hidden="true"/><i className="crop-mark bottom-right" aria-hidden="true"/>
    <p className="album-kicker"><span>TRACK<br/>01</span><b>ALBUMNESIA MODE</b><span>SIDE<br/>A</span></p>
    <h1>HOW WILL YOU DROP THE NEEDLE?</h1>
    <div className="album-mode-grid">
      <article className="album-mode daily-mode"><span className="album-badge orange">🔥 {home?.streak || 0} DAY STREAK</span><DailyArtwork/><h2>DAILY ALBUM</h2><p>One altered cover. Five clues. New every day.</p><button className="album-cta orange" disabled={!home?.daily_available} onClick={daily}>{home?.completed_today ? 'VIEW TODAY' : home?.daily_available ? 'PLAY TODAY →' : 'NEEDS AN ACTIVE ALBUM'}</button></article>
      <article className="album-mode battle-mode"><span className="album-badge teal">♟ 2–8 PLAYERS</span><BattleArtwork/><h2>BATTLE OF THE BANDS</h2><p>Same puzzle. Play anytime. Highest score wins.</p><button className="album-cta teal" onClick={() => setShowCreate(value => !value)}>CREATE A ROOM →</button></article>
    </div>
    {showCreate && <section className="listening-party"><h2>START A LISTENING PARTY</h2><form className="album-room-form" onSubmit={create}><label>Player name<input value={name} onChange={e => setName(e.target.value)} minLength={2} maxLength={40} required/></label><label>Lobby name<input value={roomName} onChange={e => setRoomName(e.target.value)} minLength={2} maxLength={80} required/></label><button className="album-cta teal" disabled={creating}>{creating ? 'CREATING…' : 'CREATE ROOM'}</button><button type="button" onClick={() => {setShowCreate(false);setError('')}}>CANCEL</button></form></section>}
    <form className="album-join" onSubmit={join}><label>Already have a room code?<input value={joinCode} onChange={e => setJoinCode(e.target.value)} placeholder="ABC2345" maxLength={12}/></label><button>JOIN</button></form>
    {error && <p className="album-error" role="alert">{error}</p>}
    <footer><span>33⅓ RPM</span><em>For people who read the liner notes.</em><span>SIDE B</span></footer>
  </section></main></>
}

function RoomLobby({ code, navigate }: { code: string; navigate: (path:string)=>void }) {
  const [room, setRoom] = useState<AlbumRoom | null>(null)
  const [name, setName] = useState(localStorage.getItem(DISPLAY_NAME_KEY) || '')
  const [error, setError] = useState('')
  const [joining, setJoining] = useState(false); const [continuing, setContinuing] = useState(false); const [copied, setCopied] = useState(false)
  useEffect(() => { albumnesiaApi.room(code).then(setRoom).catch(reason => setError(errorMessage(reason))) }, [code])
  const link = `${window.location.origin}/albumnesia/room/${code.toUpperCase()}`
  const invite = room ? `Join ${room.host_name} in ${room.name} to compete in Albumnesia!\n\n${link}` : ''
  const copyInvite = async () => { try { await navigator.clipboard.writeText(invite); setCopied(true); window.setTimeout(() => setCopied(false), 2200) } catch { setError('Clipboard permission was denied. Select and copy the joining URL instead.') } }
  const nativeShare = async () => { if (!room || !navigator.share) return; try { await navigator.share({ title:room.name, text:`Join ${room.host_name} in ${room.name} to compete in Albumnesia!`, url:link }) } catch (reason) { if ((reason as Error)?.name !== 'AbortError') setError('The invitation could not be shared. You can still copy it.') } }
  const join = async (event: FormEvent) => { event.preventDefault(); if(joining) return; setError(''); if(name.trim().length<2){setError('Player name must contain at least two characters.');return} setJoining(true); try { localStorage.setItem(DISPLAY_NAME_KEY, name.trim()); setRoom(await albumnesiaApi.joinRoom(code, name.trim())) } catch (reason) { setError(errorMessage(reason)) } finally { setJoining(false) } }
  const continueGame = async () => { if(continuing) return; setContinuing(true); setError(''); try { const attempt=await albumnesiaApi.continueRoom(code); navigate(`/albumnesia/play/${attempt.attempt_id}`) } catch(reason){setError(errorMessage(reason));setContinuing(false)} }
  if (!room) return <><AlbumNav navigate={navigate}/><main className="album-page album-loading">{error || 'Finding the listening party…'}</main></>
  return <><AlbumNav navigate={navigate}/><main className="album-page"><section className="album-board album-lobby">
    <p className="album-kicker">{room.joined ? 'YOUR LISTENING PARTY' : 'YOU’VE BEEN INVITED'}</p><h1>{room.name}</h1>
    <p>Join {room.host_name} in {room.name} to compete in Albumnesia.</p>
    {!room.joined ? <form onSubmit={join}><label>Player name<input autoFocus value={name} onChange={e=>setName(e.target.value)} minLength={2} maxLength={40} required/></label><button className="album-cta orange" disabled={joining}>{joining?'JOINING…':'JOIN LOBBY →'}</button></form> : <section className="room-confirmation"><h2>{room.current_player_name === room.host_name ? 'ROOM CREATED' : `WELCOME, ${room.current_player_name}`}</h2><div className="room-code"><small>ROOM CODE</small>{room.code}</div><label className="joining-link">Shareable joining URL<input readOnly value={link}/></label><p>{room.participant_count} player{room.participant_count===1?'':'s'} joined · Everyone receives the same five covers and transformations.</p><div className="album-actions"><button onClick={copyInvite}>{copied?'INVITE COPIED':'COPY INVITE'}</button>{typeof navigator.share==='function'&&<button onClick={nativeShare}>NATIVE SHARE</button>}<button className="album-cta orange" disabled={continuing} onClick={continueGame}>{continuing?'PREPARING…':room.attempt_id?'RESUME GAME':'CONTINUE TO GAME'}</button></div>{copied&&<p role="status">The complete invitation was copied.</p>}</section>}
    {error&&<p className="album-error" role="alert">{error}</p>}
  </section></main></>
}

function Autocomplete({ value, onChange, onSubmit, disabled }: { value:string; onChange:(v:string)=>void; onSubmit:()=>void; disabled:boolean }) {
  const [options, setOptions] = useState<string[]>([]); const [open, setOpen] = useState(false); const [active, setActive] = useState(0)
  useEffect(() => { if (disabled) return; const id = window.setTimeout(() => albumnesiaApi.titles(value, value ? 8 : 100).then(setOptions).catch(() => setOptions([])), 100); return () => clearTimeout(id) }, [value, disabled])
  const keys = (event: KeyboardEvent<HTMLInputElement>) => { if (event.key === 'ArrowDown') { event.preventDefault(); setOpen(true); setActive(i => Math.min(i + 1, options.length - 1)) } else if (event.key === 'ArrowUp') { event.preventDefault(); setActive(i => Math.max(0, i - 1)) } else if (event.key === 'Enter') { event.preventDefault(); if (open && options[active]) { onChange(options[active]); setOpen(false) } else onSubmit() } else if (event.key === 'Escape') setOpen(false) }
  return <div className="album-autocomplete"><label htmlFor="album-title" className="sr-only">Album title</label><input id="album-title" autoFocus autoComplete="off" placeholder="Type the album title…" value={value} disabled={disabled} onChange={e => {onChange(e.target.value); setOpen(true); setActive(0)}} onFocus={() => setOpen(true)} onKeyDown={keys} aria-expanded={open}/><button type="button" className="browse-titles" onClick={() => setOpen(v => !v)}>Browse all titles</button>{open && options.length > 0 && <ul role="listbox">{options.map((option, index) => <li key={option}><button type="button" className={index === active ? 'active' : ''} onMouseDown={e => e.preventDefault()} onClick={() => {onChange(option); setOpen(false)}}>{option}</button></li>)}</ul>}</div>
}

function Results({ game, navigate }: { game: AlbumAttempt; navigate:(path:string)=>void }) {
  const [board, setBoard] = useState<AlbumLeaderboard | null>(null); const [room, setRoom] = useState<AlbumRoom|null>(null); const [copied, setCopied] = useState(false); const [error,setError]=useState('')
  const loadBoard=()=>{if(game.room_code) Promise.all([albumnesiaApi.leaderboard(game.room_code),albumnesiaApi.room(game.room_code)]).then(([ranking,details])=>{setBoard(ranking);setRoom(details);setError('')}).catch(reason=>setError(`Leaderboard could not be loaded. ${errorMessage(reason)}`))}
  useEffect(loadBoard,[game.room_code])
  const share = async () => { try { const marks = game.results?.map(r => r.correct ? '●' : '○').join(' ') || ''; await navigator.clipboard.writeText(`FrameByFrame Albumnesia\n${marks}\n${game.correct_count}/${game.total_rounds} · ${score(game.total_score)} / ${score(game.max_score)}`); setCopied(true) } catch { setError('Clipboard permission was denied.') } }
  const copyInvite=async()=>{if(!room||!game.room_code)return;try{const link=`${window.location.origin}/albumnesia/room/${game.room_code}`;await navigator.clipboard.writeText(`Join ${room.host_name} in ${room.name} to compete in Albumnesia!\n\n${link}`);setCopied(true)}catch{setError('Clipboard permission was denied.')}}
  const average=(game.results?.reduce((sum,row)=>sum+row.answer_time_ms,0)||0)/game.total_rounds
  return <main className="album-page"><section className="album-board album-results"><p className="album-kicker">THE NEEDLE LIFTS</p><h1>{game.correct_count === game.total_rounds ? 'PERFECT PRESSING.' : 'THAT’S THE RECORD.'}</h1><div className="result-score"><strong>{score(game.total_score)}</strong><span>/ {score(game.max_score)}</span><small>{game.correct_count} OF {game.total_rounds} CORRECT · AVG {(average/1000).toFixed(2)}s</small></div>{game.legacy_score&&<p>Legacy score converted explicitly to the current display scale.</p>}<div className="album-result-list">{game.results?.map(row => <article key={row.round_number} className={row.correct ? 'correct' : ''}><b>{row.round_number}</b><div><strong>{row.title}</strong><small>{row.artist}</small></div><span>{row.correct ? `+${score(row.score)}` : 'MISS'}</span></article>)}</div>{game.mode === 'daily' && <p className="streak-line">🔥 {game.streak} day streak</p>}{board && <section className="album-leaderboard"><h2>{board.room_name} · Leaderboard</h2><div className="leaderboard-head"><span>Rank · Player</span><span>Result · Score · Average</span></div><ol>{board.entries.map((entry, i) => <li key={`${entry.display_name}-${i}`} className={entry.is_current?'current-player':''}><b>{i+1}. {entry.display_name}</b>{entry.finished ? <span>{entry.correct_count}/5 · {score(entry.score)} / 50.00 · {((entry.average_response_ms||0)/1000).toFixed(2)}s</span> : <span>Not Finished</span>}</li>)}</ol></section>}<div className="album-actions"><button onClick={share}>SHARE RESULT</button>{game.room_code&&<><button onClick={loadBoard}>REFRESH LEADERBOARD</button><button onClick={copyInvite}>COPY INVITE</button></>}<button className="album-cta orange" onClick={() => navigate('/albumnesia')}>RETURN TO ALBUMNESIA</button></div>{copied && <p role="status">Copied successfully.</p>}{error&&<p className="album-error" role="alert">{error} <button onClick={loadBoard}>Retry</button></p>}</section></main>
}

function Play({ id, navigate }: { id:string; navigate:(path:string)=>void }) {
  const [game, setGame] = useState<AlbumAttempt | null>(null); const [cover, setCover] = useState(''); const [answer, setAnswer] = useState(''); const [remaining, setRemaining] = useState(5); const [error, setError] = useState(''); const [loadingCover, setLoadingCover] = useState(false); const [prepared,setPrepared]=useState(false); const [preparedRound,setPreparedRound]=useState(0); const starting = useRef(false); const loadedRound = useRef(0); const autoStartingRound = useRef(0)
  const refresh = () => albumnesiaApi.state(id).then(setGame).catch(reason => setError(errorMessage(reason)))
  useEffect(() => { refresh(); const visible = () => refresh(); document.addEventListener('visibilitychange', visible); return () => document.removeEventListener('visibilitychange', visible) }, [id])
  useEffect(() => { if (!game?.phase_deadline || !['memorize','guess','feedback'].includes(game.phase)) return; const serverOffset = new Date(game.server_time).getTime() - Date.now(); const tick = () => { const left = Math.max(0, new Date(game.phase_deadline!).getTime() - (Date.now() + serverOffset)); setRemaining(left / 1000); if (left <= 0) refresh() }; tick(); const timer = setInterval(tick, 50); return () => clearInterval(timer) }, [game?.phase, game?.phase_deadline, game?.server_time])
  useEffect(() => { if (game?.phase !== 'ready' || !game.image_url || !game.distortion) return; if (loadedRound.current !== game.round_number) {starting.current=false;setPrepared(false);setPreparedRound(0)} if(starting.current)return; let cancelled = false; let original = ''; starting.current = true; loadedRound.current = game.round_number; setLoadingCover(true); preloadImage(game.image_url).then(value => { original=value; return renderDistortedCover(value, game.distortion!, game.distortion_seed || 1, game.subject_mask_regions || [], game.text_mask_regions || []) }).then(value => { if (cancelled) return; setCover(value); setPrepared(true); setPreparedRound(game.round_number) }).catch(reason => { starting.current = false; setError(`${errorMessage(reason)} Retry when the cover is available.`) }).finally(() => { if(original) URL.revokeObjectURL(original); setLoadingCover(false) }); return () => { cancelled = true } }, [game?.phase, game?.round_number, game?.image_url, game?.distortion, id])
  useEffect(() => { if (game?.phase !== 'guess') setAnswer('') }, [game?.phase, game?.round_number])
  const submit = async () => { if (!answer.trim() || game?.phase !== 'guess') return; try { setGame(await albumnesiaApi.submit(id, answer)); setAnswer('') } catch (reason) { setError(errorMessage(reason)); refresh() } }
  const beginRound=async()=>{if(!prepared||game?.phase!=='ready')return;setError('');try{setGame(await albumnesiaApi.ready(id))}catch(reason){setError(errorMessage(reason));refresh()}}
  useEffect(() => {
    if (!game || game.mode !== 'room' || game.phase !== 'ready' || game.round_number <= 1 || !prepared || preparedRound !== game.round_number || autoStartingRound.current === game.round_number) return
    autoStartingRound.current = game.round_number
    setError('')
    albumnesiaApi.ready(id).then(setGame).catch(reason => {
      autoStartingRound.current = 0; starting.current = false; loadedRound.current = 0
      setPrepared(false); setPreparedRound(0); setError(`${errorMessage(reason)} Retrying the next round…`); refresh()
    })
  }, [game, prepared, preparedRound, id])
  if (!game) return <main className="album-page album-loading">{error || 'Dropping the needle…'}</main>
  if (game.phase === 'results') return <Results game={game} navigate={navigate}/>
  const memorizing = game.phase === 'memorize'
  return <><AlbumNav navigate={navigate}/><main className="album-page"><section className="album-board album-game">
    <header className="round-header"><strong>ROUND {String(game.round_number).padStart(2,'0')} / {String(game.total_rounds).padStart(2,'0')}</strong><div><span className={memorizing ? 'current' : 'done'}>{memorizing ? '1' : '✓'} <b>MEMORIZE</b></span><i/><span className={game.phase === 'guess' ? 'current' : ''}>2 <b>GUESS</b></span></div><strong>{game.phase === 'guess' ? `TIME LEFT ${remaining.toFixed(1)}s` : `MAX SCORE ${score(game.max_score)}`}</strong></header>
    {memorizing && <><div className="memory-banner"><b>MEMORIZE EVERYTHING</b><strong>{remaining.toFixed(1)}</strong><span>SECONDS</span><progress max="5" value={remaining}/></div><div className="memory-grid">{cover && <img className="album-cover" src={cover} alt="Distorted album cover" draggable={false}/>}<section className="clue-panel"><h1>ALL YOUR CLUES</h1><div><article><i>ABC</i><span><b>INITIALS</b>{game.clues?.artist_initials}</span></article><article><i>▣</i><span><b>RELEASED</b>{game.clues?.release_year || 'Unknown'}</span></article><article className="track-clue"><i>★</i><span><b>KNOWN FOR</b>{game.clues?.recognizable_track}</span></article></div></section></div><div className="locked-answer">Answer unlocks after the reveal.</div></>}
    {game.phase === 'ready' && <div className="ready-cover"><Vinyl/><h1>{loadingCover ? 'LOADING THE COVER…' : game.mode === 'room' && game.round_number > 1 ? 'NEXT TRACK READY' : 'GET READY'}</h1><p>{game.mode === 'room' && game.round_number > 1 ? `Round ${game.round_number} starts automatically when its cover is prepared.` : 'The five-second memorisation timer begins only when you are ready.'}</p>{!(game.mode === 'room' && game.round_number > 1) && <button className="album-cta orange" disabled={!prepared||loadingCover} onClick={beginRound}>I’M READY — DROP THE NEEDLE</button>}{game.mode === 'room' && game.round_number > 1 && <p className="control-state" role="status">KEEP THE NEEDLE MOVING…</p>}{error && <><p role="alert">{error}</p><button onClick={() => {autoStartingRound.current=0;starting.current=false;loadedRound.current=0;setPrepared(false);setPreparedRound(0);setGame({...game})}}>RETRY COVER</button></>}</div>}
    {game.phase === 'guess' && <section className="guess-phase"><p>ANSWER BEFORE THE TRACK ENDS</p><progress max="5" value={remaining}/><h1>WHAT WAS THE ALBUM?</h1><p>The cover and clues are gone. Trust your memory.</p><div className="guess-grid"><div className="no-peeking"><span>?</span><b>NO PEEKING</b></div><form onSubmit={e => {e.preventDefault(); submit()}}><Autocomplete value={answer} onChange={setAnswer} onSubmit={submit} disabled={false}/><button className="album-cta orange" disabled={!answer.trim()}>LOCK IN ANSWER</button><small>PRESS ENTER TO SUBMIT</small><strong>Correct now: {score(Math.max(0, Math.min(5, remaining)) * 2)} points</strong><p>One answer only. Lose 2.00 points per guessing second. Wrong answers earn 0.00.</p></form></div></section>}
    {game.phase === 'feedback' && <section className={`album-feedback ${game.last_correct ? 'correct' : ''}`}><p>{game.last_correct ? 'ON THE RECORD' : 'MISSED THE BEAT'}</p><h1>{game.revealed_title}</h1><h2>{game.revealed_artist}</h2><strong>{game.last_correct ? `+${score(game.last_score)} POINTS` : '0.00 POINTS'}</strong></section>}
    <footer className="round-footer"><div>{Array.from({length:game.total_rounds},(_,index)=>index+1).map(n => <i key={n} className={n < game.round_number ? 'done' : n === game.round_number ? 'current' : ''}>{n}</i>)}</div><strong>GAME TOTAL <span>{score(game.total_score)}</span> / {score(game.max_score)}</strong></footer>{error && game.phase !== 'ready' && <p className="album-error" role="alert">{error}</p>}
  </section></main></>
}

export function AlbumnesiaApp({ path, navigate }: { path:string; navigate:(path:string)=>void }) {
  const play = path.match(/^\/albumnesia\/play\/([^/]+)$/)
  const room = path.match(/^\/albumnesia\/room\/([^/]+)$/)
  if (play) return <Play id={play[1]} navigate={navigate}/>
  if (room) return <RoomLobby code={room[1]} navigate={navigate}/>
  return <Landing navigate={navigate}/>
}
