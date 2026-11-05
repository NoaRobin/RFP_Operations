import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import '@fontsource-variable/fredoka'
import '@fontsource-variable/nunito'
import '@fontsource-variable/jetbrains-mono'
import '@fontsource-variable/space-grotesk'
import '@fontsource-variable/dm-sans'
import './styles/global.css'
import './styles/qviapi.css'
import './motion/gsap'
import App from './App'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </StrictMode>,
)
