Google AI Studio has switched from the old AIza-style keys to new AQ... authentication keys for Gemini, and your account is now expected to use these AQ keys going forward.

What changed (AQ vs AIza)
Google is phasing out “Standard” traffic keys that started with AIza and replacing them with more secure Authentication keys that start with AQ..

New keys created in Google AI Studio are now AQ auth keys by default, so seeing AQ.... is normal and expected.

Unrestricted AIza keys already started getting rejected by Gemini API from 19 June 2026, and all AIza keys will stop working around September 2026.

How to use the new AQ key
Go to Google AI Studio → API keys and create or copy your existing key; it will be in the AQ... format.

Replace your old AIza... key in your app (env vars, config, headers) with the new AQ... key and test requests against the native Gemini endpoints (for example, generativelanguage.googleapis.com).

The AQ key works only with Google’s official Gemini API endpoints, not with third‑party “OpenAI-compatible” endpoints that expect AIza style keys, so some tools or wrappers may reject it.

If your quota shows “Unavailable” or issues in AI Studio
If AI Studio shows “quota tier unavailable” instead of Free Tier, you usually need to ensure your Google Cloud project has billing enabled, even if you plan to stay within the free Gemini limits.

Make sure the Gemini API / Generative Language API is enabled in that same project in Google Cloud Console.

What you should do now (practical steps)
For any old projects using AIza keys:

Create a new API key in AI Studio (it will be an AQ... auth key).

Update your code and deployment configs to use the AQ key.

After confirming everything works, delete or revoke the old AIza key to avoid misuse