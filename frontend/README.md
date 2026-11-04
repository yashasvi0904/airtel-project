# Frontend

Next.js 16 (App Router) + React 19 + TypeScript + Tailwind 4. All pages are client components that call same-origin `/api/*`, which `next.config.ts` proxies to the FastAPI backend (`BACKEND_URL`, default `http://127.0.0.1:8000`). See the repository `README.md` for setup and `AGENTS.md` for the note about this Next.js version.

```
npm install
npm run dev        # or: npm run build && npm run start
npm run lint
```

Pages: `/` landing · `/onboarding` · `/advisor` · `/bundle` · `/checkout` · `/login` `/register` · `/orders` · `/orders/[id]` (tracker + scheduling) · `/orders/[id]/kyc` · `/admin`.
