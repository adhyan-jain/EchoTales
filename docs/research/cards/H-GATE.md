# Card: H-GATE, masking and confidence gating (objective preconditions)

- **Hypothesis:**
  - (a) distinctiveness unmasks errors;
  - (b) gating on pipeline confidence beats random gating.
- **Data:** the ladder's real errors on PDNC; 22 EARS voices; Chatterbox speaker embeddings.
- **Result:**
  - (a) holds: 22.4% of errors masked under a homogeneous cast vs 2.2% under a diverse one; mean error distance 0.095 vs 0.186.
  - (b) holds but weakly: the bootstrap CI excludes 0, yet gating closes only 16-18% of the random-to-oracle gap.
- **Implication:** the perceptual science must not depend on the posterior; any policy contribution needs a better posterior.
- **Limitation:** embedding distance is a proxy, not perception.
- **Reproducibility:** `python -m echotales.research run commitment_gating`.
