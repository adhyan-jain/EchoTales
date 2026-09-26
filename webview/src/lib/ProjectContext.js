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

  // ProjectLayout keys this provider by project id, so every project gets
  // fresh state and refs: nothing here has to be reset on a switch, and the
  // pages below it remount too (React review, 2026-09-26: Review kept the
  // previous project's pending corrections and could POST them to the new
  // one; the old reset effect also ran *after* the child's request and
  // silently cleared the "already requested" flag, so the 9.6 MB payload was
  // fetched a second time on the next page).
  const requested = useRef(false); // some page has asked for the payload
  const seq = useRef(0); // the newest request wins; older responses are dropped
  const held = useRef(false); // a payload is already on screen
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  const refetch = useCallback(() => {
    if (!novelId) return Promise.resolve();
    const mine = ++seq.current;
    setLoading(true);
    return api
      .novel(novelId)
      .then((payload) => {
        if (!mounted.current || mine !== seq.current) return;
        held.current = true;
        setNovel(payload);
        setError(null);
        setErrorStatus(null);
      })
      .catch((e) => {
        if (!mounted.current || mine !== seq.current) return;
        requested.current = false; // the next page that asks tries again
        // A refresh after a correction that fails must not replace a book the
        // reviewer is in the middle of; the correction itself was saved.
        if (held.current) return;
        setError(describeError(e, 'Could not load this project.'));
        setErrorStatus(e && typeof e.status === 'number' ? e.status : null);
      })
      .finally(() => {
        if (mounted.current && mine === seq.current) setLoading(false);
      });
  }, [novelId]);

  // The novel payload is the whole book (9.4 MB for Reverend Insanity), and
  // Characters, Studio and Settings never read it -- fetching it for every
  // page cost ~9 MB per visit, ~19 MB in the Studio (perf sanity, 2026-09-26).
  // It loads when a page that reads it asks (`useNovelData`), stays cached
  // across those pages, and is retried by the next page after a failure (a
  // project ingested in Settings after a 404 would otherwise stay stuck).
  const requestNovel = useCallback(() => {
    if (requested.current) return;
    requested.current = true;
    refetch();
  }, [refetch]);

  const refreshProjects = useCallback(() => {
    return api
      .listProjects()
      .then((l) => mounted.current && setProjects(l || []))
      .catch(() => mounted.current && setProjects([]));
  }, []);

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
