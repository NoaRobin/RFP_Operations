import {
  BookOpen, Calendar, ChartBar, Crown, Eye, FileSpreadsheet, FlaskConical, Gem, Globe, Hourglass, Key, Landmark,
  Layers, Lightbulb, Mail, Map, Moon, Scale, ScrollText, Search, Shield, Sparkles, Star, Table2, Target, WandSparkles,
  type LucideIcon, type LucideProps,
} from 'lucide-react'

/** Icônes utilisables dans manifest.yaml (champ `icon`). Liste courte = bundle léger. */
const ICONS: Record<string, LucideIcon> = {
  'book-open': BookOpen,
  calendar: Calendar,
  chart: ChartBar,
  crown: Crown,
  eye: Eye,
  'file-spreadsheet': FileSpreadsheet,
  flask: FlaskConical,
  gem: Gem,
  globe: Globe,
  hourglass: Hourglass,
  key: Key,
  landmark: Landmark,
  layers: Layers,
  lightbulb: Lightbulb,
  mail: Mail,
  map: Map,
  moon: Moon,
  scale: Scale,
  scroll: ScrollText,
  search: Search,
  shield: Shield,
  sparkles: Sparkles,
  star: Star,
  table: Table2,
  target: Target,
  wand: WandSparkles,
}

export function SpellIcon({ name, ...props }: { name: string } & LucideProps) {
  const Component = ICONS[name] ?? Sparkles
  return <Component aria-hidden="true" {...props} />
}

export const availableIcons = Object.keys(ICONS)
