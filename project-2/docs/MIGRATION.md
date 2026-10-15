# Migration assessment

The v1 application has a React/Vite customer workspace, FastAPI REST/WebSocket routes, SQLAlchemy/SQLite persistence, 20 keyword intents, ten Markdown policies, hashing retrieval, extractive generation, deterministic verification, trust scoring, handoffs, replay, analytics and 22 evaluation samples.

There is no six-scenario backend switch. The six visible shortcuts in frontend/src/pages/Workspace.jsx obscure the actual bottlenecks: a small catalog in services/intent.py, ten documents and a lexical hash index in services/rag.py, and exact-intent / blanket credential refusals in services/decision.py and privacy.py. The existing speech hook is browser-only; no phone lifecycle exists.

Retain: stored conversations/turns/escalations, provider interface, independent safety verification, trust inspector, replay, and text/browser test workspace.

Incremental migration:
1. Versioned structured catalog, 80+ intents with 15+ examples, 200+ authored concept/procedure articles, structured product facts.
2. Corpus-trained semantic vectors plus word/character retrieval, broader entities/context, credential reset versus disclosure distinction.
3. Synthetic core adapter and explicit per-call demo verification.
4. Call sessions/events/state machine, mock provider, browser call transport, silence/interruptions, optional signed Twilio webhook integration.
5. Operations navigation, live monitor, call history, queue, demo customers, KB CRUD/reindex, intent testing, security and gap analytics.
6. Expanded evaluation and backend/browser regression tests; startup and integration documentation.

Modify: app/core/config.py, database/store.py, services/{intent,rag,privacy,decision,pipeline,generation,evaluation}.py, api/routes.py, main.py, frontend/src/main.jsx, shared UI/styles, requirements, tests, README.
Add: data/banking catalog and product configuration, services/{embeddings,core_banking,calls,telephony,knowledge}.py, api/{calls,knowledge,operations,telephony}.py, call/KB request schemas, React operations/call/management views, larger evaluation fixtures and migration tests.

Existing tables are preserved. New tables are additive. Legacy knowledge remains available as source files; new indexing deactivates superseded seed records without deleting conversation evidence. Administrative knowledge changes survive restarts. Real banking integration and production certification are out of scope; real telephone connectivity requires externally supplied provider configuration.
