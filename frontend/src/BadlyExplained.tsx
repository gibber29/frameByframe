import { FormEvent, useEffect, useRef, useState } from 'react'
import { badlyApi, preloadImage } from './api'
import type { BadlyBoard, BadlyRoom, BadlyState } from './types'

const NAME = 'framebyframe-badly-name'
const err = (error: unknown) => error instanceof Error ? error.message : 'Something went wrong.'

function Nav({ go }: { go: (path: string) => void }) {
  return <nav className="bad-nav" aria-label="Main navigation">
    <button className="bad-logo" onClick={() => go('/')} aria-label="Frame By Frame home"><i />FRAME <small>BY</small> FRAME<i /></button>
    <div className="game-nav-links"><button className="active" aria-current="page" onClick={() => go('/badly-explained')}>BADLY EXPLAINED</button><button onClick={() => go('/albumnesia')}>ALBUMNESIA</button></div>
    <span className="bad-controls" aria-label="Sound and profile controls"><b aria-hidden="true">◖))</b><i aria-hidden="true" /></span>
  </nav>
}

function Creature({ tired = false }: { tired?: boolean }) {
  return <svg className={`bad-creature-svg ${tired ? 'tired' : ''}`} viewBox="0 0 300 260" aria-hidden="true">
    <g className="creature-arms" fill="none" stroke="currentColor" strokeWidth="8" strokeLinecap="round"><path d="M64 137Q28 120 20 89M235 126q35-18 45-48M28 91l-18-8m19 8-4-19m248 8 17-10m-16 10 3-20" /><path d="M105 218l-9 25-20 5m91-31 10 27 22 1" /></g>
    <path className="creature-body" d="M70 76Q92 24 149 35q65 4 87 69 16 61-17 105-32 35-91 24-60-7-71-64-10-54 13-93Z" />
    <path fill="none" stroke="currentColor" strokeWidth="7" strokeLinecap="round" d="m92 47 13-25m13 20 5-31m17 31 16-28m7 36 27-21" />
    <g className="creature-eyes"><ellipse cx="102" cy="105" rx="42" ry="47" /><ellipse cx="188" cy="91" rx="36" ry="40" /><circle cx="111" cy="112" r="10" /><circle cx="181" cy="84" r="9" /></g>
    <path className="creature-mouth" d={tired ? 'M112 178q31-18 60 2' : 'M105 169q35 42 73-2Z'} />{!tired && <path className="creature-teeth" d="m117 176 10 18 11-13 11 15 11-19" />}
    <path fill="none" stroke="currentColor" strokeWidth="5" d="m61 63-20-11m207 8 21-17M48 180l-24 13m222-7 30 15" />
  </svg>
}

function Portraits() {
  return <svg className="bad-portraits-svg" viewBox="0 0 660 230" aria-hidden="true">
    <g className="portrait portrait-a"><path className="portrait-paper" d="m38 23 187 2 5 177-192 3Z" /><path className="tape-svg" d="m105 8 72 5-6 32-72-6Z" /><circle cx="133" cy="109" r="54" fill="#f4d5b9" stroke="currentColor" strokeWidth="5" /><path d="M82 89q6-61 63-53 52 8 49 68l-18-29-12 24-18-31-20 30-15-27-29 18Z" /><circle cx="114" cy="108" r="6" /><circle cx="157" cy="106" r="6" /><path d="M111 136q24 23 48-2" fill="none" stroke="currentColor" strokeWidth="5" /><path d="M71 196q65-57 128 1" fill="#3c67dd" stroke="currentColor" strokeWidth="5" /></g>
    <g className="paper-flight" fill="none" stroke="currentColor" strokeWidth="4" strokeLinecap="round"><path className="flight-path" strokeDasharray="7 12" d="M236 111q72-75 143 1t85-12" /><path className="plane" fill="#fff" d="m319 74 74 29-41 12-17 37-5-43Z" /></g>
    <g className="portrait portrait-b"><path className="portrait-paper" d="m438 25 185-2 1 181-190-1Z" /><path className="tape-svg" d="m508 6 69 7-5 31-73-5Z" /><circle cx="530" cy="112" r="53" fill="#f1c6a5" stroke="currentColor" strokeWidth="5" /><path d="M476 98q-5-54 46-66 67-8 70 67-20-12-28-35-12 28-26 3-11 25-24-2-8 27-38 33Z" fill="#bc593e" /><circle cx="512" cy="111" r="6" /><circle cx="551" cy="110" r="6" /><path d="M508 137q23 21 47-2" fill="none" stroke="currentColor" strokeWidth="5" /><path d="M468 198q62-60 129 0" fill="#ab66ce" stroke="currentColor" strokeWidth="5" /></g>
    <path className="spark" d="m263 31 8 20m-18-8 20 2m133 132 9 21m-20-5 20-5" />
  </svg>
}

function SideDoodles() {
  return <div className="bad-decor" aria-hidden="true"><p className="side-a">SAME MOVIE<br />DIFFERENT HINTS<br />:)</p><p className="side-b">BAD ART<br />GOOD PEOPLE<br />...</p><p className="side-c">ANIMATION MAKES<br />LIFE WEIRDER<br />(BETTER)</p><p className="side-d">GUESS<br />LAUGH<br />REPEAT</p><i className="star star-a">☆</i><i className="star star-b">☆</i><i className="smile">☺</i><i className="crumb crumb-a" /><i className="crumb crumb-b" /></div>
}

function Home({ go }: { go: (path: string) => void }) {
  const [home, setHome] = useState<{ streak: number; daily_available: boolean }>(); const [open, setOpen] = useState(false); const [name, setName] = useState(localStorage.getItem(NAME) || ''); const [lobby, setLobby] = useState('Drawing Disaster'); const [error, setError] = useState('')
  useEffect(() => { badlyApi.home().then(setHome).catch(error => setError(err(error))) }, [])
  const daily = async () => { try { const state = await badlyApi.startDaily(); go(`/badly-explained/play/${state.attempt_id}`) } catch (error) { setError(err(error)) } }
  const create = async (event: FormEvent) => { event.preventDefault(); try { localStorage.setItem(NAME, name.trim()); const room = await badlyApi.createRoom(lobby.trim(), name.trim()); go(`/badly-explained/room/${room.code}`) } catch (error) { setError(err(error)) } }
  return <><Nav go={go} /><main className={`bad-page bad-home ${open ? 'is-expanded' : ''}`}><SideDoodles /><section className="bad-board"><div className="bad-heading"><p className="bad-label">BADLY EXPLAINED MODE</p><h1><i />HOW BADLY DO YOU WANT TO GUESS?<i /></h1><p className="bad-sub">Four terrible explanations. One suspicious image. One animated movie. Somehow, this is your problem now.</p></div><div className="bad-cards">
    <article className="bad-card daily"><div className="doodle-paper"><i className="tape" /><Creature /><span className="play-sketch">▶</span></div><div className="card-copy"><h2>DAILY<br />DISASTER</h2><p>One new mystery every day.<br />Solve it before the final image.</p><strong>🔥 {home?.streak || 0} DAY STREAK</strong></div><button disabled={!home?.daily_available} onClick={daily}>PLAY TODAY</button></article>
    <article className="bad-card friends"><Portraits /><div className="card-copy"><h2>CHALLENGE FRIENDS</h2><p>Same mystery. Different times.<br />Fewest hints wins.</p><strong>♟ 2–8 PLAYERS</strong></div><button onClick={() => setOpen(value => !value)}>CREATE A ROOM</button></article>
  </div>{open && <form className="bad-create" onSubmit={create}><label>PLAYER NAME<input required minLength={2} value={name} onChange={event => setName(event.target.value)} /></label><label>LOBBY NAME<input required minLength={2} value={lobby} onChange={event => setLobby(event.target.value)} /></label><button>CONTINUE</button></form>}{error && <p className="bad-error" role="alert">{error}</p>}<footer><span />Bad art. Worse guesses. Excellent friendships.<span /></footer></section></main></>
}

function Lobby({ code, go }: { code: string; go: (path: string) => void }) {
  const [room, setRoom] = useState<BadlyRoom>(); const [name, setName] = useState(localStorage.getItem(NAME) || ''); const [error, setError] = useState('')
  useEffect(() => { badlyApi.room(code).then(setRoom).catch(error => setError(err(error))) }, [code])
  const join = async (event: FormEvent) => { event.preventDefault(); try { localStorage.setItem(NAME, name); setRoom(await badlyApi.join(code, name)) } catch (error) { setError(err(error)) } }; const play = async () => { try { const state = await badlyApi.continue(code); go(`/badly-explained/play/${state.attempt_id}`) } catch (error) { setError(err(error)) } }
  if (!room) return <main>{error || 'Finding challenge…'}</main>; const link = `${location.origin}/badly-explained/room/${room.code}`
  return <><Nav go={go} /><main className="bad-page"><section className="bad-board bad-lobby"><p className="bad-label">{room.joined ? 'CHALLENGE READY' : 'YOU’VE BEEN INVITED'}</p><h1>{room.name}</h1><p>Join {room.host_name} in {room.name} to compete in Badly Explained!</p>{!room.joined ? <form onSubmit={join}><label>Player name<input autoFocus required minLength={2} value={name} onChange={event => setName(event.target.value)} /></label><button>JOIN LOBBY</button></form> : <><h2>ROOM CODE: {room.code}</h2><input aria-label="Shareable link" readOnly value={link} /><p>{room.participant_count} player{room.participant_count === 1 ? '' : 's'} joined</p><button onClick={() => navigator.clipboard.writeText(`Join ${room.host_name} in ${room.name} to compete in Badly Explained!\n\n${link}`)}>COPY INVITE</button><button onClick={play}>CONTINUE TO GAME</button></>}{error && <p role="alert">{error}</p>}</section></main></>
}

function Picker({ value, setValue, disabled }: { value: string; setValue: (value: string) => void; disabled: boolean }) {
  const [items, setItems] = useState<string[]>([])
  const [selected, setSelected] = useState<string | null>(null)
  const query = value.trim()
  useEffect(() => {
    setItems([])
    if (disabled || !query || value === selected) return
    let cancelled = false
    const timer = setTimeout(() => {
      badlyApi.titles(query).then(titles => {
        if (!cancelled) setItems(titles)
      }).catch(() => { if (!cancelled) setItems([]) })
    }, 100)
    return () => { cancelled = true; clearTimeout(timer) }
  }, [query, disabled, selected, value])
  const matches = !disabled && query && value !== selected
    ? items.filter(title => title.toLocaleLowerCase().includes(query.toLocaleLowerCase())).slice(0, 3)
    : []
  return <div className="bad-picker"><label htmlFor="bad-title">Movie title</label><input id="bad-title" autoComplete="off" value={value} disabled={disabled} onChange={event => { setSelected(null); setValue(event.target.value) }} />{matches.length > 0 && <ul>{matches.map(item => <li key={item}><button type="button" onClick={() => { setSelected(item); setValue(item); setItems([]) }}>{item}</button></li>)}</ul>}</div>
}

function ResultSteps({ solved }: { solved: number | null }) {
  return <div className="bad-result-steps" aria-label="Attempt stages">{[1, 2, 3, 4, 5].map(stage => { const state = solved === stage ? 'won' : solved === null || stage < solved ? 'lost' : 'future'; return <div className={`result-step ${state}`} key={stage}><b>{stage} {stage === 5 ? 'IMAGE' : 'HINT'}</b><span>{state === 'won' ? '✓' : state === 'lost' ? '✕' : stage === 5 ? '▧' : '—'}</span></div> })}</div>
}

function Result({ game, go }: { game: BadlyState; go: (path: string) => void }) {
  const result = game.result!; const solved = result.successful_round; const [board, setBoard] = useState<BadlyBoard>(); const [copied, setCopied] = useState(false); const [imageFailed, setImageFailed] = useState(false)
  const heading = solved ? solved === 5 ? 'SOLVED ON THE IMAGE' : `SOLVED IN ${solved} HINT${solved === 1 ? '' : 'S'}` : 'YOU MISSED ALL FIVE'
  const quality = solved ? ['', 'Suspiciously competent.', 'Still annoyingly impressive.', 'Respectable recovery.', 'You crawled across the finish line.', 'The pixels personally rescued you.'][solved] : 'Even the actual image could not negotiate with you.'
  const share = `Badly Explained #${result.daily_number ?? game.room_code ?? 'Challenge'}\n${solved ? solved === 5 ? 'Saved by the image' : `Solved in ${solved} hint${solved === 1 ? '' : 's'}` : 'The image could not save me'}\n${[1, 2, 3, 4, 5].map(stage => stage === solved ? '🟩' : !solved || stage < solved ? '🟥' : '⬜').join(' ')}`
  const shareResult = async () => { try { await navigator.clipboard.writeText(share); setCopied(true); window.setTimeout(() => setCopied(false), 1800) } catch { setCopied(false) } }
  const resultLine = solved ? solved === 5 ? 'Solved on the final image' : 'Solved before the final image' : 'Not solved after all five stages'
  return <><Nav go={go} /><main className={`bad-page bad-result-page ${board ? 'has-leaderboard' : ''}`}><section className={`bad-board bad-result ${solved ? 'success' : 'failure'} ${board ? 'has-leaderboard' : ''}`}><div className="result-heading"><p className="bad-label">{solved ? 'CASE CLOSED' : 'CASE COLD'}</p><h1>{heading}</h1><p>{quality}</p></div><ResultSteps solved={solved} /><div className="result-scene"><div className="result-note">{solved ? 'Good guessing!' : 'Maybe next time.'}<i>↘</i></div><figure><i className="photo-tape one" /><i className="photo-tape two" />{imageFailed ? <div className="image-fallback">THE EVIDENCE WOULD NOT LOAD</div> : <img src={result.image_url} onError={() => setImageFailed(true)} alt={`Final image for ${result.title}`} />}<figcaption><strong>{result.title}</strong><small>Today’s mystery</small></figcaption></figure><div className="result-stamp">{solved ? solved === 5 ? <>SAVED BY<br />THE IMAGE</> : <>GOT IT ON<br />HINT {solved}</> : <>CASE<br />UNSOLVED</>}</div><div className="party-creature"><Creature tired={!solved} /></div><i className="result-star">☆</i></div><div className="result-summary"><b>RESULT</b><span>{resultLine}</span><ResultSteps solved={solved} /></div><div className="result-actions">{game.room_code && <button onClick={() => badlyApi.board(game.room_code!).then(setBoard)}>VIEW LEADERBOARD</button>}<button className="share" onClick={shareResult}>{copied ? 'RESULT COPIED' : 'SHARE RESULT'} <span>↥</span></button><button onClick={() => go('/badly-explained')}>BACK TO BADLY EXPLAINED</button></div>{board && <section className="bad-leaderboard-panel" aria-label="Room leaderboard"><h2>LEADERBOARD</h2><ol className="bad-leaderboard">{board.entries.map((entry, index) => <li className={entry.is_current ? 'me' : ''} key={entry.display_name}>{index + 1}. {entry.display_name} — {entry.finished ? entry.successful_round ? entry.successful_round === 5 ? 'Image' : `Hint ${entry.successful_round}` : 'Missed all five' : 'Not Finished'}</li>)}</ol></section>}</section></main></>
}

function Play({ id, go }: { id: string; go: (path: string) => void }) {
  const [game, setGame] = useState<BadlyState>(); const [answer, setAnswer] = useState(''); const [remaining, setRemaining] = useState(10); const [image, setImage] = useState(''); const [error, setError] = useState(''); const starting = useRef(0); const refresh = () => badlyApi.state(id).then(setGame).catch(error => setError(err(error)))
  useEffect(() => { void refresh() }, [id]); useEffect(() => { if (!game?.deadline || !['active', 'feedback'].includes(game.phase)) return; const offset = new Date(game.server_time).getTime() - Date.now(); const tick = () => { const left = Math.max(0, new Date(game.deadline!).getTime() - (Date.now() + offset)); setRemaining(left / 1000); if (!left) refresh() }; tick(); const timer = setInterval(tick, 50); return () => clearInterval(timer) }, [game?.deadline, game?.phase, game?.server_time])
  useEffect(() => { if (game?.phase !== 'ready' || starting.current === game.round_number) return; const start = async () => { starting.current = game.round_number; if (game.round_number === 5 && game.image_url) { try { setImage(await preloadImage(game.image_url)) } catch (error) { setError(err(error)); starting.current = 0; return } } if (game.round_number > 1) setGame(await badlyApi.ready(id)) }; void start() }, [game?.phase, game?.round_number, game?.image_url, id])
  const ready = async () => setGame(await badlyApi.ready(id)); const submit = async (event: FormEvent) => { event.preventDefault(); if (!answer.trim()) return; try { setGame(await badlyApi.submit(id, answer)); setAnswer('') } catch (error) { setError(err(error)) } }
  if (!game) return <main>{error || 'Loading mystery…'}</main>; if (game.phase === 'results') return <Result game={game} go={go} />; const active = game.phase === 'active'
  return <><Nav go={go} /><main className="bad-page"><section className="bad-board bad-game"><header><b>{game.mode === 'daily' ? 'TODAY’S MYSTERY' : game.lobby_name}</b><nav>{[1, 2, 3, 4, 5].map(stage => <span className={stage === game.round_number ? 'now' : stage < game.round_number ? 'past' : 'future'} key={stage}>{stage} {stage === 5 ? 'IMAGE' : 'HINT'} {stage < game.round_number ? '✕' : stage > game.round_number ? '🔒' : ''}</span>)}</nav><b>ROUND {String(game.round_number).padStart(2, '0')} / 05</b></header>{active && <div className={`bad-timer ${remaining < 3 ? 'urgent' : ''}`}><b>GUESS BEFORE THE INK DRIES</b><strong>{remaining.toFixed(1)}</strong><span>SECONDS LEFT</span><progress max="10" value={remaining} /></div>}<div className="bad-play-grid"><section><article className="hint-paper">{game.round_number < 5 ? <><b>HINT {String(game.round_number).padStart(2, '0')}</b><h2>{game.current_hint || 'Get ready…'}</h2><div className="scribble">?　☆　?</div></> : <><b>FINAL IMAGE</b>{image && <img src={image} alt="Final stored movie clue" />}</>}</article><div className="old-hints">{game.previous_hints.map((hint, index) => <details open key={index}><summary>HINT {String(index + 1).padStart(2, '0')}</summary><p>{hint}</p></details>)}</div></section><section className="bad-answer"><h2>NAME THE ANIMATED MOVIE</h2>{game.phase === 'ready' ? <button className="lock" onClick={ready}>I’M READY</button> : game.phase === 'feedback' ? <><h3>{game.last_correct ? 'NAILED IT' : 'NOT EVEN CLOSE'}</h3><p>Next terrible clue incoming…</p></> : <form onSubmit={submit}><Picker value={answer} setValue={setAnswer} disabled={!active} /><button className="lock" disabled={!answer.trim()}>LOCK IN GUESS</button><small>ONE GUESS THIS ROUND</small></form>}</section></div><footer>Wrong or out of time? The next clue starts automatically. <span>{[1, 2, 3, 4, 5].map(stage => <i className={stage === game.round_number ? 'on' : ''} key={stage} />)}</span></footer>{error && <p role="alert">{error}</p>}</section></main></>
}

export function BadlyExplainedApp({ path, navigate }: { path: string; navigate: (path: string) => void }) { const play = path.match(/^\/badly-explained\/play\/([^/]+)$/); const room = path.match(/^\/badly-explained\/room\/([^/]+)$/); if (play) return <Play id={play[1]} go={navigate} />; if (room) return <Lobby code={room[1]} go={navigate} />; return <Home go={navigate} /> }
