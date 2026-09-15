import { describe, expect, it } from 'vitest'
import css from './styles.css?raw'

describe('responsive accessibility CSS', () => {
  it('keeps mobile game navigation visible and contains lobby codes and inputs', () => {
    const mobile = css.slice(css.indexOf('/* Keep both games reachable'))
    expect(mobile).toContain('@media (max-width: 850px)')
    expect(mobile).toContain('.album-nav>div.game-nav-links, .bad-nav>div.game-nav-links')
    expect(mobile).toContain('display:grid')
    expect(mobile).toContain('grid-row:2')
    expect(mobile).toContain('position:static')
    expect(mobile).toContain('.album-lobby .room-code')
    expect(mobile).toContain('font-size:clamp(1.25rem,6vw,2.75rem)')
    expect(mobile).toContain('text-overflow:ellipsis')
  })
  it('contains mobile-first breakpoints', () => {
    expect(css).toContain('@media (min-width: 560px)')
    expect(css).toContain('@media (min-width: 840px)')
  })
  it('disables animation and transitions for reduced motion', () => {
    expect(css).toContain('@media (prefers-reduced-motion: reduce)')
    expect(css).toContain('transition: none !important')
  })
  it('locks the collapsed landing page to the viewport and unlocks it for the expanded lobby form', () => {
    expect(css).toContain('.album-landing{height:calc(100dvh - 62px)')
    expect(css).toContain('.album-landing.is-expanded{height:auto;min-height:calc(100dvh - 62px);overflow:visible}')
  })
  it('reserves bottom background space and limits motion to card interaction', () => {
    expect(css).toContain('clamp(1.55rem,4vh,2.7rem)')
    expect(css).toContain('.album-mode:hover .daily-record')
    expect(css).toContain('.battle-mode:hover .wave i')
  })
})
