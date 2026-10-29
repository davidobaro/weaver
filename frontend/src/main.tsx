import React from 'react'
import ReactDOM from 'react-dom/client'
import SessionApp from './SessionApp'
import BuildVersion from './BuildVersion'
import './style.css'

ReactDOM.createRoot(document.getElementById('root')!).render(<React.StrictMode><SessionApp /><BuildVersion /></React.StrictMode>)
