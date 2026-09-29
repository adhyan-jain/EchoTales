"""Phase 7: minimal EchoTales demonstrator (use case, not the invention).

Run: PYTHONPATH=../src python3 echotales_demo.py   (from this directory)

Maps a tiny fragment of "novel state" onto E-CRDT:
  ASSERT_WORLD  <- a scene event enters the novel's canon (world truth: what
                    actually happened in the story, independent of any
                    character's awareness of it)
  OBSERVE       <- a character is physically present for / perceives a scene
  COMMUNICATE   <- one character tells another character what happened
                    (in-story dialogue disclosing information)
  INFER         <- a character deduces something from what they already know

Two "observer states" (readers/characters) end up with a converged view of
what happened in the novel (W), but different personal knowledge (K) --
exactly the reader-facing property EchoTales' persona/appearance rendering
would need if it ever generated observer-specific scene summaries or
character-POV panels: a scene panel drawn "from Aria's POV" should not leak
facts Aria has no in-story way of knowing, even though the novel's canonical
graph already contains them.

This is a demonstration of the mapping only -- it does not touch
echotales-core or echotales-pipeline, and does not generate any real media.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from ecrdt.replica import Replica


def observer_context(replica: Replica, all_facts_text: dict) -> str:
    """The kind of thing a persona/panel-direction prompt would want: only
    what this observer actually knows, rendered as text."""
    known, _ = replica.materialize()
    lines = [f"[{replica.replica_id}'s knowledge, {len(known)} facts]"]
    for f in sorted(known):
        lines.append(f"  - {all_facts_text.get(f, f)}")
    return "\n".join(lines)


def main():
    world_authority = Replica(replica_id="narrator")  # the novel's omniscient canon writer
    aria = Replica(replica_id="Aria")
    borin = Replica(replica_id="Borin")

    facts_text = {
        "scene1_poison": "The steward poisoned the duke's wine at the feast.",
        "scene2_letter": "The duke's sister received a warning letter the same night.",
        "scene3_guard_bribed": "The east-gate guard was bribed to look away.",
    }

    # --- world truth: the narrator (world authority) asserts what happened
    for f in facts_text:
        world_authority.assert_world(f)

    # everyone eventually syncs the canonical world (world convergence)
    aria.merge(world_authority)
    borin.merge(world_authority)

    # --- Aria was physically present at the feast: she perceives scene1
    aria.observe("scene1_poison")

    # --- Aria tells Borin what she saw, in a later scene (in-story dialogue)
    borin.merge(aria)  # Borin must have Aria's event log before she can address him
    aria.communicate("Borin", "scene1_poison")
    borin.merge(aria)

    # --- Borin, suspicious, deduces the guard must have been involved
    known, _ = borin.materialize()
    if "scene1_poison" in known:
        borin.infer("suspects_inside_job", ["scene1_poison"])

    # --- scene2 and scene3 happened in the world but NEITHER character
    # witnessed or was told about them -- they stay epistemically dark
    # even though the world (W) has fully converged for everyone.

    print("=== World state (all replicas converge) ===")
    for r in (world_authority, aria, borin):
        print(f"{r.replica_id:10s} W = {sorted(r.W.facts())}")

    print("\n=== Observer-specific knowledge (intentionally divergent) ===")
    print(observer_context(aria, facts_text))
    print()
    print(observer_context(borin, facts_text))

    print("\n=== Non-interference check ===")
    print(f"Aria knows about scene2_letter (never disclosed to her)?  {aria.knows('scene2_letter')}")
    print(f"Borin knows about scene3_guard_bribed (never disclosed)?  {borin.knows('scene3_guard_bribed')}")
    assert not aria.knows("scene2_letter")
    assert not borin.knows("scene3_guard_bribed")
    print("(both False, as required -- world converged, knowledge did not)")


if __name__ == "__main__":
    main()
