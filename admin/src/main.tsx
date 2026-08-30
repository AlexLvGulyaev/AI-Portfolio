import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import App from './App';
import './styles/globals.css';

// Метка сборки в заголовке вкладки: всегда видно, какой build загружен.
document.title = `AIP Admin · сборка ${__BUILD_STAMP__.slice(11, 16)}`;

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <BrowserRouter basename="/admin">
      <App />
    </BrowserRouter>
  </React.StrictMode>,
);
