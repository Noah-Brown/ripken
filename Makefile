.PHONY: backend frontend db-init install install-backend install-frontend dev

# Install all dependencies
install: install-backend install-frontend

install-backend:
	uv venv .venv
	. .venv/bin/activate && uv pip install -e ".[dev]"

install-frontend:
	cd frontend && npm install

# Start backend (FastAPI on :8000)
backend:
	. .venv/bin/activate && uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000

# Start frontend (Next.js on :3000)
frontend:
	cd frontend && npm run dev

# Initialize / reset the database (tables created on backend startup via SQLAlchemy)
db-init:
	. .venv/bin/activate && python3 -c "import asyncio; from backend.database.connection import engine; from backend.database.models import Base; asyncio.run((lambda: Base.metadata.create_all(engine))())"
	@echo "Database initialized."

# Run both backend and frontend in parallel
dev:
	$(MAKE) -j2 backend frontend

# Run tests
test:
	. .venv/bin/activate && pytest backend/tests -v

# Lint
lint:
	. .venv/bin/activate && ruff check backend/ shared/
