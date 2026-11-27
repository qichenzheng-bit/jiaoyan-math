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
import './styles/layout/app-shell.css'
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

/* Shared design system, then ordered compatibility blocks. Keep cascade order until each feature is migrated. */
import './design-system.css'
import './workflow-ui.css'
import './intake-workflow.css'
import './doc-work-v2.css'
import './styles/compat/clean-shell-and-workflows.css'
import './styles/compat/clean-manual-intake.css'
import './styles/compat/clean-inference.css'
import './chat-layout-v3.css'
import './styles/compat/shell-appearance.css'
import './styles/compat/manual-document.css'
import './styles/compat/inline-attachments.css'
import './styles/compat/header-and-mobile-intake.css'
import './styles/compat/resource-and-production-hubs.css'
import './styles/compat/composition.css'
import './styles/compat/navigation-and-desktop.css'
import './styles/compat/production-desktop.css'
import './styles/resource-components.css'
import './styles/interaction-components.css'
import './styles/layout/sidebar-navigation.css'
import './styles/layout/ai-home.css'
import './styles/layout/chat-conversation.css'
import './styles/layout/persistent-work.css'

const router=createBrowserRouter([{path:'*',element:<App/>}])
createRoot(document.getElementById('root')!).render(
  <StrictMode><RouterProvider router={router} /></StrictMode>,
)
