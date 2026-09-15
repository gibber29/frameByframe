export const SCORE_SCALE = '50.00'

export function formatScore(value: string | number): string {
  return Number(value).toFixed(2)
}

export function scoreToCents(value: string | number): number {
  return Math.round(Number(value) * 100)
}

export function centsToScore(value: number): string {
  return (Math.max(0, value) / 100).toFixed(2)
}
