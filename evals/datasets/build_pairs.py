"""Spit out the 20 synthetic pairs. Fictional people only."""

from __future__ import annotations

import json
from pathlib import Path

# skill lists are all things the resume actually claims. the gate should pass.
ROWS = [
    ("p01", "Jordan Q. Sample", "Austin, TX", ["Python", "FastAPI", "PostgreSQL", "Docker"], "Backend Engineer"),
    ("p02", "Priya N. Example", "Denver, CO", ["Python", "Django", "PostgreSQL", "Redis"], "Backend Engineer"),
    ("p03", "Samir T. Demo", "Seattle, WA", ["Java", "Kafka", "Docker", "Kubernetes"], "Platform Engineer"),
    ("p04", "Casey L. Placeholder", "Chicago, IL", ["Golang", "Kubernetes", "Terraform", "AWS"], "Platform Engineer"),
    ("p05", "Morgan A. Fictitious", "Portland, OR", ["React", "TypeScript", "GraphQL", "PostgreSQL"], "Software Engineer"),
    ("p06", "Riley Chen Sample", "Boston, MA", ["Python", "Pandas", "Spark", "Airflow"], "Data Engineer"),
    ("p07", "Avery Brooks Example", "Atlanta, GA", ["Python", "PyTorch", "Docker", "AWS"], "Software Engineer"),
    ("p08", "Quinn Patel Demo", "Dallas, TX", ["Java", "Kafka", "Redis", "Docker"], "Backend Engineer"),
    ("p09", "Harper Diaz Placeholder", "Miami, FL", ["Ruby", "Rails", "PostgreSQL", "Redis"], "Software Engineer"),
    ("p10", "Skyler Nguyen Sample", "San Jose, CA", ["Python", "Flask", "Docker", "PostgreSQL"], "Backend Engineer"),
    ("p11", "Reese Okonkwo Example", "Minneapolis, MN", ["Scala", "Spark", "Kafka", "AWS"], "Data Engineer"),
    ("p12", "Drew Alvarez Demo", "Phoenix, AZ", ["Kotlin", "Java", "Docker", "Kubernetes"], "Software Engineer"),
    ("p13", "Emerson Walsh Placeholder", "Nashville, TN", ["Rust", "PostgreSQL", "Docker", "Kubernetes"], "Backend Engineer"),
    ("p14", "Rowan Kim Sample", "Raleigh, NC", ["Python", "Terraform", "GCP", "Kubernetes"], "Platform Engineer"),
    ("p15", "Finley Abbas Example", "Columbus, OH", ["Python", "Airflow", "Snowflake", "dbt"], "Data Engineer"),
    ("p16", "Sawyer Ibrahim Demo", "Madison, WI", ["JavaScript", "TypeScript", "React", "Nodejs"], "Software Engineer"),
    ("p17", "Parker Cho Placeholder", "Boise, ID", ["Python", "FastAPI", "Redis", "Docker"], "Backend Engineer"),
    ("p18", "Blake Moreau Sample", "Omaha, NE", ["Python", "Prometheus", "Grafana", "Kubernetes"], "Software Engineer"),
    ("p19", "Hayden Costa Example", "Tucson, AZ", ["Python", "Pydantic", "FastAPI", "PostgreSQL"], "Backend Engineer"),
    ("p20", "Jules Berg Demo", "Spokane, WA", ["Python", "Celery", "Redis", "Docker"], "Backend Engineer"),
]


def resume_for(name: str, city: str, skills: list[str], title: str) -> str:
    a, b, c, d = skills
    email = name.split()[0].lower() + "." + name.split()[-1].lower() + "@example.com"
    return (
        f"{name}\n"
        f"{city} | {email}\n"
        f"\n"
        f"SUMMARY\n"
        f"Software engineer who uses {a} and {b} on production systems.\n"
        f"\n"
        f"EXPERIENCE\n"
        f"{title}, Fictional Labs LLC, 2021 - Present\n"
        f"• Built {a} services with {b} for internal tools at Fictional Labs LLC.\n"
        f"• Shipped {c} backed workflows and {d} deploys for the same team.\n"
        f"\n"
        f"EDUCATION\n"
        f"B.S. Computer Science, State University of Nowhere (fictional), 2018\n"
        f"Relevant coursework: {a}\n"
        f"\n"
        f"SKILLS\n"
        f"{a}, {b}, {c}, {d}\n"
        f"\n"
        f"PROJECTS\n"
        f"Weekend notes app using {b}. Personal project, not a product.\n"
    )


def jd_for(title: str, skills: list[str]) -> str:
    listed = ", ".join(skills)
    return (
        f"Example Corp (fictional) — {title}\n"
        f"Must have: {listed}.\n"
        f"Nice to have: writing things down.\n"
    )


def pairs() -> list[dict]:
    out = []
    for pid, name, city, skills, title in ROWS:
        out.append({
            "id": pid,
            "name": name,
            "company": "Example Corp",
            "title": title,
            "must_have": skills,
            "resume_text": resume_for(name, city, skills, title),
            "jd_text": jd_for(title, skills),
        })
    return out


def main() -> None:
    dest = Path(__file__).with_name("pairs.jsonl")
    lines = [json.dumps(row, ensure_ascii=True) for row in pairs()]
    dest.write_text("\n".join(lines) + "\n")
    print(f"wrote {len(lines)} pairs to {dest}")


if __name__ == "__main__":
    main()
