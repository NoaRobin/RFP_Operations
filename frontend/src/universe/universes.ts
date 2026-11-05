/**
 * Les quatre univers de l'app. Chaque univers redéfinit les mêmes variables de couleur (tokens.css, [data-universe]) :
 * tous les composants existants changent de couleur sans être réécrits.
 */
export type UniverseId = 'merlin' | 'rfp' | 'suivi' | 'pitstop'

export interface Page { to: string; label: string }

export interface Universe {
  id: UniverseId
  home: string
  pages: Page[]
  name: string
  sub: string
  mascot: 'wizard' | 'book' | 'butler' | 'mechanic'
  greeting: string
  accent: string // pastille de navigation
}

export const UNIVERSES: Record<UniverseId, Universe> = {
  merlin: { id: 'merlin', home: '/', pages: [{ to: '/', label: 'Le carrefour' }, { to: '/a-propos', label: 'À propos' }], name: 'Merlin', sub: 'l\'atelier de l\'équipe RFP', mascot: 'wizard', greeting: 'Merlin ouvre son grimoire…', accent: '#7c5cff' },
  rfp: { id: 'rfp', home: '/rfp', pages: [{ to: '/rfp', label: 'Le coin RFP' }, { to: '/rfi', label: 'Remplir un RFI' }, { to: '/atelier/fonds', label: 'Fiche fonds' }, { to: '/atelier', label: 'Atelier Excel' }, { to: '/documents', label: 'Documents' }, { to: '/omni', label: 'OMNI' }, { to: '/qui-contacter', label: 'Qui contacter' }, { to: '/rfpascontente', label: 'RFPascontente' }], name: 'RFP pas envie', sub: 'de travailler', mascot: 'book', greeting: 'Le livre court remplir vos RFI…', accent: '#ffd23f' },
  suivi: { id: 'suivi', home: '/suivi-activite', pages: [{ to: '/suivi-activite', label: 'Suivi d\'activité' }, { to: '/tableau-de-bord', label: 'Tableau de bord' }, { to: '/historique', label: 'Historique' }], name: 'Suivi d\'activité', sub: 'tenu par Alfred', mascot: 'butler', greeting: 'Alfred vous ouvre les registres.', accent: '#2ec4b6' },
  pitstop: { id: 'pitstop', home: '/qvidian', pages: [{ to: '/qvidian', label: 'Le garage' }, { to: '/merge-codes', label: 'Merge codes' }], name: 'QviAPI', sub: 'le garage Qvidian de Gus', mascot: 'mechanic', greeting: 'Gus sort la caisse à outils…', accent: '#2f6bff' },
}

const ROUTES: [string, UniverseId][] = [
  ['/qvidian', 'pitstop'], ['/merge-codes', 'pitstop'], ['/atelier', 'rfp'],
  ['/rfp', 'rfp'], ['/rfi', 'rfp'], ['/documents', 'rfp'], ['/omni', 'rfp'], ['/qui-contacter', 'rfp'], ['/rfpascontente', 'rfp'],
  ['/suivi-activite', 'suivi'], ['/tableau-de-bord', 'suivi'], ['/historique', 'suivi'], ['/executions', 'suivi'],
]

export function universeOf(pathname: string): Universe {
  const hit = ROUTES.find(([p]) => pathname === p || pathname.startsWith(`${p}/`))
  return UNIVERSES[hit ? hit[1] : 'merlin']
}

export const ORDER: UniverseId[] = ['merlin', 'rfp', 'pitstop', 'suivi']
