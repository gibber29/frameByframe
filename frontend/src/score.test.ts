import { describe, expect, it } from 'vitest'
import { centsToScore, formatScore, scoreToCents } from './score'

describe('normalized score formatting', () => {
  it('always displays exactly two decimal places', () => {
    expect(formatScore('36.8')).toBe('36.80')
    expect(formatScore('0')).toBe('0.00')
    expect(formatScore('50.00')).toBe('50.00')
  })

  it('tracks the live estimate in integer cents', () => {
    expect(scoreToCents('36.80')).toBe(3680)
    expect(centsToScore(3675)).toBe('36.75')
    expect(centsToScore(-5)).toBe('0.00')
  })
})
