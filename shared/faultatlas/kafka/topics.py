class Topics:
    DOCUMENTS_UPLOADED = "faultatlas.documents.uploaded"
    CHUNKS_CREATED = "faultatlas.chunks.created"
    EMBEDDINGS_CREATED = "faultatlas.embeddings.created"
    INDEX_UPDATED = "faultatlas.index.updated"
    AGENT_REQUESTED = "faultatlas.agent.requested"
    AGENT_COMPLETED = "faultatlas.agent.completed"
    INCIDENTS_CREATED = "faultatlas.incidents.created"
    AUDIT_EVENTS = "faultatlas.audit.events"

    # Dead-letter queues
    DLQ_DOCUMENTS = "faultatlas.dlq.documents.uploaded"
    DLQ_CHUNKS = "faultatlas.dlq.chunks.created"
    DLQ_EMBEDDINGS = "faultatlas.dlq.embeddings.created"

    @classmethod
    def all_topics(cls) -> list[str]:
        return [v for k, v in vars(cls).items() if not k.startswith("_") and isinstance(v, str)]
