import React from 'react';
import ReactDOM from 'react-dom/client';
import { RouterProvider } from 'react-router-dom';
import './index.css';
import { ToastProvider } from './components/ui/Toast';
import { router } from './router';
import { initTheme } from './theme';

initTheme();

// Screens are chosen by URL (src/router.js). Until the 2026-09-26 redesign
// this file picked one of three screens by query param and set #root's
// display by hand; both are gone.
ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <ToastProvider>
      <RouterProvider router={router} />
    </ToastProvider>
  </React.StrictMode>
);
