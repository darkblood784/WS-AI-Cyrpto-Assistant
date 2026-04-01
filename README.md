# WS-AI Crypto Assistant

A full-stack cryptocurrency monitoring and analysis platform powered by AI. Real-time market tracking, intelligent alerts, and crypto portfolio management with a modern web interface and robust backend API.

## 🎯 Features

- **Real-Time Market Monitoring** - Track Bitcoin, Ethereum, and 10,000+ cryptocurrencies
- **AI-Powered Analysis** - Intelligent market insights and trend analysis
- **Portfolio Management** - Track your crypto holdings and performance
- **Email Alerts** - Customizable notifications for price movements
- **Multi-Chain Support** - Monitor blockchain networks
- **RESTful API** - Fast, scalable backend for data operations
- **Responsive UI** - Modern Next.js frontend with real-time updates

## 📋 Tech Stack

### Frontend
- **Framework:** Next.js with TypeScript
- **Styling:** TailwindCSS
- **State Management:** React hooks
- **Real-time Updates:** WebSocket support
- **Deployment Ready:** Vercel compatible

### Backend
- **Framework:** FastAPI (Python)
- **Database:** PostgreSQL with SQLAlchemy ORM
- **API Documentation:** OpenAPI/Swagger
- **Email Service:** SMTP integration
- **Authentication:** JWT-based

### Infrastructure
- **Containerization:** Docker & Docker Compose
- **Database:** PostgreSQL
- **Reverse Proxy:** Cloudflare integration
- **Environment:** Linux (Tested on Ubuntu 20.04+)

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

## 📁 Project Structure

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

## 🔐 Security

- **Never commit `.env`** - Use `.env.example` as template
- **Rotate API keys** regularly
- **Use strong passwords** for databases
- **Enable HTTPS** in production
- **Keep dependencies updated** - Run `npm audit`, `pip-audit`
- **Validate all inputs** on backend and frontend

### Sensitive Files Excluded
The `.gitignore` protects:
- Environment files (`.env*`)
- Certificate files (`*.pem`, `*.key`)
- Dependency caches (`node_modules/`, `__pycache__/`)
- Secrets and credentials

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

## 📊 Database Schema

The application uses PostgreSQL with alembic for schema management. Key tables:
- `users` - User accounts and authentication
- `portfolios` - User crypto holdings
- `cryptocurrencies` - Tracked assets
- `price_history` - Historical price data
- `alerts` - User alert configurations

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

**Last Updated:** April 2026
**Status:** Active Development
