import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { createBrowserRouter, RouterProvider } from 'react-router-dom'
import App from './App'
import './theme.css'
import './styles.css'
import './auth.css'
import './workspace.css'
import './model-center.css'

const router=createBrowserRouter([{path:'*',element:<App/>}])
createRoot(document.getElementById('root')!).render(
  <StrictMode><RouterProvider router={router} /></StrictMode>,
)

import './chat.css'

import './knowledge.css'

import './doc-work.css'

import './chat-refs.css'

import './print-doc.css'

import './studio.css'

import './cover.css'

import './legacy-ui.css'

import './math-content.css'
import './design-system.css'
import './workflow-ui.css'
import './intake-workflow.css'
import './doc-work-v2.css'

import './clean-workspace.css'
