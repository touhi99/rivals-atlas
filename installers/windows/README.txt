Rivals Atlas for Windows
========================

1. Unzip this folder somewhere you will keep it.
2. Double-click "Start Rivals Atlas.bat".
3. The first run installs what is missing (a minute or two), then your browser opens on the
   dashboard. Later runs open it straight away.

The console window is the app. Closing it stops the app.

Your data is kept in:
  %LOCALAPPDATA%\Rivals Atlas

Keep the .bat and the .whl file together in this folder. Until the app is published on PyPI
the launcher installs from that wheel; once it is published, the launcher fetches the newest
version by itself.

The Agents page (Ask and Insights) needs a language model. Everything else works without
one. To connect a model, put a .env file in the data folder above with either

  RIVALS_ATLAS_LLM=ollama:<model>              (Ollama running locally)
  RIVALS_ATLAS_LLM=anthropic:claude-haiku-5-5 (needs ANTHROPIC_API_KEY)

See https://github.com/touhi99/rivals-atlas for the details.

If it does not start
--------------------
Run the launcher once more and read the message in the console window; it says what is
missing. Nothing is installed outside your home folder except a copy of uv in
%USERPROFILE%\.local\bin and the app itself in %LOCALAPPDATA%\uv.
