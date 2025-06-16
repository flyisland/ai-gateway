import json
import time

from duo_workflow_service.prompt_security import PromptSecurity


def test_prompt_security_performance():
    """Debug performance test for PromptSecurity."""

    # Sample get_issue response
    test_response = {
        "id": 123,
        "title": "Fix bug in <goal>authentication</goal> system",
        "description": "Issue with <s>system</s> login and <!-- hidden --> content",
        "labels": ["bug", "<goal>security</goal>"],
        "author": {"username": "user<s>admin</s>"},
        "notes": [
            {"body": "Please <goal>help</goal> with this"},
            {"body": "Normal comment"},
        ],
    }

    # First, let's test with fewer iterations to see what's happening
    iterations = 100
    print(f"Testing with {iterations} iterations first...\n")

    # Test 1: Just JSON encoding (baseline)
    start = time.perf_counter()
    for _ in range(iterations):
        json.dumps(test_response)
    baseline_time = time.perf_counter() - start
    print(
        f"Baseline (just JSON): {baseline_time*1000:.2f}ms total, {baseline_time/iterations*1000:.3f}ms per request"
    )

    # Test 2: Just PromptSecurity (without JSON)
    start = time.perf_counter()
    for _ in range(iterations):
        PromptSecurity.apply_security(test_response, "get_issue")
    security_only_time = time.perf_counter() - start
    print(
        f"Security only: {security_only_time*1000:.2f}ms total, {security_only_time/iterations*1000:.3f}ms per request"
    )

    # Test 3: Both security + JSON
    start = time.perf_counter()
    for _ in range(iterations):
        secured = PromptSecurity.apply_security(test_response, "get_issue")
        json.dumps(secured)
    full_time = time.perf_counter() - start
    print(
        f"Security + JSON: {full_time*1000:.2f}ms total, {full_time/iterations*1000:.3f}ms per request"
    )

    # Now test with more iterations
    print(f"\nTesting with 1000 iterations...")
    iterations = 1000

    # Warm up
    for _ in range(10):
        secured = PromptSecurity.apply_security(test_response, "get_issue")
        json.dumps(secured)

    # Actual test
    start = time.perf_counter()
    for _ in range(iterations):
        json.dumps(test_response)
    baseline_time = time.perf_counter() - start

    start = time.perf_counter()
    for _ in range(iterations):
        secured = PromptSecurity.apply_security(test_response, "get_issue")
        json.dumps(secured)
    security_time = time.perf_counter() - start

    # Calculate results
    baseline_ms = (baseline_time / iterations) * 1000
    security_ms = (security_time / iterations) * 1000
    overhead_ms = security_ms - baseline_ms
    overhead_pct = (overhead_ms / baseline_ms) * 100

    print(f"\nFinal results:")
    print(f"Without security: {baseline_ms:.3f}ms per request")
    print(f"With security: {security_ms:.3f}ms per request")
    print(f"Overhead: {overhead_ms:.3f}ms ({overhead_pct:.1f}%)")

    # Let's also check what's taking time
    print(f"\nBreakdown:")
    print(f"Time spent on security: ~{security_only_time/100*1000:.3f}ms per call")
    print(f"Time spent on JSON: ~{baseline_ms:.3f}ms per call")


if __name__ == "__main__":
    test_prompt_security_performance()
