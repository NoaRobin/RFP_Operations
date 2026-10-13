/**
 * RFPascontente : le défouloir 3D. On déguise la tête sur mesure, puis on lui lance peinture, verres, tomates, œufs,
 * tartes, tasses et classeurs. Les motifs de colère tournent tout seuls ; la tête répond à chaque coup.
 * Page à part : le fun ne bloque jamais une action. Mouvement réduit respecté (ni secousse, ni gouttelettes, ni pop).
 */
import { useEffect, useRef, useState } from 'react'
import { Brush, Expand, Shirt, Shuffle, Volume2, VolumeX } from 'lucide-react'
import { Button } from '../components/ui/Button'
import { texts } from '../content/texts'
import { prefersReducedMotion } from '../motion/tokens'
import type { Defouloir, Weapon } from '../components/three/defouloir/engine'
import { DEFAULT_COSTUME, EMPTY, ITEMS, randomCostume, SLOTS, type Costume, type Slot } from '../components/three/defouloir/costume'

const T = texts.rfpascontente
const C = T.costume
const CHOICES: (Weapon | 'hasard')[] = ['peinture', 'verre', 'tomate', 'oeuf', 'tarte', 'tasse', 'classeur', 'hasard']
const PAINTS = ['arc-en-ciel', '#ff3d7f', '#ffd23f', '#3ddc97', '#4cc9f0', '#9b5de5', '#1b1530']
const COSTUME_KEY = 'rfppasenvie.costume'

function webgl() {
  try {
    const c = document.createElement('canvas')
    return !!(c.getContext('webgl2') || c.getContext('webgl'))
  } catch {
    return false
  }
}

function savedCostume(): Costume {
  try {
    const raw = window.localStorage.getItem(COSTUME_KEY)
    if (raw) return { ...EMPTY, ...(JSON.parse(raw) as Partial<Costume>) }
  } catch {
    /* stockage indisponible : tenue par défaut */
  }
  return DEFAULT_COSTUME
}

/** Tirage sans répétition immédiate. */
function nextIndex(n: number, current: number) {
  if (n < 2) return 0
  let i = current
  while (i === current) i = Math.floor(Math.random() * n)
  return i
}

export default function RFPascontente() {
  const stage = useRef<HTMLDivElement>(null)
  const frame = useRef<HTMLDivElement>(null)
  const engine = useRef<Defouloir | null>(null)
  const [state, setState] = useState<'loading' | 'ready' | 'error' | 'nogl'>('loading')
  const [weapon, setWeapon] = useState<Weapon | 'hasard'>('peinture')
  const [paint, setPaint] = useState('arc-en-ciel')
  const [sound, setSound] = useState(true)
  const [hits, setHits] = useState(0)
  const [costume, setCostume] = useState<Costume>(savedCostume)
  const [knocked, setKnocked] = useState<Slot[]>([])
  const [reason, setReason] = useState(0)
  const [bubble, setBubble] = useState<{ text: string; key: number } | null>(null)
  const [combo, setCombo] = useState<{ n: number; key: number } | null>(null)
  const streak = useRef({ n: 0, last: 0 })
  const bubbleTimer = useRef(0)
  const lastBubble = useRef(0)
  const reduced = prefersReducedMotion()

  const say = (text: string, force = false) => {
    const now = performance.now()
    if (!force && now - lastBubble.current < 1400) return
    lastBubble.current = now
    setBubble({ text, key: now })
    window.clearTimeout(bubbleTimer.current)
    bubbleTimer.current = window.setTimeout(() => setBubble(null), 2600)
  }

  useEffect(() => {
    document.title = `${T.title} · RFP pas envie de travailler`
    if (!stage.current) return
    if (!webgl()) { setState('nogl'); return }
    let alive = true
    let instance: Defouloir | null = null
    void import('../components/three/defouloir/engine').then(({ Defouloir }) => {
      if (!alive || !stage.current) return
      instance = new Defouloir(stage.current, {
        reduced,
        onReady: () => alive && setState('ready'),
        onError: () => alive && setState('error'),
        onHit: () => {
          if (!alive) return
          setHits((n) => n + 1)
          const now = performance.now()
          const s = streak.current
          s.n = now - s.last < 1600 ? s.n + 1 : 1
          s.last = now
          if (s.n >= 3) setCombo({ n: s.n, key: now })
          say(T.reactions[Math.floor(Math.random() * T.reactions.length)])
        },
        onKnock: (slot) => {
          if (!alive) return
          setKnocked((k) => [...new Set([...k, slot])])
          if (T.knocked[slot]) say(T.knocked[slot], true)
        },
      })
      instance.setCostume(costume)
      engine.current = instance
    })
    return () => { alive = false; instance?.dispose(); engine.current = null; window.clearTimeout(bubbleTimer.current) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Motifs de colère : un nouveau toutes les 7 secondes
  useEffect(() => {
    setReason(Math.floor(Math.random() * T.reasons.length))
    const id = window.setInterval(() => setReason((r) => nextIndex(T.reasons.length, r)), 7000)
    return () => window.clearInterval(id)
  }, [])

  useEffect(() => {
    if (!combo) return
    const id = window.setTimeout(() => setCombo(null), 1500)
    return () => window.clearTimeout(id)
  }, [combo])

  useEffect(() => { if (engine.current) engine.current.weapon = weapon }, [weapon, state])
  useEffect(() => { if (engine.current) engine.current.paint = paint }, [paint, state])
  useEffect(() => { if (engine.current) engine.current.sounds.enabled = sound }, [sound, state])
  useEffect(() => {
    engine.current?.setCostume(costume)
    try { window.localStorage.setItem(COSTUME_KEY, JSON.stringify(costume)) } catch { /* stockage indisponible */ }
  }, [costume])

  const putBack = () => {
    engine.current?.setCostume(costume, true)
    setKnocked([])
  }
  const dress = (c: Costume) => { setCostume(c); setKnocked([]) }
  const setSlot = (slot: Slot, patch: Partial<Costume[Slot]>) => setCostume((c) => ({ ...c, [slot]: { ...c[slot], ...patch } }))
  const clean = () => {
    engine.current?.clean()
    setHits(0)
    setKnocked([])
    streak.current = { n: 0, last: 0 }
    setReason((r) => nextIndex(T.reasons.length, r))
  }

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement)?.closest('input, textarea, select, [contenteditable]')) return
      const n = Number(e.key)
      if (n >= 1 && n <= CHOICES.length) setWeapon(CHOICES[n - 1])
      if (e.key.toLowerCase() === 'n') clean()
      if (e.key.toLowerCase() === 'd') dress(randomCostume())
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  })

  const stress = Math.max(0, 100 - hits * 3)
  const fullscreen = () => {
    if (document.fullscreenElement) void document.exitFullscreen()
    else void frame.current?.requestFullscreen?.()
  }

  return (
    <div className="mx-auto w-[min(100%-2rem,82rem)] pt-10 sm:pt-14">
      <header className="max-w-3xl">
        <p className="eyebrow"><Brush size={13} aria-hidden="true" />{T.eyebrow}</p>
        <h1 className="mt-4 text-[clamp(2.2rem,5.5vw,4rem)] font-bold">{T.title}</h1>
        <div className="mt-4 flex flex-wrap items-start gap-3">
          <p className="min-h-[3.5rem] flex-1 text-lg font-semibold text-fg-2" aria-live="polite">
            <span key={reason} className={reduced ? '' : 'animate-[fadeIn_.4s_ease-out]'}>{T.reasons[reason]}</span>
          </p>
          <Button size="sm" variant="secondary" icon={<Shuffle size={16} />} onClick={() => setReason((r) => nextIndex(T.reasons.length, r))}>{T.anotherReason}</Button>
        </div>
      </header>

      <div ref={frame} className="mt-6 flex flex-col overflow-hidden rounded-[var(--radius-card)] border-[2.5px] border-fg bg-card shadow-[var(--shadow-pop-lg)]">
        <div className="flex flex-wrap items-center gap-2 border-b-2 border-fg bg-card p-3" role="toolbar" aria-label={T.title}>
          {CHOICES.map((w, i) => (
            <button key={w} onClick={() => setWeapon(w)} aria-pressed={weapon === w} title={`${T.weapons[w]} (${i + 1})`}
              className={`flex items-center gap-1.5 rounded-full border-2 border-fg px-3 py-1.5 text-sm font-bold transition-[transform,box-shadow] motion-safe:hover:-translate-y-0.5 ${weapon === w ? 'bg-sun-400 shadow-[2px_2px_0_0_var(--color-fg)]' : 'bg-card'}`}>
              <span aria-hidden="true" className="text-lg leading-none">{T.emoji[w]}</span>{T.weapons[w]}
            </button>
          ))}
          <div className="ml-auto flex flex-wrap items-center gap-2">
            <Button size="sm" variant="secondary" onClick={() => setSound((s) => !s)} icon={sound ? <Volume2 size={16} /> : <VolumeX size={16} />} aria-pressed={sound}>{T.sound}</Button>
            <Button size="sm" variant="secondary" onClick={fullscreen} icon={<Expand size={16} />}>{T.fullscreen}</Button>
            <Button size="sm" variant="secondary" onClick={clean}>{T.clean}</Button>
          </div>
        </div>
        {(weapon === 'peinture' || weapon === 'hasard') && (
          <div className="flex flex-wrap items-center gap-2 border-b-2 border-fg bg-card-2 px-3 py-2" role="radiogroup" aria-label={T.paint}>
            <span className="text-xs font-bold uppercase tracking-wider text-fg-3">{T.paint}</span>
            {PAINTS.map((c) => (
              <button key={c} role="radio" aria-checked={paint === c} onClick={() => setPaint(c)} title={c === 'arc-en-ciel' ? T.rainbow : c}
                aria-label={c === 'arc-en-ciel' ? T.rainbow : c}
                className={`size-7 rounded-full border-2 border-fg ${paint === c ? 'ring-4 ring-magic-400/60' : ''}`}
                style={{ background: c === 'arc-en-ciel' ? 'conic-gradient(#ff3d7f,#ffd23f,#3ddc97,#4cc9f0,#9b5de5,#ff3d7f)' : c }} />
            ))}
          </div>
        )}
        <div className="relative min-h-[420px] bg-[radial-gradient(circle_at_50%_30%,#fffaf0,#efe6ff)]" style={{ height: 'min(72vh, 760px)' }}>
          <div ref={stage} className="absolute inset-0" />
          {state !== 'ready' && (
            <div className="pointer-events-none absolute inset-0 grid place-items-center p-6 text-center font-display text-xl font-semibold text-fg-2">
              {state === 'loading' ? T.loading : state === 'error' ? T.error : T.noWebgl}
            </div>
          )}
          <div className="pointer-events-none absolute left-3 top-3 rounded-2xl border-2 border-fg bg-card/90 px-4 py-2 shadow-[3px_3px_0_0_var(--color-fg)]">
            <p className="text-xs font-bold uppercase tracking-wider text-fg-3">{T.hits}</p>
            <p className="font-display text-3xl font-bold tabular-nums">{hits}</p>
          </div>
          <div className="pointer-events-none absolute right-3 top-3 w-44 rounded-2xl border-2 border-fg bg-card/90 px-4 py-2 shadow-[3px_3px_0_0_var(--color-fg)]">
            <p className="text-xs font-bold uppercase tracking-wider text-fg-3">{T.stress} · {stress} %</p>
            <div className="mt-1.5 h-3 overflow-hidden rounded-full border-2 border-fg bg-card-2" role="meter" aria-valuemin={0} aria-valuemax={100} aria-valuenow={stress} aria-label={T.stress}>
              <div className="h-full bg-bubble-400 transition-[width] duration-300" style={{ width: `${stress}%` }} />
            </div>
            <p className="mt-1 text-xs font-semibold text-fg-2">{T.calm(hits)}</p>
          </div>
          {bubble && (
            <div key={bubble.key} role="status"
              className={`pointer-events-none absolute left-1/2 top-[12%] max-w-[min(26rem,80%)] -translate-x-1/2 rounded-3xl border-[2.5px] border-fg bg-card px-5 py-3 text-center font-display text-lg font-semibold shadow-[4px_4px_0_0_var(--color-fg)] ${reduced ? '' : 'animate-[pop_.35s_cubic-bezier(.34,1.56,.64,1)]'}`}>
              {bubble.text}
              <span aria-hidden="true" className="absolute -bottom-[11px] left-1/2 size-5 -translate-x-1/2 rotate-45 border-b-[2.5px] border-r-[2.5px] border-fg bg-card" />
            </div>
          )}
          {combo && (
            <p key={combo.key} aria-live="polite"
              className={`pointer-events-none absolute bottom-6 left-1/2 -translate-x-1/2 -rotate-3 rounded-full border-[2.5px] border-fg bg-sun-400 px-5 py-2 font-display text-2xl font-bold shadow-[4px_4px_0_0_var(--color-fg)] ${reduced ? '' : 'animate-[pop_.35s_cubic-bezier(.34,1.56,.64,1)]'}`}>
              {T.combo(combo.n)}
            </p>
          )}
          {knocked.length > 0 && (
            <div className="absolute bottom-3 right-3">
              <Button size="sm" variant="secondary" icon={<Shirt size={16} />} onClick={putBack}>{C.putBack}</Button>
            </div>
          )}
        </div>
        <p className="border-t-2 border-fg bg-card px-3 py-2 text-xs font-semibold text-fg-2">{T.help}</p>
      </div>

      <section className="glass mt-6 rounded-[var(--radius-card)] p-5 sm:p-6" aria-labelledby="costume-title">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h2 id="costume-title" className="flex items-center gap-2 text-2xl"><Shirt size={22} aria-hidden="true" />{C.title}</h2>
            <p className="mt-1 text-sm font-semibold text-fg-2">{C.lead}</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button size="sm" variant="secondary" icon={<Shuffle size={16} />} onClick={() => dress(randomCostume())}>{C.random}</Button>
            <Button size="sm" variant="secondary" onClick={() => dress(EMPTY)}>{C.strip}</Button>
          </div>
        </div>
        <div className="mt-5 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {SLOTS.map((slot) => {
            const style = costume[slot]
            return (
              <fieldset key={slot} className="rounded-2xl border-2 border-fg bg-card p-3">
                <legend className="px-1 font-display text-lg font-semibold">{C.slots[slot]}</legend>
                <div className="flex flex-wrap gap-1.5">
                  {[null, ...ITEMS[slot].map((i) => i.id)].map((id) => (
                    <button key={id ?? 'none'} aria-pressed={style.item === id}
                      onClick={() => setSlot(slot, { item: id, ...(id && style.item !== id ? { color: ITEMS[slot].find((i) => i.id === id)!.color } : {}) })}
                      className={`rounded-full border-2 border-fg px-2.5 py-1 text-xs font-bold ${style.item === id ? 'bg-sun-400' : 'bg-card'}`}>
                      {id ? C.items[`${slot}.${id}`] : C.none}
                    </button>
                  ))}
                </div>
                {style.item && (
                  <div className="mt-3 flex items-center gap-3">
                    <label className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-fg-3">
                      {C.color}
                      <input type="color" value={style.color} onChange={(e) => setSlot(slot, { color: e.target.value })}
                        className="size-8 cursor-pointer rounded-full border-2 border-fg bg-card p-0.5" />
                    </label>
                    <label className="flex flex-1 items-center gap-2 text-xs font-bold uppercase tracking-wider text-fg-3">
                      {C.size}
                      <input type="range" min={0.7} max={1.5} step={0.05} value={style.size} onChange={(e) => setSlot(slot, { size: Number(e.target.value) })}
                        className="flex-1 accent-[var(--color-magic-400)]" />
                    </label>
                  </div>
                )}
              </fieldset>
            )
          })}
        </div>
      </section>
      <p className="mt-3 text-xs font-semibold text-fg-3">{T.credits}</p>
    </div>
  )
}
