#!/usr/bin/env python3
"""Teste manual da integração QueryBuscas.

Uso:
  QUERYBUSCAS_USERNAME=... QUERYBUSCAS_PASSWORD=... \
    python3 test_querybuscas_integration.py 09386765632 --card 5502091234567890

O script executa o mesmo fluxo usado pela API: login, nonce/sig, score e BIN.
Nunca informe a senha como argumento da linha de comando.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")


def digits(value: str) -> str:
    return re.sub(r"\D", "", value)


class QueryBuscas:
    def __init__(self, username: str, password: str, base_url: str) -> None:
        self.base = base_url.rstrip("/")
        self.client = httpx.Client(timeout=30, follow_redirects=True)
        self.username = username
        self.password = password

    def close(self) -> None:
        self.client.close()

    def login(self) -> dict:
        response = self.client.post(
            f"{self.base}/api/auth/login",
            json={"username": self.username, "password": self.password},
            headers={"Accept": "*/*", "Origin": self.base, "Referer": f"{self.base}/"},
        )
        data = response.json() if response.content else {}
        if response.status_code != 200 or not data.get("success"):
            raise RuntimeError(f"Login falhou ({response.status_code}): {data}")
        return data.get("user") or {}

    def nonce(self, referer_page: str) -> tuple[str, str]:
        response = self.client.post(
            f"{self.base}/api/consultas/nonce",
            headers={"Accept": "*/*", "Origin": self.base, "Referer": f"{self.base}/pages/consultas/{referer_page}"},
        )
        data = response.json() if response.content else {}
        if response.status_code != 200 or "nonce" not in data or "sig" not in data:
            raise RuntimeError(f"Nonce falhou ({response.status_code}): {data}")
        return data["nonce"], data["sig"]

    def score(self, document: str) -> dict:
        nonce, signature = self.nonce("Score")
        response = self.client.get(
            f"{self.base}/api/consultas/score/{digits(document)}",
            headers={"Accept": "*/*", "x-qb-nonce": nonce, "x-qb-sig": signature, "Referer": f"{self.base}/pages/consultas/Score"},
        )
        data = response.json() if response.content else {}
        if response.status_code != 200:
            raise RuntimeError(f"Score falhou ({response.status_code}): {data}")
        return data

    def bin(self, card_or_bin: str) -> dict:
        code = digits(card_or_bin)
        if len(code) > 8:
            code = code[:8]
        if not 6 <= len(code) <= 8:
            raise ValueError("BIN deve ter entre 6 e 8 dígitos")
        nonce, signature = self.nonce("Bin")
        response = self.client.get(
            f"{self.base}/api/consultas/bin/{code}",
            headers={"Accept": "*/*", "x-qb-nonce": nonce, "x-qb-sig": signature, "Referer": f"{self.base}/pages/consultas/Bin"},
        )
        data = response.json() if response.content else {}
        if response.status_code != 200:
            raise RuntimeError(f"BIN falhou ({response.status_code}): {data}")
        data["BIN"] = data.get("BIN") or code
        return data


def main() -> int:
    parser = argparse.ArgumentParser(description="Testa login, score e BIN no QueryBuscas.")
    parser.add_argument("document", help="CPF/documento usado na consulta de score")
    parser.add_argument("--card", help="Número do cartão ou BIN para consultar a bandeira")
    parser.add_argument("--base-url", default=os.getenv("QUERYBUSCAS_BASE_URL", "https://querybuscas.com"))
    args = parser.parse_args()
    username = os.getenv("QUERYBUSCAS_USERNAME")
    password = os.getenv("QUERYBUSCAS_PASSWORD")
    if not username or not password:
        print("Configure QUERYBUSCAS_USERNAME e QUERYBUSCAS_PASSWORD.", file=sys.stderr)
        return 2

    client = QueryBuscas(username, password, args.base_url)
    try:
        user = client.login()
        result: dict[str, object] = {"login": {"ok": True, "username": user.get("username"), "plano": user.get("plano")}, "score": client.score(args.document)}
        if args.card:
            result["bin"] = client.bin(args.card)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (httpx.HTTPError, RuntimeError, ValueError) as error:
        print(f"Integração falhou: {error}", file=sys.stderr)
        return 1
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
