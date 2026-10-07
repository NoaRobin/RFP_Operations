import { gsap } from 'gsap'
import { Flip } from 'gsap/Flip'
import { ScrollTrigger } from 'gsap/ScrollTrigger'
import { SplitText } from 'gsap/SplitText'
import { useGSAP } from '@gsap/react'
import './tokens'

gsap.registerPlugin(Flip, ScrollTrigger, SplitText, useGSAP)

export { gsap, Flip, ScrollTrigger, SplitText, useGSAP }
