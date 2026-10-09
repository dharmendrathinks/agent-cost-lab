"""Optional local API-equivalent scenarios. No network, billing, or API execution."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

from .accounting import complete_tokens, metric, model_identity, safe_text


@dataclass(frozen=True)
class PriceTable:
    as_of: str
    source: str
    models: dict[str, dict]


def load_prices(path: Path) -> PriceTable:
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    if raw.get("schema_version") != 1 or raw.get("currency") != "USD" or raw.get("service_tier") != "standard":
        raise ValueError("pricing requires schema_version=1, currency=USD, service_tier=standard")
    stamp = str(raw.get("as_of", ""))
    try:
        date.fromisoformat(stamp)
    except ValueError as exc:
        raise ValueError("pricing requires an ISO as_of date") from exc
    source = raw.get("source")
    if not isinstance(source, str) or not source.startswith("https://"):
        raise ValueError("pricing requires an HTTPS source citation")
    models = raw.get("models")
    if not isinstance(models, dict) or not models:
        raise ValueError("pricing table has no models")
    for model, contexts in models.items():
        if not isinstance(contexts, dict) or not contexts or set(contexts) - {"short", "long"}:
            raise ValueError("invalid pricing context for " + model)
        for context, rates in contexts.items():
            required = {"input", "cached_input", "output"}
            if not isinstance(rates, dict) or not required <= set(rates) or set(rates) - (required | {"cache_write_input"}):
                raise ValueError("pricing requires input, cached_input, output rates per million tokens")
            for key, value in rates.items():
                try:
                    number = Decimal(str(value))
                except InvalidOperation as exc:
                    raise ValueError("invalid price") from exc
                if not number.is_finite() or number < 0:
                    raise ValueError("prices must be finite and nonnegative")
                rates[key] = number
    return PriceTable(stamp, source, models)


def estimate(record: dict, table: PriceTable, context: str = "short") -> tuple[Decimal | None, str]:
    requested, effective, identity = model_identity(record)
    if identity in {"mixed", "rerouted"} or requested in {"mixed", "unknown"}:
        return None, "model unknown, mixed, or rerouted"
    model = effective if identity == "confirmed" else requested
    rates = table.models.get(model, {}).get(context)
    if rates is None:
        return None, "no exact model/context price"
    tokens = complete_tokens(record)
    if tokens is None:
        return None, "incomplete or invalid usage"
    inputs, cached, outputs = tokens
    writes, write_state = metric(record, "cache_write_input_tokens")
    assumptions = ["effective model" if identity == "confirmed" else "requested model; effective model unconfirmed"]
    if writes is None:
        writes = 0
        assumptions.append("cache writes assumed zero")
    elif write_state != "complete":
        return None, "incomplete cache-write usage"
    if writes + cached > inputs:
        return None, "invalid cache subsets"
    if writes and "cache_write_input" not in rates:
        return None, "cache-write price unavailable"
    amount = (Decimal(inputs - cached - writes) * rates["input"]
              + Decimal(cached) * rates["cached_input"]
              + Decimal(writes) * rates.get("cache_write_input", Decimal(0))
              + Decimal(outputs) * rates["output"]) / Decimal(1_000_000)
    return amount, "; ".join(assumptions)


def pricing_lines(records: list[dict], table: PriceTable, context: str) -> list[str]:
    estimates = [(record, *estimate(record, table, context)) for record in records]
    known = [value for _, value, _ in estimates if value is not None]
    age = (date.today() - date.fromisoformat(table.as_of)).days
    lines = ["## Optional API-equivalent estimate", "",
             f"Local price snapshot: {table.as_of}; [official price reference]({table.source}).",
             f"Scenario: standard service, **{context} context for every request**, USD per million tokens.",
             "This is a hypothetical token-cost estimate, not the Codex bill, subscription allowance, or monetary savings. "
             "Context tier is an assumption: thread totals cannot identify per-request context length. "
             "Tool fees, regional uplifts, taxes, and subscription charges are excluded. Reasoning tokens are already included in output."]
    if age > 30:
        lines.append(f"Price snapshot is {age} days old; update the local table before relying on the estimate.")
    elif age < 0:
        lines.append("Price snapshot is future-dated relative to this machine; verify the table date.")
    if known:
        coverage = "complete scenario total" if len(known) == len(records) else "priced subtotal only"
        lines.append(f"API-equivalent USD: **${sum(known):.6f}** ({coverage}; {len(known)}/{len(records)} records priced).")
    else:
        lines.append(f"API-equivalent USD: **unknown** (0/{len(records)} records priced).")
    lines.extend(["", "| Run | API-equivalent USD | Basis / reason unpriced |", "| --- | ---: | --- |"])
    for record, value, reason in estimates:
        lines.append(f"| {safe_text(record.get('run_id', 'unknown'))} | {'unknown' if value is None else f'${value:.6f}'} | {safe_text(reason)} |")
    lines.append("")
    return lines
