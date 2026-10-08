/** Easter eggs discrets : Konami code, « abracadabra », message aux curieux de la console. */
import { useEffect } from 'react'
import { texts } from '../../content/texts'
import { useToast } from '../ui/Toast'

const KONAMI = ['ArrowUp', 'ArrowUp', 'ArrowDown', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'ArrowLeft', 'ArrowRight', 'b', 'a']
const WORDS = { abracadabra: texts.easterEggs.abracadabra, celine: texts.easterEggs.celine, kohlanta: texts.easterEggs.kohlanta } as Record<string, string>
const LONGEST = Math.max(...Object.keys(WORDS).map((w) => w.length))
let greeted = false

export function EasterEggs() {
  const toast = useToast()

  useEffect(() => {
    if (!greeted) {
      greeted = true
      console.info(
        '%c✦ RFP pas envie de travailler%c\n' + texts.easterEggs.console,
        'font: 700 22px Fredoka, sans-serif; color: #ffd23f; -webkit-text-stroke: 1px #1b1530; text-shadow: 2px 2px 0 #1b1530;',
        'color: #7c5cff;',
      )
    }
    let konami = 0
    let typed = ''
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement
      const key = e.key.length === 1 ? e.key.toLowerCase() : e.key
      konami = key === KONAMI[konami] ? konami + 1 : key === KONAMI[0] ? 1 : 0
      if (konami === KONAMI.length) {
        konami = 0
        const on = document.documentElement.classList.toggle('aurora')
        window.dispatchEvent(new Event('rfp:shower'))
        toast('magic', on ? texts.easterEggs.konami : texts.easterEggs.konamiOff)
      }
      if (target.closest('input, textarea, select, [contenteditable="true"]')) return
      if (e.key.length === 1) {
        typed = (typed + e.key.toLowerCase()).slice(-LONGEST)
        const word = Object.keys(WORDS).find((w) => typed.endsWith(w))
        if (word) {
          typed = ''
          window.dispatchEvent(new Event('rfp:shower'))
          toast('magic', WORDS[word])
        }
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [toast])

  return null
}
