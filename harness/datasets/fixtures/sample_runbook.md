# Runbook: Memory Exhaustion Incident Response

## Severity: High
## Service: JVM-based microservices (payment-processor, order-service)

## Detection
- Alert: `jvm_memory_heap_usage_ratio > 0.90` for > 5 minutes
- Log pattern: `OutOfMemoryError: Java heap space`
- Log pattern: `Heap usage at [89-99]%`

## Immediate Response (0–5 minutes)

1. Confirm the affected service and pod name:
   ```bash
   kubectl get pods -n production | grep -E "payment|order" | grep -v Running
   ```

2. Capture a heap dump before restarting (if service is still responsive):
   ```bash
   kubectl exec -it <pod-name> -- jcmd 1 GC.heap_info
   kubectl exec -it <pod-name> -- jcmd 1 VM.native_memory
   ```

3. Restart the affected pod to restore service:
   ```bash
   kubectl rollout restart deployment/payment-processor -n production
   ```

## Root Cause Investigation (5–30 minutes)

### Common causes by frequency

| Cause | Indicator | Fix |
|---|---|---|
| Memory leak in request handler | Heap grows monotonically under constant traffic | Profile with async-profiler, patch leak |
| Undersized -Xmx setting | Heap maxes out at low traffic | Increase -Xmx; current recommended: -Xmx2g for payment-processor |
| Large in-memory cache not bounded | Cache size grows with unique keys | Add eviction policy (LRU, TTL) |
| Off-heap memory not accounted | Container limit hit despite Xmx headroom | Add 20% buffer between -Xmx and container memory limit |

### Heap dump analysis
```bash
# Download heap dump
kubectl cp <pod-name>:/tmp/heapdump.hprof ./heapdump.hprof

# Analyze with Eclipse MAT or jmap
jmap -histo <pid> | head -30
```

## Escalation
- If restart loop continues after 3 restarts within 1 hour: page on-call infra team
- If heap dump shows > 80% held by a single object type: file a P1 bug with heap dump attached

## Recommended JVM settings
```
-Xms512m -Xmx2g -XX:+UseG1GC -XX:MaxGCPauseMillis=200
-XX:+HeapDumpOnOutOfMemoryError -XX:HeapDumpPath=/tmp/
```
