# Reveal-Aware Visual Memory: Phase 2 Implementation Note

**Date**: 2026-10-13  
**Status**: Implementation Phase 2 complete; Cutoff-Scoped Visual Asset Emission implemented and verified; model-free test suite passing (10/10 tests); full visual memory regression suite passing (26/26 tests); default rendering behavior preserved.

---

## 1. Overview & Objective

Phase 2 builds upon the provenance-scoped selector layer established in Phase 1 (`VisualMemorySelector`, R1–R6 selection rules) by implementing the asset generation and compilation side: **Cutoff-Scoped Visual Asset Emission** (`emit_scoped_reference`).

The mission of Phase 2 is to compile reusable character reference assets under explicit narrative coordinates:
1. Story position $p$: The story-world time being depicted.
2. Discourse cutoff $k$: The narrative revelation boundary available to the viewer.
3. Observer $o$: The audience or character viewpoint (`READER`, character observer, or `SYSTEM`).
4. Disclosure policy $\Pi$: Information revelation rules (`IN_SEQUENCE`, `RETROSPECTIVE`, `OMNISCIENT`).

Crucially, **story position $p$ and discourse cutoff $k$ are strictly decoupled**. In sequential reading ($p=5, k=5$), later reveals (e.g., a scar disclosed at chapter 100) are strictly excluded from early prompts. In retrospective rendering (e.g., a flashback to $p=5$ rendered for a reader at $k=100$), the scar is admitted because it held in-world at $p=5$ and has been revealed to the viewer by cutoff $k=100$.

Prompts are assembled **strictly from facts admissible under $(p, k, o, \Pi)$**, accompanied by a verifiable provenance manifest (`<asset_id>_manifest.json`) recording the exact facts, physical row IDs, semantic assertions, temporal bounds, and engine parameters used.

---

## 2. Architectural Design & Enhancements

### 2.1 Fact Identity: Physical Row ID vs. Semantic Assertion Identity

A core design requirement was establishing reliable provenance linking every prompt token to its underlying database assertion:
- **Physical Row Identity (`source_row_id`)**: The SQLite autoincrement primary key `attribute.id`. This represents the physical database row. It is ephemeral across total database rebuilds but provides exact, verifiable auditability for an active database instance.
- **Semantic Assertion Identity (`fact_ref`)**: Generated via `observable_ref(attr)` in `echotales.core.readset` (e.g., `attr:s1:hair_color:black`). Survives database rebuilds and re-extractions.
- **Epistemic Attestation Tuple**: `(fact_ref, learned_at_pos, valid_interval, retracted_at, observer_id, truth_status)`. Uniquely identifies the bitemporal assertion in the graph.

**Core Changes**:
- In `packages/core/src/echotales/core/models.py`: Added `source_row_id: int | None = None` to `TemporalFact` so that all fact models (`Attribute`, `AliasBinding`, etc.) can hold the physical row ID.
- In `packages/core/src/echotales/core/store.py`: Updated `Store.get_attributes` to populate `source_row_id=r["id"] if "id" in r.keys() else None` from the SQLite row.
- In `packages/core/src/echotales/core/visual_memory.py`: Added `source_row_id: int | None = None` to `FactProvenance`.

### 2.2 Authoritative Epistemic Resolution: `StateResolver.resolve_admissible_attributes`

The legacy reference path (`appearance_of`) inspected only `interval.from_lb <= p` and ignored `learned_at_pos`, `retracted_at`, and observer scoping. Furthermore, `StateResolver.state_of` resolved facts through epistemic gates (`_visible_to_observer`, `_temporal_certainty`) but collapsed them into a flat `dict[str, str]`, discarding the underlying `Attribute` instances and their provenance metadata.

To resolve this without altering legacy behavior:
- Added `resolve_admissible_attributes` to `StateResolver` (`packages/core/src/echotales/core/state.py`):
  - Accepts `target_id`, `target_kind=TargetKind.PERSONA`, `timeline_id`, `position=p`, `observer_id=o`, `knowledge_pos=k`, and `include_plausible=False`.
  - Filters attributes through `_visible_to_observer` and `_temporal_certainty`.
  - Resolves key collisions deterministically (later-learned facts win on collision).
  - Returns the winning `list[Attribute]` with full temporal and physical metadata intact, sorted deterministically by attribute key.

### 2.3 Prompt Assembly Discipline

To prevent post-cutoff information leakage:
1. **No Unchecked Canon Injections**: `apply_canon` was a position-free, cutoff-free table overlay. In `emit_scoped_reference`, `include_canon` defaults to `False`. Attributes must come from grounded store rows.
2. **No Whole-Novel Demographic Scans**: Legacy `_demographics` performed un-scoped text scans (`gather_appearance_passages`) over the whole novel when traits were missing. In `emit_scoped_reference`, demographics are derived directly from admissible `Attribute` rows (or explicit arguments); if absent, they fall back closed to `"unknown"` gender and `"adult"` age without scanning future prose.
3. **Deterministic Tag Assembly**: Attributes are phrased via `build_reference_prompt` into Danbooru tags and descriptive clauses in fixed sentence order (`_PROMPT_ORDER`).
4. **Content-Addressed Hashing**: A SHA-256 digest of the final prompt (`prompt_digest`) is computed and incorporated into the content-addressed asset ID: `ref_{novel_id}_{self_id}_{persona_id}_p{int(p)}_k{k.chapter}_{prompt_digest[:8]}`.

### 2.4 Transitive Parent Asset Verification

When emitting derived reference sheets (e.g., an img2img transformation or refined body sheet conditioned on prior assets):
- All parent asset IDs (`parent_asset_ids`) are verified against `parent_assets` and/or the registry.
- Transitive lineage is checked: if any parent asset has an effective cutoff $k_{\text{parent}} > k$, or depends on a fact that was retracted as of $k$, or was witnessed only by an unauthorized observer, the emission fails closed with `EmissionStatus.REJECTED` and specific rejection reasons (`CUTOFF_EXCEEDED`, `FACT_RETRACTED`, `TRANSITIVE_LINEAGE_VIOLATION`).

---

## 3. Provenance Manifest Specification

Alongside every generated reference image, a verifiable JSON provenance manifest (`<asset_id>_manifest.json`) is serialized.

### 3.1 JSON Manifest Schema

```json
{
  "asset_id": "ref_test_novel_s1_p1_p5_k5_8863aa9b",
  "asset_kind": "character_portrait",
  "body_epoch_index": 1,
  "checkpoint_id": "",
  "discourse_cutoff": {
    "chapter": 5,
    "offset": 0
  },
  "effective_cutoff": {
    "chapter": 1,
    "offset": 0
  },
  "engine_id": "stub",
  "image_content_digest": "",
  "image_path": "/path/to/ref_test_novel_s1_p1_p5_k5_8863aa9b.png",
  "manifest_path": "/path/to/ref_test_novel_s1_p1_p5_k5_8863aa9b_manifest.json",
  "observer_id": "READER",
  "observer_scope": [
    "READER",
    "SYSTEM"
  ],
  "parent_asset_ids": [],
  "persona_id": "p1",
  "policy": "in_sequence",
  "prompt": "1boy, solo, male, black hair, inked manga illustration, clean lines",
  "prompt_digest": "8863aa9bf2da06ba",
  "provenance_version": "1.0",
  "rendering_params": [],
  "seed": 0,
  "self_id": "s1",
  "source_facts": [
    {
      "certainty": "CERTAIN",
      "fact_ref": "attr:p1:hair_color:black",
      "learned_at_pos": {
        "chapter": 1,
        "offset": 0
      },
      "observer_id": "READER",
      "retracted_at": null,
      "source_row_id": 1,
      "truth_status": "TRUE",
      "valid_interval": {
        "from_lb": 1.0,
        "from_ub": 1.0,
        "to_lb": 100.0,
        "to_ub": 100.0
      }
    }
  ],
  "story_interval": {
    "from_lb": 1.0,
    "from_ub": 1.0,
    "to_lb": 100.0,
    "to_ub": 100.0
  },
  "story_pos": 5.0
}
```

Serialization and deserialization methods are provided on `VisualAssetRecord`:
- `record.save_manifest(path: str | Path)`
- `VisualAssetRecord.load_manifest(path: str | Path) -> VisualAssetRecord`
- `record.to_dict()` and `VisualAssetRecord.from_dict(d)`

---

## 4. Verification & Model-Free Test Suite

The test suite in `packages/pipeline/tests/test_scoped_reference.py` executes 10 model-free test cases without invoking LLMs, downloading models, or generating GPU diffusion images:

| Test Case | Narrative Scenario | Epistemic Verification | Status |
|---|---|---|---|
| `test_sequential_reveal` | Scar disclosed at $k=100$, query at $p=5, k=5$ under `IN_SEQUENCE`. | Scar excluded from prompt and manifest; only ch 1 hair fact included. | PASS |
| `test_retrospective_reconstruction` | Flashback at $p=5$, reader at $k=100$ under `RETROSPECTIVE`. | Scar admitted into prompt and manifest alongside ch 1 hair fact. | PASS |
| `test_body_transition` | Mortal body active on $[1, 20]$, Zombie body on $[21, 50]$. Query at $p=25$. | Requesting Mortal body fails closed (`EMBODIMENT_MISMATCH`); default binds Zombie body. | PASS |
| `test_observer_restriction` | Reader secret mark vs. witnessed hair color for observer `wu_clan`. | Secret mark excluded for `wu_clan`; witnessed hair color admitted. | PASS |
| `test_retraction_preservation_and_invalidation` | Robes disguise learned at $k=1$, retracted at $k=50$. Queries at $k=20$ and $k=60$. | Believed at $k=20$ (robes in prompt); retracted at $k=60$ (robes excluded). | PASS |
| `test_transitive_lineage` | Derived asset depends on parent asset with cutoff $k=50$. Queries at $k=20$ and $k=60$. | Rejected at $k=20$ (`CUTOFF_EXCEEDED`); admitted at $k=60$. | PASS |
| `test_fail_closed_fallback` | Non-existent entity or missing parent asset. | Fails closed (`NO_ADMISSIBLE_EMBODIMENT`, `TRANSITIVE_LINEAGE_VIOLATION`). | PASS |
| `test_digest_sensitivity` | Cutoff $k=5$ vs $k=100$ on character with late-revealed scar. | Produces distinct prompts, prompt digests, and asset IDs. | PASS |
| `test_manifest_serialization` | Emission with disk output. | Manifest and image written; round-tripped JSON matches record and preserves SQLite row IDs. | PASS |
| `test_legacy_compatibility` | Legacy `generate_references` call on store. | Executes unmodified and returns standard `ReferenceReport`. | PASS |

### Test Suite Execution Output

```bash
uv run pytest packages/core/tests/test_visual_memory.py packages/pipeline/tests/test_scoped_reference.py packages/research/tests/test_import_direction.py packages/pipeline/tests/test_plan_builder.py
============================== 26 passed in 5.68s ==============================
```

---

## 5. Non-Negotiables & Integrity Audit

1. **Working Tree Safety**: No commits, stashes, resets, or overwrites were performed on pre-existing work.
2. **Rendering Behavior**: Default render plans and legacy `generate_references` remain completely unchanged. Scoped reference emission is an opt-in entry point (`emit_scoped_reference`).
3. **Zero Financial/GPU Cost**: All tests use in-memory SQLite fixtures and `StubImageEngine`. No LLM APIs, image diffusion weights, or network calls were initiated.
4. **Strict Architectural Layering**: Confirmed by `test_import_direction.py`. `echotales.core` does not depend on `echotales.pipeline`.
5. **Claims Discipline**: The implementation and tests demonstrate deterministic, provenance-checked input generation and manifest emission under narrative coordinates. They do not claim formal mathematical proofs of diffusion model behavior or entity resolution.
