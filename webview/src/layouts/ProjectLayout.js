import React, { useEffect, useState } from 'react';
import { NavLink, Outlet, useLocation, useNavigate, useParams } from 'react-router-dom';
import {
  BookOpen,
  ChevronLeft,
  ClipboardCheck,
  Clapperboard,
  LayoutDashboard,
  Menu,
  Settings,
  Users,
  X,
} from 'lucide-react';
import { Logo, ThemeToggle } from '../components/app/Chrome';
import { ProjectProvider, useProject } from '../lib/ProjectContext';

/**
 * Workspace shell for one project. Each job the old single screen crammed
 * together (reading, casting, generating, correcting, project admin) is its
 * own routed page here, so the URL says where you are and the back button
 * works. Review sits under "Tools", apart from the reading pages: it is the
 * one area whose actions change the book, so a reader should never land on
 * it by accident.
 */
const NAV = [
  { to: '', label: 'Overview', icon: LayoutDashboard, end: true },
  { to: 'read', label: 'Read', icon: BookOpen },
  { to: 'characters', label: 'Characters', icon: Users },
  { to: 'studio', label: 'Studio', icon: Clapperboard },
];
const NAV_TOOLS = [
  { to: 'review', label: 'Review', icon: ClipboardCheck },
  { to: 'settings', label: 'Settings', icon: Settings },
];

function NavItem({ item, onNavigate }) {
  const Icon = item.icon;
  return (
    <NavLink
      to={item.to}
      end={item.end}
      onClick={onNavigate}
      className={({ isActive }) =>
        'group flex items-center gap-3 rounded-xl px-3 py-2 text-sm font-medium transition-colors ' +
        (isActive
          ? 'bg-primary/15 text-text shadow-[inset_0_0_0_1px_rgb(var(--c-accent)/0.3)]'
          : 'text-muted hover:bg-surface2 hover:text-text')
      }
    >
      {({ isActive }) => (
        <>
          <Icon className={`h-[18px] w-[18px] ${isActive ? 'text-accent' : ''}`} aria-hidden="true" />
          {item.label}
        </>
      )}
    </NavLink>
  );
}

function Sidebar({ novelId, projects, onNavigate, idPrefix }) {
  const navigate = useNavigate();
  const current = projects.find((p) => p.id === novelId);
  return (
    <div className="flex h-full flex-col gap-6 p-4">
      <div className="px-1">
        <Logo to="/projects" />
      </div>

      <div>
        <label
          htmlFor={`${idPrefix}-project-switch`}
          className="px-1 text-xs font-semibold uppercase tracking-[0.14em] text-muted"
        >
          Project
        </label>
        <select
          id={`${idPrefix}-project-switch`}
          value={novelId}
          onChange={(e) => {
            if (onNavigate) onNavigate();
            navigate(`/p/${encodeURIComponent(e.target.value)}`);
          }}
          className="mt-2 h-10 w-full rounded-xl border border-border bg-surface2 px-3 text-sm font-semibold text-text"
        >
          {!current && <option value={novelId}>{novelId}</option>}
          {projects.map((p) => (
            <option key={p.id} value={p.id}>
              {p.title || p.id}
            </option>
          ))}
        </select>
      </div>

      <nav className="flex flex-col gap-1" aria-label={idPrefix === 'drawer' ? 'Project (menu)' : 'Project'}>
        {NAV.map((item) => (
          <NavItem key={item.label} item={item} onNavigate={onNavigate} />
        ))}
        <div className="mx-3 my-3 h-px bg-border" role="separator" />
        <div className="px-3 pb-1 text-xs font-semibold uppercase tracking-[0.14em] text-muted">Tools</div>
        {NAV_TOOLS.map((item) => (
          <NavItem key={item.label} item={item} onNavigate={onNavigate} />
        ))}
      </nav>

      <div className="mt-auto flex items-center justify-between gap-2 border-t border-border pt-4">
        <NavLink
          to="/projects"
          className="inline-flex items-center gap-1.5 rounded-lg px-2 py-1.5 text-sm text-muted transition-colors hover:text-text"
        >
          <ChevronLeft className="h-4 w-4" aria-hidden="true" /> All projects
        </NavLink>
        <ThemeToggle />
      </div>
    </div>
  );
}

export default function ProjectLayout() {
  const { projectId } = useParams();
  // useParams() already decodes; decoding again would throw URIError on any
  // id containing a literal '%' and take down the whole workspace.
  return (
    <ProjectProvider novelId={projectId}>
      <LayoutBody novelId={projectId} />
    </ProjectProvider>
  );
}

function LayoutBody({ novelId }) {
  // The project list is fetched once by the provider and shared with the
  // Overview page (it used to be fetched by both).
  const { projects: sharedProjects } = useProject();
  const projects = sharedProjects || [];
  const [drawerOpen, setDrawerOpen] = useState(false);
  const location = useLocation();

  // The mobile drawer closes on navigation and on Escape.
  useEffect(() => setDrawerOpen(false), [location.pathname]);
  useEffect(() => {
    if (!drawerOpen) return undefined;
    const onKey = (e) => e.key === 'Escape' && setDrawerOpen(false);
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [drawerOpen]);

  return (
    <div className="flex min-h-screen bg-bg text-text">
      <aside className="sticky top-0 hidden h-screen w-64 shrink-0 border-r border-border bg-surface lg:block">
        <Sidebar novelId={novelId} projects={projects} idPrefix="rail" />
      </aside>

      {drawerOpen && (
        <div className="fixed inset-0 z-50 lg:hidden" role="dialog" aria-modal="true" aria-label="Navigation">
          <div
            className="absolute inset-0 bg-black/60 backdrop-blur-sm"
            onClick={() => setDrawerOpen(false)}
            aria-hidden="true"
          />
          <div className="absolute inset-y-0 left-0 w-72 overscroll-contain border-r border-border bg-surface">
            <button
              type="button"
              onClick={() => setDrawerOpen(false)}
              aria-label="Close navigation"
              className="absolute right-3 top-4 inline-flex h-9 w-9 items-center justify-center rounded-xl text-muted hover:text-text"
            >
              <X className="h-5 w-5" aria-hidden="true" />
            </button>
            <Sidebar novelId={novelId} projects={projects} idPrefix="drawer" onNavigate={() => setDrawerOpen(false)} />
          </div>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="glass sticky top-0 z-30 flex h-14 items-center gap-3 border-b border-border/60 px-4 lg:hidden">
          <button
            type="button"
            onClick={() => setDrawerOpen(true)}
            aria-label="Open navigation"
            className="inline-flex h-9 w-9 items-center justify-center rounded-xl border border-border text-text"
          >
            <Menu className="h-5 w-5" aria-hidden="true" />
          </button>
          <Logo to="/projects" />
        </header>
        <main className="flex min-w-0 flex-1 flex-col">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
