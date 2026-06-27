# Repo Analysis — what every repo does, and where it's at

> Generated 2026-06-27 by analyzing the REAL code (deps, routes, README) of 128 non-fork repos via the local claude-lean gateway (claude-fast:sonnet). LLM output is **synthesis** — grounded in code evidence, honest 'empty' where there's nothing. Forks excluded.

## Summary

- **128 repos analyzed**
- Grades: ?: 2, B: 34, B+: 6, C: 32, D: 17, F: 37
- Deployed: 23
- By business: custom / unknown (74), AI agents / infra (19), aireinvestor (real estate) (17), Pete (sales job) (13), homelab / tooling (4), Twilio / A2P (Pete-adjacent) (1)


## AI agents / infra

### markcarpenter1-com  `B+` · working · 143 commits · 🌐 [https://autonomous.markcarpenter1.com](https://autonomous.markcarpenter1.com)
**What:** A Next.js 15 web application serving as a personal homelab command center — it surfaces real-time service status, syncs documentation from a private GitHub repo, and provides a UI for dispatching tasks to an autonomous AI agent called Terry. It also includes consulting/payment tiers via Stripe and Polar.sh.

**Why:** Centralizes monitoring, AI operations, and documentation for a self-hosted homelab infrastructure so the owner can manage and delegate infrastructure work through a single authenticated dashboard.

**Grade reason:** 98.6% E2E test coverage, live Vercel deployment, and 6/6 backend endpoints integrated, but several Sprint 1-6 features remain unfinished (multi-agent tracking, PR review, revenue dashboard).  
**Stack (package.json):** @clerk/backend, @clerk/nextjs, @eslint/eslintrc, @hookform/resolvers, @octokit/rest, @playwright/test, @polar-sh/nextjs, @radix-ui/react-accordion, @radix-ui/react-alert-dialog, @radix-ui/react-aspect-ratio, @radix-ui/react-avatar, @radix-ui/react-checkbox · 0 routes

### PAI  `C` · prototype · 79 commits
**What:** PAI (Personal AI Infrastructure) is an open-source framework for orchestrating personal and professional life using AI, with Playwright as its primary dependency suggesting browser automation or end-to-end testing capabilities.

**Why:** It exists to give individuals a self-hosted AI infrastructure layer that automates and orchestrates tasks across their life and work using AI agents.

**Grade reason:** README is polished and versioned (v0.2) but only one dependency detected and no API routes found, indicating early-stage or incomplete evidence.  
**Stack (package.json):** @playwright/test · 0 routes

### terry-management  `B` · working · 29 commits · 🌐 [https://terry.markcarpenter1.com](https://terry.markcarpenter1.com)
**What:** A Next.js control panel for managing Terry, an autonomous AI agent (Claude CLI running as a Linux user) that receives GitHub issue assignments and autonomously writes code, creates branches, and opens PRs.

**Why:** Provides a human-facing management layer — assign work, monitor mission status, review results — for a self-hosted AI coding agent running on a Hetzner server.

**Grade reason:** Live deployment with a proven end-to-end mission pipeline and 8 documented pages, but no API routes were detected and the mission runner cron is not yet enabled, indicating active development with some gaps.  
**Stack (package.json):** @base-ui/react, @clerk/nextjs, @tailwindcss/postcss, @types/node, @types/react, @types/react-dom, class-variance-authority, clsx, eslint, eslint-config-next, lucide-react, next · 0 routes

### ai-automater  `C` · prototype · 23 commits
**What:** A Next.js web application for building and running AI automations, integrating multiple LLM providers (Anthropic, OpenAI, Google, Mistral) with user authentication and subscription billing.

**Why:** Provides a multi-provider AI automation platform with auth (Clerk) and monetization (Polar) so developers or end-users can create and manage AI-powered workflows without building auth and billing from scratch.

**Grade reason:** Rich dependency set signals real intent and partial build-out, but no API routes are detected and the README is the unmodified create-next-app boilerplate, indicating early-stage work.  
**Stack (package.json):** @ai-sdk/anthropic, @ai-sdk/google, @ai-sdk/mistral, @ai-sdk/openai, @clerk/backend, @clerk/nextjs, @clerk/testing, @eslint/eslintrc, @hookform/resolvers, @playwright/test, @polar-sh/nextjs, @polar-sh/sdk · 0 routes

### agent-eos  `D` · prototype · 22 commits · 🌐 [https://agent-eos.markcarpenter1.com](https://agent-eos.markcarpenter1.com)
**What:** A Next.js/React web application using shadcn UI components, react-hook-form, and zod for form validation — likely a frontend dashboard or agent management interface based on the 'eos' naming and dependency stack.

**Why:** Appears to provide a UI layer for configuring or interacting with an AI agent system, given the 'agent-eos' name and modern React toolchain with validation primitives.

**Grade reason:** No API routes detected and empty README leave the actual functionality entirely undocumented; deps show a well-chosen stack but no evidence of implemented features.  
**Stack (package.json):** @base-ui/react, @hookform/resolvers, @tailwindcss/postcss, @types/js-yaml, @types/node, @types/react, @types/react-dom, @types/uuid, class-variance-authority, clsx, eslint, eslint-config-next · 0 routes

### terry-backend  `D` · prototype · 20 commits · 🌐 [https://terry-backend.markcarpenter1.com](https://terry-backend.markcarpenter1.com)
**What:** A FastAPI/uvicorn backend service; no routes or README content detected to determine specific functionality.

**Why:** Exists as a Python web service scaffold, but purpose is indeterminate from available evidence.

**Grade reason:** Dependencies indicate a real stack choice, but no routes, README, or application logic are present to demonstrate working functionality.  
**Stack (pyproject.toml):** fastapi, uvicorn · 0 routes

### terry-viewer-next  `C` · prototype · 20 commits · 🌐 [https://terry-viewer.markcarpenter1.com](https://terry-viewer.markcarpenter1.com)
**What:** A Next.js frontend application for viewing 'terry' content (likely diagrams or structured data), featuring zoom/pan/pinch interaction, Mermaid diagram rendering, and a shadcn/Tailwind UI component system.

**Why:** Provides an interactive browser-based viewer with diagram support and polished UI components, likely to visualize structured or relational content that benefits from pan/zoom navigation.

**Grade reason:** Solid dependency choices and test tooling (Playwright, Vitest) are in place, but the README is the unmodified create-next-app boilerplate and no API routes were detected, suggesting early-stage development.  
**Stack (package.json):** @base-ui/react, @playwright/test, @tailwindcss/postcss, @testing-library/dom, @testing-library/react, @types/node, @types/react, @types/react-dom, @vitejs/plugin-react, class-variance-authority, clsx, eslint · 0 routes

### aivoiceagents  `D` · prototype · 15 commits
**What:** Converts text to speech using the Chatterbox TTS engine, with NLTK likely used for text preprocessing (tokenization, sentence splitting) before synthesis.

**Why:** Provides a local voice/audio output layer for AI agent pipelines without relying on cloud TTS services.

**Grade reason:** Only two dependencies declared, no API routes, and an empty README — the project has intent but no documented surface or evidence of completeness.  
**Stack (requirements.txt):** chatterbox-tts, nltk · 0 routes

### terry  `C` · prototype · 15 commits · 🌐 [https://terry.markcarpenter1.com](https://terry.markcarpenter1.com)
**What:** A FastAPI service exposing system analysis and cycle-run endpoints, with health/status monitoring and Prometheus metrics collection.

**Why:** Provides an HTTP API for an AI agent ('Terry') to trigger analysis cycles and expose operational telemetry.

**Grade reason:** Functional route surface and solid dependency choices, but the near-empty README and single-sentence initialization message suggest early-stage development with minimal documentation.  
**Stack (pyproject.toml):** fastapi, httpx, prometheus-client, psutil, pydantic, requests, uvicorn · 6 routes

### clawbot  `D` · prototype · 13 commits
**What:** Local workspace directory on Mark's M5 Mac for configuring and steering Clawbot, a second-tier orchestration agent provisioned on a Hostinger VPS that dispatches tasks to a homelab executor (Terry). The VPS runtime code is not in this directory.

**Why:** Provides a human-side working copy for thinking about, scripting, and documenting Clawbot's role in a 3-tier AI agent hierarchy (Kai → Clawbot → Terry) without co-mingling with the VPS runtime.

**Grade reason:** Only evidence of implementation is a single @types/bun dev dependency; no routes, no runtime code, and the README explicitly states Clawbot is 'not yet wired into the orchestration model.'  
**Stack (package.json):** @types/bun · 0 routes

### CODE_ANAYLZER  `C` · prototype · 12 commits
**What:** An AI-powered code analysis tool that uses multi-agent crews (crewai) to perform code analysis, generate documentation, and apply systematic code updates against a SQL-backed store.

**Why:** Automates code review, documentation generation, and update workflows for developers using LLM-based agent orchestration.

**Grade reason:** Working crew components and DB tooling are present but no API routes exist, the pip install is marked 'COMING SOON', and the README features are aspirational rather than evidenced by routes or tests.  
**Stack (pyproject.toml):** alembic, click, crewai, loguru, pendulum, python-dotenv, sqlalchemy · 0 routes

### mongo-crews  `D` · prototype · 8 commits
**What:** A Python service that integrates CrewAI multi-agent workflows with MongoDB persistence, exposed via FastAPI.

**Why:** Provides a hosted API layer for running CrewAI agent crews with durable state storage in MongoDB.

**Grade reason:** Dependencies indicate clear intent but no routes are implemented and the README contains only a placeholder test trigger.  
**Stack (pyproject.toml):** crewai, fastapi, loguru, pymongo, pytest, python-dotenv, uvicorn · 0 routes

### opencode  `C` · prototype · 5 commits
**What:** A Python CLI tool that bridges OpenCode AI coding assistance with RunPod serverless GPU orchestration and a personal AI infrastructure layer called PAI.

**Why:** Provides a cost-effective, self-hosted AI coding assistant pipeline by routing model inference to RunPod serverless GPUs instead of proprietary cloud endpoints.

**Grade reason:** Foundation phase only — deps and README are present but no API routes detected and 8 of 9 planned phases remain unimplemented.  
**Stack (pyproject.toml):** click, python-dotenv, pyyaml, requests, runpod, structlog · 0 routes

### oopenModels  `C` · prototype · 4 commits
**What:** A FastAPI service exposing hardware discovery, model management, benchmarking, and compatibility checking for local/open LLMs. Separately, a content-extraction pipeline that pulls YouTube video transcripts and distills wisdom using the Fabric toolchain.

**Why:** Provides a programmatic API layer for managing and evaluating local AI models, while the video pipeline captures knowledge from AI/ML educational content.

**Grade reason:** API routes suggest meaningful functionality but the README describes only a learning/scraping repo with one video processed, indicating early/experimental state with mismatched evidence.  
**Stack (pyproject.toml):** fastapi, uvicorn · 7 routes

### Tennant-Screening-APP  `C` · prototype · 4 commits
**What:** A Python backend (FastAPI) + optional frontend (Streamlit) application that integrates with the Vapi voice-agent API/SDK to manage voice agents, tools, and knowledge bases.

**Why:** Provides a structured wrapper around Vapi to automate tenant screening workflows via AI voice agents.

**Grade reason:** README and structure exist but no routes were detected and pyproject.toml deps are absent, suggesting early-stage scaffolding with incomplete implementation.  
**Stack (pyproject.toml):** — · 0 routes

### visualize-all-ai-frontend  `C` · prototype · 3 commits
**What:** A Next.js web frontend for visualizing AI agent activity, likely rendering real-time diagrams and dashboards using Mermaid, Socket.io, and a component library stack (shadcn/ui, Radix, Geist).

**Why:** Provides a UI layer for monitoring or exploring AI agent workflows, filling the gap between raw agent output and human-readable visualization.

**Grade reason:** Dependencies signal real intent (Mermaid, Socket.io, next-auth, TanStack Query) but the README is boilerplate create-next-app with no routes detected, indicating early/scaffolded state.  
**Stack (package.json):** @eslint/eslintrc, @geist-ui/core, @radix-ui/react-slot, @shadcn/ui, @tanstack/react-query, @types/node, @types/react, @types/react-dom, class-variance-authority, clsx, eslint, eslint-config-next · 0 routes

### WORKSTATION  `C` · prototype · 2 commits
**What:** A FastAPI-based AI agent workstation that orchestrates multi-agent workflows using CrewAI and LangChain with OpenAI backends, served over HTTP with async file handling and a rich terminal UI.

**Why:** Provides a local development environment for building and running AI agent pipelines with persistent storage (Postgres via SQLAlchemy) and real-time file watching.

**Grade reason:** Rich dependency stack signals real intent, but no routes detected and an empty README indicate early-stage work with no documented or exposed API surface.  
**Stack (pyproject.toml):** aiofiles, click, crewai, duckduckgo-search, fastapi, jinja2, langchain, langchain-community, langchain-core, langchain-openai, loguru, markdown · 0 routes

### openclaw  `C` · prototype · 1 commits
**What:** Setup scripts and configuration templates for deploying OpenClaw (an open-source AI agent platform) on a Hostinger VPS, following a NetworkChuck tutorial.

**Why:** Provides a reproducible self-hosted AI agent deployment so the owner controls their own API keys and infrastructure.

**Grade reason:** README and project structure are clear but no actual scripts, config, or code evidence was provided — only documentation scaffolding.  
**Stack (unknown):** — · 0 routes

### test-terry-repo  `F` · empty · 1 commits
**What:** A test repository created to support Terry autonomous agent missions; no functional code is present.

**Why:** Provides a sandbox environment for testing autonomous agent workflows without affecting production systems.

**Grade reason:** No dependencies, no routes, and a placeholder README indicate no implementation exists.  
**Stack (unknown):** — · 0 routes


## Pete (sales job)

### peterei_intercom  `B` · working · 268 commits
**What:** A Next.js 15 web application housing three AI agents (general help, conversation analysis, and onboarding questionnaire) built on OpenAI, used to update and interact with 'Pete' training data via an Intercom-style interface.

**Why:** Provides an admin-protected UI for managing and testing AI agent training workflows, deployed as a homelab/internal tool at peterei.com.

**Grade reason:** Deployed to production on Render with auth, multiple agents, and documented structure, but only one dependency detected and no API routes surfaced in evidence.  
**Stack (package.json):** openai · 0 routes

### pete-db  `B` · working · 214 commits · 🌐 [https://deploy-pete-db.markcarpenter1.com](https://deploy-pete-db.markcarpenter1.com)
**What:** A schema-aware database intelligence platform that enables natural language querying of SQL databases by combining LangChain/LangGraph AI pipelines with schema-driven SQL generation, CLI tooling, and multi-table join optimization.

**Why:** Exists to let non-technical users and AI agents query complex business databases (150+ tables) using plain English instead of hand-written SQL.

**Grade reason:** 89.5% test pass rate and broad dependency coverage signal real functionality, but schema management tests at 37.5% pass rate and no detected HTTP routes suggest incomplete surface area.  
**Stack (pyproject.toml):** aiohttp, fastapi, google-api-python-client, google-auth-oauthlib, httpx, langchain, langchain-community, langchain-core, langchain-mcp-adapters, langchain-openai, langgraph, langgraph-checkpoint-sqlite · 0 routes

### peterental-nextjs  `C` · prototype · 153 commits
**What:** A Next.js web application with Clerk authentication, Vapi AI voice integration, and a Radix UI component library — likely a voice-AI-powered rental or property management interface.

**Why:** Provides an authenticated frontend for interacting with Vapi AI voice agents, probably to handle rental inquiries or tenant interactions hands-free.

**Grade reason:** Dependencies indicate a real feature set (auth, voice AI, UI components, tests) but no API routes were detected and the README is the unmodified create-next-app boilerplate, suggesting early-stage scaffolding.  
**Stack (package.json):** @clerk/nextjs, @clerk/testing, @eslint/eslintrc, @playwright/test, @radix-ui/react-collapsible, @radix-ui/react-label, @radix-ui/react-progress, @radix-ui/react-slot, @radix-ui/react-switch, @radix-ui/react-tabs, @tailwindcss/postcss, @tanstack/react-query · 0 routes

### Pete_ollama_agent  `B` · working · 143 commits
**What:** A FastAPI-based system that fine-tunes local Ollama models on 3,555 real property-manager conversations to make an AI respond like a specific person (Jamie). Includes a chat UI, admin dashboard, and self-correcting validation loop.

**Why:** Automates persona-specific AI training for property management so a custom local model can handle tenant interactions in Jamie's exact communication style without relying on a cloud LLM.

**Grade reason:** Rich feature set (training pipeline, validation, analytics, MCP integration) with a documented quick-start, but no detected registered API routes suggests incomplete FastAPI wiring or non-standard route structure.  
**Stack (pyproject.toml):** beartype, fastapi, httpx, loguru, mcp, pendulum, psutil, pydantic, pytest, pytest-asyncio, python-dotenv, requests · 0 routes

### PeteRental_vapi_10_02_25  `B` · working · 114 commits
**What:** FastAPI platform integrating a VAPI voice AI agent with Microsoft Calendar for property viewing appointment scheduling, plus LangChain-powered rental listing scraping via DuckDuckGo and Playwright.

**Why:** Automates appointment booking and rental property search for a property management business using voice AI and LLM-driven web scraping.

**Grade reason:** Solid dependency stack with OAuth, PostgreSQL, Docker, and multi-provider LLM support, but only two discoverable routes (/ and /health) visible in evidence, suggesting most functionality lives in undocumented or internal handlers.  
**Stack (pyproject.toml):** aiohttp, anyio, asyncpg, beautifulsoup4, black, clerk-backend-api, cryptography, ddgs, duckduckgo-search, email-validator, fastapi, httpx · 2 routes

### VapiSimple2  `B` · working · 79 commits · 🌐 [https://vapi2simple-ui.markcarpenter1.com](https://vapi2simple-ui.markcarpenter1.com)
**What:** A FastAPI-based webhook integration platform that connects VAPI voice agents to Google Calendar and a PeteDB CRM, enabling voice agents to look up customer data by phone number and check calendar availability during calls.

**Why:** Bridges the gap between AI voice agents and business data systems so voice agents can answer customer-specific questions and schedule appointments without human intervention.

**Grade reason:** Rich README with detailed feature checklist and no detected API routes suggests the route discovery may have failed, but the dep stack and documented capabilities indicate a real, functional integration.  
**Stack (pyproject.toml):** fastapi, google-api-python-client, google-auth, google-auth-oauthlib, python-dotenv, uvicorn · 0 routes

### PeteDataCleaner  `B` · working · 75 commits
**What:** A desktop GUI application (PyQt5) that ingests messy CSV/Excel spreadsheets, runs a fast data-cleaning and owner-analysis pipeline using Polars, and exports results to Pete CRM or investor-analysis formats with Google Sheets integration.

**Why:** Saves real-estate data analysts time by automating phone prioritization, owner deduplication, and CRM-ready export — replacing manual spreadsheet cleanup.

**Grade reason:** Full GUI stack, rich deps, passing tests, and a clear README quick-start, but no API routes exposed and badge shows only 6 tests against a substantial dependency surface.  
**Stack (pyproject.toml):** fastapi, gitpython, google-api-python-client, google-auth, google-auth-oauthlib, gspread, loguru, lxml, matplotlib, numpy, oauth2client, openpyxl · 0 routes

### pete-company-ops-viewer  `F` · empty · 51 commits · 🌐 [https://petevisualizer.markcarpenter1.com](https://petevisualizer.markcarpenter1.com)
**What:** No code or documentation evidence found to determine what this repository does.

**Why:** Cannot be determined from available evidence.

**Grade reason:** No dependencies, routes, or README content present to evaluate.  
**Stack (unknown):** — · 0 routes

### pete-data-sanitizer  `B` · working · 31 commits · 🌐 [https://pete-cleandata.markcarpenter1.com](https://pete-cleandata.markcarpenter1.com)
**What:** A CLI/web data-cleaning pipeline that ingests DealMachine real-estate lead exports (XLSX), deduplicates rows to one-per-address, selects preferred seller contacts, and outputs Pete Properties Import-ready XLSX and CSV files plus staging reports.

**Why:** DealMachine exports contain multiple rows per address (one per seller/contact), but the Pete Properties import template requires exactly one row per property, making an automated dedup-and-reshape step necessary.

**Grade reason:** Detailed README, appropriate deps (pandas, openpyxl, FastAPI, Typer, pytest, YAML config), and multiple output artifacts indicate a functional, thoughtfully designed tool, but v0.02 versioning and zero detected API routes despite FastAPI being a dependency suggest it is still early-stage and the web layer is incomplete or unused.  
**Stack (pyproject.toml):** fastapi, httpx, jinja2, loguru, openpyxl, pandas, pydantic, pyflowchart, pytest, python-multipart, pyyaml, questionary · 0 routes

### PETE_GHL_WORKSTSATION  `C` · prototype · 9 commits
**What:** A full-stack AI workstation combining a Next.js/React frontend with a Python backend (FastAPI + CrewAI + LangChain) for multi-agent AI workflows, likely targeting GHL (GoHighLevel) CRM automation or related tasks.

**Why:** Provides a local AI agent workstation — probably to automate GoHighLevel CRM workflows using LLM-powered crews without relying on cloud SaaS tooling.

**Grade reason:** Dependencies are rich and intentional but no routes were detected and the README is empty, suggesting early-stage scaffolding that is not yet operational.  
**Stack (pyproject.toml+package.json):** @base-ui/react, @tailwindcss/postcss, @types/node, @types/react, @types/react-dom, aiofiles, beautifulsoup4, class-variance-authority, click, clsx, crewai, duckduckgo-search · 0 routes

### fireworks-sales  `D` · prototype · 3 commits
**What:** A Next.js web application named 'fireworks-sales' with Prisma ORM and Tailwind CSS, likely intended as a sales or e-commerce frontend with a database backend — but no routes or custom logic are detectable yet.

**Why:** Appears to exist as a scaffolded starting point for a fireworks sales platform, solving the need for a web UI with persistent data storage.

**Grade reason:** Stack is fully configured (Next.js, Prisma, Tailwind, TypeScript) but the README is the unmodified create-next-app template and no routes or application logic have been built.  
**Stack (package.json):** @eslint/eslintrc, @prisma/client, @tailwindcss/postcss, @types/node, @types/react, @types/react-dom, eslint, eslint-config-next, next, prisma, react, react-dom · 0 routes

### petereibb  `B` · working · 2 commits
**What:** A data migration pipeline that extracts contacts and properties from REI BlackBook CRM and transforms them into CSV files compatible with Pete's target system, including campaign attribution and address validation.

**Why:** Exists to perform a one-time (or repeatable) CRM migration preserving lead statuses, campaign links, and property data with high accuracy between two real estate investor systems.

**Grade reason:** README claims production-ready results with concrete metrics and the dep stack (polars, pandas, pyarrow, openpyxl) matches the stated pipeline, but no API routes and no visible test infrastructure lower the grade.  
**Stack (pyproject.toml):** beautifulsoup4, curl-cffi, fastexcel, flake8, mypy, openpyxl, pandas, polars, pyarrow, pydeps, pylint, python-dotenv · 0 routes

### AIRIE_BUSINESS  `D` · prototype · 2 commits
**What:** A CLI tool that converts Markdown files to PDF and integrates with GoHighLevel (GHL) to create and upload sales funnels and lead magnets.

**Why:** Automates content production and funnel deployment for a business using GHL as its CRM/marketing platform.

**Grade reason:** README shows a clear surface but no deps, no detected routes, and no code evidence — shell scripts and CLI commands only, nothing verifiable beyond documentation.  
**Stack (unknown):** — · 0 routes


## Twilio / A2P (Pete-adjacent)

### Twilio_tools  `B+` · working · 153 commits · 🌐 [https://twilio-tools.markcarpenter1.com](https://twilio-tools.markcarpenter1.com)
**What:** A dual-stack CLI and FastAPI platform for managing 289 Twilio subaccounts, automating A2P compliance, TrustHub health checks, error analytics, and phone number intelligence via both a rich terminal UI and a Next.js web frontend.

**Why:** Eliminates manual Twilio subaccount administration at scale by centralizing compliance automation, error dashboards, and campaign submission across a large multi-account estate.

**Grade reason:** Comprehensive README with clear architecture and quick-start, broad dependency stack (Playwright, FastAPI, Twilio SDK, Rich) matching stated features, but no routes were detected and frontend integration details are cut off.  
**Stack (pyproject.toml):** beautifulsoup4, click, fastapi, httpx, loguru, nltk, playwright, python-dotenv, rich, twilio, uvicorn · 0 routes


## aireinvestor (real estate)

### app.Aireinvestor  `F` · empty · 524 commits
**What:** A TypeScript project with React Markdown rendering capability; exact application purpose is unclear from available evidence.

**Why:** Insufficient evidence to determine the problem it solves.

**Grade reason:** No routes, no meaningful README, and only a minimal dependency set with no application code surface visible.  
**Stack (package.json):** @types/node, react-markdown, rehype-raw, ts-node, typescript · 0 routes

### if3scraper  `B` · working · 112 commits · 🌐 [https://if3scraper.markcarpenter1.com](https://if3scraper.markcarpenter1.com)
**What:** A CLI-driven Python scraper that pulls real estate opportunity data from an API and exports it to JSON, CSV, and Excel formats.

**Why:** Automates collection and cleaning of real estate leads from a proprietary API, replacing manual data gathering.

**Grade reason:** Well-structured Clean Architecture layout with tests and docs, but only one dependency detected (httpx) and no API routes exposed, suggesting a standalone CLI tool rather than a service.  
**Stack (pyproject.toml):** httpx · 0 routes

### localleasing  `B` · working · 90 commits · 🌐 [https://localleasing.markcarpenter1.com](https://localleasing.markcarpenter1.com)
**What:** Property management platform with email analytics, lead tracking, and contact/portfolio management backed by a FastAPI backend and a separate frontend.

**Why:** Centralizes Gmail-sourced lead data and property records into a single dashboard so property managers can track prospects, tenants, and occupancy without juggling raw email.

**Grade reason:** README describes substantial implemented features (150K emails, 49 E2E tests, auth, multi-source leads) but no API routes were detected in the evidence, leaving the backend surface unverifiable.  
**Stack (pyproject.toml):** fastapi, uvicorn · 0 routes

### AI-REI-TEACHINGS  `F` · empty · 53 commits
**What:** A community-facing open source scaffold for an AI automation and education platform, currently containing only a README and no implemented code or routes.

**Why:** Exists to recruit contributors and signal vision for an AI-powered blogging/consulting platform built on Next.js, Go, and OpenRouter.

**Grade reason:** No dependencies, no routes, and no source code detected — only a README describing future intent.  
**Stack (unknown):** — · 0 routes

### aireinvestor  `C` · working · 42 commits · 🌐 [https://theairealestateinvestor.com](https://theairealestateinvestor.com)
**What:** Static marketing website for an AI real estate investing consultancy, serving pages exported from GoHighLevel via a Docker-hosted web server.

**Why:** Provides a self-hosted alternative to GoHighLevel's hosting for the theairealestateinvestor.com consulting brand.

**Grade reason:** Complete page structure and deployment config present, but no application logic, API routes, or dependencies detected — pure static content delivery.  
**Stack (unknown):** — · 0 routes

### aire_learning_platform  `C` · prototype · 21 commits
**What:** A quiz-based study game for real estate investment education, serving interactive learning modules with immediate feedback and progress tracking.

**Why:** Provides AI-branded educational tooling for real estate investors to learn investment strategies through self-paced quizzes.

**Grade reason:** README describes features clearly but no dependencies or API routes were detected, suggesting a thin or early-stage implementation.  
**Stack (unknown):** — · 0 routes

### Llhb-website  `C` · prototype · 7 commits
**What:** A Next.js web application for 'LLHB' (likely Local House Buyers) with authentication, database persistence, and a data-table-driven UI featuring forms and dialogs.

**Why:** Provides a client-facing or internal web portal for a real estate / home-buying business, handling user auth (Clerk), structured data (Prisma + libSQL/Turso), and rich UI components (Radix UI, TanStack Table).

**Grade reason:** Solid dependency foundation with auth, ORM, and UI libraries wired up, but no API routes detected and the README is the unmodified create-next-app boilerplate, indicating early-stage scaffolding.  
**Stack (package.json):** @clerk/nextjs, @eslint/eslintrc, @hookform/resolvers, @libsql/client, @prisma/adapter-libsql, @prisma/client, @radix-ui/react-checkbox, @radix-ui/react-dialog, @radix-ui/react-dropdown-menu, @radix-ui/react-slot, @tailwindcss/forms, @tailwindcss/postcss · 0 routes

### AIRE_LEARNING_PLATFORM  `C` · prototype · 6 commits
**What:** A quiz-based study game web app for real estate investment education, serving interactive learning modules with immediate feedback and progress tracking.

**Why:** Exists to help real estate investors learn investment strategies through an AI-branded educational platform.

**Grade reason:** README describes features but no deps or routes were detected, suggesting early or incomplete implementation.  
**Stack (unknown):** — · 0 routes

### aireinvestor-ghl-sites  `F` · empty · 4 commits
**What:** No evidence found — the repository has no detectable dependencies, routes, or README content.

**Why:** Cannot be determined from the available evidence.

**Grade reason:** Zero evidence: no deps, no routes, no README.  
**Stack (unknown):** — · 0 routes

### vapi-rental  `C` · prototype · 4 commits
**What:** A LangChain agent that extracts rental property listings from public websites and exposes them via a FastAPI proxy for Vapi voice/chat assistant integration.

**Why:** Enables a Vapi voice assistant to answer questions about available rental listings by combining LLM-powered HTML extraction with structured JSON output.

**Grade reason:** No routes detected despite FastAPI being a dependency, suggesting the proxy layer is incomplete or not yet wired up.  
**Stack (pyproject.toml):** duckduckgo-search, fastapi, httpx, langchain, langchain-community, langchain-openai, python-dotenv, uvicorn, wikipedia · 0 routes

### skip-tracing  `B` · working · 3 commits · 🌐 [https://skip-tracing.markcarpenter1.com](https://skip-tracing.markcarpenter1.com)
**What:** A CLI tool that performs skip tracing (locating property owner contact info) and bulk address verification by calling a third-party Real Estate API, with rate limiting, batch processing, and CSV/JSON/Excel I/O.

**Why:** Automates high-volume real estate lead research workflows that would otherwise require manual API calls or expensive SaaS tooling.

**Grade reason:** Well-documented with clear setup, matching deps, and multiple features, but FastAPI and uvicorn are listed as deps with no routes detected, suggesting a server layer is planned or partially built but not yet exposed.  
**Stack (pyproject.toml):** fastapi, httpx, loguru, openpyxl, python-dotenv, python-multipart, typer, uvicorn · 0 routes

### REI-CLEAN0-DATA  `C` · prototype · 2 commits
**What:** A Python CLI tool that sends contact information to the Endato Contact Enrichment API and returns enriched data for a given person and address.

**Why:** Exists to simplify REI (real estate investor) lead enrichment by wrapping the Endato API with credential management and basic error handling.

**Grade reason:** README is thorough but deps block is empty and no routes exist, suggesting a bare-bones script with hardcoded sample data and no evident tests or packaging.  
**Stack (unknown):** — · 0 routes

### REISIFT  `B` · working · 2 commits
**What:** A Flask web application that ingests Excel files of real estate leads and transforms them into a standardized CSV format compatible with REISift's import requirements, including name parsing, address splitting, and phone number normalization.

**Why:** Eliminates manual data reformatting work for real estate investors who collect leads in arbitrary Excel layouts but need a specific schema to import into REISift CRM.

**Grade reason:** Full feature set documented and coherent dependency stack, but no detected API routes suggests either a form-based UI with no REST layer or incomplete route registration — functional but not production-hardened.  
**Stack (requirements.txt):** flask, nameparser, openpyxl, pandas, pydantic, python-dotenv, werkzeug · 0 routes

### AIREGIGWORK  `D` · prototype · 2 commits
**What:** A framework for managing and monetizing freelance gig work on platforms like Fiverr and Upwork, including tools for proposal generation, price monitoring, and marketing automation.

**Why:** Exists to systematically convert one-off development engagements into repeatable, sellable services that generate revenue to fund AireInvestor.com and developer salaries.

**Grade reason:** README describes intentions and structure but no dependencies or API routes were detected, suggesting mostly planning/templates with little to no runnable code.  
**Stack (unknown):** — · 0 routes

### aire_vid_recorder  `D` · prototype · 2 commits
**What:** A screen recording tool; exact capabilities unknown beyond the name and minimal README.

**Why:** Likely exists to capture screen or video content, but motivation is undocumented.

**Grade reason:** No dependencies, no routes, and a placeholder README leave almost nothing to assess.  
**Stack (unknown):** — · 0 routes

### ai-rei-worksations  `F` · empty · 1 commits
**What:** Insufficient evidence to determine purpose — no dependencies, routes, or README content were provided.

**Why:** Cannot be determined from the available evidence.

**Grade reason:** No code artifacts, dependencies, routes, or documentation were present to evaluate.  
**Stack (unknown):** — · 0 routes

### REI-CLEAN-DATA  `F` · empty · 0 commits
**What:** No evidence of functionality detected — the repository contains no detectable dependencies, routes, or README content.

**Why:** Cannot be determined from available evidence.

**Grade reason:** No deps, no routes, no README — nothing to evaluate.  
**Stack (unknown):** — · 0 routes


## custom / unknown

### wes  `F` · empty · 458 commits · 🌐 [https://fairdealhousebuyer.com](https://fairdealhousebuyer.com)
**What:** Insufficient evidence to determine what this repository does — no dependencies, routes, or README content were provided.

**Why:** Cannot be determined from the evidence supplied.

**Grade reason:** No code evidence, dependencies, routes, or documentation were present to evaluate.  
**Stack (unknown):** — · 0 routes

### 0ne52bar  `C` · prototype · 102 commits
**What:** A full-featured web application for a bar and restaurant (152 Bar) built with Next.js 15, covering menu browsing, online ordering, a loyalty program (TapPass), event management, and a merchandise store with an admin dashboard for managing all of the above.

**Why:** To provide a branded digital presence and self-service ordering/loyalty platform for a specific bar and restaurant business.

**Grade reason:** README describes an ambitious feature set but no deps or routes were detected, suggesting the implementation may be incomplete or scaffolded but not yet wired up.  
**Stack (unknown):** — · 0 routes

### my-book-buddy  `B` · working · 63 commits · 🌐 [https://mybookbuddyai.com](https://mybookbuddyai.com)
**What:** A Next.js web app that lets users upload books (PDF) and have AI-powered voice conversations about them using Vapi and ElevenLabs for speech, Clerk for auth, and MongoDB for persistence.

**Why:** Provides an interactive AI book companion so readers can ask questions about book content via voice rather than reading alone.

**Grade reason:** Full stack is wired (auth, storage, DB, voice AI, payments via Polar) but no API routes were detected, suggesting either server actions only or incomplete route registration.  
**Stack (package.json):** @clerk/nextjs, @hookform/resolvers, @polar-sh/nextjs, @tailwindcss/postcss, @types/node, @types/react, @types/react-dom, @vapi-ai/web, @vercel/blob, class-variance-authority, clsx, eslint · 0 routes

### chameleoncollective  `F` · empty · 55 commits
**What:** No meaningful functionality detected; repository contains only a placeholder README.

**Why:** Unknown — insufficient evidence to determine purpose.

**Grade reason:** No dependencies, no routes, and a one-line README with no content.  
**Stack (unknown):** — · 0 routes

### amandas-app-public  `F` · empty · 44 commits
**What:** No evidence available — no dependencies, routes, or README content were provided.

**Why:** Cannot be determined from the supplied evidence.

**Grade reason:** All evidence fields are empty; nothing can be assessed.  
**Stack (unknown):** — · 0 routes

### npm-auth-proxy  `D` · prototype · 41 commits · 🌐 [https://nging.markcarpenter1.com](https://nging.markcarpenter1.com)
**What:** A Next.js web application that provides an authentication proxy using Clerk for identity management, built with shadcn/ui components and Tailwind CSS.

**Why:** Likely exists to gate access to npm packages or a registry behind authentication, acting as a proxy layer for authorized users.

**Grade reason:** Dependencies are set up but no API routes were detected and the README is empty, suggesting early scaffolding with no implemented functionality visible from the evidence.  
**Stack (package.json):** @base-ui/react, @clerk/nextjs, @clerk/themes, @tailwindcss/postcss, @types/node, @types/react, @types/react-dom, class-variance-authority, clsx, eslint, eslint-config-next, lucide-react · 0 routes

### bank-app  `F` · empty · 37 commits
**What:** No discernible purpose — no dependencies, routes, or README content were found.

**Why:** Cannot be determined from available evidence.

**Grade reason:** Zero evidence: no deps, no routes, no README.  
**Stack (unknown):** — · 0 routes

### Learn-go  `D` · prototype · 30 commits
**What:** A personal learning repository documenting a developer's journey to master Go, featuring a Todo app MVP as a practical exercise.

**Why:** Created to build Go skills targeting an enterprise engineering role (specifically a Geico Staff Engineer position), demonstrating Go microservices and API development.

**Grade reason:** README is polished and goal-oriented but no deps, no detected routes, and minimal code evidence suggest very early or incomplete implementation.  
**Stack (unknown):** — · 0 routes

### amandas-app  `F` · empty · 29 commits
**What:** No code, dependencies, routes, or documentation were found — the repository contains no evidence of functionality.

**Why:** Cannot be determined from available evidence.

**Grade reason:** No deps, no routes, no README, and no detectable content of any kind.  
**Stack (unknown):** — · 0 routes

### Mark0025  `F` · empty · 28 commits
**What:** No evidence available to determine what this repository does.

**Why:** Cannot be inferred from the provided evidence.

**Grade reason:** No dependencies, routes, or README content were provided.  
**Stack (unknown):** — · 0 routes

### CALL-CENTER  `F` · empty · 25 commits
**What:** No code or documentation evidence found; the repository contains no detectable dependencies, routes, or README content.

**Why:** Cannot be determined from available evidence.

**Grade reason:** Zero evidence: no deps, no routes, no README.  
**Stack (unknown):** — · 0 routes

### ghl-workstation  `B` · working · 25 commits
**What:** A FastAPI service that extracts and analyzes GoHighLevel (GHL) CRM accounts for any client company, flattening data to CSVs and exposing structured views of entities, fields, migration status, and mapping quality.

**Why:** Eliminates hand-written, stale status pages by generating live, code-driven reports of what was pulled from a GHL account and how it maps toward a target system (Pete).

**Grade reason:** Rich route surface and clear architectural principles, but README describes an ongoing build-out from scripts to a proper backend, suggesting core functionality works but the system is not yet complete.  
**Stack (pyproject.toml):** fastapi, httpx, loguru, python-dotenv, uvicorn · 19 routes

### claude-phone  `B` · working · 24 commits
**What:** Voice interface that bridges SIP/3CX phone calls to Claude Code — handling inbound calls (talk to Claude) and outbound alerts (Claude calls you) via Whisper STT and ElevenLabs TTS.

**Why:** Gives Claude Code a phone number so developers can interact with their AI assistant and receive proactive alerts hands-free over a standard phone/VoIP line.

**Grade reason:** Clear README, multi-route API surface, and real integrations (ElevenLabs, Whisper, 3CX), but only lint/husky in deps — no test framework or runtime dependencies visible.  
**Stack (package.json):** eslint, husky · 6 routes

### call-center-ops  `F` · empty · 21 commits
**What:** No code, routes, or dependencies were found — the repository contains only an empty README stub.

**Why:** Cannot be determined from available evidence.

**Grade reason:** No implementation whatsoever; only a blank README exists.  
**Stack (unknown):** — · 0 routes

### white-glove-dashboard  `B` · working · 17 commits · 🌐 [https://white-glove.markcarpenter1.com](https://white-glove.markcarpenter1.com)
**What:** A FastAPI dashboard for managing and visualizing White Glove onboarding migrations — tracking client data extraction, CRM migration phases, A2P compliance, and team progress in real time.

**Why:** Exists to give Pete's team a single pane of glass for high-touch client onboarding, replacing manual tracking of multi-phase CRM migrations.

**Grade reason:** Rich route surface covering CRUD, compliance workflows, dry-run/apply patterns, and document templates suggests a functional internal tool, but the flat project structure and single-developer README indicate limited polish and no apparent test coverage.  
**Stack (pyproject.toml):** fastapi, uvicorn · 27 routes

### git-advisor  `B+` · working · 17 commits
**What:** A read-only CLI and web dashboard that inspects local git repositories and reports branch state, dirty files, open PRs, and rule-compliant next steps; also profiles repos for purpose/stack/health and can fact-check profiles against live GitHub.

**Why:** Provides deterministic, read-only git governance and fleet visibility for a homelab or multi-repo developer workflow without risking accidental changes.

**Grade reason:** README is thorough with a clear feature table, install instructions, and Docker support, but no deps are listed and no routes were detected, leaving the implementation surface unverified.  
**Stack (unknown):** — · 0 routes

### langflow-railway  `C` · prototype · 16 commits
**What:** A Railway-hosted deployment template for LangFlow, a visual framework for building LangChain-based AI pipelines via a drag-and-drop UI.

**Why:** Provides a one-click Railway deploy of LangFlow so developers can run a self-hosted visual LLM workflow builder without manual server setup.

**Grade reason:** Template-only repo with no custom code, no detected routes, and minimal configuration — purely a deployment scaffold.  
**Stack (pyproject.toml):** — · 0 routes

### portfolio  `B` · working · 15 commits
**What:** A personal developer portfolio website built with Next.js and React, showcasing skills, projects, and contact information with a visitor counter feature.

**Why:** Exists to present Mark Carpenter's full-stack and AI engineering credentials to potential employers or clients.

**Grade reason:** Complete stack with testing (Playwright), theming (next-themes), state management (zustand), and CI-ready scripts, but no backend routes detected beyond a visitor counter endpoint.  
**Stack (package.json):** @eslint/eslintrc, @playwright/test, @tailwindcss/postcss, @types/node, @types/react, @types/react-dom, @typescript-eslint/eslint-plugin, @typescript-eslint/parser, autoprefixer, eslint, eslint-config-next, eslint-config-prettier · 0 routes

### portfolio  `?` · ? · 15 commits
**What:** —

**Why:** —

**Grade reason:** —  
**Stack (package.json):** @eslint/eslintrc, @playwright/test, @tailwindcss/postcss, @types/node, @types/react, @types/react-dom, @typescript-eslint/eslint-plugin, @typescript-eslint/parser, autoprefixer, eslint, eslint-config-next, eslint-config-prettier · 0 routes

### coachinginc  `B` · prototype · 14 commits
**What:** A public-facing Next.js web page displaying member profiles, genius zones, AI builder spotlights, and event photos for the BAM FAM WhatsApp group at Coaching Inc. Mastermind Orlando 2026.

**Why:** Exists to give the BAM FAM community group a shareable, branded landing page showcasing member expertise and event content.

**Grade reason:** Clear scope and working stack with documented deployment steps, but no detected API routes and appears to be a static display page with placeholder content still in place.  
**Stack (package.json):** @tailwindcss/postcss, @types/node, @types/react, @types/react-dom, mermaid, next, postcss, react, react-dom, tailwindcss, typescript · 0 routes

### go-local-aibot  `B+` · working · 12 commits
**What:** A Go HTTP server that wraps the local Claude CLI and exposes it as an OpenAI-compatible chat-completions endpoint, including streaming SSE responses and token-based auth.

**Why:** Lets any OpenAI-protocol client (TUI agents, local orchestrators, RunPod workers) target a full Claude-Code-with-PAI backend by swapping a base URL instead of changing client code.

**Grade reason:** Clear README, real auth, streaming pipeline, and recent active commits, but no deps list was extractable and routes were not detected by the scanner.  
**Stack (unknown):** — · 0 routes

### devloop  `F` · empty · 10 commits
**What:** No detectable code, dependencies, routes, or documentation were found in this repository.

**Why:** Cannot be determined from available evidence.

**Grade reason:** No dependencies, routes, or README content were present to evaluate.  
**Stack (unknown):** — · 0 routes

### mac-project-manager  `B` · working · 9 commits
**What:** Automated git repository inventory and health auditing tool for macOS that scans local repos, classifies them, scores them against best practices, and syncs results to GitHub Issues for kanban tracking.

**Why:** Solves the problem of managing 90+ git repos on a single Mac by providing daily automated health checks, scoring, and project board synchronization without manual overhead.

**Grade reason:** Well-documented with clear commands and automation, but only one dependency detected and no API routes, suggesting a CLI-only tool with limited code surface verified.  
**Stack (package.json):** @types/bun · 0 routes

### pr-reviewer  `B` · working · 9 commits · 🌐 [https://pr-reviewer.markcarpenter1.com](https://pr-reviewer.markcarpenter1.com)
**What:** TypeScript CLI and webhook server that analyzes GitHub pull requests for main-branch risks, race conditions, and dependency conflicts using the GitHub API.

**Why:** Automates PR safety checks across any GitHub repository without per-repo configuration, reducing manual review overhead.

**Grade reason:** Well-structured with clear docs, modular analyzers, Docker support, and webhook server, but no test framework in deps and no CI configuration evident.  
**Stack (package.json):** @octokit/rest, @types/node, chalk, dotenv, ts-node, typescript · 0 routes

### Visualize-all-AI  `F` · empty · 9 commits
**What:** Unknown — no code, dependencies, or documentation present beyond a repository name.

**Why:** Cannot be determined from available evidence.

**Grade reason:** Repository contains only a title-level README with no dependencies, routes, or implementation.  
**Stack (unknown):** — · 0 routes

### melbudget  `D` · prototype · 8 commits
**What:** A Flask-based budget management application using SQLAlchemy for persistence and pandas for data processing.

**Why:** Exists to provide a personal or small-team budget tracking tool with a web interface backed by a relational database.

**Grade reason:** Dependencies indicate a real stack but no routes were detected and the README is empty, suggesting very early or incomplete scaffolding.  
**Stack (requirements.txt):** flask, flask-sqlalchemy, pandas, python-dotenv, sqlalchemy, werkzeug · 0 routes

### newuser-whiteglove  `F` · empty · 7 commits
**What:** No code or documentation evidence found — repository appears to be empty or uninitialized.

**Why:** Cannot be determined from available evidence.

**Grade reason:** No dependencies, routes, or README content present.  
**Stack (unknown):** — · 0 routes

### war-game  `B` · working · 7 commits
**What:** A command-line and browser-based implementation of the card game War in Go, with both a terminal auto-play mode and an HTTP server rendering a browser UI.

**Why:** Exists as a deliberate learning project to teach Go fundamentals and a real Git workflow simultaneously, using a simple game as a low-distraction vehicle.

**Grade reason:** Well-structured with clear goals, browser and CLI modes, and a test suite, but is explicitly a learning project with a phased roadmap suggesting it is still in progress.  
**Stack (unknown):** — · 0 routes

### npm-auth-gateway  `C` · prototype · 6 commits
**What:** A Next.js companion app for Nginx Proxy Manager that adds user-level access control by auto-whitelisting authenticated users' IPs via OAuth providers (Clerk/NextAuth) into NPM access lists through NPM's REST API.

**Why:** Eliminates the manual admin burden of maintaining IP whitelists in Nginx Proxy Manager as users' IPs change (mobile, VPN, travel) by letting users self-service via authentication.

**Grade reason:** Dependencies and README show a clear, well-articulated design but no API routes were detected, indicating the core automation logic is incomplete or not yet wired up.  
**Stack (package.json):** @base-ui/react, @clerk/nextjs, @clerk/themes, @tailwindcss/postcss, @types/node, @types/react, @types/react-dom, class-variance-authority, clsx, eslint, eslint-config-next, lucide-react · 0 routes

### yt-git-helper  `C` · prototype · 6 commits
**What:** A Go CLI tool that processes YouTube videos by extracting transcripts, formatting them into structured markdown, generating book-style summaries and step-by-step guides, and publishing results as GitHub gists.

**Why:** Automates the extraction and structuring of knowledge from YouTube videos so developers can recreate applications or processes described in video content.

**Grade reason:** README describes ambitious goals with clear structure, but no dependencies or routes were detected, suggesting early-stage scaffolding with little or no implementation.  
**Stack (unknown):** — · 0 routes

### AGOE  `D` · prototype · 5 commits
**What:** A ground-up RTS game implementation in C#/Unity modeled after Age of Empires, built as a structured learning project with planned sprints covering camera, economy, combat, and AI systems.

**Why:** Exists to give the developer a practical, real-world project for mastering C# and Unity architecture through incremental game development.

**Grade reason:** Architecture and planning docs are complete but no code has been written yet — project is pre-implementation.  
**Stack (unknown):** — · 0 routes

### Linux-cheats  `B` · working · 5 commits
**What:** A CLI tool that displays Linux command cheat sheets in both a terminal view and a local web interface, with categorized command references and mnemonics.

**Why:** Provides developers and sysadmins a quick, visually rich reference for common Linux commands without leaving the terminal or browser.

**Grade reason:** Clear README, reasonable deps, CLI and web modes documented, but not yet on PyPI and no routes detected suggesting the web server is embedded rather than a proper API.  
**Stack (requirements.txt):** click, loguru, markdown, pandoc, pillow, pypandoc, python-dotenv, rich, termcolor · 0 routes

### AI-CLEAN-CPU  `C` · prototype · 4 commits
**What:** A Python CLI tool that uses AI (OpenAI GPT-4) to intelligently clean and organize the local file system — scanning directories, assessing risk, and safely moving or deleting files.

**Why:** Solves the problem of manual, error-prone file cleanup by adding AI-driven context awareness and safety guardrails (rollback, backups, validation) around file system operations.

**Grade reason:** README describes an ambitious feature set but no API routes exist, deps show only basic utilities (send2trash, tqdm, colorama) with no OpenAI SDK present, suggesting the implementation lags significantly behind the documentation.  
**Stack (requirements.txt):** colorama, pathlib, pytest, pytest-cov, python-dotenv, send2trash, tqdm · 0 routes

### Fabric-wrksp  `F` · empty · 4 commits
**What:** No evidence found — the repository appears to be empty or uninitialized.

**Why:** Cannot be determined from available evidence.

**Grade reason:** No dependencies, no routes, and no README content were provided.  
**Stack (unknown):** — · 0 routes

### Facebook-Event-Extractor  `B` · working · 4 commits
**What:** A Chrome extension that extracts event details from a Facebook page (152 Bar) and downloads them as JSON, with a popup UI and background service worker.

**Why:** Exists to automate scraping and exporting Facebook event data for a specific venue without manual copy-paste.

**Grade reason:** Complete extension scaffold with proper tooling (TypeScript, ESLint, Prettier, web-ext, hot reload) and clear structure, but no tests and narrowly scoped to a single venue.  
**Stack (package.json):** @extend-chrome/messages, @types/chrome, @types/debug, @types/facebook-js-sdk, @types/node, @types/webextension-polyfill, concurrently, debug, eslint, eslint-config-prettier, eslint-plugin-prettier, prettier · 0 routes

### go-high-level-automation-demo  `B` · prototype · 4 commits
**What:** A Node.js demo suite simulating Go High Level CRM automation tasks: CSV validation/import, phone number normalization, SMS workflow cloning, webhook dispatch, and data purge.

**Why:** Created as a portfolio/skills demonstration for a Go High Level Automation & CRM Specialist role, not as production software.

**Grade reason:** Well-structured with clear scripts, README, and appropriate deps, but explicitly a demo with simulated (not real) integrations and no API routes or tests.  
**Stack (package.json):** csv-parse, csv-stringify, libphonenumber-js, puppeteer · 0 routes

### myzshrc  `C` · working · 4 commits
**What:** A Zsh configuration repository that bundles the Yai AI terminal assistant (OpenAI-powered command generation) with a Python/uv shell automation toolkit.

**Why:** Provides a portable, reproducible shell environment combining AI-assisted command-line tooling with Python automation utilities.

**Grade reason:** README describes two distinct tools but deps are absent and no routes exist, limiting confidence in actual implementation completeness.  
**Stack (unknown):** — · 0 routes

### n8n-clone  `F` · empty · 3 commits
**What:** No code or documentation was detected in this repository.

**Why:** Cannot be determined from available evidence.

**Grade reason:** No dependencies, routes, or README content were found.  
**Stack (unknown):** — · 0 routes

### ts2prisma  `B` · working · 3 commits
**What:** A CLI tool that generates Prisma schema files from TypeScript type definitions and interfaces, with watch mode for automatic regeneration.

**Why:** Inverts Prisma's schema-first workflow so TypeScript-centric teams can use their existing type definitions as the single source of truth for both app types and database schema.

**Grade reason:** Clear purpose, CLI surface, watch mode, and published npm package indicate a functional tool, but no routes and thin dep list suggest limited scope with no evidence of tests or advanced polish.  
**Stack (package.json):** @types/node, chokidar, commander, rimraf, ts-node, typescript · 0 routes

### appwrite2stripe-tutorial  `B` · working · 2 commits
**What:** An Appwrite cloud function that integrates Stripe subscriptions — it initiates checkout sessions and handles Stripe webhooks to create/delete subscriptions and update Appwrite user permissions accordingly.

**Why:** Solves the boilerplate of wiring Stripe recurring payments into an Appwrite-hosted backend without a custom server.

**Grade reason:** Well-documented routes and clear dependencies, but no detected route files in code — logic likely lives in a single entrypoint not surfaced by the route scan.  
**Stack (package.json):** node-appwrite, prettier, stripe, stripe-event-types · 0 routes

### claude-ai-proclamation  `F` · empty · 2 commits
**What:** A repository containing markdown documents asserting an AI constitutional compliance proclamation and violation tracking framework.

**Why:** Appears to exist as a social/political statement or attempted manipulation framework rather than a software tool.

**Grade reason:** No code, no dependencies, no routes — only markdown documents with no functional implementation.  
**Stack (unknown):** — · 0 routes

### DOG-AGE-CALC  `C` · prototype · 2 commits
**What:** A command-line tool that converts a dog's age in human years to dog years using a tiered formula (15 years for year 1, 9 for year 2, 5 for each subsequent year).

**Why:** Built as a teaching project to introduce basic Python concepts to the developer's children.

**Grade reason:** README is complete and the concept is clear, but no dependency manifest or route surface exists to confirm implementation depth beyond the README description.  
**Stack (unknown):** — · 0 routes

### oscn-webscraper  `F` · empty · 2 commits
**What:** A web scraper targeting OSCN (likely Oklahoma State Courts Network), but no implementation is present.

**Why:** Intended to extract court records or case data from the OSCN public portal.

**Grade reason:** No dependencies, no routes, and a blank README — only the repo name exists as evidence.  
**Stack (unknown):** — · 0 routes

### Go-Book-Store-App  `C` · prototype · 2 commits
**What:** A full-stack bookstore demo with a Go REST API backend (gorilla/mux) and a Next.js frontend for listing books.

**Why:** Exists as a learning reference for beginner-to-intermediate developers exploring Go+Next.js full-stack patterns.

**Grade reason:** README documents intent and structure well but no deps or routes were detected, suggesting incomplete or scaffold-only implementation.  
**Stack (unknown):** — · 0 routes

### next-js-reps  `D` · prototype · 2 commits
**What:** A Next.js web application scaffolded from the default create-next-app template with Tailwind CSS and TypeScript. No custom routes or features have been added.

**Why:** Serves as a starting point for a Next.js project; no domain-specific problem is evident from the evidence.

**Grade reason:** Unmodified scaffolding with no custom routes, components, or functionality beyond the boilerplate.  
**Stack (package.json):** @eslint/eslintrc, @tailwindcss/postcss, @types/node, @types/react, @types/react-dom, eslint, eslint-config-next, next, react, react-dom, tailwindcss, typescript · 0 routes

### Marks-Resume  `C` · working · 2 commits
**What:** A personal CLI toolset that converts Markdown resume and cover letter files into styled PDFs and compiles certificate images into a single PDF document.

**Why:** Eliminates manual formatting by letting the developer maintain resume content in plain Markdown and regenerate polished PDFs on demand.

**Grade reason:** Functional for its narrow personal use case but has no routes, no tests, no abstraction, and is a collection of one-off scripts rather than a structured application.  
**Stack (package.json):** http-server, image-size, markdown-it, markdown-pdf, pdf-lib, pdfkit, puppeteer · 0 routes

### tauros  `?` · ? · 2 commits
**What:** —

**Why:** —

**Grade reason:** —  
**Stack (unknown):** — · 0 routes

### notesappwrite  `F` · empty · 2 commits
**What:** A Next.js web application scaffold named 'notesappwrite', intended to be a notes app, but containing only the default create-next-app boilerplate with no application code.

**Why:** Likely created as a starting point for a notes-taking application, but no meaningful functionality has been implemented yet.

**Grade reason:** No routes, no application logic, and an unmodified README — this is a bare scaffold with zero domain implementation.  
**Stack (package.json):** @eslint/eslintrc, @tailwindcss/postcss, @types/node, @types/react, @types/react-dom, eslint, eslint-config-next, next, react, react-dom, tailwindcss, typescript · 0 routes

### aider-enhance  `C` · prototype · 1 commits
**What:** A Python tool that extends and configures the Aider AI coding assistant, adding configuration management, model selection, usage analysis, and workflow templates on top of the base aider-chat package.

**Why:** Exists to simplify and optimize Aider setup for developers who want guided configuration and enhanced workflows beyond Aider's defaults.

**Grade reason:** Dependencies are substantive and README describes real features, but usage docs are placeholder text and no routes or runnable entry points are evident.  
**Stack (requirements.txt):** aider-chat, anthropic, inquirer, openai, playwright, pytest, pytest-cov, python-dotenv, pyyaml, rich, schedule · 0 routes

### auto-dossier  `C` · prototype · 1 commits
**What:** A FastAPI-based web service likely providing automated dossier or report generation, combining data processing (pandas), web scraping (beautifulsoup4), and HTML/Markdown rendering (jinja2, markdown2) into structured outputs with optional visualizations (plotly).

**Why:** Automates the creation of research dossiers or intelligence reports by gathering, processing, and presenting data in a formatted, web-accessible interface.

**Grade reason:** Solid dependency selection signals a real design intent, but no routes are implemented and the README is empty, indicating early-stage scaffolding.  
**Stack (pyproject.toml):** beautifulsoup4, black, fastapi, httpx, isort, jinja2, loguru, markdown2, mypy, pandas, plotly, pydantic · 0 routes

### completed-interviews  `F` · empty · 1 commits
**What:** No evidence found — the repository appears to be empty or contains no detectable code, dependencies, or routes.

**Why:** Cannot be determined from available evidence.

**Grade reason:** No dependencies, routes, or README content were provided.  
**Stack (unknown):** — · 0 routes

### crawler  `F` · empty · 1 commits
**What:** A web crawler HTTP service; exact behavior is undocumented.

**Why:** Likely exists to fetch and index web content via HTTP, but no implementation details are available.

**Grade reason:** No dependencies, no routes, and a README with only a title — no evidence of working code.  
**Stack (unknown):** — · 0 routes

### FastAPI  `D` · prototype · 1 commits · 🌐 [https://pete-fastapi.markcarpenter1.com](https://pete-fastapi.markcarpenter1.com)
**What:** A minimal FastAPI web server with a single GET / route, served via Hypercorn.

**Why:** Exists as a Railway deployment template to give developers a ready-to-deploy FastAPI starting point.

**Grade reason:** Bare scaffold with one route and no application logic beyond the framework defaults.  
**Stack (requirements.txt):** fastapi, hypercorn · 1 routes

### FINANCES  `F` · empty · 1 commits
**What:** No implementation found; repository contains only a title.

**Why:** Unknown — insufficient evidence.

**Grade reason:** No dependencies, no routes, and a README with only a heading — nothing to evaluate.  
**Stack (unknown):** — · 0 routes

### Gdrive-SuperAGI  `D` · prototype · 1 commits
**What:** A Python toolkit that wraps the Google Drive API to provide file upload, download, listing, and deletion operations via a single GoogleDriveAPI class.

**Why:** Provides a reusable Google Drive integration module, likely intended as a tool/plugin for the SuperAGI autonomous agent framework.

**Grade reason:** Dependencies and README describe intent but no routes or implemented source code are evident — documentation precedes actual implementation.  
**Stack (requirements.txt):** google-api-python-client, google-auth-httplib2, google-auth-oauthlib · 0 routes

### GOOGLE-COLAB  `F` · empty · 1 commits
**What:** A repository initialized from Google Colab containing only shell commands for setting up git and pushing to GitHub. No application code, logic, or functionality is present.

**Why:** Exists as a placeholder or scratch space created during a Colab session to sync notebook work to GitHub.

**Grade reason:** No source code, dependencies, or routes — only git initialization shell commands in the README.  
**Stack (unknown):** — · 0 routes

### nextjs  `B` · prototype · 1 commits · 🌐 [https://aireinvestor.com](https://aireinvestor.com)
**What:** A Next.js todo list app that stores todos in a PostgreSQL database using Prisma ORM with SWR for client-side data fetching and optimistic updates.

**Why:** Serves as a reference/template for deploying a full-stack Next.js + Prisma + PostgreSQL application on Railway.

**Grade reason:** Well-defined stack with migrations and SWR integration, but no API routes detected and scope is limited to a demo todo app.  
**Stack (package.json):** @prisma/client, @types/node, @types/react, next, prisma, react, react-dom, swr, typescript · 0 routes

### okcounty-scraper  `F` · empty · 1 commits
**What:** No code or documentation evidence found — the repository appears to be empty or uninitialized.

**Why:** Cannot be determined from available evidence.

**Grade reason:** No dependencies, no routes, and no README content detected.  
**Stack (unknown):** — · 0 routes

### OPENAI  `C` · prototype · 1 commits
**What:** A minimal ChatGPT plugin quickstart that exposes a per-user to-do list via a REST API, including the required plugin manifest and OpenAPI spec endpoints.

**Why:** Provides a working reference implementation for developers learning to build ChatGPT plugins.

**Grade reason:** Functional scaffold with all required plugin endpoints but no persistence layer, auth, or production hardening.  
**Stack (requirements.txt):** quart, quart-cors · 6 routes

### python-training  `F` · empty · 1 commits
**What:** No evidence found — the repository appears to be empty or contains no detectable dependencies, routes, or README content.

**Why:** Cannot be determined from available evidence.

**Grade reason:** No dependencies, no routes, and no README content were provided to evaluate.  
**Stack (unknown):** — · 0 routes

### Runpod_image_gen  `B` · working · 1 commits
**What:** A FastAPI server that bridges RunPod GPU image generation jobs with a local web gallery — it accepts AI-generated images from RunPod (via base64 API responses or direct upload), stores them, and serves them through a browser-based gallery UI.

**Why:** Provides a lightweight self-hosted frontend and REST API to manage and view AI-generated images produced by RunPod serverless GPU workers, removing the need for manual file handling.

**Grade reason:** Full CRUD route surface, responsive UI, scripted workflow, and clean dependency set indicate a functional and reasonably polished tool, but no tests, auth, or production hardening are evident.  
**Stack (pyproject.toml):** aiofiles, fastapi, httpx, pillow, psutil, python-dotenv, python-multipart, requests, uvicorn, watchdog · 10 routes

### snapify  `B+` · working · 1 commits
**What:** Snapify is a self-hostable screen recording and sharing platform that lets users record their tab, desktop, or applications and share recordings via public links with optional expiry/unlisting.

**Why:** It exists as an open-source, self-hostable alternative to Loom for async video communication without vendor lock-in.

**Grade reason:** Full production stack (Next.js/tRPC/Prisma/S3/Auth/Redis/QStash/Playwright) with a live deployment and uptime monitoring, but no API routes were detected in the evidence scan, leaving the callable surface unconfirmed.  
**Stack (package.json):** @aws-sdk/client-s3, @aws-sdk/s3-request-presigner, @headlessui/react, @heroicons/react, @next-auth/prisma-adapter, @playwright/test, @popperjs/core, @prisma/client, @radix-ui/react-icons, @radix-ui/react-tooltip, @tanstack/react-query, @trpc/client · 0 routes

### testagi  `F` · empty · 1 commits
**What:** No evidence available to determine what this repository does.

**Why:** Cannot be determined from the provided evidence.

**Grade reason:** No dependencies, no routes, and no README content were provided.  
**Stack (unknown):** — · 0 routes

### Website-Copier  `F` · empty · 1 commits
**What:** No evidence of functionality could be found — no dependencies, no routes, and no README content.

**Why:** Cannot be determined from the available evidence.

**Grade reason:** Zero evidence of implementation: no deps, no routes, no README.  
**Stack (unknown):** — · 0 routes

### OLLAMA-DEEPSEEK  `F` · empty · 1 commits
**What:** No evidence found — the repository appears to be empty or uninitialized.

**Why:** Cannot be determined from available evidence.

**Grade reason:** No dependencies, no routes, and no README content were provided.  
**Stack (unknown):** — · 0 routes

### QuickBooks-PO-Automation  `C` · prototype · 1 commits
**What:** Extracts data from purchase order documents (PDFs, scanned images) using OCR and AI, then creates vendors, items, and purchase orders in QuickBooks Desktop Enterprise.

**Why:** Eliminates manual data entry for fashion and beauty businesses processing high volumes of purchase orders.

**Grade reason:** Dependencies and README are coherent but no API routes exist and the repo appears demo/presentation-oriented rather than production-deployed.  
**Stack (package.json):** @types/jest, @types/node, csv-parser, dotenv, jest, node-quickbooks, openai, pdf-parse, tesseract.js, ts-jest, ts-node, typescript · 0 routes

### speeduplearner  `B` · working · 1 commits
**What:** A Chrome extension that adds playback speed controls to YouTube, letting users select from 0.25x–3.0x speeds with an overlay UI and persistent settings between sessions.

**Why:** Gives learners finer-grained control over YouTube video speed than the native player provides, optimizing content consumption pace.

**Grade reason:** Well-structured TypeScript/Webpack build pipeline, clear feature set, and documented code layout, but no routes or tests are evident and no production distribution mechanism is present.  
**Stack (package.json):** @types/chrome, @types/node, @typescript-eslint/eslint-plugin, @typescript-eslint/parser, clean-webpack-plugin, copy-webpack-plugin, css-loader, eslint, eslint-config-prettier, eslint-plugin-import, html-webpack-plugin, prettier · 0 routes

### Francis-Ablola  `F` · empty · 1 commits
**What:** No code, dependencies, routes, or README content were found in this repository.

**Why:** Cannot be determined from the available evidence.

**Grade reason:** Repository appears to be completely empty with no detectable code, dependencies, or documentation.  
**Stack (unknown):** — · 0 routes

### Mark.Ai  `F` · empty · 0 commits
**What:** Evidence is insufficient to determine what this repository does — no dependencies, routes, or README content were provided.

**Why:** Cannot be determined from the available evidence.

**Grade reason:** No code, dependencies, routes, or documentation were present in the evidence supplied.  
**Stack (unknown):** — · 0 routes

### portfolio  `B` · working · 0 commits
**What:** A personal developer portfolio website built with Next.js and React, showcasing skills, projects, and contact information with features like a visitor counter and dark mode support.

**Why:** Exists to market Mark Carpenter as a full-stack and AI engineer to potential clients or employers.

**Grade reason:** Complete component structure, testing setup (Playwright), state management (Zustand), and a live deployment, but no API routes were detected despite the README referencing a visitor counter endpoint.  
**Stack (package.json):** @eslint/eslintrc, @playwright/test, @tailwindcss/postcss, @types/node, @types/react, @types/react-dom, @typescript-eslint/eslint-plugin, @typescript-eslint/parser, autoprefixer, eslint, eslint-config-next, eslint-config-prettier · 0 routes

### rmdclone  `F` · empty · 0 commits
**What:** No evidence of any code, dependencies, or routes was found in this repository.

**Why:** Cannot be determined — the repository appears to be empty or uninitialized.

**Grade reason:** No dependencies, no routes, and no README content detected.  
**Stack (unknown):** — · 0 routes

### WhatsWorking  `F` · empty · 0 commits
**What:** No code, routes, or README content was detected in this repository.

**Why:** Cannot be determined from available evidence.

**Grade reason:** No dependencies, routes, or README content found to evaluate.  
**Stack (unknown):** — · 0 routes

### portfolio  `B` · working · 0 commits
**What:** A personal developer portfolio built with Next.js, React, and Tailwind CSS, showcasing skills, projects, and a visitor counter with a contact modal.

**Why:** Exists to present Mark Carpenter's full-stack and AI engineering credentials to potential clients or employers.

**Grade reason:** Well-structured Next.js app with Playwright tests, theming, and state management, but no backend API routes were detected beyond the described visitor counter.  
**Stack (package.json):** @eslint/eslintrc, @playwright/test, @tailwindcss/postcss, @types/node, @types/react, @types/react-dom, @typescript-eslint/eslint-plugin, @typescript-eslint/parser, autoprefixer, eslint, eslint-config-next, eslint-config-prettier · 0 routes

### Company-wrkflow  `F` · empty · 0 commits
**What:** No code, dependencies, routes, or README content are present in the evidence.

**Why:** Cannot be determined from the available evidence.

**Grade reason:** Repository contains no detectable code, dependencies, or documentation.  
**Stack (unknown):** — · 0 routes


## homelab / tooling

### 00Myhomelab  `B+` · production · 1519 commits · 🌐 [https://terry.markcarpenter1.com](https://terry.markcarpenter1.com)
**What:** A self-managing homelab infrastructure platform on Hetzner Cloud, combining Claude Code AI automation, n8n workflow orchestration, monitoring (Prometheus/Grafana), and containerized services into an autonomous, self-healing system.

**Why:** Exists to give Mark Carpenter a production-grade personal homelab that manages and heals itself using AI-driven automation cycles rather than manual ops.

**Grade reason:** Rich README with concrete runtime metrics (212+ cycles, 23/23 containers, active dashboards) and a real FastAPI/uvicorn stack, but no routes are detected in the codebase scan, leaving the API surface unverified.  
**Stack (pyproject.toml):** fastapi, mypy, ruff, uvicorn · 0 routes

### bash  `B` · working · 35 commits
**What:** A deterministic Bash-and-artifact execution engine that discovers CLI tools via semantic capability mapping, executes commands through capability routing, and stores artifacts with SHA256 verification and SQLite-backed integrity.

**Why:** Exists to provide reproducible, auditable CLI pipeline execution for personal infrastructure automation without relying on cloud orchestrators or AI decision engines.

**Grade reason:** 100% tests passing and clear architecture docs, but self-declared not production-ready and lacking load/concurrency validation.  
**Stack (pyproject.toml):** — · 0 routes

### homelab-status  `B` · working · 28 commits
**What:** A FastAPI web dashboard and CLI that ingests GitHub activity across 120+ repos and 4 homelab servers, then surfaces cross-repo analytics, service health, infrastructure summaries, and AI-generated learning content (journey interviews, fix-commit ratios, agent attribution) in a single UI.

**Why:** Exists to give a solo homelab operator a unified view of 200+ repos and 4 servers so recurring patterns, repeated mistakes, and architectural decisions are visible and learnable rather than scattered across GitHub history.

**Grade reason:** Shipped core ingestion, analytics, and dashboard routes with a real data footprint (121 repos, 5k+ commits), but README explicitly flags two planned epics as unimplemented and the route surface suggests several capabilities are still in-progress stubs.  
**Stack (pyproject.toml):** anthropic, anyio, fastapi, httpx, jinja2, loguru, pandas, plotly, rich, typer, uvicorn · 57 routes

### 00infrastructure  `D` · prototype · 14 commits
**What:** Documentation and analysis repo that records discovered problems with Claude Code context-loading hooks and proposes fixes for a home-lab AI infrastructure setup.

**Why:** Exists to diagnose and prove fixes for a broken hook-based context system where Claude was not loading the correct CLAUDE.md files during sessions.

**Grade reason:** No code, no deps, no routes — purely a README with a problem statement and a partial fix sketch.  
**Stack (unknown):** — · 0 routes
