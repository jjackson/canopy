# Canopy plugin secrets — inject with 1Password CLI:
#   op inject -i .env.tpl -o ~/.claude/canopy/.env --account dimagi.1password.com
#
# Or for plugin data directory:
#   op inject -i .env.tpl -o ~/.claude/plugins/data/canopy-canopy/.env --account dimagi.1password.com

# Workbench write token — allows the hook to POST skill actions to canopy-web
WORKBENCH_WRITE_TOKEN=op://AI-Agents/Canopy - Workbench Write Token/credential

# Canopy-web API URL (default: production Cloud Run)
CANOPY_WEB_API_URL=https://canopy-web-hhhi4yut3q-uc.a.run.app

# ElevenLabs API key — per-beat voiceover for the local video engine
# (video-engine/render_locally.py). The renderer refuses to render silent, so
# this must resolve for any DDD / connect-ddd-walkthrough render.
ELEVENLABS_API_KEY=op://AI-Agents/ACE - ElevenLabs API Key/credential
