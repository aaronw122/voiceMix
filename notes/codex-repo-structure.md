# Question: repo structure for a new project

I'm building a product called **voiceMix**. It has two main parts:
1. An **iOS app** (Swift — a host app plus an iMessage extension).
2. A **full-stack web app** (TypeScript — frontend + backend).

I'm deciding how to structure the git repositories. Options I'm weighing:
- **A monorepo** containing everything (iOS + web frontend + web backend).
- **Two repos**: one for iOS, one for the full-stack web app (frontend + backend together).
- **Three repos**: iOS, web frontend, web backend — all separate.

I'm currently leaning toward **two repos** (iOS separate, full-stack web together).

Please give your independent recommendation. Be concise (a few short paragraphs max). Cover:
- Which option you'd pick and why.
- The main tradeoff I'd be giving up.
- Any conditions under which you'd choose differently.

Write your answer to notes/codex-repo-structure-output.md
