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
        '%c◍ MERIDIAN%c\n' + texts.easterEggs.console,
        'font: 600 20px Georgia, serif; color: #e3cfa1; text-shadow: 0 0 8px #8fa6c3;',
        'color: #bfc3cc;',
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
        window.dispatchEvent(new Event('meridian:shower'))
        toast('magic', on ? texts.easterEggs.konami : texts.easterEggs.konamiOff)
      }
      if (target.closest('input, textarea, select, [contenteditable="true"]')) return
      if (e.key.length === 1) {
        typed = (typed + e.key.toLowerCase()).slice(-WORD.length)
        if (typed === WORD) {
          typed = ''
          window.dispatchEvent(new Event('meridian:shower'))
          toast('magic', texts.easterEggs.abracadabra)
        }
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [toast])

  return null
}
