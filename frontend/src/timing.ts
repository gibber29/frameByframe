export type SequenceResult = 'complete' | 'interrupted' | 'cancelled'

interface SequenceOptions {
  countdownMs: number
  durationMs: number
  signal: AbortSignal
  onCountdown: (value: number | null) => void
  onVisible: (visible: boolean) => void
}

function delay(ms: number, signal: AbortSignal): Promise<SequenceResult> {
  return new Promise(resolve => {
    if (signal.aborted) return resolve('cancelled')
    const timer = window.setTimeout(() => finish('complete'), ms)
    const hidden = () => document.hidden && finish('interrupted')
    const aborted = () => finish('cancelled')
    function finish(result: SequenceResult) {
      window.clearTimeout(timer)
      document.removeEventListener('visibilitychange', hidden)
      signal.removeEventListener('abort', aborted)
      resolve(result)
    }
    document.addEventListener('visibilitychange', hidden)
    signal.addEventListener('abort', aborted, { once: true })
  })
}

export async function runGlimpseSequence(options: SequenceOptions): Promise<SequenceResult> {
  const interval = options.countdownMs / 3
  for (const number of [3, 2, 1]) {
    options.onCountdown(number)
    const result = await delay(interval, options.signal)
    if (result !== 'complete') {
      options.onCountdown(null)
      options.onVisible(false)
      return result
    }
  }
  options.onCountdown(null)
  if (document.hidden || options.signal.aborted) return document.hidden ? 'interrupted' : 'cancelled'
  options.onVisible(true)
  const startedAt = performance.now()
  const result = await new Promise<SequenceResult>(resolve => {
    let frame = 0
    const hidden = () => document.hidden && finish('interrupted')
    const aborted = () => finish('cancelled')
    function finish(value: SequenceResult) {
      cancelAnimationFrame(frame)
      document.removeEventListener('visibilitychange', hidden)
      options.signal.removeEventListener('abort', aborted)
      resolve(value)
    }
    function measure(now: number) {
      if (now - startedAt >= options.durationMs) return finish('complete')
      frame = requestAnimationFrame(measure)
    }
    document.addEventListener('visibilitychange', hidden)
    options.signal.addEventListener('abort', aborted, { once: true })
    frame = requestAnimationFrame(measure)
  })
  options.onVisible(false)
  return result
}

export function waitUntil(isoTimestamp: string | null): Promise<void> {
  if (!isoTimestamp) return Promise.resolve()
  return new Promise(resolve => window.setTimeout(resolve, Math.max(0, Date.parse(isoTimestamp) - Date.now())))
}
