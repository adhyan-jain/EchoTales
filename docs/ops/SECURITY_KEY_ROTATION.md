# SECURITY & KEY ROTATION GUIDE

**Notice:** Secret values are omitted from this document.

## 1. Key Inventory & Exposure Status
During prior session logs, third-party API key values in `.env` were exposed in system transcript logs. Although `.env` is `.gitignore`d and has **never been committed to git**, the live credentials must be rotated by the service owner.

### Managed Keys Inventory

| Service / Key Type | Environment Variable | Reference Locations | Action Required | Verification Command / Step |
|---|---|---|---|---|
| OpenRouter API Key | `OPENROUTER_API_KEY` | `.env` | Revoke existing key on OpenRouter dashboard and generate new secret key. Update `.env`. | `curl -H "Authorization: Bearer $OPENROUTER_API_KEY" https://openrouter.ai/api/v1/auth/key` |
| Gemini API Key | `GEMINI_API_KEY` | `.env` | Regenerate key in Google AI Studio. Update `.env`. | Run fallback LLM check script. |
| NVIDIA API Key | `NVIDIA_API_KEY` | `.env` | Rotate key in NVIDIA NGC Developer Portal. Update `.env`. | Test NVIDIA NIM API endpoint. |
| CivitAI API Key | `CIVITAI_API_KEY` | `.env` | Regenerate API Token in CivitAI Account Settings. Update `.env`. | `curl -H "Authorization: Bearer $CIVITAI_API_KEY" https://civitai.com/api/v1/models` |

## 2. Verification Steps
After updating `.env` with newly generated keys:
1. Verify `.env` remains gitignored: `git check-ignore .env`
2. Test pipeline execution without API errors.
