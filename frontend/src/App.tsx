import { lazy, Suspense } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
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
import Home from './pages/Home'

const Intro = lazy(() => import('./pages/Intro'))
const Library = lazy(() => import('./pages/Library'))
const Rfi = lazy(() => import('./pages/Rfi'))
const FundShop = lazy(() => import('./pages/FundShop'))
const Omni = lazy(() => import('./pages/Omni'))
const MergeCodes = lazy(() => import('./pages/MergeCodes'))
const Suivi = lazy(() => import('./pages/Suivi'))
const AutomationPage = lazy(() => import('./pages/AutomationPage'))
const RunPage = lazy(() => import('./pages/Run'))
const Atelier = lazy(() => import('./pages/Atelier'))
const Dashboard = lazy(() => import('./pages/Dashboard'))
const HistoryPage = lazy(() => import('./pages/History'))
const About = lazy(() => import('./pages/About'))
const NotFound = lazy(() => import('./pages/NotFound'))

function Shell() {
  return (
    <AppShell>
      <PageTransition>
        {(display) => (
          <Suspense fallback={<Loading />}>
            <Routes location={display}>
              <Route path="/" element={<Home />} />
              <Route path="/rfi" element={<Rfi />} />
              <Route path="/documents" element={<FundShop />} />
              <Route path="/omni" element={<Omni />} />
              <Route path="/merge-codes" element={<MergeCodes />} />
              <Route path="/suivi-activite" element={<Suivi />} />
              <Route path="/sorts" element={<Library />} />
              <Route path="/bibliotheque" element={<Navigate to="/sorts" replace />} />
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
