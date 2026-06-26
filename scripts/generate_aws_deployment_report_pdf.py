"""Generate Smart Shopper AWS deployment options PDF report."""

from __future__ import annotations

from pathlib import Path

try:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import (
        PageBreak,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "reportlab is required. Install with: python -m pip install reportlab"
    ) from exc


OUTPUT = Path(__file__).resolve().parents[1] / "docs" / "Smart_Shopper_AWS_Deployment_Report.pdf"


def _cell(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def build_story() -> list:
    styles = getSampleStyleSheet()
    title = ParagraphStyle(
        "Title",
        parent=styles["Title"],
        fontSize=20,
        spaceAfter=14,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#1a365d"),
    )
    h1 = ParagraphStyle(
        "H1",
        parent=styles["Heading1"],
        fontSize=14,
        spaceBefore=16,
        spaceAfter=8,
        textColor=colors.HexColor("#1a365d"),
    )
    h2 = ParagraphStyle(
        "H2",
        parent=styles["Heading2"],
        fontSize=11,
        spaceBefore=10,
        spaceAfter=6,
        textColor=colors.HexColor("#2c5282"),
    )
    body = ParagraphStyle(
        "Body",
        parent=styles["BodyText"],
        fontSize=9,
        leading=13,
        alignment=TA_JUSTIFY,
        spaceAfter=6,
    )
    bullet = ParagraphStyle(
        "Bullet",
        parent=body,
        leftIndent=12,
        bulletIndent=0,
        spaceAfter=3,
    )
    small = ParagraphStyle("Small", parent=body, fontSize=8, textColor=colors.grey)

    story: list = []

    story.append(Paragraph("Smart Shopper", title))
    story.append(Paragraph("AWS Cloud Deployment Options Report", title))
    story.append(Spacer(1, 0.2 * cm))
    story.append(
        Paragraph(
            "Minimum cost vs best quality — benchmark comparison for the Smart Shopper "
            "multi-agent architecture (Kafka, NER, Playwright scrapers, Redis, MongoDB).",
            body,
        )
    )
    story.append(Spacer(1, 0.3 * cm))
    story.append(
        Paragraph(
            "<b>Project:</b> Smart Shopper PFA &nbsp;|&nbsp; "
            "<b>Region recommendation:</b> eu-west-3 (Paris) or eu-south-2 (Spain) &nbsp;|&nbsp; "
            "<b>Date:</b> June 2026",
            small,
        )
    )
    story.append(Spacer(1, 0.5 * cm))

    # Executive summary
    story.append(Paragraph("Executive Recommendation", h1))
    story.append(
        Paragraph(
            "<b>Best balance (recommended): Option B — ECS on EC2 (Graviton) + self-hosted Kafka "
            "+ ElastiCache Valkey + MongoDB Atlas M10</b>",
            body,
        )
    )
    rec_data = [
        ["Aspect", "Detail"],
        ["Estimated cost", "~$180–280/month (production-like beta)"],
        ["Reliability", "Managed cache + DB, separate compute, auto-restart"],
        ["Fit", "Docker images ready; no Kubernetes required yet"],
        ["Avoid for now", "EKS $73/month + MSK $450+/month until traffic justifies them"],
    ]
    t = Table(rec_data, colWidths=[4 * cm, 13 * cm])
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2c5282")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f7fafc")]),
            ]
        )
    )
    story.append(t)
    story.append(Spacer(1, 0.3 * cm))
    story.append(
        Paragraph(
            "<b>PFA / demo (lowest cost):</b> Option A — single EC2 + docker-compose.full.yml "
            "(~$90–150/month with Spot/Reserved Instance).",
            body,
        )
    )
    story.append(
        Paragraph(
            "<b>Production at scale:</b> Option C — EKS + MSK (~$550–900/month) when you have "
            "traffic and a Kubernetes-capable team. Existing deploy/k8s/ manifests are ready.",
            body,
        )
    )

    # Workload profile
    story.append(Paragraph("Your Workload Profile", h1))
    workload = [
        ["Component", "Resources", "Notes"],
        ["NER service", "3–6 GB RAM, 1–2 vCPU", "Hugging Face model ~1 GB; must stay warm"],
        ["Scraper ×3", "1–3 GB each", "Playwright-heavy; 14 parallel sites"],
        ["6 other agents", "~512 MB each", "Light Kafka consumers"],
        ["Kafka", "12+ topics", "Most expensive managed-service mistake if mis-sized"],
        ["Redis", "512 MB – 1 GB", "Cache + rate limits"],
        ["MongoDB", "512 MB – 2 GB", "User memory + price watches"],
        ["Minimum server", "32 GB RAM, 4–8 vCPU", "Or split app + data tier"],
    ]
    wt = Table(workload, colWidths=[3.5 * cm, 4.5 * cm, 9 * cm])
    wt.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2c5282")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 7.5),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f7fafc")]),
            ]
        )
    )
    story.append(wt)

    story.append(PageBreak())

    # Five options
    story.append(Paragraph("Five AWS Deployment Options", h1))

    options = [
        (
            "Option A — Single EC2 + Docker Compose (Cheapest MVP)",
            "~$90–150/month",
            "1× EC2 r7g.xlarge (4 vCPU, 32 GB) running docker-compose.full.yml. "
            "MongoDB Atlas M0 (free) optional.",
            [
                ("EC2 r7g.xlarge (eu-west-3)", "~$184"),
                ("50 GB gp3 EBS", "~$5"),
                ("Data transfer", "~$5–15"),
                ("MongoDB Atlas M0", "$0"),
                ("Total (on-demand)", "~$194"),
                ("With Spot / 1-yr RI", "~$90–120"),
            ],
            "Pros: Cheapest, identical to local dev, fast PFA demo setup.",
            "Cons: No HA, single point of failure, manual backups.",
            "Scores: Cost 10/10 | Reliability 3/10 | Scalability 2/10 | PFA ready 10/10",
        ),
        (
            "Option B — ECS on EC2 + Managed Data (RECOMMENDED)",
            "~$180–280/month",
            "2× EC2 r7g.large ECS workers. Self-hosted Kafka on t4g.medium OR MSK kafka.t3.small. "
            "ElastiCache Valkey cache.t4g.small. MongoDB Atlas M10. ECR for images.",
            [
                ("2× r7g.large ECS workers", "~$184"),
                ("1× t4g.medium Kafka (self-hosted)", "~$30"),
                ("ElastiCache cache.t4g.small (Valkey)", "~$24"),
                ("MongoDB Atlas M10", "~$57"),
                ("ECR + CloudWatch + secrets", "~$10–20"),
                ("Total", "~$305"),
                ("With Spot + 1-yr RI", "~$180–220"),
            ],
            "Pros: Best cost/quality ratio; managed Redis + Mongo; Dockerfiles work as-is.",
            "Cons: You manage Kafka (or ~$100 for minimal MSK).",
            "Scores: Cost 9/10 | Reliability 7/10 | Scalability 7/10 | Production 8/10",
        ),
        (
            "Option C — EKS + MSK + Managed Services (Production)",
            "~$550–900/month",
            "EKS cluster using existing deploy/k8s/ manifests. MSK kafka.t3.small × 3. "
            "ElastiCache + Atlas M10. HPA for scrapers (hpa.yaml).",
            [
                ("EKS control plane", "$73"),
                ("2× m7g.xlarge nodes", "~$278"),
                ("MSK kafka.t3.small × 3", "~$100"),
                ("ElastiCache cache.t4g.small", "~$24"),
                ("MongoDB Atlas M10", "~$57"),
                ("NAT Gateway + ALB + logs", "~$52–85"),
                ("Total", "~$584–627"),
                ("Under HPA peak load", "~$800–1,200"),
            ],
            "Pros: Matches K8s manifests, HPA, multi-AZ capable, production-grade.",
            "Cons: $73/month before compute; needs Kubernetes expertise (3–6 months learning).",
            "Scores: Cost 4/10 | Reliability 10/10 | Scalability 10/10 | K8s fit 10/10",
        ),
        (
            "Option D — ECS Fargate (Simplest Ops)",
            "~$350–500/month",
            "All 13 containers on Fargate (serverless). MSK or self-hosted Kafka. "
            "ElastiCache + Atlas M10.",
            [
                ("NER (2 vCPU, 4 GB)", "~$60"),
                ("Scraper ×3 (1 vCPU, 2 GB)", "~$90"),
                ("7 other agents", "~$70"),
                ("Kafka + Redis + Mongo", "+$130–280"),
                ("Total", "~$350–500"),
            ],
            "Pros: No EC2 patching; auto-scaling per service.",
            "Cons: 40–60% more expensive than ECS on EC2 for 24/7 workloads.",
            "Scores: Cost 6/10 | Reliability 8/10 | Ops simplicity 9/10",
        ),
        (
            "Option E — MSK Serverless (AVOID for MVP)",
            "~$730–860+/month",
            "MSK Serverless has ~$0.75/hour cluster fee = ~$558/month minimum even with no traffic.",
            [
                ("MSK Serverless (cluster only)", "~$558"),
                ("Partitions + data", "+$20–100"),
                ("EC2 for agents", "+$150–200"),
                ("Total", "~$730–860+"),
            ],
            "Do NOT use for PFA/MVP. Use self-hosted Kafka or MSK Provisioned kafka.t3.small instead.",
            "No HA benefit over cheaper alternatives at this price point.",
            "Scores: Cost 2/10 | Worst choice for low-traffic MVP",
        ),
    ]

    for title_text, cost, desc, cost_rows, pros, cons, scores in options:
        story.append(Paragraph(title_text, h2))
        story.append(Paragraph(f"<b>Estimated cost:</b> {cost}", body))
        story.append(Paragraph(desc, body))
        cost_table = [["Item", "Monthly"]] + cost_rows
        ct = Table(cost_table, colWidths=[10 * cm, 4 * cm])
        ct.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#edf2f7")),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 7.5),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
                    ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
                ]
            )
        )
        story.append(ct)
        story.append(Spacer(1, 0.15 * cm))
        story.append(Paragraph(f"<b>Pros:</b> {pros}", bullet))
        story.append(Paragraph(f"<b>Cons:</b> {cons}", bullet))
        story.append(Paragraph(scores, small))
        story.append(Spacer(1, 0.25 * cm))

    story.append(PageBreak())

    # Benchmark matrix
    story.append(Paragraph("Benchmark Matrix (1 = poor, 10 = excellent)", h1))
    bench = [
        ["Criteria", "A: EC2", "B: ECS", "C: EKS", "D: Fargate", "E: MSK SL"],
        ["Lowest cost", "10", "9", "4", "6", "2"],
        ["Reliability / HA", "3", "7", "10", "8", "8"],
        ["Scalability", "2", "7", "10", "8", "9"],
        ["Ops simplicity", "8", "7", "3", "9", "6"],
        ["Fits Docker setup", "10", "9", "8", "9", "7"],
        ["Fits K8s YAML", "2", "4", "10", "4", "6"],
        ["Playwright scraping", "7", "8", "9", "7", "7"],
        ["NER isolation", "6", "8", "9", "8", "7"],
        ["PFA / demo ready", "10", "9", "5", "8", "3"],
        ["Production ready", "3", "8", "10", "8", "7"],
        ["Monthly cost ($)", "90–194", "180–305", "584–900", "350–500", "730–860"],
        ["Weighted score", "6.2", "8.1", "7.4", "7.6", "4.8"],
    ]
    bt = Table(bench, colWidths=[4.2 * cm, 2.2 * cm, 2.2 * cm, 2.2 * cm, 2.4 * cm, 2.4 * cm])
    bt.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a365d")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 7),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("ALIGN", (1, 1), (-1, -1), "CENTER"),
                ("BACKGROUND", (2, -1), (2, -1), colors.HexColor("#c6f6d5")),
                ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, colors.HexColor("#f7fafc")]),
            ]
        )
    )
    story.append(bt)
    story.append(Spacer(1, 0.4 * cm))

    # Managed services
    story.append(Paragraph("Managed Services — What to Pick", h1))
    ms = [
        ["Service", "Cheapest good choice", "Avoid"],
        ["Kafka", "Self-hosted t4g.medium (~$30) or MSK kafka.t3.small (~$33 dev)", "MSK Serverless (~$558/mo base)"],
        ["Redis", "ElastiCache Valkey cache.t4g.small (~$24, 20% cheaper)", "Serverless for steady cache"],
        ["MongoDB", "Atlas M0 (demo) → M10 (~$57 prod)", "DocumentDB (different API)"],
        ["LLM", "Groq API (pay per token)", "SageMaker / GPU EC2 ($500+/mo)"],
        ["Secrets", "AWS Secrets Manager + SSM", "Plain text .env on EC2"],
        ["Images", "ECR", "Docker Hub rate limits"],
        ["Monitoring", "CloudWatch + /metrics endpoint", "Paid Grafana Cloud at start"],
    ]
    mst = Table(ms, colWidths=[2.5 * cm, 7.5 * cm, 7 * cm])
    mst.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2c5282")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 7.5),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    story.append(mst)

    # 3-phase rollout
    story.append(Spacer(1, 0.4 * cm))
    story.append(Paragraph("3-Phase Rollout Plan", h1))
    phases = [
        ["Phase", "When", "Architecture", "Est. cost/mo"],
        ["1 – PFA demo", "< 100 users", "1× EC2 + docker-compose.full.yml + Atlas M0", "$90–150"],
        ["2 – Beta", "First real users", "ECS + EC2 Spot + Valkey + Atlas M10 + self-hosted Kafka", "$180–280"],
        ["3 – Production", "1K+ users, need HPA", "EKS + MSK + Valkey + Atlas M10 (deploy/k8s/)", "$550–900"],
    ]
    pt = Table(phases, colWidths=[2.5 * cm, 3 * cm, 8 * cm, 3.5 * cm])
    pt.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2c5282")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    story.append(pt)

    # What NOT to do
    story.append(Spacer(1, 0.4 * cm))
    story.append(Paragraph("What NOT to Do", h1))
    dont = [
        ["Mistake", "Why it hurts"],
        ["MSK Serverless for MVP", "~$558/month minimum before any messages"],
        ["EKS on day 1 without K8s experience", "+$73/mo + high ops time; delays PFA"],
        ["Fargate for all 13 services 24/7", "40–60% more than ECS on EC2"],
        ["GPU EC2 for LLM", "Groq API is cheaper (LLM_PROVIDER=groq)"],
        ["Playwright on all 14 sites at max concurrency", "RAM spikes; keep SCRAPE_PLAYWRIGHT_PROVIDERS=avito"],
        ["us-east-1 for Moroccan users", "Higher latency; use eu-west-3 (Paris)"],
    ]
    dt = Table(dont, colWidths=[6 * cm, 11 * cm])
    dt.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#c53030")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    story.append(dt)

    # External costs
    story.append(Spacer(1, 0.4 * cm))
    story.append(Paragraph("External Costs (Not AWS)", h1))
    ext = [
        ["Item", "Cost"],
        ["Groq LLM API", "~$0–20/mo at MVP volume"],
        ["Telegram Bot", "Free"],
        ["Hugging Face NER model", "Free (cached in NER Docker image)"],
        ["Route 53 domain", "~$0.50/mo if needed"],
    ]
    et = Table(ext, colWidths=[6 * cm, 11 * cm])
    et.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#edf2f7")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ]
        )
    )
    story.append(et)

    # Final answer
    story.append(Spacer(1, 0.5 * cm))
    story.append(Paragraph("Final Answer", h1))
    final = [
        ["Goal", "Best option"],
        ["Absolute minimum cost", "Option A — EC2 + Docker Compose (~$90–150/mo)"],
        ["Best cost + quality (recommended)", "Option B — ECS on EC2 + Valkey + Atlas M10 (~$180–280/mo)"],
        ["Best quality at scale", "Option C — EKS + MSK (~$550–900/mo)"],
    ]
    ft = Table(final, colWidths=[6 * cm, 11 * cm])
    ft.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a365d")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("BACKGROUND", (0, 2), (-1, 2), colors.HexColor("#c6f6d5")),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ]
        )
    )
    story.append(ft)
    story.append(Spacer(1, 0.5 * cm))
    story.append(
        Paragraph(
            "For Smart Shopper as a PFA project moving toward real users, Option B is the sweet spot: "
            "professional enough for demos and early production, 3–4× cheaper than full EKS+MSK, "
            "and migration to existing Kubernetes manifests (deploy/k8s/) requires no application code changes.",
            body,
        )
    )
    story.append(Spacer(1, 0.8 * cm))
    story.append(
        Paragraph(
            "Generated for Smart Shopper — ENIAD IA PFA Project. "
            "Pricing estimates based on AWS public rates (eu-west-3, June 2026). "
            "Verify with AWS Pricing Calculator before deployment.",
            small,
        )
    )

    return story


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(OUTPUT),
        pagesize=A4,
        rightMargin=1.8 * cm,
        leftMargin=1.8 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
        title="Smart Shopper AWS Deployment Report",
        author="Smart Shopper / ENIAD IA",
    )
    doc.build(build_story())
    print(f"PDF written to: {OUTPUT}")


if __name__ == "__main__":
    main()
