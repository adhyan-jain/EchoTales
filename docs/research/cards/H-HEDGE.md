# Card: H-HEDGE, posterior-weighted voice interpolation (killed)

- **Hypothesis:** interpolating speaker conditioning yields a graded identity.
- **Prior expectation:** failure (categorical voice perception; interpolation creates new speakers).
- **Result:**
  - **Killed at machine level.** About 82% of the identity change happens at the discrete prompt switch.
  - Continuous-embedding interpolation alone barely moves identity.
- **Caveat:** nearest-voice identification on single sentences is noisy, so no phantom-speaker claim is made.
- **Value:** a negative result that a T1 paper can report in one paragraph.
- **Patent:** this was the only concrete candidate mechanism; it is dead.
- **Reproducibility:** `python -m echotales.research run hedged_voice_feasibility` (needs a GPU and Chatterbox).
