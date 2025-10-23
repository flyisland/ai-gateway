from prometheus_client import Counter, Histogram

ENTITLEMENTS_CHECK_TOTAL = Counter(
    "entitlements_check_total",
    "Total entitlement decisions at gateway (post-cache)",
    ["result", "realm"],  # result: allow | deny | fail_open
)

ENTITLEMENTS_CUSTOMERSDOT_REQUESTS_TOTAL = Counter(
    "entitlements_customersdot_requests_total",
    "CustomersDot resolve outcomes (pre-enforcement)",
    ["outcome", "status"],  # outcome: success|denied|timeout|http_error|unexpected
)

ENTITLEMENTS_CUSTOMERSDOT_LATENCY_SECONDS = Histogram(
    "entitlements_customersdot_latency_seconds",
    "Latency of CustomersDot resolve requests",
    ["realm"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
)
