/** Easter eggs discrets : Konami code, « abracadabra », message aux curieux de la console. */
import { useEffect } from 'react'
import { texts } from '../../content/texts'
import { useToast } from '../ui/Toast'

const KONAMI = ['ArrowUp', 'ArrowUp', 'ArrowDown', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'ArrowLeft', 'ArrowRight', 'b', 'a']
const WORD = 'abracadabra'
let greeted = false

export function EasterEggs() {
  const toast = useToast()

  useEffect(() => {
    if (!greeted) {
      greeted = true
      console.info(
        '%c✦ GRIMOIRE%c\n' + texts.easterEggs.console,
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
        window.dispatchEvent(new Event('grimoire:shower'))
        toast('magic', on ? texts.easterEggs.konami : texts.easterEggs.konamiOff)
      }
      if (target.closest('input, textarea, select, [contenteditable="true"]')) return
      if (e.key.length === 1) {
        typed = (typed + e.key.toLowerCase()).slice(-WORD.length)
        if (typed === WORD) {
          typed = ''
          window.dispatchEvent(new Event('grimoire:shower'))
          toast('magic', texts.easterEggs.abracadabra)
        }
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [toast])

  return null
}
