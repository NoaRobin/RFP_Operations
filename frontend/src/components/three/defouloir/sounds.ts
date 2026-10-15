/** Bruitages synthétisés à la volée (Web Audio) : aucun fichier son, volume modéré, coupables à tout moment. */
export class Sounds {
  enabled = true
  private ctx: AudioContext | null = null
  private master: GainNode | null = null
  private noise: AudioBuffer | null = null

  /** Le navigateur n'autorise le son qu'après un geste de l'utilisateur. */
  unlock() {
    if (!this.enabled) return
    if (!this.ctx) {
      const Ctx = window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext
      if (!Ctx) return
      this.ctx = new Ctx()
      this.master = this.ctx.createGain()
      this.master.gain.value = 0.35
      this.master.connect(this.ctx.destination)
      const len = this.ctx.sampleRate
      this.noise = this.ctx.createBuffer(1, len, this.ctx.sampleRate)
      const data = this.noise.getChannelData(0)
      for (let i = 0; i < len; i++) data[i] = Math.random() * 2 - 1
    }
    if (this.ctx.state === 'suspended') void this.ctx.resume()
  }

  private ready() {
    return this.enabled && this.ctx && this.master && this.noise ? { ctx: this.ctx, out: this.master, noise: this.noise } : null
  }

  private burst(type: BiquadFilterType, freq: number, dur: number, gain: number, delay = 0, q = 1) {
    const r = this.ready()
    if (!r) return
    const t = r.ctx.currentTime + delay
    const src = r.ctx.createBufferSource()
    src.buffer = r.noise
    const f = r.ctx.createBiquadFilter()
    f.type = type
    f.frequency.value = freq
    f.Q.value = q
    const g = r.ctx.createGain()
    g.gain.setValueAtTime(gain, t)
    g.gain.exponentialRampToValueAtTime(0.0001, t + dur)
    src.connect(f).connect(g).connect(r.out)
    src.start(t, Math.random() * 0.5, dur + 0.05)
  }

  private tone(from: number, to: number, dur: number, gain: number, delay = 0, type: OscillatorType = 'sine') {
    const r = this.ready()
    if (!r) return
    const t = r.ctx.currentTime + delay
    const o = r.ctx.createOscillator()
    o.type = type
    o.frequency.setValueAtTime(from, t)
    o.frequency.exponentialRampToValueAtTime(Math.max(to, 1), t + dur)
    const g = r.ctx.createGain()
    g.gain.setValueAtTime(gain, t)
    g.gain.exponentialRampToValueAtTime(0.0001, t + dur)
    o.connect(g).connect(r.out)
    o.start(t)
    o.stop(t + dur + 0.05)
  }

  whoosh() { this.burst('bandpass', 900 + Math.random() * 400, 0.18, 0.12, 0, 0.8) }

  splat(size = 1) {
    this.burst('lowpass', 700, 0.22 * size, 0.9)
    this.tone(180, 60, 0.18, 0.5 * size)
  }

  crack() {
    this.burst('highpass', 2500, 0.05, 0.6)
    this.splat(0.6)
  }

  glass() {
    for (let i = 0; i < 6; i++) this.burst('highpass', 3000 + Math.random() * 3000, 0.08 + Math.random() * 0.15, 0.5, i * 0.025)
    for (let i = 0; i < 5; i++) this.tone(2500 + Math.random() * 3500, 2000, 0.25 + Math.random() * 0.3, 0.06, i * 0.04, 'triangle')
  }

  ceramic() {
    for (let i = 0; i < 4; i++) this.burst('bandpass', 1800 + Math.random() * 1500, 0.08, 0.6, i * 0.03, 2)
    this.tone(900, 500, 0.12, 0.08, 0, 'triangle')
  }

  thud(strength = 1) {
    this.tone(110, 45, 0.2, 0.7 * strength)
    this.burst('lowpass', 400, 0.12, 0.5 * strength)
  }

  dispose() {
    void this.ctx?.close()
    this.ctx = null
  }
}
