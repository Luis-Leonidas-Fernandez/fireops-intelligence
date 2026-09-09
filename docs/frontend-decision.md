# Frontend decision

This document records the current frontend direction for FireOps Intelligence.

## Decision

Use **React + Vite + TypeScript** for the first internal web application.

## Why

The backend is already designed as a FastAPI API. A separate React + Vite frontend keeps the system easy to explain and teach:

```text
React + Vite
  ↓ HTTP requests
FastAPI
  ↓ SQLAlchemy
PostgreSQL
```

This separation helps beginners understand what each layer does.

## What React provides

React will be used for:

- forms;
- tables;
- filters;
- screens;
- client-side validation messages;
- API result rendering;
- reusable UI components.

## What Vite provides

Vite will be used for:

- fast local development;
- React project setup;
- hot reload while coding;
- production builds.

## Alternatives considered

| Option | Current decision | Reason |
|---|---|---|
| Next.js | Not first choice for the initial class path | Adds SSR and full-stack concepts too early |
| Astro | Useful later for public docs or landing pages | Better for content sites than internal CRUD screens |
| Flutter Web | Not first choice for this web app | Adds Dart and a different UI model while students are learning Python, SQL, Git, and APIs |
| Django | Not selected for the current backend | The project already uses FastAPI, SQLAlchemy, Alembic, and explicit API architecture |

## Teaching rule

The first frontend should reinforce the backend concepts already being taught:

```text
form input
  ↓
fetch POST /inventory/assets
  ↓
FastAPI validates and saves
  ↓
PostgreSQL stores the asset
  ↓
React shows the result
```

Do not introduce a heavier framework until there is a real product need.
