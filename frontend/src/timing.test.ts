import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { runGlimpseSequence } from './timing'

describe('glimpse timing', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => window.setTimeout(() => callback(performance.now()), 10))
    vi.stubGlobal('cancelAnimationFrame', (id: number) => window.clearTimeout(id))
    Object.defineProperty(document, 'hidden', { configurable: true, value: false })
  })
  afterEach(() => vi.useRealTimers())

  it('runs 3-2-1 then hides the glimpse after its exact performance window', async () => {
    const countdown: Array<number | null> = []
    const visibility: boolean[] = []
    const promise = runGlimpseSequence({
      countdownMs: 1800, durationMs: 300, signal: new AbortController().signal,
      onCountdown: value => countdown.push(value), onVisible: value => visibility.push(value),
    })
    await vi.advanceTimersByTimeAsync(2110)
    await expect(promise).resolves.toBe('complete')
    expect(countdown).toEqual([3, 2, 1, null])
    expect(visibility).toEqual([true, false])
  })

  it('cancels visibility when the tab is hidden without restarting', async () => {
    const visibility: boolean[] = []
    const promise = runGlimpseSequence({
      countdownMs: 1800, durationMs: 300, signal: new AbortController().signal,
      onCountdown: () => undefined, onVisible: value => visibility.push(value),
    })
    await vi.advanceTimersByTimeAsync(1900)
    Object.defineProperty(document, 'hidden', { configurable: true, value: true })
    document.dispatchEvent(new Event('visibilitychange'))
    await expect(promise).resolves.toBe('interrupted')
    expect(visibility.at(-1)).toBe(false)
  })
})
