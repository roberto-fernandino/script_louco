#!/usr/bin/env python3
"""Login na QueryBuscas e consulta BIN, agrupando o resultado por banco.

Uso:
  python3 check_bins.py 550209
  python3 check_bins.py 550209 411111
  python3 check_bins.py --file bins.txt
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from collections import defaultdict
from http.cookiejar import CookieJar

BASE = "https://querybuscas.com"
USERNAME = "accounts@intelecttus.com.br"
PASSWORD = "Intelecttus_ma1l"
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36"
)


class QueryBuscas:
    def __init__(self, username: str, password: str) -> None:
        self.username = username
        self.password = password
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(CookieJar())
        )

    def _call(
        self,
        path: str,
        method: str = "GET",
        body: bytes | None = None,
        headers: dict[str, str] | None = None,
        referer: str = f"{BASE}/",
    ) -> tuple[int, dict]:
        hdrs = {
            "Accept": "*/*",
            "Origin": BASE,
            "Referer": referer,
            "User-Agent": UA,
        }
        if headers:
            hdrs.update(headers)
        req = urllib.request.Request(
            BASE + path, data=body, headers=hdrs, method=method
        )
        try:
            with self.opener.open(req, timeout=30) as resp:
                raw = resp.read().decode()
                status = resp.status
        except urllib.error.HTTPError as err:
            raw = err.read().decode()
            status = err.code
        try:
            data = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            data = {"raw": raw}
        return status, data

    def login(self) -> dict:
        status, data = self._call(
            "/api/auth/login",
            method="POST",
            body=json.dumps(
                {"username": self.username, "password": self.password}
            ).encode(),
            headers={"Content-Type": "application/json"},
        )
        if status == 429:
            raise SystemExit("Muitas tentativas de login. Espere 10 minutos.")
        if status == 403 and data.get("statusMessage") == "PlanExpired":
            raise SystemExit("Plano expirado.")
        if status != 200 or not data.get("success"):
            msg = data.get("message") or data.get("statusMessage") or status
            raise SystemExit(f"Login falhou: {msg}")
        return data.get("user") or {}

    def _nonce(self) -> tuple[str, str]:
        status, data = self._call(
            "/api/consultas/nonce",
            method="POST",
            body=b"",
            referer=f"{BASE}/pages/consultas/Bin",
        )
        if status != 200 or "nonce" not in data or "sig" not in data:
            raise SystemExit(f"Nonce falhou ({status}): {data}")
        return data["nonce"], data["sig"]

    def check_bin(self, bin_code: str) -> dict:
        nonce, sig = self._nonce()
        status, data = self._call(
            f"/api/consultas/bin/{bin_code}",
            headers={"x-qb-nonce": nonce, "x-qb-sig": sig},
            referer=f"{BASE}/pages/consultas/Bin",
        )
        if status == 403 and data.get("requireCaptcha"):
            raise SystemExit(
                "A API pediu captcha (Turnstile). Rode de novo daqui a pouco, "
                "ou faça uma consulta no navegador antes."
            )
        if status != 200:
            return {"BIN": bin_code, "erro": data.get("message") or status, "resposta": data}
        data["BIN"] = data.get("BIN") or bin_code
        return data


def normalize_bin(value: str) -> str:
    digits = "".join(ch for ch in value if ch.isdigit())
    if not 6 <= len(digits) <= 8:
        raise SystemExit(f"BIN inválido: {value!r} (use 6 a 8 dígitos)")
    return digits


def load_bins(args: argparse.Namespace) -> list[str]:
    values = list(args.bins)
    if args.file:
        text = args.file.read()
        values.extend(line.strip() for line in text.splitlines() if line.strip())
    if not values:
        raise SystemExit("Passe pelo menos um BIN.")
    seen: set[str] = set()
    bins: list[str] = []
    for value in values:
        code = normalize_bin(value.split()[0])
        if code not in seen:
            seen.add(code)
            bins.append(code)
    return bins


def group_by_bank(results: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for item in results:
        bank = item.get("BANCO") or "DESCONHECIDO"
        grouped[bank].append(
            {
                "bin": item.get("BIN"),
                "bandeira": item.get("BANDEIRA"),
                "nivel": item.get("NIVEL"),
                "encontrado": bool(item.get("ENCONTRADO") or item.get("hasResult")),
                **({"erro": item["erro"]} if "erro" in item else {}),
            }
        )
    return dict(sorted(grouped.items(), key=lambda pair: pair[0].lower()))


def main() -> None:
    parser = argparse.ArgumentParser(description="Consulta BIN na QueryBuscas e agrupa por banco.")
    parser.add_argument("bins", nargs="*", help="BINs (6 a 8 dígitos)")
    parser.add_argument("--file", type=argparse.FileType("r"), help="Arquivo com um BIN por linha")
    args = parser.parse_args()

    bins = load_bins(args)
    client = QueryBuscas(USERNAME, PASSWORD)
    user = client.login()
    print(
        f"Login ok: {user.get('username')} plano={user.get('plano')} "
        f"dias={user.get('diasRestantes')}",
        file=sys.stderr,
    )

    results = [client.check_bin(code) for code in bins]
    grouped = group_by_bank(results)
    json.dump({"total": len(results), "por_banco": grouped}, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
