Rivals Atlas for macOS
======================

1. Unzip this folder somewhere you will keep it (for example Applications).
2. Right-click "Start Rivals Atlas.command" and choose Open the first time. macOS blocks
   double-clicking a script downloaded from the internet; after that, double-click is fine.
3. A Terminal window opens. The first run installs what is missing (a minute or two), then
   your browser opens on the dashboard.

The Terminal window is the app. Closing it stops the app.

Your data is kept in:
  ~/Library/Application Support/Rivals Atlas

The "openssl" folder carries the OpenSSL libraries the graph engine needs, so Homebrew is
not required. Keep the launcher, the .whl file and the "openssl" folder together: until the
app is published on PyPI, the launcher installs from that wheel; once it is published, the
launcher fetches the newest version by itself.

The Agents page (Ask and Insights) needs a language model. Everything else works without
one. To connect a model, put a .env file in the data folder above with either

  RIVALS_ATLAS_LLM=ollama:<model>              (Ollama running locally)
  RIVALS_ATLAS_LLM=anthropic:claude-haiku-5-5 (needs ANTHROPIC_API_KEY)

See https://github.com/touhi99/rivals-atlas for the details.

If it does not start
--------------------
Run the launcher once more and read the message in the Terminal window; it says what is
missing. Nothing is installed outside your home folder except a copy of uv in ~/.local/bin
and the app itself in ~/.cache/uv.
