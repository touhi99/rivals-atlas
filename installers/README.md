# Launchers

The files people download instead of using a terminal. Each release ships two zips; each zip
carries the built wheel and a launcher. The launcher prefers the published package (so it stays
current) and falls back to the wheel in its own folder when the package is not on PyPI yet or
the index cannot be reached.

| Zip | Platform | What the launcher does |
|---|---|---|
| `RivalsAtlas-windows.zip` | Windows | Installs uv if missing, then `uvx --from rivals-atlas ...`, falling back to the bundled wheel |
| `RivalsAtlas-macos.zip` | macOS | Same, and points `RIVALS_ATLAS_OPENSSL_DIR` at the OpenSSL libraries in `openssl/<arch>` |

Both keep their data outside the checkout: `%LOCALAPPDATA%\Rivals Atlas` on Windows and
`~/Library/Application Support/Rivals Atlas` on macOS. Closing the console window stops the app.

The Mac launcher must stay in the same folder as `openssl/` and the wheel. The OpenSSL folder is
added by the release workflow, not stored in git (the libraries are Homebrew's OpenSSL 3 build,
Apache-2.0).

## Where to publish

**PyPI, at https://pypi.org — not GitHub Packages.** GitHub Packages only hosts Maven, NuGet,
RubyGems, npm and container images; it has no Python registry. A Python package goes to PyPI.

### One-time PyPI setup (trusted publishing, no token)

1. Create an account at https://pypi.org/account/register/ and enable two-factor authentication.
2. Open https://pypi.org/manage/account/publishing/ and choose **Add a new pending publisher**
   (this is the page for a project that does not exist yet):
   - PyPI project name: `rivals-atlas`
   - Owner: `touhi99`
   - Repository name: `rivals-atlas`
   - Workflow name: `release.yml`
   - Environment name: `pypi`
3. In the GitHub repository: **Settings → Environments → New environment**, name it `pypi`.
   No secret is needed; the workflow authenticates with a short-lived OIDC token.
4. **Settings → Secrets and variables → Actions → Variables → New repository variable**:
   `PUBLISH_TO_PYPI` = `true`. This turns on the publish job.

The first successful run creates the `rivals-atlas` project on PyPI. After that, publishing is
just a tag push.

If you would rather use a token than trusted publishing, create an API token on PyPI and add it
to the repository as `PYPI_API_TOKEN`, then replace the `pypi` job with `uv publish` and
`UV_PUBLISH_TOKEN`.

### Until PyPI access is restored

Leave `PUBLISH_TO_PYPI` unset. The `pypi` job is skipped, the release still succeeds, and the
launchers install from the wheel inside each zip. When the account is usable again, add the
variable and push the next tag; the same launchers then switch to the published version on
their next run, with no new download needed.

### Making a release

1. Bump `version` in `pyproject.toml`.
2. `git tag v0.1.0 && git push origin v0.1.0`.

The workflow builds the front end, builds the wheel with `ui/` inside it, publishes to PyPI
when enabled, copies `libssl.3.dylib` and `libcrypto.3.dylib` from Homebrew on both macOS
architectures, assembles both zips, and attaches them plus the wheel to the GitHub release.

## Why macOS needs the OpenSSL folder

The macOS wheel of LadybugDB (`_lbug*.so`) links to `/opt/homebrew/opt/openssl@3/lib/libssl.3.dylib`
by absolute path. Without Homebrew the extension cannot load, and because the graph engine is
imported before the dashboard starts, the app would not start at all. `src/rivals_atlas/openssl_fix.py`
rewrites those two load commands to `@loader_path` and signs the result ad hoc, so the bundled
libraries are used instead. It runs before anything imports LadybugDB and is a no-op elsewhere.

## Trying the launchers

The Windows file needs a Windows machine to test. On a Mac you can try the macOS launcher
before any release: copy it next to a built wheel and a matching `openssl/$(uname -m)` folder
and run the copy, which exercises the fallback path.

```
uv build --wheel
mkdir -p /tmp/macos-launcher/openssl/$(uname -m)
cp dist/*.whl /tmp/macos-launcher/
cp /opt/homebrew/opt/openssl@3/lib/libssl.3.dylib \
   /opt/homebrew/opt/openssl@3/lib/libcrypto.3.dylib \
   /tmp/macos-launcher/openssl/$(uname -m)/
cp "installers/macos/Start Rivals Atlas.command" /tmp/macos-launcher/
```

For day-to-day work use the source checkout instead: `./scripts/setup.sh && uv run rivals-atlas serve --open`.
