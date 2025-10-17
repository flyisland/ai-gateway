#!/bin/bash

# Test script for validating Duo Workflow Service functionality on AWS EKS deployment
# This script performs comprehensive testing of DWS functionality after deployment

set -euo pipefail

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_FILE="${SCRIPT_DIR}/test-results-$(date +%Y%m%d-%H%M%S).log"
ENVIRONMENT="${1:-staging}"  # staging or production
BASE_URL=""

# Set base URL based on environment
if [[ "$ENVIRONMENT" == "staging" ]]; then
    BASE_URL="https://duo-workflow.aws.staging.gitlab.com"
elif [[ "$ENVIRONMENT" == "production" ]]; then
    BASE_URL="https://duo-workflow.aws.gitlab.com"
else
    echo "Error: Environment must be 'staging' or 'production'"
    exit 1
fi

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging function
log() {
    echo -e "$1" | tee -a "$LOG_FILE"
}

# Test result tracking
TESTS_PASSED=0
TESTS_FAILED=0
TESTS_TOTAL=0

# Function to run a test
run_test() {
    local test_name="$1"
    local test_command="$2"
    local expected_status="${3:-0}"
    
    TESTS_TOTAL=$((TESTS_TOTAL + 1))
    log "${BLUE}[TEST $TESTS_TOTAL] $test_name${NC}"
    
    if eval "$test_command" >> "$LOG_FILE" 2>&1; then
        if [[ $? -eq $expected_status ]]; then
            log "${GREEN}✓ PASSED${NC}"
            TESTS_PASSED=$((TESTS_PASSED + 1))
            return 0
        else
            log "${RED}✗ FAILED (unexpected exit code)${NC}"
            TESTS_FAILED=$((TESTS_FAILED + 1))
            return 1
        fi
    else
        log "${RED}✗ FAILED${NC}"
        TESTS_FAILED=$((TESTS_FAILED + 1))
        return 1
    fi
}

# Function to test HTTP endpoint
test_http_endpoint() {
    local endpoint="$1"
    local expected_status="${2:-200}"
    local description="$3"
    
    run_test "$description" "curl -s -o /dev/null -w '%{http_code}' '$BASE_URL$endpoint' | grep -q '$expected_status'"
}

# Function to test JSON response
test_json_response() {
    local endpoint="$1"
    local jq_filter="$2"
    local expected_value="$3"
    local description="$4"
    
    run_test "$description" "curl -s '$BASE_URL$endpoint' | jq -r '$jq_filter' | grep -q '$expected_value'"
}

# Main testing function
main() {
    log "${BLUE}Starting Duo Workflow Service AWS EKS Functionality Tests${NC}"
    log "${BLUE}Environment: $ENVIRONMENT${NC}"
    log "${BLUE}Base URL: $BASE_URL${NC}"
    log "${BLUE}Log file: $LOG_FILE${NC}"
    log ""
    
    # Test 1: Health Check
    test_http_endpoint "/health" "200" "Health endpoint returns 200"
    
    # Test 2: Readiness Check
    test_http_endpoint "/ready" "200" "Readiness endpoint returns 200"
    
    # Test 3: Metrics Endpoint
    test_http_endpoint "/metrics" "200" "Metrics endpoint returns 200"
    
    # Test 4: Service Info
    test_json_response "/health" ".status" "ok" "Health endpoint returns OK status"
    
    # Test 5: Workflow Service Availability
    test_http_endpoint "/v1/workflows" "200" "Workflows endpoint is accessible"
    
    # Test 6: Tool Listing
    test_http_endpoint "/v1/tools" "200" "Tools endpoint is accessible"
    
    # Test 7: Flow Listing
    test_http_endpoint "/v1/flows" "200" "Flows endpoint is accessible"
    
    # Test 8: Service Configuration
    run_test "Service environment variables are set correctly" "kubectl get pods -l app=duo-workflow-svc-eks -o jsonpath='{.items[0].spec.containers[0].env[?(@.name==\"DUO_WORKFLOW_SERVICE_ENVIRONMENT\")].value}' | grep -q '$ENVIRONMENT'"
    
    # Test 9: Pod Health
    run_test "All pods are running" "kubectl get pods -l app=duo-workflow-svc-eks -o jsonpath='{.items[*].status.phase}' | grep -v Running | wc -l | grep -q '^0$'"
    
    # Test 10: Service Discovery
    run_test "Service is discoverable via DNS" "nslookup duo-workflow-svc-eks-service.default.svc.cluster.local"
    
    # Test 11: Load Balancer Health
    run_test "Load balancer is healthy" "kubectl get svc duo-workflow-svc-eks-service -o jsonpath='{.status.loadBalancer.ingress[0].hostname}' | grep -q '.'"
    
    # Test 12: Ingress Configuration
    run_test "Ingress is configured correctly" "kubectl get ingress duo-workflow-svc-eks-ingress -o jsonpath='{.spec.rules[0].host}' | grep -q 'duo-workflow.aws'"
    
    # Test 13: HPA Status
    run_test "Horizontal Pod Autoscaler is active" "kubectl get hpa duo-workflow-svc-eks-hpa -o jsonpath='{.status.conditions[?(@.type==\"AbleToScale\")].status}' | grep -q 'True'"
    
    # Test 14: Resource Limits
    run_test "Resource limits are set correctly" "kubectl get pods -l app=duo-workflow-svc-eks -o jsonpath='{.items[0].spec.containers[0].resources.limits.memory}' | grep -q '8Gi'"
    
    # Test 15: Secret Mounting
    run_test "Secrets are mounted correctly" "kubectl get pods -l app=duo-workflow-svc-eks -o jsonpath='{.items[0].spec.volumes[?(@.name==\"gcp-service-account\")].secret.secretName}' | grep -q 'gcp-service-account'"
    
    # Test 16: Network Connectivity (internal)
    run_test "Internal service connectivity" "kubectl run test-pod --image=curlimages/curl --rm -i --restart=Never -- curl -s -o /dev/null -w '%{http_code}' http://duo-workflow-svc-eks-service:8000/health | grep -q '200'"
    
    # Test 17: Logging Configuration
    run_test "Logging is configured" "kubectl logs -l app=duo-workflow-svc-eks --tail=10 | grep -q '.'"
    
    # Test 18: Metrics Collection
    run_test "Metrics are being collected" "curl -s '$BASE_URL/metrics' | grep -q 'duo_workflow'"
    
    # Test 19: SSL/TLS Configuration
    run_test "SSL certificate is valid" "curl -s --head '$BASE_URL/health' | grep -q 'HTTP/2 200'"
    
    # Test 20: Response Time
    run_test "Response time is acceptable" "curl -s -o /dev/null -w '%{time_total}' '$BASE_URL/health' | awk '{if(\$1 < 2.0) exit 0; else exit 1}'"
    
    # Summary
    log ""
    log "${BLUE}Test Summary:${NC}"
    log "${GREEN}Passed: $TESTS_PASSED${NC}"
    log "${RED}Failed: $TESTS_FAILED${NC}"
    log "${BLUE}Total: $TESTS_TOTAL${NC}"
    
    if [[ $TESTS_FAILED -eq 0 ]]; then
        log "${GREEN}All tests passed! DWS AWS EKS deployment is functional.${NC}"
        exit 0
    else
        log "${RED}Some tests failed. Please check the logs and fix issues.${NC}"
        exit 1
    fi
}

# Check prerequisites
check_prerequisites() {
    local missing_tools=()
    
    command -v curl >/dev/null 2>&1 || missing_tools+=("curl")
    command -v kubectl >/dev/null 2>&1 || missing_tools+=("kubectl")
    command -v jq >/dev/null 2>&1 || missing_tools+=("jq")
    
    if [[ ${#missing_tools[@]} -gt 0 ]]; then
        log "${RED}Error: Missing required tools: ${missing_tools[*]}${NC}"
        log "Please install the missing tools and try again."
        exit 1
    fi
    
    # Check kubectl connectivity
    if ! kubectl cluster-info >/dev/null 2>&1; then
        log "${RED}Error: Cannot connect to Kubernetes cluster${NC}"
        log "Please ensure kubectl is configured correctly."
        exit 1
    fi
}

# Cleanup function
cleanup() {
    log "${YELLOW}Cleaning up test resources...${NC}"
    kubectl delete pod test-pod --ignore-not-found=true >/dev/null 2>&1 || true
}

# Set up signal handlers
trap cleanup EXIT INT TERM

# Run the tests
check_prerequisites
main "$@"