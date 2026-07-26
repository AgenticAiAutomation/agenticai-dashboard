"""
Seed script to import data from SEO_CONTENT_TASKS.md and keyword-cluster.md
Run with: python -m app.seed
"""
import re
import os
import sys
from sqlalchemy.orm import Session
from app.database import SessionLocal, engine
from app.models import User, Keyword, Article, Task, Base
from app.auth import get_password_hash
from app.config import settings


def parse_tasks_md(filepath: str) -> list:
    """Parse SEO_CONTENT_TASKS.md to extract tasks"""
    tasks = []

    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # Extract tasks from each phase
    phase_pattern = r'##\s+Phase\s+(\d+)[^\n]*\n(.*?)(?=##\s+Phase|\Z)'
    phases = re.findall(phase_pattern, content, re.DOTALL)

    for phase_num, phase_content in phases:
        # Extract task items: - [ ] **X.Y** Task title
        task_pattern = r'-\s+\[\s*\]\s+\*\*([0-9.]+)\*\*\s+([^\n]+)'
        task_matches = re.findall(task_pattern, phase_content)

        for task_code, title in task_matches:
            # Determine owner_role based on phase or task content
            owner_role = 'seo'  # Default
            if phase_num == '0':
                owner_role = 'owner'
            elif 'distribution' in title.lower() or 'linkedin' in title.lower():
                owner_role = 'owner'

            tasks.append({
                'phase': phase_num,
                'task_code': task_code,
                'title': title.strip(),
                'owner_role': owner_role,
                'status': 'open'
            })

    return tasks


def parse_keywords_md(filepath: str) -> list:
    """Parse keyword-cluster.md to extract keywords"""
    keywords = []

    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # Track A - BFSI
    bfsi_pattern = r'### Pillar 1: BFSI.*?\n\n\*\*Cluster keywords.*?\n\n(.*?)(?=\*\*Notes:|###|\Z)'
    bfsi_match = re.search(bfsi_pattern, content, re.DOTALL)
    if bfsi_match:
        keywords.extend(parse_keyword_table(bfsi_match.group(1), 'A', 'BFSI'))

    # Track A - Logistics
    logistics_pattern = r'### Pillar 2: Logistics.*?\n\n\*\*Cluster keywords.*?\n\n(.*?)(?=\*\*Notes:|###|\Z)'
    logistics_match = re.search(logistics_pattern, content, re.DOTALL)
    if logistics_match:
        keywords.extend(parse_keyword_table(logistics_match.group(1), 'A', 'Logistics'))

    # Track B - D2C
    d2c_pattern = r'### Pillar 3: WhatsApp Automation for D2C.*?\n\n\*\*Cluster keywords.*?\n\n(.*?)(?=\*\*Notes:|###|\Z)'
    d2c_match = re.search(d2c_pattern, content, re.DOTALL)
    if d2c_match:
        keywords.extend(parse_keyword_table(d2c_match.group(1), 'B', 'D2C'))

    # Track B - Coaching
    coaching_pattern = r'### Pillar 4: WhatsApp Automation for Coaching.*?\n\n\*\*Cluster keywords.*?\n\n(.*?)(?=\*\*Notes:|###|\Z)'
    coaching_match = re.search(coaching_pattern, content, re.DOTALL)
    if coaching_match:
        keywords.extend(parse_keyword_table(coaching_match.group(1), 'B', 'Coaching'))

    return keywords


def parse_keyword_table(table_text: str, track: str, pillar: str) -> list:
    """Parse a keyword table from markdown"""
    keywords = []
    lines = table_text.strip().split('\n')

    for line in lines:
        if '|' not in line or '---' in line or '# | Keyword' in line:
            continue

        parts = [p.strip() for p in line.split('|')]
        if len(parts) < 7:
            continue

        # Skip header and separator rows
        if parts[1] in ['#', '']:
            continue

        try:
            keyword_text = parts[2]
            intent = parts[3] if len(parts) > 3 else None
            comp = int(parts[4]) if len(parts) > 4 and parts[4].isdigit() else None
            fit = int(parts[5]) if len(parts) > 5 and parts[5].isdigit() else None
            qw = int(parts[6]) if len(parts) > 6 and parts[6].isdigit() else None

            # Extract score from last column (may have stars)
            score_col = parts[7] if len(parts) > 7 else '0'
            score_match = re.search(r'\*\*(\d+)\*\*', score_col)
            score = int(score_match.group(1)) if score_match else 0

            keywords.append({
                'track': track,
                'pillar': pillar,
                'keyword': keyword_text,
                'intent': intent,
                'comp': comp,
                'fit': fit,
                'qw': qw,
                'score': score,
                'status': 'draft'
            })
        except (ValueError, IndexError):
            continue

    return keywords


def create_initial_articles(db: Session, keywords: list) -> None:
    """Create article placeholders for pillars, clusters, and countries"""
    articles = []

    # 4 pillar pages
    pillars = [
        ('enterprise-bfsi', 'Agentic AI in Banking and Insurance', 'A', 'BFSI', 'pillar'),
        ('enterprise-logistics', 'Agentic AI for Logistics Automation', 'A', 'Logistics', 'pillar'),
        ('whatsapp-d2c', 'WhatsApp Automation for D2C Brands', 'B', 'D2C', 'pillar'),
        ('whatsapp-coaching', 'WhatsApp Automation for Coaching Institutes', 'B', 'Coaching', 'pillar'),
    ]

    for slug, title, track, vertical, article_type in pillars:
        article = Article(
            slug=slug,
            title=title,
            track=track,
            vertical=vertical,
            article_type=article_type,
            status='briefed'
        )
        db.add(article)
        articles.append(article)

    # 32 cluster articles (one per keyword)
    for idx, kw in enumerate(keywords[:32]):  # Limit to 32
        slug = kw['keyword'].lower().replace(' ', '-')[:50]
        article = Article(
            slug=f"{slug}-{idx}",
            title=kw['keyword'].title(),
            track=kw['track'],
            vertical=kw['pillar'],
            article_type='cluster',
            status='briefed'
        )
        db.add(article)

    # 10 country pages
    countries = [
        ('bfsi-us', 'Agentic AI for Banking - United States', 'US', 'BFSI'),
        ('bfsi-uk', 'Agentic AI for Banking - United Kingdom', 'UK', 'BFSI'),
        ('bfsi-canada', 'Agentic AI for Banking - Canada', 'Canada', 'BFSI'),
        ('bfsi-au', 'Agentic AI for Banking - Australia', 'AU', 'BFSI'),
        ('bfsi-nz', 'Agentic AI for Banking - New Zealand', 'NZ', 'BFSI'),
        ('bfsi-sg', 'Agentic AI for Banking - Singapore', 'SG', 'BFSI'),
        ('bfsi-uae', 'Agentic AI for Banking - UAE', 'UAE', 'BFSI'),
        ('logistics-germany', 'Agentic AI for Logistics - Germany', 'Germany', 'Logistics'),
        ('logistics-us', 'Agentic AI for Logistics - United States', 'US', 'Logistics'),
        ('logistics-sg', 'Agentic AI for Logistics - Singapore', 'SG', 'Logistics'),
    ]

    for slug, title, country, vertical in countries:
        article = Article(
            slug=slug,
            title=title,
            track='A',
            vertical=vertical,
            country=country,
            article_type='country',
            status='briefed'
        )
        db.add(article)

    db.commit()
    print(f"✓ Created {len(pillars) + 32 + len(countries)} article placeholders")


def seed_database():
    """Main seed function"""
    db = SessionLocal()

    try:
        print("Starting database seed...")

        # 1. Create owner user
        owner_email = settings.INITIAL_OWNER_EMAIL.lower()
        existing_owner = db.query(User).filter(User.email == owner_email).first()
        if not existing_owner:
            owner = User(
                email=owner_email,
                password_hash=get_password_hash(settings.INITIAL_OWNER_PASSWORD),
                full_name="Jai (Owner)",
                role="owner"
            )
            db.add(owner)
            db.commit()
            print(f"✓ Created owner user: {settings.INITIAL_OWNER_EMAIL}")
        else:
            print(f"✓ Owner user already exists: {settings.INITIAL_OWNER_EMAIL}")

        # 2. Parse and import tasks
        tasks_file = os.path.join(os.path.dirname(__file__), '..', 'seed-data', 'SEO_CONTENT_TASKS.md')
        if os.path.exists(tasks_file):
            tasks = parse_tasks_md(tasks_file)
            for task_data in tasks:
                task = Task(**task_data)
                db.add(task)
            db.commit()
            print(f"✓ Imported {len(tasks)} tasks from SEO_CONTENT_TASKS.md")
        else:
            print(f"⚠ Tasks file not found: {tasks_file}")

        # 3. Parse and import keywords
        keywords_file = os.path.join(os.path.dirname(__file__), '..', 'seed-data', 'keyword-cluster.md')
        if os.path.exists(keywords_file):
            keywords = parse_keywords_md(keywords_file)
            for kw_data in keywords:
                keyword = Keyword(**kw_data)
                db.add(keyword)
            db.commit()
            print(f"✓ Imported {len(keywords)} keywords from keyword-cluster.md")

            # 4. Create article placeholders
            create_initial_articles(db, keywords)
        else:
            print(f"⚠ Keywords file not found: {keywords_file}")

        print("\n✅ Database seeding completed successfully!")
        print(f"\nInitial login credentials:")
        print(f"  Email: {settings.INITIAL_OWNER_EMAIL}")
        print(f"  Password: {settings.INITIAL_OWNER_PASSWORD}")
        print(f"\n⚠️  Change the password on first login!")

    except Exception as e:
        print(f"\n❌ Error during seeding: {str(e)}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed_database()
