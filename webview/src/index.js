import React from 'react';
import ReactDOM from 'react-dom/client';
import './index.css';
import App from './App';
import Viewer from './Viewer';
import DesignGallery from './components/DesignGallery';
import { ToastProvider } from './components/ui/Toast';
import { initTheme } from './theme';

initTheme();

// Three genuinely different screens share this one build, picked by query
// param rather than a real router (no react-router dependency, and this
// mirrors the `?gallery` convention that already existed): `Viewer` (the
// end-user product surface) is the default; `?review` opens `App` (the
// production-desk reviewer tool this project's Section 7.2 work built);
// `?gallery` is the internal primitives style guide. See `Viewer.js`'s own
// docstring for why the reviewer tool and the reader-facing screen are not
// the same component with a mode flag.
const params = new URLSearchParams(window.location.search);
const isGallery = params.has('gallery');
const isReview = params.has('review');
const rootEl = document.getElementById('root');
if (isGallery || !isReview) rootEl.style.display = 'block'; // #root's grid layout is App(reviewer)-only

const root = ReactDOM.createRoot(rootEl);
root.render(
  <React.StrictMode>
    <ToastProvider>
      {isGallery ? <DesignGallery /> : isReview ? <App /> : <Viewer />}
    </ToastProvider>
  </React.StrictMode>
);
