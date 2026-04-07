from fastapi import APIRouter, HTTPException
from faultatlas.mongo.client import Collections

from ..benchmark import run_benchmark
from ..dependencies import AuthDep, DBDep, RedisDep, SettingsDep
from ..llm.errors import LLMBackendUnavailableError
from ..schemas.benchmark import BenchmarkRunResponse

router = APIRouter()


@router.post("/run", response_model=BenchmarkRunResponse)
async def trigger_benchmark(
    request: dict | None,
    _: AuthDep,
    db: DBDep,
    redis: RedisDep,
    settings: SettingsDep,
) -> BenchmarkRunResponse:
    request = request or {}
    try:
        return await run_benchmark(
            db=db,
            redis=redis,
            settings=settings,
            runs_per_condition=int(request.get("runs_per_condition", 5)),
            backend_override=request.get("backend"),
        )
    except LLMBackendUnavailableError as exc:
        raise HTTPException(status_code=503, detail="llm_unavailable") from exc


@router.get("/latest", response_model=BenchmarkRunResponse)
async def get_latest_benchmark(_: AuthDep, db: DBDep) -> BenchmarkRunResponse:
    cursor = db[Collections.BENCHMARK_RUNS].find().sort("created_at", -1).limit(1)
    documents = await cursor.to_list(length=1)
    if not documents:
        raise HTTPException(status_code=404, detail="No benchmark runs found")
    document = documents[0]
    return BenchmarkRunResponse(
        run_id=document["_id"],
        **{k: v for k, v in document.items() if k != "_id"},
    )


@router.get("/{run_id}", response_model=BenchmarkRunResponse)
async def get_benchmark(run_id: str, _: AuthDep, db: DBDep) -> BenchmarkRunResponse:
    document = await db[Collections.BENCHMARK_RUNS].find_one({"_id": run_id})
    if not document:
        raise HTTPException(status_code=404, detail="Benchmark run not found")
    return BenchmarkRunResponse(
        run_id=document["_id"],
        **{k: v for k, v in document.items() if k != "_id"},
    )
