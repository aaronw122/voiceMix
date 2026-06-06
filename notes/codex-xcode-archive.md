# Investigate: Xcode shows no schemes, Archive greyed out

## Context
- macOS, Xcode 26.x. Project at `ios/voiceMixer.xcodeproj` (open it / inspect it).
- It was just generated once by XcodeGen from a now-deleted `project.yml`, then committed as a plain `.xcodeproj`. XcodeGen is retired — we edit the project directly now.
- Two targets:
  - `voiceMixer` — iOS host application (`type: application`).
  - `voiceMixerMessages` — iMessage extension (`com.apple.product-type.app-extension.messages`), embedded in the host app.
- Bundle IDs: `com.aaron.voiceMixer` and `com.aaron.voiceMixer.Messages`. Deployment target iOS 16.
- Goal: Archive the host app and upload to TestFlight (Product ▸ Archive ▸ Distribute).

## Symptom
- In Xcode the **entire Product menu is greyed out** (Run, Build, Test, Analyze, Archive all disabled).
- `Product ▸ Scheme` opens but shows **nothing** — there appear to be **no schemes at all**.
- Note: per-user state (`xcuserdata`) is git-ignored and the repo did NOT commit any `xcshareddata/xcschemes`, so there may be zero scheme files on disk.

## What to investigate (use real commands against the project)
1. Run `xcodebuild -list -project ios/voiceMixer.xcodeproj` and report the exact output (targets, schemes, configurations). This tells us if schemes truly are missing.
2. Inspect `ios/voiceMixer.xcodeproj/` contents — is there an `xcshareddata/xcschemes/` dir with any `.xcscheme` files? List what's there.
3. Sanity-check `ios/voiceMixer.xcodeproj/project.pbxproj` for both targets being present and well-formed (the application target especially — a missing/invalid app target would also grey out the menu).
4. Determine the root cause of "no schemes" and the greyed Product menu.

## What I need back (write to `notes/codex-output.md`)
- Root cause, stated plainly.
- The **exact fix**, preferring the most reliable path. Consider:
  - Creating shared schemes from the command line if possible, OR
  - Precise Xcode GUI clicks to autocreate/add a shared `voiceMixer` scheme, OR
  - Generating a correct `.xcscheme` file and where it must live (`ios/voiceMixer.xcodeproj/xcshareddata/xcschemes/voiceMixer.xcscheme`).
- After the fix, the exact steps to Archive for an `Any iOS Device (arm64)` destination.
- Any signing prerequisites (DEVELOPMENT_TEAM is currently empty) that will block Distribute, and where to set them.
- If you can safely create the shared scheme file yourself, do it and say exactly what you changed. Do NOT modify source code or delete anything.

Keep the output concise and actionable — numbered steps. Write it to `notes/codex-output.md`.
