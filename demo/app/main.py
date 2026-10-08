from fastapi import FastAPI

app = FastAPI(
    title="FaultBrief Demo SaaS",
    version="0.1.0",
    description="Separate demo service. Customer failure scenarios are not implemented yet.",
)


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok", "service": "faultbrief-demo"}
