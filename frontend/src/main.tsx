import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { createBrowserRouter, RouterProvider } from 'react-router-dom'
import App from './App'

/* Global tokens and base controls */
import './theme.css'
import './styles.css'

/* Existing feature styles: keep cascade order */
import './auth.css'
import './workspace.css'
import './model-center.css'
import './chat.css'
import './knowledge.css'
import './doc-work.css'
import './chat-refs.css'
import './print-doc.css'
import './studio.css'
import './cover.css'
import './legacy-ui.css'
import './math-content.css'

/* Shared design system, then current workflow and shell overrides */
import './design-system.css'
import './workflow-ui.css'
import './intake-workflow.css'
import './doc-work-v2.css'
import './clean-workspace.css'
import './chat-layout-v3.css'

const router=createBrowserRouter([{path:'*',element:<App/>}])
createRoot(document.getElementById('root')!).render(
  <StrictMode><RouterProvider router={router} /></StrictMode>,
)
