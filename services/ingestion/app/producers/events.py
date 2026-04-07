from faultatlas.kafka.producer import KafkaProducer
from faultatlas.kafka.topics import Topics
from faultatlas.events.chunk_events import ChunksCreated, EmbeddingsCreated
from faultatlas.events.document_events import DocumentIndexed


def publish_chunks_created(
    producer: KafkaProducer, document_id: str, chunk_ids: list[str], correlation_id: str
) -> None:
    producer.publish(
        Topics.CHUNKS_CREATED,
        ChunksCreated(document_id=document_id, chunk_ids=chunk_ids, correlation_id=correlation_id),
        key=document_id,
    )


def publish_embeddings_created(
    producer: KafkaProducer, document_id: str, chunk_ids: list[str], model: str, correlation_id: str
) -> None:
    producer.publish(
        Topics.EMBEDDINGS_CREATED,
        EmbeddingsCreated(
            document_id=document_id,
            chunk_ids=chunk_ids,
            embedding_model=model,
            correlation_id=correlation_id,
        ),
        key=document_id,
    )


def publish_index_updated(
    producer: KafkaProducer, document_id: str, chunk_count: int, correlation_id: str
) -> None:
    producer.publish(
        Topics.INDEX_UPDATED,
        DocumentIndexed(document_id=document_id, chunk_count=chunk_count, correlation_id=correlation_id),
        key=document_id,
    )
