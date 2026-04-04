# Vakil AI - Intelligent Legal Research Platform

## Introduction

VakilAI is a specialized preparation infrastructure designed for Indian litigation lawyers to streamline the review of massive case files. Built on the principle of zero-trust generation, every piece of information provided by the AI is hard-linked to a specific page and paragraph in the uploaded documents. The system acts as a secure, isolated vault for proprietary data, ensuring that no case information is used for training or shared across users. By focusing on reliability and transparency, VakilAI helps lawyers identify risks and contradictions that might otherwise be missed in hundreds of pages of legal documentation.

---

## Technologies Used

| Category | Technology Stack |
|----------|------------------|
| **Frontend** | Next.js, React, TypeScript ,TailwindCSS|
| **Backend** | Python, FastAPI |
| **Database** | PostgreSQL, pgvector, SQL |
| **Document Processing** | AWS Textract, Vector Embeddings, Chunking |
| **AI/ML Services** | OpenAI Embedding Models, Groq(llama3-70b-versatile) |
| **Cloud Services** | Vultr (VPS), Cloudinary, ElevenLabs, Indian Kanoon API |
| **Other/Tools** | pnpm, uv/venv, Git/Github |

---

## Key Features

- **Document Analysis (X-Ray):** Advanced PDF and document scanning with AI-powered insights
- **Brief Generation:** Automatic creation of hearing briefs from case documents
- **Contradiction Detection:** Machine learning-based identification of case inconsistencies
- **Legal Search:** Full-text search across statute database and uploaded documents
- **Speech Synthesis:** Audio generation for briefs via ElevenLabs integration
- **Multi-User Authentication:** Secure login and role-based access control
- **Case Management:** Organize, categorize, and manage multiple legal cases
- **File Management:** Cloudinary integration for secure document storage

---

## Project Folder Structure

```
vakil-ai/
├── backend/
│   ├── routers/          (API endpoints)
│   ├── services/         (Business logic)
│   ├── pipelines/        (Data processing)
│   ├── database/         (DB connection & schema)
│   ├── data/             (Statutes & uploads)
│   └── main.py           (FastAPI application)
├── frontend/
│   ├── app/              (Next.js pages & layouts)
│   ├── components/       (React components)
│   ├── lib/              (API client & utilities)
│   └── package.json      (Dependencies)
└── README.md
```



## Prerequisites & Installation

### Requirements
- Python 3.10+ (uv)
- Node.js 18+ (pnpm/npm)
- PostgreSQL 13+

### Backend Setup

```bash
cd backend
cp .env.local .env
uv sync
uv run uvicorn main:app --reload --port 8000
```

### Frontend Setup

```bash
cd frontend
pnpm install
cp .env.local .env
pnpm dev
```


Access the application at **http://localhost:3000**

---

## API Documentation

Backend API documentation available at: **http://localhost:8000/docs**

---

## Architecture Diagram

VakilAI Architecture Diagram available at: **https://drive.google.com/file/d/1trKacQyVeSLT2Gt3QIP4DzjSiLFC3Kfo/view?usp=sharing**

---
