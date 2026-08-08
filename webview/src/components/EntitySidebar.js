import React from 'react';

/**
 * The cast list. Clicking an entity filters the script view to lines that
 * touch it -- everything else dims rather than disappears, so a reviewer can
 * still see it *in context* rather than losing the surrounding scene.
 *
 * In edit mode, a second click target (the merge icon) starts a two-step
 * pick: click the icon on the wrong entity, then click any other row to name
 * it "this is actually that one" -- the exact fix for the identity-continuity
 * splits this session found (Klein / Zhou Mingrui / Klein Moretti).
 */
export default function EntitySidebar({
  entities,
  search,
  onSearchChange,
  focusId,
  onToggleFocus,
  editMode,
  mergeSourceId,
  onStartMerge,
  onConfirmMerge,
  onCancelMerge,
}) {
  const q = search.toLowerCase();
  const filtered = entities.filter((e) => e.label.toLowerCase().includes(q));
  const picking = editMode && mergeSourceId != null;

  return (
    <aside>
      <div className="search">
        <input
          type="search"
          placeholder="Filter entities…"
          value={search}
          onChange={(e) => onSearchChange(e.target.value)}
        />
        {picking && (
          <div className="merge-hint">
            Pick the entity to merge into&hellip; <button onClick={onCancelMerge}>cancel</button>
          </div>
        )}
      </div>
      <ul id="entity-list">
        {filtered.map((ent) => {
          const isSource = ent.id === mergeSourceId;
          return (
            <li
              key={ent.id}
              className={[
                ent.id === focusId ? 'active' : '',
                isSource ? 'merge-source' : '',
                picking && !isSource ? 'merge-target' : '',
              ].filter(Boolean).join(' ')}
              title={`${ent.aliases.join(', ')}  ·  ch${ent.first_chapter}–${ent.last_chapter}`}
              onClick={() => {
                if (picking) {
                  if (!isSource) onConfirmMerge(ent.id);
                  return;
                }
                onToggleFocus(ent.id);
              }}
            >
              <span className="swatch" style={{ background: ent.colour }} />
              <span className="name">{ent.label}</span>
              {ent.speaks && <span className="speaks">🗣</span>}
              <span className="count">{ent.count}</span>
              {editMode && !picking && (
                <button
                  className="merge-icon"
                  title="Merge this entity into another"
                  onClick={(e) => {
                    e.stopPropagation();
                    onStartMerge(ent.id);
                  }}
                >
                  ⇄
                </button>
              )}
            </li>
          );
        })}
      </ul>
    </aside>
  );
}
