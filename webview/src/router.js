import React from 'react';
import { createBrowserRouter, Link, Navigate, useLocation, useNavigate, useParams } from 'react-router-dom';
import AuthGate from './components/app/AuthGate';
import { CenterMessage } from './components/app/Chrome';
import DesignGallery from './components/DesignGallery';
import NewProject from './components/NewProject';
import ProjectLayout from './layouts/ProjectLayout';
import Landing from './pages/Landing';
import Projects, { AccountShell } from './pages/Projects';
import Overview from './pages/project/Overview';
import { Cast, Settings, Studio } from './pages/project/Pages';
import Read from './pages/project/Read';
import Review from './pages/project/Review';

/**
 * Route map (2026-09-26 redesign). The old build picked one of three screens
 * by query param (`?review`, `?gallery`, default viewer) with no real
 * routing, so nothing could be deep-linked and the back button left the
 * app. Old bookmarks still land somewhere sensible via LegacyEntry.
 *
 *   /                          landing (public)
 *   /projects                  library dashboard
 *   /projects/new              new-project wizard
 *   /p/:projectId              overview
 *   /p/:projectId/read/:ch?    reader
 *   /p/:projectId/characters/:self?  characters (/cast/* redirects here)
 *   /p/:projectId/studio       generate + library (?tab=library)
 *   /p/:projectId/review       reviewer desk (?ch=)
 *   /p/:projectId/settings     project settings
 *   /design                    internal primitives gallery
 */
function LegacyEntry() {
  const { search } = useLocation();
  const q = new URLSearchParams(search);
  if (q.has('gallery')) return <Navigate to="/design" replace />;
  if (q.has('review')) return <Navigate to="/projects" replace />;
  return <Landing />;
}

// The Characters page lived at /cast until the 2026-09-26 QA pass renamed it
// to match its sidebar label; old /cast links keep working.
function LegacyCastRedirect() {
  const { selfId } = useParams();
  const { search } = useLocation();
  // relative="path" climbs URL segments, so /cast/<id> needs two levels up.
  const to = selfId ? `../../characters/${encodeURIComponent(selfId)}` : '../characters';
  return <Navigate to={`${to}${search}`} relative="path" replace />;
}

function NewProjectPage() {
  const navigate = useNavigate();
  return (
    <AccountShell>
      <NewProject onCreated={(created) => navigate(`/p/${encodeURIComponent(created.id)}/settings`)} />
    </AccountShell>
  );
}

function NotFound() {
  return (
    <main>
      <CenterMessage title="Page not found">
        <Link to="/" className="text-accent hover:underline">
          Back to EchoTales
        </Link>
      </CenterMessage>
    </main>
  );
}

export const routes = [
  { path: '/', element: <LegacyEntry /> },
  { path: '/design', element: <DesignGallery /> },
  {
    element: <AuthGate />,
    children: [
      { path: '/projects', element: <Projects /> },
      { path: '/projects/new', element: <NewProjectPage /> },
      {
        path: '/p/:projectId',
        element: <ProjectLayout />,
        children: [
          { index: true, element: <Overview /> },
          { path: 'read', element: <Read /> },
          { path: 'read/:chapter', element: <Read /> },
          { path: 'characters', element: <Cast /> },
          { path: 'characters/:selfId', element: <Cast /> },
          { path: 'cast', element: <LegacyCastRedirect /> },
          { path: 'cast/:selfId', element: <LegacyCastRedirect /> },
          { path: 'studio', element: <Studio /> },
          { path: 'review', element: <Review /> },
          { path: 'settings', element: <Settings /> },
        ],
      },
    ],
  },
  { path: '*', element: <NotFound /> },
];

export const router = createBrowserRouter(routes);
