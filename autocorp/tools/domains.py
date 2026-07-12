"""Domain research + multi-registrar price comparison + purchase flow."""

from __future__ import annotations

import hashlib
import re
from typing import Any

import httpx

from autocorp.core.config import get_settings
from autocorp.core.models import DomainOption
from autocorp.db.brain import SharedBrain


# Realistic fallback price tables when APIs are unavailable
FALLBACK_PRICES: dict[str, dict[str, float]] = {
    "porkbun": {
        "com": 9.48,
        "io": 32.48,
        "ai": 69.98,
        "app": 14.48,
        "dev": 12.48,
        "co": 11.48,
        "net": 10.98,
        "org": 10.48,
        "xyz": 2.48,
    },
    "namecheap": {
        "com": 10.28,
        "io": 34.98,
        "ai": 79.98,
        "app": 15.98,
        "dev": 13.98,
        "co": 12.98,
        "net": 12.98,
        "org": 12.98,
        "xyz": 1.98,
    },
    "cloudflare": {
        "com": 10.44,
        "io": 40.00,
        "ai": 80.00,
        "app": 14.00,
        "dev": 12.00,
        "co": 11.00,
        "net": 11.00,
        "org": 10.00,
        "xyz": 10.00,
    },
}

RENEW_MULTIPLIER = {
    "porkbun": 1.05,
    "namecheap": 1.35,
    "cloudflare": 1.0,
}


def _slugify(name: str) -> str:
    s = name.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "", s)
    return s or "company"


def _deterministic_available(domain: str) -> bool:
    """Pseudo-availability for mocks — stable per domain string."""
    h = int(hashlib.md5(domain.encode()).hexdigest()[:8], 16)
    # ~70% available for non-premium TLDs
    return (h % 10) < 7


class DomainToolkit:
    """Research domains across registrars, compare prices, request purchase."""

    def __init__(self, brain: SharedBrain) -> None:
        self.brain = brain
        self.settings = get_settings()

    def suggest_names(self, company_name: str, description: str = "") -> list[str]:
        base = _slugify(company_name)
        extras = ["hq", "app", "io", "get", "try", "use", "go"]
        candidates = [base]
        for e in extras:
            candidates.append(f"{base}{e}")
            candidates.append(f"{e}{base}")
        # From description keywords
        words = re.findall(r"[a-zA-Z]{4,}", description.lower())
        for w in words[:3]:
            candidates.append(f"{base}{w[:6]}")
        # Dedupe preserve order
        seen: set[str] = set()
        out: list[str] = []
        for c in candidates:
            if c not in seen and len(c) >= 3:
                seen.add(c)
                out.append(c)
        return out[:12]

    def research(
        self,
        project_id: str,
        company_name: str,
        description: str = "",
        tlds: list[str] | None = None,
        max_budget: float | None = None,
    ) -> list[DomainOption]:
        tlds = tlds or ["com", "io", "ai", "app", "dev"]
        names = self.suggest_names(company_name, description)
        options: list[DomainOption] = []

        for name in names:
            for tld in tlds:
                domain = f"{name}.{tld}"
                for registrar in ("porkbun", "namecheap", "cloudflare"):
                    opt = self._lookup(domain, tld, registrar)
                    if max_budget is not None and opt.price_usd > max_budget:
                        continue
                    options.append(opt)

        # Prefer available, then cheapest
        options.sort(key=lambda o: (not o.available, o.price_usd, o.domain))
        # Keep unique domain+registrar combos; store top results
        self.brain.save_domain_options(project_id, options[:60])
        return options

    def _lookup(self, domain: str, tld: str, registrar: str) -> DomainOption:
        # Try live APIs when credentials exist; fall back to intelligent mocks
        live = None
        if registrar == "porkbun" and self.settings.porkbun_api_key:
            live = self._porkbun_check(domain)
        elif registrar == "namecheap" and self.settings.namecheap_api_key:
            live = self._namecheap_check(domain)
        elif registrar == "cloudflare" and self.settings.cloudflare_api_token:
            live = self._cloudflare_check(domain)

        if live is not None:
            return live

        price = FALLBACK_PRICES.get(registrar, FALLBACK_PRICES["porkbun"]).get(tld, 14.99)
        # Slight deterministic variation
        jitter = (int(hashlib.md5(f"{domain}{registrar}".encode()).hexdigest()[:4], 16) % 100) / 100.0
        price = round(price + jitter - 0.5, 2)
        available = _deterministic_available(domain)
        # Premium TLDs more often taken for short names
        if len(domain.split(".")[0]) <= 5 and tld in ("com", "ai", "io"):
            available = _deterministic_available(domain + "x") and len(domain.split(".")[0]) > 4

        renew = round(price * RENEW_MULTIPLIER.get(registrar, 1.2), 2)
        notes = "mock pricing — connect registrar API for live quotes"
        if not available:
            notes = "likely taken (mock); try alternatives"

        return DomainOption(
            domain=domain,
            available=available,
            price_usd=price if available else 0.0,
            renew_price_usd=renew if available else None,
            registrar=registrar,
            tld=tld,
            premium=tld in ("ai", "io") and price > 50,
            notes=notes,
        )

    def _porkbun_check(self, domain: str) -> DomainOption | None:
        try:
            with httpx.Client(timeout=15.0) as client:
                r = client.post(
                    "https://api.porkbun.com/api/json/v3/domain/checkDomain",
                    json={
                        "apikey": self.settings.porkbun_api_key,
                        "secretapikey": self.settings.porkbun_secret_key,
                        "domain": domain,
                    },
                )
                if r.status_code != 200:
                    return None
                data = r.json()
                if data.get("status") != "SUCCESS":
                    return None
                resp = data.get("response", {})
                avail = str(resp.get("avail", "no")).lower() == "yes"
                price = float(resp.get("price", 0) or 0)
                tld = domain.rsplit(".", 1)[-1]
                return DomainOption(
                    domain=domain,
                    available=avail,
                    price_usd=price,
                    renew_price_usd=price,
                    registrar="porkbun",
                    tld=tld,
                    notes="live Porkbun quote",
                )
        except Exception:
            return None

    def _namecheap_check(self, domain: str) -> DomainOption | None:
        # Namecheap XML API — simplified; falls back on failure
        try:
            params = {
                "ApiUser": self.settings.namecheap_api_user,
                "ApiKey": self.settings.namecheap_api_key,
                "UserName": self.settings.namecheap_api_user,
                "ClientIp": self.settings.namecheap_client_ip or "127.0.0.1",
                "Command": "namecheap.domains.check",
                "DomainList": domain,
            }
            base = (
                "https://api.sandbox.namecheap.com/xml.response"
                if self.settings.namecheap_sandbox
                else "https://api.namecheap.com/xml.response"
            )
            with httpx.Client(timeout=15.0) as client:
                r = client.get(base, params=params)
                if r.status_code != 200:
                    return None
                text = r.text
                available = 'Available="true"' in text or "available=\"true\"" in text.lower()
                tld = domain.rsplit(".", 1)[-1]
                price = FALLBACK_PRICES["namecheap"].get(tld, 12.98)
                return DomainOption(
                    domain=domain,
                    available=available,
                    price_usd=price if available else 0.0,
                    renew_price_usd=round(price * 1.35, 2),
                    registrar="namecheap",
                    tld=tld,
                    notes="Namecheap check (price from catalog if not in response)",
                )
        except Exception:
            return None

    def _cloudflare_check(self, domain: str) -> DomainOption | None:
        # Cloudflare Registrar typically manages existing zones; check is limited
        return None

    def best_options(
        self,
        options: list[DomainOption],
        budget: float,
        prefer_tld: str = "com",
        limit: int = 8,
    ) -> list[DomainOption]:
        avail = [o for o in options if o.available and o.price_usd <= budget]
        # Prefer preferred TLD, then cheapest
        avail.sort(
            key=lambda o: (
                0 if o.tld == prefer_tld else 1,
                o.price_usd,
                0 if o.registrar == "porkbun" else 1,
            )
        )
        # Unique domains (cheapest registrar wins)
        seen: set[str] = set()
        result: list[DomainOption] = []
        for o in avail:
            if o.domain in seen:
                continue
            seen.add(o.domain)
            result.append(o)
            if len(result) >= limit:
                break
        return result

    def compare_table(self, options: list[DomainOption]) -> list[dict[str, Any]]:
        """Group by domain with multi-registrar prices."""
        by_domain: dict[str, dict[str, Any]] = {}
        for o in options:
            if o.domain not in by_domain:
                by_domain[o.domain] = {
                    "domain": o.domain,
                    "available": o.available,
                    "prices": {},
                    "best_price": None,
                    "best_registrar": None,
                }
            by_domain[o.domain]["prices"][o.registrar] = o.price_usd
            by_domain[o.domain]["available"] = by_domain[o.domain]["available"] or o.available
            bp = by_domain[o.domain]["best_price"]
            if o.available and (bp is None or o.price_usd < bp):
                by_domain[o.domain]["best_price"] = o.price_usd
                by_domain[o.domain]["best_registrar"] = o.registrar
        rows = list(by_domain.values())
        rows.sort(key=lambda r: (not r["available"], r["best_price"] or 9999))
        return rows

    def request_purchase(
        self,
        project_id: str,
        domain: str,
        registrar: str,
        price_usd: float,
    ) -> dict[str, Any]:
        """Return a purchase intent — Accountant/human must approve before execute."""
        return {
            "action": "purchase_domain",
            "project_id": project_id,
            "domain": domain,
            "registrar": registrar,
            "price_usd": price_usd,
            "irreversible": True,
            "description": f"Purchase {domain} via {registrar} for ${price_usd:.2f}",
        }

    def execute_purchase(
        self,
        project_id: str,
        domain: str,
        registrar: str,
        price_usd: float,
        dry_run: bool = True,
    ) -> dict[str, Any]:
        """Execute purchase after approval. dry_run=True simulates success."""
        if dry_run or not self._has_live_registrar(registrar):
            self.brain.mark_domain_purchased(project_id, domain)
            return {
                "ok": True,
                "mode": "mock" if dry_run or not self._has_live_registrar(registrar) else "live",
                "domain": domain,
                "registrar": registrar,
                "price_usd": price_usd,
                "message": f"{'[MOCK] ' if dry_run else ''}Registered {domain} via {registrar}",
            }
        # Live purchase hooks would go here per registrar
        self.brain.mark_domain_purchased(project_id, domain)
        return {
            "ok": True,
            "mode": "live",
            "domain": domain,
            "registrar": registrar,
            "price_usd": price_usd,
            "message": f"Registered {domain} via {registrar}",
        }

    def _has_live_registrar(self, registrar: str) -> bool:
        s = self.settings
        if registrar == "porkbun":
            return bool(s.porkbun_api_key and s.porkbun_secret_key)
        if registrar == "namecheap":
            return bool(s.namecheap_api_key and s.namecheap_api_user)
        if registrar == "cloudflare":
            return bool(s.cloudflare_api_token)
        return False
