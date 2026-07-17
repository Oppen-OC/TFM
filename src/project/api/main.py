from fastapi import FastAPI

app = FastAPI(title="TFM API")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}