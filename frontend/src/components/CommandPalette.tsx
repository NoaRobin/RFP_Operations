/**
 * Palette de commandes (⌘K / Ctrl+K) : tout GRIMOIRE au clavier.
 * - ↵ ouvre / exécute ; ⇧↵ lance une automatisation directement avec ses valeurs par défaut.
 * - Index unifié : automatisations, recettes, exécutions récentes, pages, actions. Mémorise les choix récents.
 * Accessibilité : combobox + listbox ARIA, focus piégé par <dialog>, Échap pour fermer.
 */
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  CalendarCheck, CalendarClock, FileDown, Paintbrush, Clock, CornerDownLeft, FileSpreadsheet, History, Info, LayoutDashboard, Library, Lightbulb,
  MonitorSmartphone, Play, PlayCircle, Plug, RotateCcw, Search, UserRound, Home, FileQuestion, Tags, Activity,
} from 'lucide-react'
import { texts } from '../content/texts'
import { api, ApiError } from '../lib/api'
import { formatRelative, todayIso } from '../lib/format'
import { getLowPowerPref, setLowPowerPref, setSkipIntro } from '../lib/storage'
import type { Automation, Recipe, Run } from '../lib/types'
import { gsap } from '../motion/gsap'
import { d, dist, ease } from '../motion/tokens'
import { SpellIcon } from './ui/Icon'
import { StatusPill } from './ui/StatusPill'
import { useToast } from './ui/Toast'

type Section = 'recent' | 'automations' | 'recipes' | 'runs' | 'pages' | 'actions'

interface Command {
  id: string
  section: Section
  title: string
  subtitle?: string
  keywords?: string
  icon: ReactNode
  hint: string
  trailing?: ReactNode
  run: () => void | Promise<void>
  quick?: (() => Promise<void>) | null
}

const RECENT_KEY = 'rfppasenvie.palette.recent'

function readRecent(): string[] {
  try {
    return JSON.parse(localStorage.getItem(RECENT_KEY) ?? '[]')
  } catch {
    return []
  }
}
function pushRecent(id: string) {
  try {
    localStorage.setItem(RECENT_KEY, JSON.stringify([id, ...readRecent().filter((x) => x !== id)].slice(0, 6)))
  } catch {
    /* stockage indisponible */
  }
}

function normalize(text: string) {
  return text.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase()
}

/** Score flou : sous-chaîne > début de mot > sous-séquence. 0 = pas de correspondance. */
export function fuzzyScore(query: string, target: string): number {
  const q = normalize(query.trim())
  if (!q) return 1
  const t = normalize(target)
  const index = t.indexOf(q)
  if (index === 0) return 100 - t.length * 0.01
  if (index > 0) return (t[index - 1] === ' ' ? 80 : 60) - index * 0.1
  let ti = 0
  let gaps = 0
  for (const ch of q) {
    const found = t.indexOf(ch, ti)
    if (found === -1) return 0
    gaps += found - ti
    ti = found + 1
  }
  return Math.max(1, 40 - gaps)
}

/** Valeurs par défaut d'une automatisation, ou null si un paramètre obligatoire n'en a pas. */
function defaultParams(a: Automation): Record<string, unknown> | null {
  const params: Record<string, unknown> = {}
  for (const p of a.params) {
    let value = p.default
    if (p.type === 'date' && value === 'today') value = todayIso()
    if (p.required && (value === null || value === undefined || value === '')) return null
    params[p.name] = value ?? null
  }
  return params
}

export function CommandPalette({ open, onClose, onSuggest, onUser, onFabric }: { open: boolean; onClose: () => void; onSuggest: () => void; onUser: () => void; onFabric: () => void }) {
  const navigate = useNavigate()
  const toast = useToast()
  const dialog = useRef<HTMLDialogElement>(null)
  const panel = useRef<HTMLDivElement>(null)
  const list = useRef<HTMLUListElement>(null)
  const input = useRef<HTMLInputElement>(null)
  const [query, setQuery] = useState('')
  const [active, setActive] = useState(0)
  const [data, setData] = useState<{ automations: Automation[]; recipes: Recipe[]; runs: Run[] } | null>(null)
  const [busy, setBusy] = useState(false)

  // Ouverture / fermeture animées (dialog natif : focus piégé, Échap géré)
  useEffect(() => {
    const el = dialog.current
    if (!el) return
    if (open && !el.open) {
      el.showModal()
      setQuery('')
      setActive(0)
      gsap.fromTo(panel.current, { opacity: 0, y: -dist('lift'), scale: 0.98 }, { opacity: 1, y: 0, scale: 1, duration: d('base'), ease: ease.out })
      requestAnimationFrame(() => input.current?.focus())
      Promise.all([api.automations(), api.atelier.recipes(), api.runs('?limit=8')])
        .then(([a, r, runs]) => setData({ automations: a.automations, recipes: r, runs }))
        .catch(() => setData({ automations: [], recipes: [], runs: [] }))
    } else if (!open && el.open) {
      gsap.to(panel.current, { opacity: 0, y: -dist('nudge'), duration: d('fast'), ease: ease.in, onComplete: () => el.close() })
    }
  }, [open])

  const go = useCallback((path: string, state?: unknown) => {
    onClose()
    navigate(path, state ? { state } : undefined)
  }, [navigate, onClose])

  const commands = useMemo<Command[]>(() => {
    const items: Command[] = []
    for (const a of data?.automations ?? []) {
      const defaults = defaultParams(a)
      items.push({
        id: `a:${a.id}`, section: 'automations', title: a.name, subtitle: a.category,
        keywords: `${a.description} ${a.tags.join(' ')} ${a.id}`,
        icon: <SpellIcon name={a.icon} size={18} />, hint: texts.palette.hints.open,
        trailing: <span className="text-xs text-fg-3">{texts.library.minutesSaved(a.estimated_minutes_saved)}</span>,
        run: () => go(`/automatisations/${a.id}`, { preview: a }),
        quick: a.healthy && defaults ? async () => {
          const run = await api.run(a.id, defaults)
          toast('success', texts.palette.launched(a.name))
          go(`/executions/${run.id}`, { run })
        } : null,
      })
    }
    for (const r of data?.recipes ?? []) {
      items.push({
        id: `r:${r.id}`, section: 'recipes', title: r.name, subtitle: r.workbook ?? undefined, keywords: 'recette atelier excel rejouer',
        icon: <FileSpreadsheet size={18} />, hint: texts.palette.hints.replay,
        run: async () => {
          const run = await api.atelier.runRecipe(r.id!)
          go(`/executions/${run.id}`, { run })
        },
      })
    }
    for (const run of data?.runs ?? []) {
      items.push({
        id: `x:${run.id}`, section: 'runs', title: run.target_name, subtitle: `${run.user} · ${formatRelative(run.created_at)}`,
        keywords: `${run.status} execution`, icon: <Clock size={18} />, hint: texts.palette.hints.open,
        trailing: <StatusPill status={run.status} />, run: () => go(`/executions/${run.id}`),
      })
    }
    const pages: [string, string, ReactNode, string][] = [
      ['/', texts.nav.home, <Home size={18} />, 'accueil rfpasenviedetravailler'],
      ['/rfi', texts.nav.rfi, <FileQuestion size={18} />, 'rfi rfp questionnaire word excel remplir due diligence'],
      ['/qvidian', texts.nav.qvidian, <Library size={18} />, 'qvidian bibliotheque contenus erreurs carte reponses types modifier masse cockpit'],
      ['/qvidian/recherche', `${texts.nav.qvidian} · ${texts.qvidian.nav.recherche}`, <Library size={18} />, 'qvidian recherche semantique sens question reponse'],
      ['/qvidian/modifier', `${texts.nav.qvidian} · ${texts.qvidian.nav.modifier}`, <Library size={18} />, 'qvidian modifier masse ecrire mot de passe'],
      ['/qvidian/api', `${texts.nav.qvidian} · ${texts.qvidian.nav.api}`, <Library size={18} />, 'qvidian api moteur modeles telemetrie synchronisation'],
      ['/merge-codes', texts.nav.merge, <Tags size={18} />, 'qvidian merge codes annees experience bot'],
      ['/suivi-activite', texts.nav.suivi, <Activity size={18} />, 'suivi activite appels offres pilotage tryv2'],
      ['/documents', texts.nav.fundshop, <FileDown size={18} />, 'documents dic prospectus reporting sfdr telecharger'],
      ['/omni', texts.nav.omni, <CalendarCheck size={18} />, 'omni holdings performances mensuel'],
      ['/rfpascontente', texts.nav.rfpascontente, <Paintbrush size={18} />, 'defouloir peinture tarte deguisement rfpascontente'],
      ['/atelier', texts.nav.atelier, <FileSpreadsheet size={18} />, 'merlin atelier excel questionnaire remplir'],
      ['/atelier/fonds', texts.fundSheet.title, <FileSpreadsheet size={18} />, 'merlin fiche fonds part isin product info jump donnees export'],
      ['/qvidian/memoire', `QviAPI · ${texts.qvidian.nav.memoire}`, <Library size={18} />, 'memoire reponses anciennes reutilisation piliers a creer rafraichir'],
      ['/tableau-de-bord', texts.nav.dashboard, <LayoutDashboard size={18} />, 'dashboard statistiques planification'],
      ['/historique', texts.nav.history, <History size={18} />, 'registre executions'],
      ['/a-propos', texts.nav.about, <Info size={18} />, 'aide'],
    ]
    for (const [path, title, icon, keywords] of pages) {
      items.push({ id: `p:${path}`, section: 'pages', title, keywords, icon, hint: texts.palette.hints.go, run: () => go(path) })
    }
    items.push(
      { id: 'act:suggest', section: 'actions', title: texts.palette.actions.suggest, icon: <Lightbulb size={18} />, hint: texts.palette.hints.do, run: () => { onClose(); onSuggest() } },
      { id: 'act:fabric', section: 'actions', title: texts.palette.actions.fabric, keywords: 'fabric lakehouse connexion microsoft vscode', icon: <Plug size={18} />, hint: texts.palette.hints.do, run: () => { onClose(); onFabric() } },
      { id: 'act:user', section: 'actions', title: texts.palette.actions.user, icon: <UserRound size={18} />, hint: texts.palette.hints.do, run: () => { onClose(); onUser() } },
      {
        id: 'act:lowpower', section: 'actions', title: texts.palette.actions.lowPower, keywords: '3d 2d performance', icon: <MonitorSmartphone size={18} />,
        hint: texts.palette.hints.do, run: () => { setLowPowerPref(!getLowPowerPref()); onClose() },
      },
      { id: 'act:schedule', section: 'actions', title: texts.nav.dashboard + ' — ' + texts.dashboard.scheduled, keywords: 'planifier planification', icon: <CalendarClock size={18} />, hint: texts.palette.hints.go, run: () => go('/tableau-de-bord') },
      { id: 'act:intro', section: 'actions', title: texts.palette.actions.intro, icon: <RotateCcw size={18} />, hint: texts.palette.hints.do, run: () => { setSkipIntro(false); go('/intro') } },
    )
    return items
  }, [data, go, onClose, onSuggest, onUser, onFabric, toast])

  const results = useMemo(() => {
    const q = query.trim()
    if (!q) {
      const recent = readRecent().map((id) => commands.find((c) => c.id === id)).filter(Boolean) as Command[]
      const recentIds = new Set(recent.map((c) => c.id))
      return [
        ...recent.map((c) => ({ ...c, section: 'recent' as Section })),
        ...commands.filter((c) => !recentIds.has(c.id) && c.section !== 'runs').slice(0, 14),
      ]
    }
    return commands
      .map((c) => ({ c, score: Math.max(fuzzyScore(q, c.title) * 1.2, fuzzyScore(q, `${c.subtitle ?? ''} ${c.keywords ?? ''}`) * 0.7) }))
      .filter((x) => x.score > 0)
      .sort((a, b) => b.score - a.score)
      .slice(0, 30)
      .reduce<{ section: Section; items: Command[] }[]>((groups, x) => {
        const group = groups.find((g) => g.section === x.c.section)
        if (group) group.items.push(x.c)
        else groups.push({ section: x.c.section, items: [x.c] })
        return groups
      }, [])
      .flatMap((g) => g.items)
  }, [commands, query])

  useEffect(() => setActive(0), [query])
  useLayoutEffect(() => {
    list.current?.querySelector(`[data-index="${active}"]`)?.scrollIntoView({ block: 'nearest' })
  }, [active])

  const execute = async (command: Command | undefined, quick = false) => {
    if (!command || busy) return
    pushRecent(command.id)
    setBusy(true)
    try {
      if (quick && command.quick) await command.quick()
      else await command.run()
    } catch (e) {
      toast('error', (e as ApiError).message ?? texts.errors.generic, (e as ApiError).hint)
    } finally {
      setBusy(false)
    }
  }

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setActive((i) => Math.min(results.length - 1, i + 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setActive((i) => Math.max(0, i - 1))
    } else if (e.key === 'Home') {
      setActive(0)
    } else if (e.key === 'End') {
      setActive(results.length - 1)
    } else if (e.key === 'Enter') {
      e.preventDefault()
      execute(results[active], e.shiftKey)
    }
  }

  const current = results[active]
  let lastSection: Section | null = null

  return (
    <dialog
      ref={dialog}
      aria-label={texts.palette.label}
      onCancel={(e) => {
        e.preventDefault()
        onClose()
      }}
      onClick={(e) => e.target === dialog.current && onClose()}
      className="m-0 mx-auto mt-[12vh] w-[min(92vw,42rem)] max-w-none bg-transparent p-0 backdrop:bg-transparent"
    >
      {open && (
        <div ref={panel} className="glass overflow-hidden rounded-2xl shadow-[var(--shadow-deep),var(--shadow-glow-magic)]">
          <div className="flex items-center gap-3 border-b hairline px-5">
            <Search size={18} className="shrink-0 text-sun-300" aria-hidden="true" />
            <input
              ref={input}
              role="combobox"
              aria-expanded="true"
              aria-controls="palette-list"
              aria-activedescendant={current ? `palette-${active}` : undefined}
              aria-autocomplete="list"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={onKeyDown}
              placeholder={texts.palette.placeholder}
              className="h-16 flex-1 bg-transparent text-lg text-fg placeholder:text-fg-3 focus:outline-none"
            />
            <kbd className="rounded-md border border-line-strong px-2 py-0.5 font-mono text-[0.7rem] text-fg-3">Esc</kbd>
          </div>

          <ul ref={list} id="palette-list" role="listbox" aria-label={texts.palette.label} className="max-h-[52vh] overflow-y-auto p-2" data-lenis-prevent>
            {!data && <li className="px-4 py-6 text-sm text-fg-3">{texts.palette.loading}</li>}
            {data && results.length === 0 && <li className="px-4 py-6 text-sm text-fg-2">{texts.palette.empty}</li>}
            {results.map((c, i) => {
              const header = c.section !== lastSection ? texts.palette.sections[c.section] : null
              lastSection = c.section
              const selected = i === active
              return (
                <li key={`${c.section}-${c.id}`} role="presentation">
                  {header && <p className="px-3 pb-1 pt-3 font-mono text-[0.65rem] uppercase tracking-[0.2em] text-fg-3" aria-hidden="true">{header}</p>}
                  <div
                    id={`palette-${i}`}
                    data-index={i}
                    role="option"
                    aria-selected={selected}
                    onMouseMove={() => active !== i && setActive(i)}
                    onClick={(e) => execute(c, e.shiftKey)}
                    className={`group flex cursor-pointer items-center gap-3 rounded-xl px-3 py-2.5 transition-colors duration-[var(--duration-instant)] ${
                      selected ? 'bg-fg/[0.07] shadow-[inset_0_0_0_1px_var(--color-line-strong)]' : ''}`}
                  >
                    <span className={`grid size-9 shrink-0 place-items-center rounded-lg border ${selected ? 'border-sun-400/50 text-sun-300' : 'border-line text-magic-300'}`}>{c.icon}</span>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-[0.95rem] text-fg">{c.title}</span>
                      {c.subtitle && <span className="block truncate text-xs text-fg-3">{c.subtitle}</span>}
                    </span>
                    {c.trailing}
                    {selected && (
                      <span className="hidden items-center gap-1 text-xs text-fg-2 sm:flex">
                        {c.quick && <span className="mr-2 inline-flex items-center gap-1 text-sun-300"><PlayCircle size={14} aria-hidden="true" />⇧↵</span>}
                        {c.hint} <CornerDownLeft size={13} aria-hidden="true" />
                      </span>
                    )}
                  </div>
                </li>
              )
            })}
          </ul>

          <footer className="flex flex-wrap items-center gap-x-5 gap-y-1 border-t hairline px-5 py-3 text-xs text-fg-3">
            <span><kbd className="font-mono text-fg-2">↑↓</kbd> {texts.palette.footer.navigate}</span>
            <span><kbd className="font-mono text-fg-2">↵</kbd> {texts.palette.footer.select}</span>
            <span className="inline-flex items-center gap-1"><Play size={11} aria-hidden="true" /><kbd className="font-mono text-fg-2">⇧↵</kbd> {texts.palette.footer.quick}</span>
            <span className="ml-auto" aria-live="polite">
              {current?.section === 'automations' && !current.quick ? texts.palette.quickRunUnavailable : current?.quick ? texts.palette.quickRun : ''}
            </span>
          </footer>
        </div>
      )}
    </dialog>
  )
}
