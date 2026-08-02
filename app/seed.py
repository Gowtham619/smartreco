"""Idempotent seed script: creates the admin account and a sample course
catalog (dual-written to SQL + the vector store via product_service).

Run with: python -m app.seed
"""

import logging

from app.auth import hash_password
from app.config import settings
from app.database import SessionLocal, init_db
from app.models import Product, User, UserRole
from app.services import product_service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("smartreco.seed")

COURSES = [
    ("Agentic AI Foundations", "Learn what makes an AI system 'agentic': tool use, planning loops, and memory. Build your first autonomous agent from scratch.", "Agentic AI & LangGraph", 49.0, "Beginner"),
    ("Building Multi-Agent Systems with LangGraph", "Design explicit reasoning workflows with LangGraph — nodes, conditional edges, retries, and shared state — for production-grade agent orchestration.", "Agentic AI & LangGraph", 129.0, "Advanced"),
    ("RAG for Production Agents", "Ground your agents in real data with retrieval-augmented generation: chunking, embeddings, vector databases, and evaluation.", "Agentic AI & LangGraph", 89.0, "Intermediate"),
    ("Advanced Agent Orchestration Patterns", "Supervisor agents, tool routing, human-in-the-loop checkpoints, and evaluation loops for complex multi-step agent systems.", "Agentic AI & LangGraph", 149.0, "Advanced"),
    ("Prompt Engineering for Autonomous Agents", "Structured prompting techniques purpose-built for agentic workflows: JSON-mode outputs, tool schemas, and self-correction.", "Agentic AI & LangGraph", 69.0, "Intermediate"),
    ("Python for Data Analysis", "Master pandas, NumPy, and data wrangling fundamentals to turn messy datasets into insight.", "Data Science & ML", 39.0, "Beginner"),
    ("Machine Learning Foundations", "Core supervised and unsupervised learning algorithms, model evaluation, and the math behind them.", "Data Science & ML", 59.0, "Beginner"),
    ("Deep Learning with PyTorch", "Build and train neural networks from scratch — CNNs, RNNs, and transformer basics — using PyTorch.", "Data Science & ML", 99.0, "Intermediate"),
    ("MLOps: Deploying ML at Scale", "Take models from notebook to production: model registries, monitoring, and automated retraining pipelines.", "Data Science & ML", 119.0, "Advanced"),
    ("Modern JavaScript Essentials", "ES2023 features, async patterns, and the fundamentals every frontend developer needs.", "Web Development", 29.0, "Beginner"),
    ("Full-Stack Web Apps with FastAPI", "Build production-ready APIs and server-rendered apps with FastAPI, SQLAlchemy, and Jinja2.", "Web Development", 79.0, "Intermediate"),
    ("React & TypeScript Bootcamp", "Component architecture, hooks, and type-safe frontend development with React and TypeScript.", "Web Development", 89.0, "Intermediate"),
    ("Scalable Backend Architecture", "Design backend systems that scale: caching, queues, database sharding, and service boundaries.", "Web Development", 139.0, "Advanced"),
    ("AWS Cloud Practitioner Bootcamp", "Core AWS services, IAM, networking, and cost management to get your first cloud certification.", "Cloud & DevOps", 49.0, "Beginner"),
    ("Kubernetes for Engineers", "Deploy, scale, and operate containerized applications on Kubernetes with confidence.", "Cloud & DevOps", 99.0, "Intermediate"),
    ("CI/CD Pipelines with GitHub Actions", "Automate testing, builds, and deployments with GitHub Actions workflows and reusable pipelines.", "Cloud & DevOps", 59.0, "Intermediate"),
    ("Product Management Fundamentals", "Roadmapping, user research, and stakeholder communication for new and aspiring PMs.", "Product Management", 45.0, "Beginner"),
    ("Data-Driven Product Strategy", "Use metrics, experimentation, and cohort analysis to make confident product decisions.", "Product Management", 75.0, "Intermediate"),
]


def seed():
    init_db()
    db = SessionLocal()
    try:
        if not db.query(User).filter(User.email == settings.admin_email).first():
            admin = User(
                email=settings.admin_email,
                password_hash=hash_password(settings.admin_password),
                role=UserRole.admin,
            )
            db.add(admin)
            db.commit()
            logger.info("Created admin account: %s", settings.admin_email)
        else:
            logger.info("Admin account already exists: %s", settings.admin_email)

        existing_titles = {p.title for p in db.query(Product.title).all()}
        created = 0
        for title, description, category, price, level in COURSES:
            if title in existing_titles:
                continue
            product_service.create_product(db, title, description, category, price, level)
            created += 1
        logger.info("Seeded %d new course(s) (dual-written to SQL + vector store)", created)
    finally:
        db.close()


if __name__ == "__main__":
    seed()
