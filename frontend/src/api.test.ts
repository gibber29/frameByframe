import { afterEach, describe, expect, it, vi } from 'vitest'
import { preloadImage } from './api'

describe('image preloading', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('fetches the private image and waits for decode before returning', async () => {
    const decode = vi.fn().mockResolvedValue(undefined)
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, blob: () => Promise.resolve(new Blob(['frame'])) }))
    vi.stubGlobal('URL', { createObjectURL: vi.fn(() => 'blob:frame'), revokeObjectURL: vi.fn() })
    vi.stubGlobal('Image', class { complete = true; src = ''; decode = decode })
    await expect(preloadImage('/api/v1/game/session/image')).resolves.toBe('blob:frame')
    expect(fetch).toHaveBeenCalledWith('/api/v1/game/session/image', { credentials: 'include', signal: undefined })
    expect(decode).toHaveBeenCalledOnce()
  })
})
