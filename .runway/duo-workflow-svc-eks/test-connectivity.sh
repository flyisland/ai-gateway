#!/bin/bash

# Connectivity test script for Duo Workflow Service on AWS EKS
# Tests connectivity to GitLab instances and external dependencies

set -euo pipefail

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_FILE="${SCRIPT_DIR}/connectivity-test-$(date +%Y%m%d-%H%M%S).log"
ENVIRONMENT="${1:-staging}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Test result tracking
TESTS_PASSED=0
TESTS_FAILED=0
TESTS_TOTAL=0

# Logging function
log() {
    echo -e "$1" | tee -a "$LOG_FILE"
}

# Function to run a connectivity test
run_connectivity_test() {
    local test_name="$1"
    local target_url="$2"
    local expected_status="${3:-200}"
    local timeout="${4:-10}"
    
    TESTS_TOTAL=$((TESTS_TOTAL + 1))
    log "${BLUE}[TEST $TESTS_TOTAL] $test_name${NC}"
    log "  Target: $target_url"
    
    # Test from within the cluster
    local pod_name="connectivity-test-$(date +%s)"
    local test_command="curl -s -o /dev/null -w '%{http_code}:%{time_total}:%{time_connect}' --max-time $timeout '$target_url'"
    
    if kubectl run "$pod_name" --image=curlimages/curl --rm -i --restart=Never --timeout=30s -- sh -c "$test_command" > /tmp/curl_result 2>/dev/null; then
        local result=$(cat /tmp/curl_result)
        local status_code=$(echo "$result" | cut -d: -f1)
        local total_time=$(echo "$result" | cut -d: -f2)
        local connect_time=$(echo "$result" | cut -d: -f3)
        
        if [[ "$status_code" == "$expected_status" ]]; then
            log "${GREEN}✓ PASSED${NC} (${status_code}, ${total_time}s total, ${connect_time}s connect)"
            TESTS_PASSED=$((TESTS_PASSED + 1))
        else
            log "${RED}✗ FAILED${NC} (Expected: $expected_status, Got: $status_code)"
            TESTS_FAILED=$((TESTS_FAILED + 1))
        fi
    else
        log "${RED}✗ FAILED${NC} (Connection timeout or error)"
        TESTS_FAILED=$((TESTS_FAILED + 1))
    fi
    
    # Cleanup
    rm -f /tmp/curl_result
}

# Function to test DNS resolution
test_dns_resolution() {
    local test_name="$1"
    local hostname="$2"
    
    TESTS_TOTAL=$((TESTS_TOTAL + 1))
    log "${BLUE}[TEST $TESTS_TOTAL] $test_name${NC}"
    log "  Hostname: $hostname"
    
    local pod_name="dns-test-$(date +%s)"
    
    if kubectl run "$pod_name" --image=busybox --rm -i --restart=Never --timeout=15s -- nslookup "$hostname" > /tmp/dns_result 2>/dev/null; then
        local ip_address=$(grep -A1 "Name:" /tmp/dns_result | grep "Address:" | head -1 | awk '{print $2}' || echo "")
        if [[ -n "$ip_address" ]]; then
            log "${GREEN}✓ PASSED${NC} (Resolved to: $ip_address)"
            TESTS_PASSED=$((TESTS_PASSED + 1))
        else
            log "${RED}✗ FAILED${NC} (No IP address resolved)"
            TESTS_FAILED=$((TESTS_FAILED + 1))
        fi
    else
        log "${RED}✗ FAILED${NC} (DNS resolution failed)"
        TESTS_FAILED=$((TESTS_FAILED + 1))
    fi
    
    # Cleanup
    rm -f /tmp/dns_result
}

# Function to test network latency
test_network_latency() {
    local test_name="$1"
    local target_host="$2"
    local max_latency_ms="${3:-100}"
    
    TESTS_TOTAL=$((TESTS_TOTAL + 1))
    log "${BLUE}[TEST $TESTS_TOTAL] $test_name${NC}"
    log "  Target: $target_host (max latency: ${max_latency_ms}ms)"
    
    local pod_name="ping-test-$(date +%s)"
    
    if kubectl run "$pod_name" --image=busybox --rm -i --restart=Never --timeout=15s -- ping -c 3 "$target_host" > /tmp/ping_result 2>/dev/null; then
        local avg_latency=$(grep "round-trip" /tmp/ping_result | awk -F'/' '{print $5}' | cut -d' ' -f1 || echo "999")
        local avg_latency_int=$(echo "$avg_latency" | cut -d. -f1)
        
        if [[ "$avg_latency_int" -le "$max_latency_ms" ]]; then
            log "${GREEN}✓ PASSED${NC} (Average latency: ${avg_latency}ms)"
            TESTS_PASSED=$((TESTS_PASSED + 1))
        else
            log "${YELLOW}⚠ WARNING${NC} (High latency: ${avg_latency}ms > ${max_latency_ms}ms)"
            TESTS_PASSED=$((TESTS_PASSED + 1))  # Count as passed but with warning
        fi
    else
        log "${RED}✗ FAILED${NC} (Ping failed)"
        TESTS_FAILED=$((TESTS_FAILED + 1))
    fi
    
    # Cleanup
    rm -f /tmp/ping_result
}

# Main testing function
main() {
    log "${BLUE}Starting Duo Workflow Service AWS EKS Connectivity Tests${NC}"
    log "${BLUE}Environment: $ENVIRONMENT${NC}"
    log "${BLUE}Log file: $LOG_FILE${NC}"
    log ""
    
    # Set GitLab URLs based on environment
    local gitlab_url=""
    local customer_portal_url=""
    
    if [[ "$ENVIRONMENT" == "staging" ]]; then
        gitlab_url="https://staging.gitlab.com"
        customer_portal_url="https://customers.staging.gitlab.com"
    else
        gitlab_url="https://gitlab.com"
        customer_portal_url="https://customers.gitlab.com"
    fi
    
    # Test 1: GitLab Main Instance
    run_connectivity_test "GitLab main instance connectivity" "$gitlab_url" "200" 15
    
    # Test 2: GitLab API
    run_connectivity_test "GitLab API connectivity" "$gitlab_url/api/v4/version" "200" 15
    
    # Test 3: Customer Portal
    run_connectivity_test "Customer Portal connectivity" "$customer_portal_url" "200" 15
    
    # Test 4: Snowplow Analytics
    run_connectivity_test "Snowplow analytics endpoint" "https://snowplowprd.trx.gitlab.net" "404" 10  # 404 is expected for root path
    
    # Test 5: LangSmith (if applicable)
    run_connectivity_test "LangSmith API connectivity" "https://api.smith.langchain.com" "200" 10
    
    # Test 6: Google Cloud APIs (for compatibility)
    run_connectivity_test "Google Cloud AI Platform API" "https://us-central1-aiplatform.googleapis.com" "404" 10  # 404 is expected for root path
    
    # Test 7: Google Cloud Discovery Engine
    run_connectivity_test "Google Cloud Discovery Engine API" "https://discoveryengine.googleapis.com" "404" 10  # 404 is expected for root path
    
    # Test 8: Sentry (if configured)
    run_connectivity_test "Sentry error tracking" "https://sentry.io" "200" 10
    
    # Test 9: AWS Services
    run_connectivity_test "AWS EC2 metadata service" "http://169.254.169.254/latest/meta-data/" "200" 5
    
    # Test 10: AWS EKS API
    run_connectivity_test "AWS EKS API endpoint" "https://eks.us-east-1.amazonaws.com" "403" 10  # 403 is expected without auth
    
    # DNS Resolution Tests
    log ""
    log "${BLUE}DNS Resolution Tests:${NC}"
    
    # Test 11: GitLab DNS
    test_dns_resolution "GitLab DNS resolution" "$(echo $gitlab_url | sed 's|https://||')"
    
    # Test 12: Customer Portal DNS
    test_dns_resolution "Customer Portal DNS resolution" "$(echo $customer_portal_url | sed 's|https://||')"
    
    # Test 13: Internal Kubernetes DNS
    test_dns_resolution "Kubernetes internal DNS" "kubernetes.default.svc.cluster.local"
    
    # Test 14: Service DNS
    test_dns_resolution "DWS service DNS resolution" "duo-workflow-svc-eks-service.default.svc.cluster.local"
    
    # Network Latency Tests
    log ""
    log "${BLUE}Network Latency Tests:${NC}"
    
    # Test 15: GitLab latency
    test_network_latency "GitLab instance latency" "$(echo $gitlab_url | sed 's|https://||')" 200
    
    # Test 16: Google APIs latency
    test_network_latency "Google APIs latency" "googleapis.com" 150
    
    # Test 17: AWS services latency
    test_network_latency "AWS services latency" "amazonaws.com" 50
    
    # Internal Connectivity Tests
    log ""
    log "${BLUE}Internal Service Connectivity Tests:${NC}"
    
    # Test 18: Internal service connectivity
    run_connectivity_test "Internal DWS service connectivity" "http://duo-workflow-svc-eks-service:8000/health" "200" 5
    
    # Test 19: Metrics endpoint connectivity
    run_connectivity_test "Internal metrics endpoint" "http://duo-workflow-svc-eks-service:8082/metrics" "200" 5
    
    # Test 20: Cross-namespace connectivity (if applicable)
    run_connectivity_test "Kubernetes API server" "https://kubernetes.default.svc.cluster.local" "403" 5  # 403 is expected without proper auth
    
    # External Dependencies Test
    log ""
    log "${BLUE}External Dependencies Tests:${NC}"
    
    # Test 21: PyPI (for potential package installations)
    run_connectivity_test "PyPI connectivity" "https://pypi.org" "200" 10
    
    # Test 22: Docker Hub (for image pulls)
    run_connectivity_test "Docker Hub connectivity" "https://registry-1.docker.io" "401" 10  # 401 is expected without auth
    
    # Test 23: GitLab Container Registry
    run_connectivity_test "GitLab Container Registry" "https://registry.gitlab.com" "401" 10  # 401 is expected without auth
    
    # Summary
    log ""
    log "${BLUE}Connectivity Test Summary:${NC}"
    log "${GREEN}Passed: $TESTS_PASSED${NC}"
    log "${RED}Failed: $TESTS_FAILED${NC}"
    log "${BLUE}Total: $TESTS_TOTAL${NC}"
    
    if [[ $TESTS_FAILED -eq 0 ]]; then
        log "${GREEN}All connectivity tests passed! DWS can connect to required services.${NC}"
        exit 0
    else
        log "${RED}Some connectivity tests failed. Please check network configuration.${NC}"
        exit 1
    fi
}

# Check prerequisites
check_prerequisites() {
    if ! command -v kubectl >/dev/null 2>&1; then
        log "${RED}Error: kubectl is not installed${NC}"
        exit 1
    fi
    
    if ! kubectl cluster-info >/dev/null 2>&1; then
        log "${RED}Error: Cannot connect to Kubernetes cluster${NC}"
        exit 1
    fi
}

# Cleanup function
cleanup() {
    log "${YELLOW}Cleaning up test resources...${NC}"
    # Clean up any remaining test pods
    kubectl delete pods -l "run" --field-selector=status.phase=Succeeded --ignore-not-found=true >/dev/null 2>&1 || true
    kubectl delete pods -l "run" --field-selector=status.phase=Failed --ignore-not-found=true >/dev/null 2>&1 || true
}

# Set up signal handlers
trap cleanup EXIT INT TERM

# Run the tests
check_prerequisites
main "$@"