import { Component, type ReactNode } from 'react'
import { texts } from '../../content/texts'

export class ErrorBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state = { error: null as Error | null }
  static getDerivedStateFromError(error: Error) {
    return { error }
  }
  render() {
    if (!this.state.error) return this.props.children
    return (
      <div role="alert" className="mx-auto my-24 max-w-xl px-6 text-center">
        <p className="eyebrow !text-danger">{texts.errors.generic}</p>
        <h1 className="mt-3 text-4xl">{texts.errors.boundaryTitle}</h1>
        <p className="mt-4 text-fg-2">{texts.errors.boundaryBody}</p>
        <pre className="mt-4 overflow-x-auto rounded-xl bg-field/70 p-3 text-left font-mono text-xs text-fg-3">{this.state.error.message}</pre>
        <button onClick={() => window.location.reload()} className="mt-6 rounded-full bg-sun-400 px-6 py-3 font-semibold text-on-accent">
          {texts.errors.reload}
        </button>
      </div>
    )
  }
}
