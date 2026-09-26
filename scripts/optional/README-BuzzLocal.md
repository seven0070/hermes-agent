# Buzz + Hermes, Windows desktop-only trial

This prepares a local Buzz community and a separate Hermes agent identity. Buzz Desktop is the chat window; Hermes gateway is a separate process. The computer must remain on. No phone/Telegram setup or public internet exposure is included.

**Not yet an unattended installer.** The supplied PowerShell script builds the Buzz Windows CLI and prepares local secrets and config, but does not start containers, install the app, change Hermes config.yaml, or start Hermes. Review it before running. It refuses to overwrite existing Buzz relay secrets and merges its Buzz settings into an existing Hermes `.env` without changing unrelated entries. It has not been run on Windows; follow the stop points if your tools or Buzz version differ.

1. Install Docker Desktop with WSL2 support and Docker Compose 2.24.4+, Git for Windows, Rust/Cargo, and a Python/Hermes environment. Start Docker Desktop. Install Buzz Desktop from the Windows release at https://github.com/block/buzz/releases. Buzz Desktop does **not** include a proven Windows `buzz.exe` CLI.
2. In Buzz Desktop, create your personal identity and copy its **64-character hex public key** from Settings > Identity > Public key. Keep its private key backed up and never paste that secret into chat. Also record your public npub (or hex key) for Hermes' allow-list.
3. Review `Setup-BuzzLocal.ps1`, then use the post-install prompt or run `Launch-BuzzLocal.ps1` from PowerShell later. It asks for the public keys and runs the setup. You can also run `Setup-BuzzLocal.ps1` directly with `-OwnerPubkey '<your public hex>' -AllowedUser '<your public npub or hex>'`. It downloads Buzz source and the official Buzz relay image, builds `buzz.exe`, and creates a loopback-only Compose override. It creates relay secrets only when absent and merges the seven Buzz settings into Hermes' existing `.env` if no Buzz settings are already present; it prints only the agent's **public** hex key. Record that public key.
4. From PowerShell in `<workspace>\buzz\deploy\compose`, check `docker compose --env-file .env -f compose.yml -f compose.local.yml config` then `docker compose --env-file .env -f compose.yml -f compose.local.yml up -d --wait`. The local override binds port 3000 only to 127.0.0.1. Do not run the upstream Compose file alone: it publishes on all interfaces. Check `http://127.0.0.1:3000/_liveness`. Never run `docker compose down -v` unless you intend to delete stored data.
5. In Buzz Desktop select Join a Community, enter `ws://127.0.0.1:3000`, and onboard your owner identity. In the Compose directory, admit the agent's public hex key: `docker compose --env-file .env -f compose.yml -f compose.local.yml exec relay /usr/local/bin/buzz-admin add-member --pubkey <agent-public-hex> --role member`. Create/join a channel with both identities.
6. The script builds the CLI from Buzz source with `cargo build --release -p buzz-cli`; verify `<workspace>\buzz\target\release\buzz.exe` and the `BUZZ_CLI_PATH` in `%LOCALAPPDATA%\hermes\.env`. This build on native Windows has **not** been verified. A Rust build may need Visual Studio C++ build tools and can take time.
7. In Hermes `%LOCALAPPDATA%\hermes\config.yaml`, merge this block rather than overwriting existing settings:

```yaml
gateway:
  platforms:
    buzz:
      enabled: true
      extra:
        relay_url: ws://127.0.0.1:3000
        channels: []           # all joined, or set your channel UUID
        allowed_users: []      # owner allow-list comes from BUZZ_ALLOWED_USERS in .env
        allow_all_users: false
        require_mention: true
        transport: auto
```

8. Smoke test from a terminal with the Hermes `.env` values available to the process: `buzz channels list`, then `hermes gateway start` and `hermes gateway status`. Send a mention to the agent in a shared channel or use a DM. Do not paste private keys into commands, screenshots or chat. If `buzz channels list` fails, check membership and URL before starting Hermes.

**URL warning:** Buzz requires one canonical URL. The relay and Buzz Desktop above use `ws://127.0.0.1:3000`, not `localhost`. The Hermes adapter accepts a ws URL for WebSocket; CLI REST behavior with this exact URL still needs a live test. If the CLI needs `http://127.0.0.1:3000`, pause and check upstream canonical-host rules before changing URLs, or you may get an auth 401/new empty community. Don't treat this package as end-to-end validated.

**Sources:** [Buzz README](https://github.com/block/buzz/blob/main/README.md), [Compose](https://github.com/block/buzz/blob/main/deploy/compose/compose.yml), [Compose template](https://github.com/block/buzz/blob/main/deploy/compose/.env.example), [self-host guide](https://engineering.block.xyz/blog/run-your-own-buzz-relay), [Buzz CLI](https://github.com/block/buzz/blob/main/crates/buzz-cli/README.md), Hermes bundled adapter and tests at `230debf416`.

**Run later:** in PowerShell, `& "$env:LOCALAPPDATA\hermes\hermes-agent\scripts\optional\Launch-BuzzLocal.ps1"` (or replace that base path if `HERMES_HOME` was customized). Choosing No does not modify Buzz. The setup is offered on the first interactive Windows CLI install after Hermes setup, and in the Electron GUI after first-run provider onboarding. Neither path requires you to set up Buzz.

In the Electron desktop first-run, a visual opt-in dialog appears after completing provider onboarding on Windows. "Open setup" launches a separate visible PowerShell window; "Not now" dismisses it. If it was skipped, use `Launch-BuzzLocal.ps1` later. This is not an unattended one-click setup: the owner still supplies public keys and finishes the steps above. No prompt is shown on macOS/Linux or on a later provider switch.
