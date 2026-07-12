"""GitHub repo creation and code push for The Brain."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from autocorp.core.config import get_settings


class GitHubToolkit:
    """Create repos and push scaffolds via PyGithub + git CLI."""

    def __init__(self) -> None:
        self.settings = get_settings()

    @property
    def configured(self) -> bool:
        return bool(self.settings.github_token)

    def _client(self):
        from github import Auth, Github

        auth = Auth.Token(self.settings.github_token)
        return Github(auth=auth)

    def create_repo(
        self,
        name: str,
        description: str,
        private: bool = False,
        auto_init: bool = True,
    ) -> dict[str, Any]:
        if not self.configured:
            slug = name.lower().replace(" ", "-")
            user = self.settings.github_username or "local"
            return {
                "ok": True,
                "mode": "mock",
                "full_name": f"{user}/{slug}",
                "html_url": f"https://github.com/{user}/{slug}",
                "clone_url": f"https://github.com/{user}/{slug}.git",
                "message": "[MOCK] GitHub repo (set GITHUB_TOKEN for live)",
            }
        try:
            g = self._client()
            if self.settings.github_org:
                org = g.get_organization(self.settings.github_org)
                repo = org.create_repo(
                    name=name,
                    description=description,
                    private=private,
                    auto_init=auto_init,
                )
            else:
                user = g.get_user()
                repo = user.create_repo(
                    name=name,
                    description=description,
                    private=private,
                    auto_init=auto_init,
                )
            return {
                "ok": True,
                "mode": "live",
                "full_name": repo.full_name,
                "html_url": repo.html_url,
                "clone_url": repo.clone_url,
                "message": f"Created {repo.full_name}",
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def write_files_local(self, root: Path, files: dict[str, str]) -> Path:
        root.mkdir(parents=True, exist_ok=True)
        for rel, content in files.items():
            path = root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        return root

    def init_and_push(
        self,
        local_path: Path,
        remote_url: str,
        commit_message: str = "feat: initial scaffold by AutoCorp Brain",
    ) -> dict[str, Any]:
        local_path = Path(local_path)
        cmds = [
            ["git", "init"],
            ["git", "checkout", "-b", "main"],
            ["git", "add", "."],
            ["git", "commit", "-m", commit_message],
        ]
        logs: list[str] = []
        try:
            for cmd in cmds:
                r = subprocess.run(
                    cmd,
                    cwd=str(local_path),
                    capture_output=True,
                    text=True,
                    check=False,
                )
                logs.append(f"$ {' '.join(cmd)}\n{r.stdout}{r.stderr}")
                if r.returncode != 0 and "nothing to commit" not in (r.stdout + r.stderr):
                    # allow re-init
                    if "re-init" in (r.stdout + r.stderr) or "already exists" in (r.stderr or ""):
                        continue
                    if cmd[1] == "commit" and "nothing to commit" in (r.stdout + r.stderr):
                        continue

            # remote + push only with token
            if self.configured and remote_url.startswith("https://"):
                token = self.settings.github_token
                auth_url = remote_url.replace("https://", f"https://{token}@")
                subprocess.run(
                    ["git", "remote", "remove", "origin"],
                    cwd=str(local_path),
                    capture_output=True,
                )
                r = subprocess.run(
                    ["git", "remote", "add", "origin", auth_url],
                    cwd=str(local_path),
                    capture_output=True,
                    text=True,
                )
                logs.append(r.stdout + r.stderr)
                r = subprocess.run(
                    ["git", "push", "-u", "origin", "main"],
                    cwd=str(local_path),
                    capture_output=True,
                    text=True,
                )
                logs.append(r.stdout + r.stderr)
                return {
                    "ok": r.returncode == 0,
                    "mode": "live",
                    "logs": logs,
                    "message": "Pushed to origin/main" if r.returncode == 0 else r.stderr,
                }

            return {
                "ok": True,
                "mode": "local",
                "logs": logs,
                "message": f"Local git repo ready at {local_path} (push skipped — no token or mock remote)",
            }
        except Exception as e:
            return {"ok": False, "error": str(e), "logs": logs}

    def scaffold_nextjs_app(
        self,
        company_name: str,
        description: str,
        tone: str = "clean, professional",
        domain: str | None = None,
    ) -> dict[str, str]:
        """Generate a minimal but polished Next.js + Supabase + Stripe starter."""
        slug = company_name.lower().replace(" ", "-")
        title = company_name
        files: dict[str, str] = {}

        files["package.json"] = f"""{{
  "name": "{slug}",
  "version": "0.1.0",
  "private": true,
  "scripts": {{
    "dev": "next dev",
    "build": "next build",
    "start": "next start",
    "lint": "next lint"
  }},
  "dependencies": {{
    "next": "^14.2.0",
    "react": "^18.3.0",
    "react-dom": "^18.3.0",
    "@supabase/supabase-js": "^2.45.0",
    "stripe": "^16.0.0",
    "clsx": "^2.1.0"
  }},
  "devDependencies": {{
    "@types/node": "^20.0.0",
    "@types/react": "^18.3.0",
    "@types/react-dom": "^18.3.0",
    "typescript": "^5.5.0",
    "tailwindcss": "^3.4.0",
    "postcss": "^8.4.0",
    "autoprefixer": "^10.4.0"
  }}
}}
"""
        files["tsconfig.json"] = """{
  "compilerOptions": {
    "target": "ES2017",
    "lib": ["dom", "dom.iterable", "esnext"],
    "allowJs": true,
    "skipLibCheck": true,
    "strict": true,
    "noEmit": true,
    "esModuleInterop": true,
    "module": "esnext",
    "moduleResolution": "bundler",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "jsx": "preserve",
    "incremental": true,
    "plugins": [{ "name": "next" }],
    "paths": { "@/*": ["./src/*"] }
  },
  "include": ["next-env.d.ts", "**/*.ts", "**/*.tsx", ".next/types/**/*.ts"],
  "exclude": ["node_modules"]
}
"""
        files["next.config.mjs"] = """/** @type {import('next').NextConfig} */
const nextConfig = { reactStrictMode: true };
export default nextConfig;
"""
        files["tailwind.config.ts"] = """import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        brand: {
          50: "#eff6ff",
          500: "#2563eb",
          600: "#1d4ed8",
          900: "#0f172a",
        },
      },
    },
  },
  plugins: [],
};
export default config;
"""
        files["postcss.config.mjs"] = """export default { plugins: { tailwindcss: {}, autoprefixer: {} } };
"""
        files[".env.example"] = """NEXT_PUBLIC_SUPABASE_URL=
NEXT_PUBLIC_SUPABASE_ANON_KEY=
SUPABASE_SERVICE_ROLE_KEY=
STRIPE_SECRET_KEY=
NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY=
STRIPE_WEBHOOK_SECRET=
NEXT_PUBLIC_APP_URL=http://localhost:3000
"""
        files["README.md"] = f"""# {title}

{description}

> Scaffolded by **AutoCorp Brain** — tone: {tone}

## Stack

- Next.js 14 (App Router)
- Supabase (auth + DB)
- Stripe (billing)
- Vercel (deploy)

## Quick start

```bash
npm install
cp .env.example .env.local
# fill Supabase + Stripe keys
npm run dev
```

## Deploy

Connected to Vercel via AutoCorp. Domain: {domain or "pending"}
"""
        files["src/app/globals.css"] = """@tailwind base;
@tailwind components;
@tailwind utilities;

:root {
  --bg: #f8fafc;
  --fg: #0f172a;
}

body {
  color: var(--fg);
  background: var(--bg);
  font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, sans-serif;
}
"""
        files["src/app/layout.tsx"] = f"""import type {{ Metadata }} from "next";
import "./globals.css";

export const metadata: Metadata = {{
  title: "{title}",
  description: "{description.replace('"', '\\"')}",
}};

export default function RootLayout({{
  children,
}}: {{
  children: React.ReactNode;
}}) {{
  return (
    <html lang="en">
      <body className="min-h-screen antialiased">{{children}}</body>
    </html>
  );
}}
"""
        files["src/app/page.tsx"] = f"""export default function Home() {{
  return (
    <main className="mx-auto flex min-h-screen max-w-3xl flex-col justify-center px-6 py-16">
      <p className="mb-3 text-sm font-medium uppercase tracking-widest text-brand-500">
        Now shipping
      </p>
      <h1 className="text-4xl font-semibold tracking-tight text-brand-900 sm:text-5xl">
        {title}
      </h1>
      <p className="mt-4 text-lg leading-relaxed text-slate-600">
        {description.replace('"', '\\"')}
      </p>
      <div className="mt-8 flex flex-wrap gap-3">
        <a
          href="#waitlist"
          className="rounded-lg bg-brand-500 px-5 py-2.5 text-sm font-medium text-white shadow-sm hover:bg-brand-600"
        >
          Join waitlist
        </a>
        <a
          href="#features"
          className="rounded-lg border border-slate-200 bg-white px-5 py-2.5 text-sm font-medium text-slate-700 hover:bg-slate-50"
        >
          See features
        </a>
      </div>
      <section id="features" className="mt-16 grid gap-4 sm:grid-cols-3">
        {{[
          ["Focus sessions", "Pomodoro-style deep work blocks with smart breaks."],
          ["Freelancer-first", "Track billable focus time without the bloat."],
          ["Calm by design", "A {tone.split(',')[0].strip()} experience that stays out of your way."],
        ].map(([t, d]) => (
          <div key={{t}} className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
            <h3 className="font-medium text-brand-900">{{t}}</h3>
            <p className="mt-1 text-sm text-slate-600">{{d}}</p>
          </div>
        ))}}
      </section>
      <section id="waitlist" className="mt-16 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <h2 className="text-xl font-semibold text-brand-900">Get early access</h2>
        <p className="mt-1 text-sm text-slate-600">We&apos;ll email you when {title} opens.</p>
        <form className="mt-4 flex flex-col gap-2 sm:flex-row">
          <input
            type="email"
            required
            placeholder="you@company.com"
            className="flex-1 rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none ring-brand-500 focus:ring-2"
          />
          <button
            type="submit"
            className="rounded-lg bg-brand-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800"
          >
            Notify me
          </button>
        </form>
      </section>
      <footer className="mt-16 text-xs text-slate-400">
        Built by AutoCorp · {title}
      </footer>
    </main>
  );
}}
"""
        files["src/lib/supabase.ts"] = """import { createClient } from "@supabase/supabase-js";

const url = process.env.NEXT_PUBLIC_SUPABASE_URL || "";
const key = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY || "";

export const supabase = url && key ? createClient(url, key) : null;
"""
        files["src/lib/stripe.ts"] = """import Stripe from "stripe";

export const stripe = process.env.STRIPE_SECRET_KEY
  ? new Stripe(process.env.STRIPE_SECRET_KEY, { apiVersion: "2024-06-20" })
  : null;
"""
        files[".gitignore"] = """node_modules
.next
.env
.env.local
.vercel
dist
*.log
"""
        return files
