#!/usr/bin/env bash
# Idempotent Kafka topic creation for local dev
# Usage: ./scripts/create_topics.sh [bootstrap-server]
set -euo pipefail

BOOTSTRAP=${1:-"localhost:9092"}

TOPICS=(
  "faultatlas.documents.uploaded:3:1"
  "faultatlas.chunks.created:3:1"
  "faultatlas.embeddings.created:3:1"
  "faultatlas.index.updated:1:1"
  "faultatlas.agent.requested:3:1"
  "faultatlas.agent.completed:3:1"
  "faultatlas.incidents.created:1:1"
  "faultatlas.audit.events:1:1"
  "faultatlas.dlq.documents.uploaded:1:1"
  "faultatlas.dlq.chunks.created:1:1"
  "faultatlas.dlq.embeddings.created:1:1"
)

for ENTRY in "${TOPICS[@]}"; do
  IFS=':' read -r TOPIC PARTITIONS REPLICATION <<< "$ENTRY"
  docker compose -f infra/compose/docker-compose.yml exec kafka \
    kafka-topics.sh \
      --bootstrap-server "$BOOTSTRAP" \
      --create --if-not-exists \
      --topic "$TOPIC" \
      --partitions "$PARTITIONS" \
      --replication-factor "$REPLICATION"
  echo "  topic: $TOPIC"
done

echo "Done."
