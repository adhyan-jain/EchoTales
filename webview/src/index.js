import React from 'react';
import ReactDOM from 'react-dom/client';
import './index.css';
import App from './App';
import DesignGallery from './components/DesignGallery';
import { ToastProvider } from './components/ui/Toast';
import { initTheme } from './theme';

initTheme();

const isGallery = new URLSearchParams(window.location.search).has('gallery');
const rootEl = document.getElementById('root');
if (isGallery) rootEl.style.display = 'block'; // #root's grid layout is App-only

const root = ReactDOM.createRoot(rootEl);
root.render(
  <React.StrictMode>
    <ToastProvider>{isGallery ? <DesignGallery /> : <App />}</ToastProvider>
  </React.StrictMode>
);
