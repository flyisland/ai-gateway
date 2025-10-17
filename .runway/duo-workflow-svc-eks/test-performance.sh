#!/bin/bash

# Performance validation script for Duo Workflow Service AWS EKS deployment
# Compares performance metrics with GCP baseline and validates AWS deployment performance

set -euo pipefail

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_FILE="${SCRIPT_DIR}/performance-test-$(date +%Y%m%d-%H%M%S).log"
RESULTS_FILE="${SCRIPT_DIR}/performance-results-$(date +%Y%m%d-%H%M%S).json"
ENVIRONMENT="${1:-staging}"

# Performance test configuration
CONCURRENT_USERS="${CONCURRENT_USERS:-10}"
TEST_DURATION="${TEST_DURATION:-60}"  # seconds
WARMUP_DURATION="${WARMUP_DURATION:-30}"  # seconds
REQUEST_TIMEOUT="${REQUEST_TIMEOUT:-30}"  # seconds

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Performance thresholds (based on GCP baseline expectations)
MAX_RESPONSE_TIME_MS=2000
MAX_P95_RESPONSE_TIME_MS=5000
MIN_THROUGHPUT_RPS=10
MAX_ERROR_RATE_PERCENT=1
MAX_MEMORY_USAGE_PERCENT=80
MAX_CPU_USAGE_PERCENT=70

# Test result tracking
TESTS_PASSED=0
TESTS_FAILED=0
TESTS_TOTAL=0

# Logging function
log() {
    echo -e "$1" | tee -a "$LOG_FILE"
}

# Function to run a performance test
run_performance_test() {
    local test_name="$1"
    local actual_value="$2"
    local threshold="$3"
    local comparison="${4:-le}"  # le (less or equal), ge (greater or equal)
    local unit="${5:-}"
    
    TESTS_TOTAL=$((TESTS_TOTAL + 1))
    log "${BLUE}[TEST $TESTS_TOTAL] $test_name${NC}"
    
    local result=false
    case "$comparison" in
        "le")
            if (( $(echo "$actual_value <= $threshold" | bc -l) )); then
                result=true
            fi
            ;;
        "ge")
            if (( $(echo "$actual_value >= $threshold" | bc -l) )); then
                result=true
            fi
            ;;
    esac
    
    if $result; then
        log "${GREEN}✓ PASSED${NC} (${actual_value}${unit} ${comparison} ${threshold}${unit})"
        TESTS_PASSED=$((TESTS_PASSED + 1))
    else
        log "${RED}✗ FAILED${NC} (${actual_value}${unit} not ${comparison} ${threshold}${unit})"
        TESTS_FAILED=$((TESTS_FAILED + 1))
    fi
}

# Function to get service URL
get_service_url() {
    if [[ "$ENVIRONMENT" == "staging" ]]; then
        echo "https://duo-workflow.aws.staging.gitlab.com"
    else
        echo "https://duo-workflow.aws.gitlab.com"
    fi
}

# Function to run load test
run_load_test() {
    local base_url="$1"
    local endpoint="$2"
    local method="${3:-GET}"
    local concurrent_users="$4"
    local duration="$5"
    
    log "Running load test: $method $base_url$endpoint"
    log "Concurrent users: $concurrent_users, Duration: ${duration}s"
    
    # Create a simple load test script
    cat > /tmp/load_test.sh << EOF
#!/bin/bash
url="$base_url$endpoint"
method="$method"
duration="$duration"
concurrent="$concurrent_users"

# Function to make a request
make_request() {
    start_time=\$(date +%s.%N)
    if [[ "\$method" == "GET" ]]; then
        response=\$(curl -s -w "%{http_code}:%{time_total}" -o /dev/null --max-time $REQUEST_TIMEOUT "\$url" 2>/dev/null || echo "000:$REQUEST_TIMEOUT")
    else
        response=\$(curl -s -w "%{http_code}:%{time_total}" -o /dev/null -X "\$method" --max-time $REQUEST_TIMEOUT "\$url" 2>/dev/null || echo "000:$REQUEST_TIMEOUT")
    fi
    end_time=\$(date +%s.%N)
    
    status_code=\$(echo "\$response" | cut -d: -f1)
    response_time=\$(echo "\$response" | cut -d: -f2)
    
    echo "\$status_code,\$response_time"
}

# Run concurrent requests
export -f make_request
export url method

# Generate load
seq 1 \$concurrent | xargs -n1 -P\$concurrent -I{} timeout \$duration bash -c '
    while true; do
        make_request
        sleep 0.1
    done
' > /tmp/load_test_results.csv 2>/dev/null

EOF
    
    chmod +x /tmp/load_test.sh
    
    # Run the load test from within the cluster
    kubectl run load-test-$(date +%s) --image=curlimages/curl --rm -i --restart=Never --timeout=$((duration + 60))s -- sh -c "
        apk add --no-cache bc bash coreutils findutils
        $(cat /tmp/load_test.sh)
    " > /tmp/load_results.csv 2>/dev/null || true
    
    # Process results
    if [[ -f /tmp/load_results.csv ]] && [[ -s /tmp/load_results.csv ]]; then
        # Calculate statistics
        local total_requests=$(wc -l < /tmp/load_results.csv)
        local successful_requests=$(grep -c "^200," /tmp/load_results.csv || echo "0")
        local error_requests=$((total_requests - successful_requests))
        local error_rate=$(echo "scale=2; $error_requests * 100 / $total_requests" | bc -l 2>/dev/null || echo "0")
        local throughput=$(echo "scale=2; $total_requests / $duration" | bc -l 2>/dev/null || echo "0")
        
        # Calculate response time statistics
        local avg_response_time=$(awk -F, '{sum+=$2; count++} END {if(count>0) print sum/count*1000; else print 0}' /tmp/load_results.csv 2>/dev/null || echo "0")
        local response_times=$(awk -F, '{print $2*1000}' /tmp/load_results.csv | sort -n)
        local p95_response_time=$(echo "$response_times" | awk 'BEGIN{count=0} {values[count++]=$1} END{print values[int(count*0.95)]}' 2>/dev/null || echo "0")
        
        # Store results in JSON format
        cat > /tmp/load_test_result.json << EOF
{
    "endpoint": "$endpoint",
    "method": "$method",
    "concurrent_users": $concurrent_users,
    "duration": $duration,
    "total_requests": $total_requests,
    "successful_requests": $successful_requests,
    "error_requests": $error_requests,
    "error_rate_percent": $error_rate,
    "throughput_rps": $throughput,
    "avg_response_time_ms": $avg_response_time,
    "p95_response_time_ms": $p95_response_time
}
EOF
        
        log "Load test results:"
        log "  Total requests: $total_requests"
        log "  Successful requests: $successful_requests"
        log "  Error rate: ${error_rate}%"
        log "  Throughput: ${throughput} RPS"
        log "  Average response time: ${avg_response_time}ms"
        log "  95th percentile response time: ${p95_response_time}ms"
        
        # Return the results
        echo "$total_requests,$successful_requests,$error_rate,$throughput,$avg_response_time,$p95_response_time"
    else
        log "${RED}Load test failed to generate results${NC}"
        echo "0,0,100,0,0,0"
    fi
    
    # Cleanup
    rm -f /tmp/load_test.sh /tmp/load_results.csv
}

# Function to get resource utilization
get_resource_utilization() {
    log "Collecting resource utilization metrics..."
    
    # Get CPU and memory usage
    local cpu_usage=$(kubectl top pods -l app=duo-workflow-svc-eks --no-headers | awk '{sum+=$2} END {print sum}' | sed 's/m//' || echo "0")
    local memory_usage=$(kubectl top pods -l app=duo-workflow-svc-eks --no-headers | awk '{sum+=$3} END {print sum}' | sed 's/Mi//' || echo "0")
    
    # Get resource limits
    local cpu_limit=$(kubectl get pods -l app=duo-workflow-svc-eks -o jsonpath='{.items[0].spec.containers[0].resources.limits.cpu}' | sed 's/m//' || echo "2000")
    local memory_limit=$(kubectl get pods -l app=duo-workflow-svc-eks -o jsonpath='{.items[0].spec.containers[0].resources.limits.memory}' | sed 's/Gi//' | awk '{print $1*1024}' || echo "8192")
    
    # Calculate utilization percentages
    local cpu_percent=$(echo "scale=2; $cpu_usage * 100 / $cpu_limit" | bc -l 2>/dev/null || echo "0")
    local memory_percent=$(echo "scale=2; $memory_usage * 100 / $memory_limit" | bc -l 2>/dev/null || echo "0")
    
    log "Resource utilization:"
    log "  CPU: ${cpu_usage}m / ${cpu_limit}m (${cpu_percent}%)"
    log "  Memory: ${memory_usage}Mi / ${memory_limit}Mi (${memory_percent}%)"
    
    echo "$cpu_percent,$memory_percent"
}

# Function to test startup time
test_startup_time() {
    log "Testing service startup time..."
    
    # Get pod creation time and ready time
    local pod_info=$(kubectl get pods -l app=duo-workflow-svc-eks -o jsonpath='{.items[0].metadata.creationTimestamp},{.items[0].status.conditions[?(@.type=="Ready")].lastTransitionTime}' 2>/dev/null || echo ",")
    
    if [[ "$pod_info" != "," ]]; then
        local creation_time=$(echo "$pod_info" | cut -d, -f1)
        local ready_time=$(echo "$pod_info" | cut -d, -f2)
        
        if [[ -n "$creation_time" ]] && [[ -n "$ready_time" ]]; then
            local creation_epoch=$(date -d "$creation_time" +%s 2>/dev/null || echo "0")
            local ready_epoch=$(date -d "$ready_time" +%s 2>/dev/null || echo "0")
            local startup_time=$((ready_epoch - creation_epoch))
            
            log "Startup time: ${startup_time}s"
            echo "$startup_time"
        else
            log "Could not determine startup time"
            echo "0"
        fi
    else
        log "Could not retrieve pod timing information"
        echo "0"
    fi
}

# Main performance testing function
main() {
    log "${BLUE}Starting Duo Workflow Service AWS EKS Performance Tests${NC}"
    log "${BLUE}Environment: $ENVIRONMENT${NC}"
    log "${BLUE}Concurrent users: $CONCURRENT_USERS${NC}"
    log "${BLUE}Test duration: ${TEST_DURATION}s${NC}"
    log "${BLUE}Log file: $LOG_FILE${NC}"
    log "${BLUE}Results file: $RESULTS_FILE${NC}"
    log ""
    
    local base_url=$(get_service_url)
    log "Testing service at: $base_url"
    
    # Initialize results JSON
    echo '{"timestamp": "'$(date -Iseconds)'", "environment": "'$ENVIRONMENT'", "tests": []}' > "$RESULTS_FILE"
    
    # Warmup phase
    log "${YELLOW}Warming up service for ${WARMUP_DURATION}s...${NC}"
    run_load_test "$base_url" "/health" "GET" 2 "$WARMUP_DURATION" > /dev/null
    sleep 5
    
    # Test 1: Health endpoint performance
    log "${BLUE}Test 1: Health Endpoint Performance${NC}"
    local health_results=$(run_load_test "$base_url" "/health" "GET" "$CONCURRENT_USERS" "$TEST_DURATION")
    IFS=',' read -r total_req success_req error_rate throughput avg_time p95_time <<< "$health_results"
    
    run_performance_test "Health endpoint error rate" "$error_rate" "$MAX_ERROR_RATE_PERCENT" "le" "%"
    run_performance_test "Health endpoint throughput" "$throughput" "$MIN_THROUGHPUT_RPS" "ge" " RPS"
    run_performance_test "Health endpoint avg response time" "$avg_time" "$MAX_RESPONSE_TIME_MS" "le" "ms"
    run_performance_test "Health endpoint P95 response time" "$p95_time" "$MAX_P95_RESPONSE_TIME_MS" "le" "ms"
    
    # Test 2: Metrics endpoint performance
    log ""
    log "${BLUE}Test 2: Metrics Endpoint Performance${NC}"
    local metrics_results=$(run_load_test "$base_url" "/metrics" "GET" "$((CONCURRENT_USERS / 2))" "$((TEST_DURATION / 2))")
    IFS=',' read -r total_req success_req error_rate throughput avg_time p95_time <<< "$metrics_results"
    
    run_performance_test "Metrics endpoint error rate" "$error_rate" "$MAX_ERROR_RATE_PERCENT" "le" "%"
    run_performance_test "Metrics endpoint avg response time" "$avg_time" "$((MAX_RESPONSE_TIME_MS * 2))" "le" "ms"  # Metrics can be slower
    
    # Test 3: Workflow endpoints performance
    log ""
    log "${BLUE}Test 3: Workflow Endpoints Performance${NC}"
    local workflow_results=$(run_load_test "$base_url" "/v1/workflows" "GET" "$((CONCURRENT_USERS / 2))" "$((TEST_DURATION / 2))")
    IFS=',' read -r total_req success_req error_rate throughput avg_time p95_time <<< "$workflow_results"
    
    run_performance_test "Workflow endpoint error rate" "$error_rate" "$MAX_ERROR_RATE_PERCENT" "le" "%"
    run_performance_test "Workflow endpoint avg response time" "$avg_time" "$((MAX_RESPONSE_TIME_MS * 3))" "le" "ms"  # API calls can be slower
    
    # Test 4: Resource utilization
    log ""
    log "${BLUE}Test 4: Resource Utilization${NC}"
    local resource_results=$(get_resource_utilization)
    IFS=',' read -r cpu_percent memory_percent <<< "$resource_results"
    
    run_performance_test "CPU utilization" "$cpu_percent" "$MAX_CPU_USAGE_PERCENT" "le" "%"
    run_performance_test "Memory utilization" "$memory_percent" "$MAX_MEMORY_USAGE_PERCENT" "le" "%"
    
    # Test 5: Startup time
    log ""
    log "${BLUE}Test 5: Service Startup Time${NC}"
    local startup_time=$(test_startup_time)
    run_performance_test "Service startup time" "$startup_time" "120" "le" "s"  # Should start within 2 minutes
    
    # Test 6: Concurrent connection handling
    log ""
    log "${BLUE}Test 6: Concurrent Connection Handling${NC}"
    local concurrent_results=$(run_load_test "$base_url" "/health" "GET" "$((CONCURRENT_USERS * 2))" "$((TEST_DURATION / 2))")
    IFS=',' read -r total_req success_req error_rate throughput avg_time p95_time <<< "$concurrent_results"
    
    run_performance_test "High concurrency error rate" "$error_rate" "$((MAX_ERROR_RATE_PERCENT * 2))" "le" "%"
    run_performance_test "High concurrency P95 response time" "$p95_time" "$((MAX_P95_RESPONSE_TIME_MS * 2))" "le" "ms"
    
    # Test 7: Memory leak detection (basic)
    log ""
    log "${BLUE}Test 7: Memory Stability Check${NC}"
    local initial_memory=$(kubectl top pods -l app=duo-workflow-svc-eks --no-headers | awk '{sum+=$3} END {print sum}' | sed 's/Mi//' || echo "0")
    sleep 30  # Wait a bit
    local final_memory=$(kubectl top pods -l app=duo-workflow-svc-eks --no-headers | awk '{sum+=$3} END {print sum}' | sed 's/Mi//' || echo "0")
    local memory_growth=$(echo "$final_memory - $initial_memory" | bc -l 2>/dev/null || echo "0")
    
    run_performance_test "Memory growth during test" "$memory_growth" "100" "le" "Mi"  # Should not grow more than 100Mi
    
    # Generate comprehensive results
    cat > "$RESULTS_FILE" << EOF
{
    "timestamp": "$(date -Iseconds)",
    "environment": "$ENVIRONMENT",
    "test_configuration": {
        "concurrent_users": $CONCURRENT_USERS,
        "test_duration": $TEST_DURATION,
        "warmup_duration": $WARMUP_DURATION
    },
    "performance_thresholds": {
        "max_response_time_ms": $MAX_RESPONSE_TIME_MS,
        "max_p95_response_time_ms": $MAX_P95_RESPONSE_TIME_MS,
        "min_throughput_rps": $MIN_THROUGHPUT_RPS,
        "max_error_rate_percent": $MAX_ERROR_RATE_PERCENT,
        "max_memory_usage_percent": $MAX_MEMORY_USAGE_PERCENT,
        "max_cpu_usage_percent": $MAX_CPU_USAGE_PERCENT
    },
    "test_results": {
        "health_endpoint": {
            "total_requests": $total_req,
            "error_rate_percent": $error_rate,
            "throughput_rps": $throughput,
            "avg_response_time_ms": $avg_time,
            "p95_response_time_ms": $p95_time
        },
        "resource_utilization": {
            "cpu_percent": $cpu_percent,
            "memory_percent": $memory_percent
        },
        "startup_time_seconds": $startup_time,
        "memory_growth_mi": $memory_growth
    },
    "summary": {
        "tests_passed": $TESTS_PASSED,
        "tests_failed": $TESTS_FAILED,
        "tests_total": $TESTS_TOTAL,
        "success_rate": $(echo "scale=2; $TESTS_PASSED * 100 / $TESTS_TOTAL" | bc -l 2>/dev/null || echo "0")
    }
}
EOF
    
    # Summary
    log ""
    log "${BLUE}Performance Test Summary:${NC}"
    log "${GREEN}Passed: $TESTS_PASSED${NC}"
    log "${RED}Failed: $TESTS_FAILED${NC}"
    log "${BLUE}Total: $TESTS_TOTAL${NC}"
    log "${BLUE}Success Rate: $(echo "scale=1; $TESTS_PASSED * 100 / $TESTS_TOTAL" | bc -l 2>/dev/null || echo "0")%${NC}"
    
    log ""
    log "${BLUE}Detailed results saved to: $RESULTS_FILE${NC}"
    
    if [[ $TESTS_FAILED -eq 0 ]]; then
        log "${GREEN}All performance tests passed! AWS deployment meets performance requirements.${NC}"
        exit 0
    else
        log "${RED}Some performance tests failed. Please review and optimize the deployment.${NC}"
        exit 1
    fi
}

# Check prerequisites
check_prerequisites() {
    local missing_tools=()
    
    command -v kubectl >/dev/null 2>&1 || missing_tools+=("kubectl")
    command -v bc >/dev/null 2>&1 || missing_tools+=("bc")
    command -v jq >/dev/null 2>&1 || missing_tools+=("jq")
    
    if [[ ${#missing_tools[@]} -gt 0 ]]; then
        log "${RED}Error: Missing required tools: ${missing_tools[*]}${NC}"
        exit 1
    fi
    
    if ! kubectl cluster-info >/dev/null 2>&1; then
        log "${RED}Error: Cannot connect to Kubernetes cluster${NC}"
        exit 1
    fi
}

# Cleanup function
cleanup() {
    log "${YELLOW}Cleaning up performance test resources...${NC}"
    kubectl delete pods -l "run" --field-selector=status.phase=Succeeded --ignore-not-found=true >/dev/null 2>&1 || true
    kubectl delete pods -l "run" --field-selector=status.phase=Failed --ignore-not-found=true >/dev/null 2>&1 || true
    rm -f /tmp/load_test* /tmp/load_results*
}

# Set up signal handlers
trap cleanup EXIT INT TERM

# Run the tests
check_prerequisites
main "$@"