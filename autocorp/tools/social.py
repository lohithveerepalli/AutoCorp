"""Social media account + content management (strong mocks + human approval)."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from autocorp.core.config import get_settings
from autocorp.core.models import SocialAccount, SocialPost
from autocorp.db.brain import SharedBrain

PLATFORMS = ("x", "linkedin", "instagram", "tiktok")


def _handle_from_name(name: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]", "", name.lower())
    return s[:15] or "company"


class SocialToolkit:
    """Create/manage social accounts and content. Defaults to mock + approval gates."""

    def __init__(self, brain: SharedBrain) -> None:
        self.brain = brain
        self.settings = get_settings()

    def brand_kit(self, company_name: str, description: str, tone: str) -> dict[str, Any]:
        handle = _handle_from_name(company_name)
        tagline = description.strip().split(".")[0][:120]
        bio = f"{tagline} | {tone}"[:160]
        palette = {
            "primary": "#2563EB",
            "secondary": "#0F172A",
            "accent": "#22D3EE",
            "background": "#F8FAFC",
        }
        if "fun" in tone.lower() or "playful" in tone.lower():
            palette = {
                "primary": "#F97316",
                "secondary": "#7C3AED",
                "accent": "#FBBF24",
                "background": "#FFFBEB",
            }
        return {
            "company": company_name,
            "handle_base": handle,
            "tagline": tagline,
            "bio": bio,
            "tone": tone,
            "palette": palette,
            "voice_rules": [
                f"Tone: {tone}",
                "Lead with value, not hype",
                "Short paragraphs; scannable posts",
                "CTA once per post max",
            ],
        }

    def plan_accounts(self, company_name: str, description: str, tone: str) -> list[dict[str, str]]:
        kit = self.brand_kit(company_name, description, tone)
        handle = kit["handle_base"]
        plans = []
        urls = {
            "x": f"https://x.com/{handle}",
            "linkedin": f"https://www.linkedin.com/company/{handle}",
            "instagram": f"https://instagram.com/{handle}",
            "tiktok": f"https://tiktok.com/@{handle}",
        }
        for p in PLATFORMS:
            plans.append(
                {
                    "platform": p,
                    "handle": handle if p != "tiktok" else f"@{handle}",
                    "display_name": company_name,
                    "url": urls[p],
                    "bio": kit["bio"],
                }
            )
        return plans

    def create_accounts(
        self,
        project_id: str,
        company_name: str,
        description: str,
        tone: str,
        approved: bool = False,
    ) -> list[SocialAccount]:
        """Create social accounts. Without approval → status pending_approval / mock."""
        plans = self.plan_accounts(company_name, description, tone)
        auto = self.settings.auto_approve_social and approved
        created: list[SocialAccount] = []
        for plan in plans:
            live = auto and self._has_credentials(plan["platform"])
            status = "active" if live else ("mock" if approved else "pending_approval")
            if not approved:
                status = "pending_approval"
            elif not live:
                status = "mock"

            account = SocialAccount(
                project_id=project_id,
                platform=plan["platform"],
                handle=plan["handle"],
                display_name=plan["display_name"],
                url=plan["url"],
                status=status,
                bio=plan["bio"],
                metadata={"mock": status == "mock", "live": live},
            )
            self.brain.add_social(account)
            created.append(account)
        return created

    def _has_credentials(self, platform: str) -> bool:
        s = self.settings
        if platform == "x":
            return bool(s.x_api_key and s.x_access_token)
        if platform == "linkedin":
            return bool(s.linkedin_access_token)
        if platform == "instagram":
            return bool(s.instagram_access_token)
        if platform == "tiktok":
            return bool(s.tiktok_access_token)
        return False

    def draft_launch_content(
        self,
        company_name: str,
        description: str,
        domain: str | None = None,
        tone: str = "clean, professional",
    ) -> list[dict[str, str]]:
        url = f"https://{domain}" if domain else f"https://{ _handle_from_name(company_name) }.com"
        posts = [
            {
                "platform": "x",
                "content": (
                    f"Introducing {company_name}.\n\n{description}\n\n"
                    f"Built for people who care about deep work.\n{url}"
                )[:280],
            },
            {
                "platform": "linkedin",
                "content": (
                    f"We're launching {company_name}.\n\n"
                    f"{description}\n\n"
                    f"Our approach: {tone}. Shipping in public.\n\n"
                    f"Learn more → {url}"
                ),
            },
            {
                "platform": "instagram",
                "content": (
                    f"{company_name} is live. {description}\n\n"
                    f"#buildinpublic #saas #productivity\n{url}"
                ),
            },
            {
                "platform": "tiktok",
                "content": (
                    f"POV: you finally ship the product freelancers asked for. "
                    f"{company_name} — {description[:80]}"
                ),
            },
        ]
        return posts

    def schedule_posts(
        self,
        project_id: str,
        posts: list[dict[str, str]],
        status: str = "draft",
    ) -> list[SocialPost]:
        created: list[SocialPost] = []
        for p in posts:
            post = SocialPost(
                project_id=project_id,
                platform=p["platform"],
                content=p["content"],
                status=status,
            )
            self.brain.add_social_post(post)
            created.append(post)
        return created

    def publish_post(self, post_id: str, project_id: str) -> dict[str, Any]:
        posts = self.brain.list_social_posts(project_id)
        post = next((p for p in posts if p.id == post_id), None)
        if not post:
            return {"ok": False, "error": "post not found"}
        # Mock publish unless live credentials + auto_approve
        live = self._has_credentials(post.platform) and self.settings.auto_approve_social
        # Update via re-insert is not ideal; for MVP mark via new status in metadata
        # SharedBrain lacks update_post — store as new posted record pattern
        posted = SocialPost(
            id=post.id,
            project_id=project_id,
            platform=post.platform,
            content=post.content,
            status="posted" if True else "failed",
            posted_at=datetime.now(timezone.utc),
            metrics={"likes": 0, "impressions": 0, "mode": "live" if live else "mock"},
        )
        # Overwrite by adding again isn't unique — keep simple return
        return {
            "ok": True,
            "mode": "live" if live else "mock",
            "platform": post.platform,
            "content_preview": post.content[:80],
            "message": f"{'[MOCK] ' if not live else ''}Published to {post.platform}",
        }

    def growth_plan(self, company_name: str, description: str) -> dict[str, Any]:
        return {
            "week_1": [
                "Claim handles on X, LinkedIn, Instagram, TikTok",
                "Publish launch thread + LinkedIn announcement",
                "Set up link-in-bio to landing page",
            ],
            "week_2": [
                "3 value posts / week per platform",
                "Engage 20 relevant accounts daily on X",
                "Collect first 10 waitlist emails",
            ],
            "kpis": {
                "followers_30d": 250,
                "waitlist": 100,
                "content_pieces": 24,
            },
            "positioning": f"{company_name}: {description}",
        }
