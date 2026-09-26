import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';
import { api } from '../api';
import { describeError } from './errors';

/**
 * One fetch of a project's novel payload, shared by every page under
 * /p/:id (Overview, Read, Review). The payload is the whole volume --
 * 9.6 MB for Reverend Insanity's 199 chapters (measured 2026-09-26) -- and
 * the old single-screen app refetched it on each view switch. Pages that
 * need other data (characters, output, jobs) still fetch it themselves,
 * because those change independently of the novel (GenerationWorkspace's
 * comment records the stale-cache bug that caused).
 */
const ProjectContext = createContext(null);

export function ProjectProvider({ novelId, children }) {
  const [novel, setNovel] = useState(null);
  const [error, setError] = useState(null);
  const [errorStatus, setErrorStatus] = useState(null);
  const [loading, setLoading] = useState(false);
  const [projects, setProjects] = useState(null);

  // `current` guards against a slow response for the previous project (the
  // payload is up to ~9.6 MB) landing after the new one and overwriting it
  // when the user switches projects quickly.
  const current = useRef(novelId);
  current.current = novelId;
  const wanted = useRef(false); // some mounted page needs the novel payload

  const refetch = useCallback(() => {
    if (!novelId) return Promise.resolve();
    setLoading(true);
    return api
      .novel(novelId)
      .then((payload) => {
        if (current.current !== novelId) return;
        setNovel(payload);
        setError(null);
        setErrorStatus(null);
      })
      .catch((e) => {
        if (current.current !== novelId) return;
        setError(describeError(e, 'Could not load this project.'));
        setErrorStatus(e && typeof e.status === 'number' ? e.status : null);
      })
      .finally(() => current.current === novelId && setLoading(false));
  }, [novelId]);

  // The novel payload is the whole book (9.4 MB for Reverend Insanity), and
  // Characters, Studio and Settings never read it -- fetching it for every
  // page cost ~9 MB per visit, ~19 MB in the Studio (perf sanity, 2026-09-26).
  // It now loads when a page that reads it asks (`useNovelData`), and stays
  // cached across those pages.
  const requestNovel = useCallback(() => {
    if (wanted.current) return;
    wanted.current = true;
    refetch();
  }, [refetch]);

  useEffect(() => {
    wanted.current = false;
    setNovel(null);
    setError(null);
    setErrorStatus(null);
    setLoading(false);
  }, [novelId]);

  const refreshProjects = useCallback(() => {
    return api
      .listProjects()
      .then((l) => current.current === novelId && setProjects(l || []))
      .catch(() => current.current === novelId && setProjects([]));
  }, [novelId]);

  useEffect(() => {
    refreshProjects();
  }, [refreshProjects]);

  return (
    <ProjectContext.Provider
      value={{ novelId, novel, error, errorStatus, loading, refetch, requestNovel, projects, refreshProjects }}
    >
      {children}
    </ProjectContext.Provider>
  );
}

export function useProject() {
  const ctx = useContext(ProjectContext);
  if (!ctx) throw new Error('useProject must be used inside ProjectProvider');
  return ctx;
}

/** Like useProject, and makes sure the novel payload is being fetched. */
export function useNovelData() {
  const ctx = useProject();
  const { requestNovel } = ctx;
  useEffect(() => {
    requestNovel();
  }, [requestNovel]);
  return ctx;
}
