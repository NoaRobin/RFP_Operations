import { lazy, Suspense } from 'react'
import { Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { AppProvider } from './components/layout/AppContext'
import { AppShell } from './components/layout/AppShell'
import { ErrorBoundary } from './components/layout/ErrorBoundary'
import { PageTransition } from './components/layout/PageTransition'
import { CursorGlow } from './components/fx/CursorGlow'
import { EasterEggs } from './components/fx/EasterEggs'
import { SmoothScroll } from './components/fx/SmoothScroll'
import { Starfield } from './components/fx/Starfield'
import { Loading } from './components/ui/States'
import { ToastProvider } from './components/ui/Toast'
import { shouldSkipIntro } from './lib/storage'
import Library from './pages/Library'

const Intro = lazy(() => import('./pages/Intro'))
const AutomationPage = lazy(() => import('./pages/AutomationPage'))
const RunPage = lazy(() => import('./pages/Run'))
const Atelier = lazy(() => import('./pages/Atelier'))
const Dashboard = lazy(() => import('./pages/Dashboard'))
const HistoryPage = lazy(() => import('./pages/History'))
const About = lazy(() => import('./pages/About'))
const NotFound = lazy(() => import('./pages/NotFound'))

function introSeenThisSession(): boolean {
  try {
    return sessionStorage.getItem('meridian.intro.seen') === '1'
  } catch {
    return true
  }
}

function Shell() {
  const location = useLocation()
  if (location.pathname === '/' && !shouldSkipIntro() && !introSeenThisSession()) {
    return <Navigate to="/intro" replace />
  }
  return (
    <AppShell>
      <PageTransition>
        {(display) => (
          <Suspense fallback={<Loading />}>
            <Routes location={display}>
              <Route path="/" element={<Library />} />
              <Route path="/automatisations/:id" element={<AutomationPage />} />
              <Route path="/executions/:runId" element={<RunPage />} />
              <Route path="/atelier" element={<Atelier />} />
              <Route path="/tableau-de-bord" element={<Dashboard />} />
              <Route path="/historique" element={<HistoryPage />} />
              <Route path="/a-propos" element={<About />} />
              <Route path="*" element={<NotFound />} />
            </Routes>
          </Suspense>
        )}
      </PageTransition>
    </AppShell>
  )
}

export default function App() {
  return (
    <ErrorBoundary>
      <ToastProvider>
        <AppProvider>
          <Starfield />
          <CursorGlow />
          <SmoothScroll />
          <EasterEggs />
          <Routes>
            <Route path="/intro" element={<Suspense fallback={null}><Intro /></Suspense>} />
            <Route path="*" element={<Shell />} />
          </Routes>
        </AppProvider>
      </ToastProvider>
    </ErrorBoundary>
  )
}
