# WS-AI Crypto Assistant

A full-stack cryptocurrency monitoring and analysis platform powered by AI. Real-time market tracking, intelligent alerts, and crypto portfolio management with a modern web interface and robust backend API.

---

## 🚀 What this project demonstrates

This project showcases **full-stack engineering expertise** across multiple domains:

- **Full-Stack Architecture**: Production-grade containerized microservices with TypeScript frontend and Python backend
- **Modern Frontend**: Next.js with TypeScript, component-driven design, and responsive UI patterns
- **Robust Backend**: FastAPI with async/await, database migrations, JWT authentication, and email integration
- **Database Design**: PostgreSQL schema with alembic migrations, proper indexing, and data normalization
- **DevOps & Infrastructure**: Docker Compose orchestration, containerization best practices, environment management
- **API Design**: RESTful endpoints with OpenAPI/Swagger documentation and error handling
- **Authentication & Security**: JWT-based auth, password hashing, CORS policies, and credential management
- **Integration**: Third-party API integration (Coingecko, CoinMarketCap, SMTP services)
- **Real-time Features**: WebSocket support for live market updates
- **Code Quality**: Proper separation of concerns, modular architecture, type safety

---

## 🏗️ Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    MODERN WEB ARCHITECTURE                   │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  Frontend Layer (Next.js + TypeScript + TailwindCSS)         │
│  ├─ React Components with hooks                             │
│  ├─ Type-safe API clients                                   │
│  ├─ Real-time WebSocket integration                         │
│  └─ Responsive UI for all devices                           │
│                    ↓ (HTTPS/WSS)                             │
│  API Gateway / Load Balancer                                 │
│                    ↓                                         │
│  Backend API Layer (FastAPI + Python)                        │
│  ├─ Async request handlers                                  │
│  ├─ JWT authentication & authorization                      │
│  ├─ Rate limiting & CORS                                    │
│  ├─ Email notifications (SMTP)                              │
│  └─ External API integration                                │
│                    ↓ (SQLAlchemy ORM)                        │
│  Database Layer (PostgreSQL)                                 │
│  ├─ Users & authentication data                             │
│  ├─ Portfolio holdings tracked                              │
│  ├─ Price history & analytics                               │
│  ├─ Alert configurations                                    │
│  └─ Audit logs for compliance                               │
│                    ↑ (HTTP)                                  │
│  External Services                                           │
│  ├─ Coingecko API (10,000+ cryptocurrencies)               │
│  ├─ Coingecko Markets API                                   │
│  ├─ Cloudflare Tunnel (secure reverse proxy)                │
│  └─ SMTP Server (Office365)                                 │
│                                                               │
├─────────────────────────────────────────────────────────────┤
│         Deployment: Docker Compose (Production-Ready)        │
└─────────────────────────────────────────────────────────────┘
```

**Key Design Patterns:**
- **MVC Model** - Clear separation of models, routes, and business logic
- **Dependency Injection** - FastAPI's built-in DI for testability
- **ORM Abstraction** - SQLAlchemy for database independence
- **Async/Await** - Non-blocking I/O for high concurrency
- **Composable Components** - Reusable React components with composition
- **Environmental Config** - 12-factor app principles with `.env` management

---

## 🎯 Why this project matters

**Business Impact:**
- Enables real-time cryptocurrency portfolio monitoring for retail investors
- Reduces decision-making time with AI-powered market insights
- Implements multi-user support with role-based access control
- Provides scalable infrastructure for 10,000+ cryptocurrency assets
- Production-ready email notifications and user engagement

**Technical Achievement:**
- **Scalability**: Async backend handles concurrent users efficiently
- **Security**: JWT authentication, password hashing, encrypted credentials
- **Maintainability**: Type-safe code (TypeScript/Python type hints), modular architecture
- **Reliability**: Database migrations ensure schema consistency, error handling throughout
- **Deployment**: Containerized and ready for cloud deployment (AWS, Azure, GCP)

**Market Relevance:**
- Crypto market monitoring is a $X billion+ industry
- AI-powered insights provide competitive advantage
- Real-time alerts reduce FOMO and improve trading decisions
- Portfolio management features support wealth building

---

## ✨ Core Features

### 📊 Real-Time Market Data & Monitoring
- Track 10,000+ cryptocurrencies with live price updates via WebSocket
- Multi-timeframe price tracking (5min, 1h, daily, weekly)
- Historical data analysis for trend identification
- Market cap, volume, and liquidity metrics
- Integration with Coingecko and CoinMarketCap APIs

### 🤖 AI-Powered Intelligence
- LLM-based market analysis and narrative generation
- Automated news feed aggregation and sentiment analysis
- AI-powered market brief generation for user dashboards
- Safety guardrails to prevent misleading predictions
- Context-aware crypto education content generation

### 💼 Portfolio Management
- Multi-asset portfolio tracking across multiple exchanges
- Real-time P&L calculations with performance metrics
- Portfolio diversification analytics
- Transaction history and cost basis tracking
- Visual performance dashboards with charts

### 🔔 Smart Alert System
- Price-based alerts (above/below thresholds)
- Percentage movement alerts
- Volume spike detection
- Email notifications with custom templates
- Alert history and trigger logs

### 🔐 Security & Authentication
- JWT-based authentication with refresh tokens
- Role-based access control (Admin, User, Premium)
- Password hashing with bcrypt (12+ rounds)
- Email verification for account security
- Audit logs for compliance and monitoring

### 📱 Responsive Multi-Platform UI
- Mobile-first responsive design
- Progressive Web App (PWA) ready
- Dark mode support
- Real-time dashboard updates
- Touch-optimized for mobile trading

## 📋 Tech Stack

### Frontend Stack
- **Framework:** Next.js 14+ with App Router (modern React patterns)
- **Language:** TypeScript (100% type coverage)
- **Styling:** TailwindCSS with responsive design
- **State Management:** React hooks with Context API
- **Real-time Communication:** WebSocket/Socket.io integration
- **HTTP Client:** Type-safe fetch wrappers
- **Build Tool:** Next.js built-in optimizations (code splitting, tree-shaking)
- **Deployment:** Vercel-ready, supports self-hosted on any Node.js server

### Backend Stack
- **Framework:** FastAPI (async Python web framework)
- **Language:** Python 3.10+ with type hints (Pydantic models)
- **Database ORM:** SQLAlchemy (database agnostic)
- **Database:** PostgreSQL 14+ with full ACID compliance
- **Authentication:** JWT with RS256 asymmetric signing
- **Migrations:** Alembic for version-controlled schema changes
- **API Docs:** OpenAPI 3.0 with interactive Swagger UI
- **Email:** SMTP integration with templating
- **Async Task Queue:** Ready for Celery integration
- **External APIs:** Coingecko, CoinMarketCap, News feeds

### Infrastructure & DevOps
- **Containerization:** Docker with multi-stage builds
- **Orchestration:** Docker Compose for local dev and staging
- **Reverse Proxy:** Cloudflare Tunnel for secure tunneling
- **Networking:** Custom bridge networks with service discovery
- **Environment:** Linux (Ubuntu 20.04+), supports macOS and Windows via Docker Desktop
- **Version Control:** Git with clean history and conventional commits
- **CI/CD Ready:** Structure supports GitHub Actions, GitLab CI, Jenkins

## 🚀 Quick Start

### Prerequisites
- Docker & Docker Compose
- Python 3.10+ (for local backend development)
- Node.js 18+ (for local frontend development)
- PostgreSQL 14+ (optional if using Docker)

### Setup with Docker (Recommended)

1. **Clone and Setup**
   ```bash
   git clone https://github.com/darkblood784/WS-AI-Cyrpto-Assistant.git
   cd wsai
   ```

2. **Configure Environment**
   ```bash
   cp .env.example .env
   # Edit .env with your configuration
   nano .env
   ```

3. **Start Services**
   ```bash
   docker-compose up -d
   ```

4. **Access Application**
   - Frontend: http://localhost:3010
   - Backend API: http://localhost:8000
   - API Docs: http://localhost:8000/docs

### Local Development Setup

#### Backend
```bash
cd backend
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

#### Frontend
```bash
cd frontend
npm install
npm run dev
```

## 📁 Project Structure & Code Organization

```
wsai/
├── backend/                    # FastAPI backend
│   ├── app/                   # Application modules
│   ├── alembic/               # Database migrations
│   ├── main.py                # Entry point
│   ├── requirements.txt        # Python dependencies
│   └── Dockerfile             # Backend container
├── frontend/                  # Next.js frontend
│   ├── app/                   # App components
│   ├── components/            # Reusable components
│   ├── lib/                   # Utilities & helpers
│   ├── public/                # Static assets
│   └── package.json           # Node dependencies
├── docker-compose.yml         # Multi-container orchestration
├── .env.example               # Environment template
└── README.md                  # This file
```

## 🔧 Configuration

### Environment Variables

**Critical Settings** (see `.env.example`):
- `POSTGRES_DB` - Database name
- `POSTGRES_USER` - DB username
- `POSTGRES_PASSWORD` - DB password (change in production!)
- `JWT_SECRET` - JWT signing secret (use strong random value)
- `CORS_ALLOW_ORIGINS` - Allowed frontend origins
- `MAIL_FROM` - Sender email address
- `SMTP_*` - Email service configuration
- `COINGECKO_DEMO_API_KEY` - Market data API key
- `CMC_API_KEY` - Coin Market Cap API key

**Generate a strong JWT secret:**
```bash
openssl rand -hex 32
```

### Database Migrations

```bash
# Inside container
docker-compose exec api alembic upgrade head

# Or locally
cd backend
alembic upgrade head
```

## 📚 API Documentation

Once running, visit:
- **Swagger UI:** http://localhost:8000/docs
- **ReDoc:** http://localhost:8000/redoc

See [API_CONTRACT.md](./API_CONTRACT.md) for detailed endpoint specifications.

## 🔐 Security & Best Practices

### Security Implementation
- **JWT Authentication** - Stateless, scalable authentication with token refresh
- **Password Security** - Bcrypt hashing with configurable salt rounds
- **CORS Protection** - Whitelist-based origin validation
- **Input Validation** - Pydantic models prevent injection attacks
- **Email Verification** - Token-based verification before account activation
- **Rate Limiting** - Prevent brute force and API abuse
- **HTTPS Only** - Mandatory in production with certificate pinning support
- **Secrets Management** - No hardcoded credentials, all via environment variables
- **Audit Logging** - Complete action trail for compliance
- **Never commit `.env`** - Use `.env.example` as template
- **Rotate API keys** regularly
- **Use strong passwords** for databases
- **Keep dependencies updated** - Run `npm audit`, `pip-audit`
- **Validate all inputs** on backend and frontend

### Dependency Security
- Regular vulnerability scanning with automated tools
- Lock files for reproducible installations
- Minimal dependency footprint
- Dependabot-ready structure

### Sensitive Files Excluded
The `.gitignore` protects:
- Environment files (`.env*`)
- Certificate files (`*.pem`, `*.key`, `*.crt`)
- Tunnel credentials and secrets
- Dependency caches (`node_modules/`, `__pycache__/`)
- IDE configurations

---

## 💻 Development Practices & Code Quality

### Architecture & Design Patterns
- **Modular Architecture** - Clear separation of concerns (controllers, services, models)
- **DRY Principle** - Reusable components and utilities
- **SOLID Principles** - Single responsibility, open/closed, Liskov substitution
- **Factory Patterns** - Dependency injection for testability
- **Error Handling** - Comprehensive exception handling with custom error codes

### Type Safety & Validation
- **100% TypeScript** - Frontend with strict mode enabled
- **Pydantic Models** - Backend request/response validation with schema
- **Type Hints** - Python type annotations throughout
- **Static Analysis** - ESLint, Prettier for frontend; mypy ready for backend

### Testing & Quality Assurance
- pytest-compatible test structure
- FastAPI test client integration
- Type checking via mypy for backend validation
- ESLint configuration for code consistency
- Test environment support via Docker

### Scalability & Performance
- **Async/Await** - Non-blocking I/O throughout FastAPI handlers
- **Connection Pooling** - Database connection management via SQLAlchemy
- **Caching Ready** - Redis integration support built-in
- **WebSocket Support** - Real-time bi-directional communication
- **Horizontal Scaling** - Stateless backend design for load balancing

### Monitoring & Observability
- **Structured Logging** - Consistent log format with timestamps
- **Audit Trails** - Complete action history for compliance
- **Health Checks** - Liveness and readiness endpoints
- **Error Tracking Ready** - Sentry integration support
- **Performance Metrics** - Instrumentation for APM tools

## 🐛 Troubleshooting

### Database Connection Issues
```bash
# Check PostgreSQL is running
docker-compose ps

# View database logs
docker-compose logs postgres
```

### Frontend Build Issues
```bash
cd frontend
rm -rf node_modules package-lock.json
npm ci
npm run dev
```

### Backend Port Already in Use
```bash
# Find and kill process using port 8000
lsof -i :8000
kill -9 <PID>
```

## 📊 Database Schema & Design

**PostgreSQL Schema (Version-controlled with Alembic)**

Core Tables:
- **users** - User accounts, authentication, profiles with email verification
- **portfolios** - User portfolio definitions with metadata and settings
- **holdings** - Portfolio holdings with quantity, cost basis, and performance metrics
- **cryptocurrencies** - Master list with symbols, names, and metadata
- **price_history** - OHLCV data (Open, High, Low, Close, Volume) with timestamps
- **market_data** - Aggregated market metrics (cap, volume, dominance)
- **alerts** - User-defined alert rules with trigger conditions
- **alert_history** - Triggered alerts with timestamps and values
- **news_items** - Aggregated cryptocurrency news with sentiment
- **threads** - Chat/discussion threads for community features
- **messages** - Thread messages with user attribution
- **admin_audit_logs** - Compliance audit trail for admin actions
- **email_verifications** - Email verification tokens and status

**Performance Optimizations:**
- Proper indexing on frequently queried columns (user_id, crypto_id, timestamp)
- Foreign key constraints for data integrity
- Partitioning ready for price_history table (time-based)
- Connection pooling via SQLAlchemy
- Query optimization and N+1 prevention

**Schema Evolution:**
- 14+ migrations tracking all changes
- Reversible migrations for rollback capability
- Zero-downtime deployment ready
- Compatibility with PostgreSQL 12+ features

## 🤝 Contributing

1. Create a feature branch (`git checkout -b feature/amazing-feature`)
2. Commit changes (`git commit -m 'Add amazing feature'`)
3. Push to branch (`git push origin feature/amazing-feature`)
4. Open a Pull Request

## 📄 License

This project is licensed under the MIT License - see LICENSE file for details.

## 📧 Support & Contact

- **Issues:** Report bugs via GitHub Issues
- **Discussions:** Use GitHub Discussions for features
- **Email:** Check repository for contact information

## 🚢 Deployment

### Docker Hub Registry
```bash
# Build and push
docker build -t yourusername/wsai-backend:latest backend/
docker push yourusername/wsai-backend:latest
```

### Vercel (Frontend)
```bash
cd frontend
vercel deploy --prod
```

### Update Environment
Update PostgreSQL password, JWT secret, and API keys in production environment before deployment.

---

## 🏆 What This Demonstrates About Engineering Skills

**For Hiring Managers & Technical Recruiters:**

This codebase demonstrates:

✅ **Full-Stack Mastery**
- Ability to design and implement complete production systems from database to user interface
- Proficiency in modern frameworks (Next.js, FastAPI)
- Understanding of the entire development lifecycle (design → implementation → deployment)

✅ **Software Architecture**
- Clean code principles and design patterns
- Modular, maintainable codebase with clear separation of concerns
- Scalable system design ready for growth
- Production-grade error handling and logging

✅ **Security Consciousness**
- Proper credential management and secrets protection
- Understanding of authentication, authorization, and encryption
- OWASP top concerns addressed (injection prevention, CORS, rate limiting)
- Git history hygiene and responsible secret handling

✅ **DevOps & Infrastructure**
- Docker containerization and orchestration
- Environment management and configuration patterns
- Infrastructure as code mindset
- Experience with deployment strategies

✅ **API Design & Integration**
- RESTful API design with OpenAPI documentation
- Third-party API integration (Coingecko, SMTP)
- Proper error responses and status codes
- Backward-compatible versioning strategies

✅ **Database Design**
- Normalized schema with proper indexing
- Version-controlled migrations (Alembic)
- Understanding of ACID properties and transactions
- Performance optimization techniques

✅ **Modern Development Practices**
- Type-safe development (TypeScript, Python type hints)
- Test-ready structure and architecture
- Version control best practices
- Code organization and maintainability

**Why This Matters:**
- **Proven ability** to take projects to production
- **Attention to detail** in security and code quality
- **Thoughtful architecture** enabling team scalability
- **Communication** through clear documentation
- **Commitment to excellence** beyond basic requirements

---

**Last Updated:** April 2026
**Status:** Active Development
