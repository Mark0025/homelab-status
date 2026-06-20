"""
ARCHIVED — Chatterbox TTS + GaryVee voice-clone experiment (parked 2026-06-15).

This was the first cut of the journey interview voice layer. It used a locally-run
Chatterbox TTS server (http://localhost:4123) and cloned Gary Vaynerchuk's voice from
a reference .wav at /tmp/garyvee_voice/garyvee_best.wav for the interviewer lines.

It was replaced by ElevenLabs (see journey.elevenlabs_tts + web.journey_tts_stream),
which needs no local server and selects voices by voice_id.

Kept for reference because the "clone a voice from a local .wav and stream per-clip
over SSE" pattern may be reused later (e.g. for a self-hosted / offline voice option).
This module is NOT imported anywhere and is not wired into the running app.

Original endpoints lived in homelab_status/web.py:
  - GET /api/journey/tts/status               (Chatterbox health)
  - GET /api/journey/episode/{id}/tts-stream  (SSE, per-line clips)
"""

# --- Chatterbox health check (was journey_tts_status) ---
#
# import httpx
# chatterbox_url = "http://localhost:4123"
# async with httpx.AsyncClient(timeout=5) as client:
#     r = await client.get(f"{chatterbox_url}/health")
#     data = r.json()
#     return {
#         "available": True,
#         "model_loaded": data.get("model_loaded", False),
#         "device": data.get("device"),
#         "state": data.get("initialization_state"),
#         "url": chatterbox_url,
#     }
#
# --- Per-line SSE synthesis (was the body of journey_tts_stream) ---
#
# chatterbox_url = "http://localhost:4123"
# gary_wav = "/tmp/garyvee_voice/garyvee_best.wav"
#
# async with httpx.AsyncClient(timeout=180) as client:
#     # gate on model_loaded via /health
#     for line in script["lines"]:
#         speaker, text = line["speaker"], line["text"]
#         use_gary = speaker == "interviewer" and Path(gary_wav).exists()
#         if use_gary:
#             with open(gary_wav, "rb") as f:
#                 resp = await client.post(
#                     f"{chatterbox_url}/audio/speech/upload",
#                     data={"input": text, "exaggeration": "0.4", "cfg_weight": "0.6"},
#                     files={"audio_file": ("voice.wav", f, "audio/wav")},
#                 )
#         else:
#             resp = await client.post(f"{chatterbox_url}/audio/speech", json={"input": text})
#         # base64-encode resp.content, yield as an SSE data: event, repeat per line
