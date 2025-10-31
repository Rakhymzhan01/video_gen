# Video Generation Backend

A production-ready video generation platform integrating Veo 3 (Google), Sora 2 (OpenAI), and Kling (Kuaishou).

## Features

- **Multi-Provider Support**: Intelligent routing between Veo 3, Sora 2, and Kling
- **Text-to-Video**: Generate videos from text prompts
- **Image-to-Video**: Generate videos from text + reference images
- **Async Processing**: Scalable worker-based architecture
- **Production Ready**: Security, monitoring, billing, error handling

## Tech Stack

- **Backend**: Python 3.11+ with FastAPI
- **Databases**: PostgreSQL (metadata), MongoDB (logs), Redis (cache/queue)
- **Queue**: RabbitMQ
- **Storage**: AWS S3 / MinIO (local dev)
- **Infrastructure**: Docker + Docker Compose
- **Monitoring**: Prometheus + Grafana + ELK Stack

## Quick Start

```bash
# Clone and setup
git clone <repo>
cd vide_gen

# Start all services
docker-compose up -d

# Run migrations
docker-compose exec api-gateway alembic upgrade head

# View logs
docker-compose logs -f
```

## Project Structure

```
vide_gen/
├── services/           # Microservices
│   ├── api-gateway/   # Main API gateway
│   ├── auth/          # Authentication service
│   ├── image/         # Image upload & processing
│   ├── video/         # Video generation orchestration
│   ├── billing/       # Credit management
│   └── notification/  # Webhooks & notifications
├── workers/           # Background workers
│   ├── video-worker/  # Video processing
│   └── post-processor/ # Video post-processing
├── shared/            # Common utilities
│   ├── database/      # DB models & connections
│   ├── auth/          # Auth utilities
│   ├── storage/       # S3/MinIO client
│   └── providers/     # Provider adapters
├── infrastructure/    # Docker & K8s configs
├── migrations/        # Database migrations
├── tests/            # Test suites
└── docs/             # Documentation
```

## API Documentation

Once running, visit:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## License

MIT