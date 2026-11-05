/** Explorateur : arbre des dossiers, table triable (usage, dates, défauts), sélection pour corriger ou analyser. */
import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowDownUp, ChevronDown, ChevronRight, Folder, FolderOpen, Search } from 'lucide-react'
import { ago } from '../../../components/qvidian/Bits'
import { Button } from '../../../components/ui/Button'
import { Switch, TextInput } from '../../../components/ui/Field'
import { texts } from '../../../content/texts'
import { api } from '../../../lib/api'
import type { QvidianFolder, QvidianItem } from '../../../lib/types'
import { useQvidian } from '../context'

const Q = texts.qvidian
const PAGE = 80
type SortKey = 'title' | 'uses' | 'last' | 'modified' | 'issues'
interface Node { name: string; path: string; children: Node[]; count: number }

function tree(folders: QvidianFolder[], items: QvidianItem[]): Node {
  const root: Node = { name: Q.allFolders, path: '', children: [], count: items.length }
  const byPath = new Map<string, Node>([['', root]])
  const paths = new Set(folders.map((f) => f.path).filter(Boolean))
  items.forEach((i) => i.folder_path && paths.add(i.folder_path))
  ;[...paths].sort().forEach((p) => {
    const parts = p.split(' / ')
    parts.forEach((_, k) => {
      const path = parts.slice(0, k + 1).join(' / ')
      if (byPath.has(path)) return
      const node: Node = { name: parts[k], path, children: [], count: 0 }
      byPath.get(parts.slice(0, k).join(' / '))!.children.push(node)
      byPath.set(path, node)
    })
  })
  byPath.forEach((n) => { if (n.path) n.count = items.filter((i) => i.folder_path === n.path || i.folder_path.startsWith(`${n.path} / `)).length })
  return root
}

function TreeNode({ node, current, onPick, depth = 0 }: { node: Node; current: string; onPick: (p: string) => void; depth?: number }) {
  const [open, setOpen] = useState(depth < 1 || current.startsWith(node.path))
  const active = current === node.path
  return (
    <li>
      <div className={`flex items-center gap-1 rounded-lg pr-2 ${active ? 'bg-sun-400/50' : 'hover:bg-card-2'}`} style={{ paddingLeft: depth * 12 }}>
        {node.children.length > 0 ? (
          <button onClick={() => setOpen(!open)} aria-label={open ? 'Replier' : 'Déplier'} aria-expanded={open} className="p-1">{open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}</button>
        ) : <span className="w-[22px]" />}
        <button onClick={() => onPick(node.path)} className="flex min-w-0 flex-1 items-center gap-1.5 py-1 text-left text-sm font-semibold">
          {active ? <FolderOpen size={14} aria-hidden="true" /> : <Folder size={14} aria-hidden="true" />}
          <span className="truncate">{node.name}</span>
          <span className="ml-auto text-xs tabular-nums text-fg-3">{node.count}</span>
        </button>
      </div>
      {open && node.children.length > 0 && (
        <ul>{node.children.map((c) => <TreeNode key={c.path} node={c} current={current} onPick={onPick} depth={depth + 1} />)}</ul>
      )}
    </li>
  )
}

export function LibraryView() {
  const { audit, selected, toggle, select } = useQvidian()
  const [folders, setFolders] = useState<QvidianFolder[]>([])
  const [folder, setFolder] = useState('')
  const [words, setWords] = useState('')
  const [onlyIssues, setOnlyIssues] = useState(false)
  const [sort, setSort] = useState<{ key: SortKey; desc: boolean }>({ key: 'uses', desc: true })
  const [shown, setShown] = useState(PAGE)
  useEffect(() => { api.qvidian.folders().then(setFolders).catch(() => setFolders([])) }, [audit?.contents])
  const items = audit?.items ?? []
  const root = useMemo(() => tree(folders, items), [folders, items])
  const rows = useMemo(() => {
    const w = words.trim().toLowerCase()
    const list = items.filter((i) => (!folder || i.folder_path === folder || i.folder_path.startsWith(`${folder} / `))
      && (!onlyIssues || i.issues.length > 0) && (!w || `${i.id} ${i.title} ${i.text}`.toLowerCase().includes(w)))
    const val = (i: QvidianItem): string | number => ({ title: i.title.toLowerCase(), uses: i.times_used, last: i.last_used ?? '', modified: i.modified ?? '', issues: i.issues.length })[sort.key]
    return [...list].sort((a, b) => (val(a) < val(b) ? -1 : val(a) > val(b) ? 1 : 0) * (sort.desc ? -1 : 1))
  }, [items, folder, words, onlyIssues, sort])
  useEffect(() => setShown(PAGE), [folder, words, onlyIssues, sort])
  const head = (key: SortKey) => (
    <th scope="col" className="p-2 text-left">
      <button onClick={() => setSort((s) => ({ key, desc: s.key === key ? !s.desc : key !== 'title' }))} className="inline-flex items-center gap-1 text-xs font-bold uppercase tracking-wider text-fg-3 hover:text-fg">
        {Q.columns[key]}<ArrowDownUp size={11} aria-hidden="true" className={sort.key === key ? 'text-fg' : 'opacity-40'} />
      </button>
    </th>
  )
  return (
    <div className="flex flex-col gap-4">
      <header data-enter>
        <h1 className="text-2xl font-semibold">{Q.libraryTitle}</h1>
        <p className="mt-2 text-sm font-semibold text-fg-2">{Q.libraryLead}</p>
      </header>
      <div className="grid gap-4 xl:grid-cols-[18rem_minmax(0,1fr)]">
        <nav data-enter aria-label="Dossiers" className="h-fit max-h-[70vh] overflow-y-auto rounded-[var(--radius-card)] border-2 border-fg bg-card p-3 xl:sticky xl:top-24" data-lenis-prevent>
          <ul><TreeNode node={root} current={folder} onPick={setFolder} /></ul>
        </nav>
        <section data-enter className="flex min-w-0 flex-col gap-3 rounded-[var(--radius-card)] border-2 border-fg bg-card p-4">
          <div className="flex flex-wrap items-center gap-3">
            <div className="relative min-w-[14rem] flex-1">
              <Search className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-fg-3" size={16} aria-hidden="true" />
              <TextInput type="search" aria-label={Q.search} placeholder={Q.search} value={words} onChange={(e) => setWords(e.target.value)} className="pl-10" />
            </div>
            <Switch checked={onlyIssues} onChange={setOnlyIssues} label={Q.onlyIssues} />
            <Button size="sm" onClick={() => select(rows.map((r) => r.id))}>{Q.selectAll} ({rows.length})</Button>
          </div>
          <p className="text-sm font-bold text-fg-2">{Q.filtered(rows.length)}{folder ? ` · ${folder}` : ''}</p>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[44rem] text-sm">
              <thead className="border-b-2 border-fg/20">
                <tr><th scope="col" className="w-8 p-2"><span className="sr-only">Cocher</span></th>{head('title')}{head('uses')}{head('last')}{head('modified')}{head('issues')}</tr>
              </thead>
              <tbody>
                {rows.slice(0, shown).map((r) => (
                  <tr key={r.id} className={`border-b border-fg/10 align-top ${selected.has(r.id) ? 'bg-sun-400/20' : 'hover:bg-card-2'}`}>
                    <td className="p-2"><input type="checkbox" aria-label={`Cocher #${r.id}`} checked={selected.has(r.id)} onChange={(e) => toggle(r.id, e.target.checked)} className="size-4 accent-[var(--color-magic-500)]" /></td>
                    <td className="max-w-0 p-2">
                      <Link to={`/qvidian/contenu/${r.id}`} className="block truncate font-semibold hover:underline">{r.title}</Link>
                      <span className="block truncate text-xs font-semibold text-fg-3">#{r.id} · {r.folder_path}{!r.enabled ? ' · désactivé' : ''}</span>
                    </td>
                    <td className="p-2 font-bold tabular-nums">{r.times_used}</td>
                    <td className="whitespace-nowrap p-2 text-xs font-semibold">{ago(r.last_used)}</td>
                    <td className="whitespace-nowrap p-2 text-xs font-semibold">{r.modified ?? '—'}</td>
                    <td className="p-2">
                      {r.issues.length > 0 ? (
                        <span title={r.issues.map((i) => i.label).join(', ')} className={`rounded-full px-2 py-0.5 text-xs font-bold ${r.issues.some((i) => i.severity === 'haute') ? 'bg-bubble-400/40' : 'bg-sun-400/50'}`}>{r.issues.length}</span>
                      ) : <span className="text-xs text-fg-3">—</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {rows.length > shown && <Button size="sm" onClick={() => setShown((n) => n + PAGE)}>+ {Math.min(PAGE, rows.length - shown)}</Button>}
        </section>
      </div>
    </div>
  )
}
