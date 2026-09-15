import type { Category, GameResult, GameState, Glimpse, GuessOutcome, Hint } from './types'
import type { AlbumAttempt, AlbumHome, AlbumLeaderboard, AlbumRoom } from './types'

const API_BASE = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '')

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message)
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    credentials: 'include',
    ...init,
    headers: { 'Content-Type': 'application/json', ...init?.headers },
  })
  if (!response.ok) {
    let message = response.statusText
    try {
      const detail = (await response.json()).detail
      message = Array.isArray(detail) ? detail.map(item => item.msg || String(item)).join('; ') : detail || message
    } catch { /* use status text */ }
    if (response.status >= 500) message = 'The server could not finish that request. Your saved progress is safe; please retry.'
    throw new ApiError(response.status, message)
  }
  return response.json() as Promise<T>
}

export const gameApi = {
  categories: () => request<Category[]>('/api/v1/game/categories'),
  start: (category: string) => request<GameState>('/api/v1/game/start', {
    method: 'POST', body: JSON.stringify({ category }),
  }),
  state: (sessionId: string) => request<GameState>(`/api/v1/game/${sessionId}/state`),
  glimpse: (sessionId: string) => request<Glimpse>(`/api/v1/game/${sessionId}/glimpse`, { method: 'POST' }),
  guess: (sessionId: string, title: string) => request<GuessOutcome>(`/api/v1/game/${sessionId}/guess`, {
    method: 'POST', body: JSON.stringify({ title }),
  }),
  crypticHint: (sessionId: string) => request<Hint>(`/api/v1/game/${sessionId}/hints/cryptic`, { method: 'POST' }),
  titlePatternHint: (sessionId: string) => request<Hint>(`/api/v1/game/${sessionId}/hints/title-pattern`, { method: 'POST' }),
  result: (sessionId: string) => request<GameResult>(`/api/v1/game/${sessionId}/result`),
}

export const albumnesiaApi = {
  home: () => request<AlbumHome>('/api/v1/albumnesia/home'),
  startDaily: () => request<AlbumAttempt>('/api/v1/albumnesia/daily/start', { method: 'POST' }),
  titles: (query = '', limit = 30) => request<string[]>(`/api/v1/albumnesia/titles?q=${encodeURIComponent(query)}&limit=${limit}`),
  createRoom: (roomName: string, displayName: string) => request<AlbumRoom>('/api/v1/albumnesia/rooms', {
    method: 'POST', body: JSON.stringify({ room_name: roomName, display_name: displayName }),
  }),
  room: (code: string) => request<AlbumRoom>(`/api/v1/albumnesia/rooms/${encodeURIComponent(code)}`),
  joinRoom: (code: string, displayName: string) => request<AlbumRoom>(`/api/v1/albumnesia/rooms/${encodeURIComponent(code)}/join`, {
    method: 'POST', body: JSON.stringify({ display_name: displayName }),
  }),
  continueRoom: (code: string) => request<AlbumAttempt>(`/api/v1/albumnesia/rooms/${encodeURIComponent(code)}/continue`, { method:'POST' }),
  leaderboard: (code: string) => request<AlbumLeaderboard>(`/api/v1/albumnesia/rooms/${encodeURIComponent(code)}/leaderboard`),
  state: (id: string) => request<AlbumAttempt>(`/api/v1/albumnesia/attempts/${id}`),
  ready: (id: string) => request<AlbumAttempt>(`/api/v1/albumnesia/attempts/${id}/ready`, { method: 'POST' }),
  submit: (id: string, title: string) => request<AlbumAttempt>(`/api/v1/albumnesia/attempts/${id}/submit`, {
    method: 'POST', body: JSON.stringify({ title }),
  }),
}

export const badlyApi = {
  home:()=>request<import('./types').BadlyHome>('/api/v1/badly-explained/home'),
  titles:(q='')=>request<string[]>(`/api/v1/badly-explained/titles?q=${encodeURIComponent(q)}`),
  startDaily:()=>request<import('./types').BadlyState>('/api/v1/badly-explained/daily/start',{method:'POST'}),
  state:(id:string)=>request<import('./types').BadlyState>(`/api/v1/badly-explained/attempts/${id}`),
  ready:(id:string)=>request<import('./types').BadlyState>(`/api/v1/badly-explained/attempts/${id}/ready`,{method:'POST'}),
  submit:(id:string,title:string)=>request<import('./types').BadlyState>(`/api/v1/badly-explained/attempts/${id}/submit`,{method:'POST',body:JSON.stringify({title})}),
  createRoom:(room_name:string,display_name:string)=>request<import('./types').BadlyRoom>('/api/v1/badly-explained/rooms',{method:'POST',body:JSON.stringify({room_name,display_name})}),
  room:(code:string)=>request<import('./types').BadlyRoom>(`/api/v1/badly-explained/rooms/${code}`),
  join:(code:string,display_name:string)=>request<import('./types').BadlyRoom>(`/api/v1/badly-explained/rooms/${code}/join`,{method:'POST',body:JSON.stringify({display_name})}),
  continue:(code:string)=>request<import('./types').BadlyState>(`/api/v1/badly-explained/rooms/${code}/continue`,{method:'POST'}),
  board:(code:string)=>request<import('./types').BadlyBoard>(`/api/v1/badly-explained/rooms/${code}/leaderboard`),
}

export async function preloadImage(path: string, signal?: AbortSignal): Promise<string> {
  const response = await fetch(`${API_BASE}${path}`, { credentials: 'include', signal })
  if (!response.ok) throw new ApiError(response.status, 'Unable to load today’s frame')
  const objectUrl = URL.createObjectURL(await response.blob())
  const image = new Image()
  image.src = objectUrl
  try {
    if (!image.complete) {
      await new Promise<void>((resolve, reject) => {
        image.onload = () => resolve()
        image.onerror = () => reject(new Error('Unable to decode today’s frame'))
      })
    }
    if (image.decode) await image.decode()
    return objectUrl
  } catch (error) {
    URL.revokeObjectURL(objectUrl)
    throw error
  }
}
